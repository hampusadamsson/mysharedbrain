"""Scheduled librarian jobs: interval/cron triggers that run the agent.

Jobs are declared in the config file (``jobs:``) — the UI edits that file, so
there is one source of truth. This module owns the *running* of them: a
background asyncio task wakes every ``scheduler.tick_seconds`` and runs due
jobs, plus an on-demand ``run_job`` for the "Run now" button.

Run history lives in sqlite (``job_runs``), which is what makes ``next_run``
computable across restarts: ``last run + interval``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from croniter import croniter

from mysharedbrain.agent import prompt_for, run_agent
from mysharedbrain.config import (
    BrainConfig,
    BrainConfigDocument,
    JobSpec,
    load_config,
    parse_duration,
)
from mysharedbrain.db import Database
from mysharedbrain.service import LIBRARIAN_ACTOR, Librarian, vault_root

log = logging.getLogger("mysharedbrain.jobs")

DETAIL_LIMIT = 4000


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


@dataclass(frozen=True)
class JobRun:
    """One execution record from the ``job_runs`` table."""

    id: int
    job_id: str
    started_at: str
    finished_at: str
    status: str
    detail: str


class JobStatus(TypedDict):
    """Per-job view for the settings UI."""

    id: str
    name: str
    enabled: bool
    schedule: str
    next_run: str
    last_run: str
    last_status: str


class JobStore:
    """Run history for one vault's scheduler."""

    def __init__(self, root: Path) -> None:
        self.db = Database(root)

    def start(self, job_id: str) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO job_runs (job_id, started_at, status) VALUES (?, ?, ?)",
                (job_id, _iso(_now()), "running"),
            )
            return int(cur.lastrowid or 0)

    def finish(self, run_id: int, status: str, detail: str = "") -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE job_runs SET finished_at = ?, status = ?, detail = ? WHERE id = ?",
                (_iso(_now()), status, detail[:DETAIL_LIMIT], run_id),
            )

    def get(self, run_id: int) -> JobRun | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM job_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return JobRun(**dict(row)) if row is not None else None

    def recent(self, job_id: str | None = None, limit: int = 20) -> list[JobRun]:
        sql = "SELECT * FROM job_runs"
        params: list[object] = []
        if job_id is not None:
            sql += " WHERE job_id = ?"
            params.append(job_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.db.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [JobRun(**dict(row)) for row in rows]

    def last(self, job_id: str) -> JobRun | None:
        runs = self.recent(job_id, limit=1)
        return runs[0] if runs else None


def next_run(
    job: JobSpec, last: datetime | None, now: datetime, *, anchored: bool
) -> datetime:
    """When ``job`` should next fire, given its last run (and start policy).

    ``anchored`` (``scheduler.run_on_start``) makes a never-run job due now;
    otherwise the first fire is one full interval/cron step away. Interval
    jobs are measured from the last run so a slow run does not stampede.
    """
    if job.cron is not None:
        base = last or now
        return croniter(job.cron, base).get_next(datetime)
    seconds = parse_duration(job.every or "0s")
    if last is None:
        return now if anchored else now + timedelta(seconds=seconds)
    return last + timedelta(seconds=seconds)


class JobScheduler:
    """Background runner for the config's scheduled jobs."""

    def __init__(self, root: Path, config: BrainConfig | None = None) -> None:
        self.root = root
        self.config: BrainConfigDocument = config or load_config()
        self.store = JobStore(root)
        self._task: asyncio.Task[None] | None = None
        self.running: set[str] = set()
        """Job ids currently executing (public: tests and status read it)."""

    # -- lifecycle -----------------------------------------------------------
    @property
    def task(self) -> asyncio.Task[None] | None:
        """The background loop task, when there is one."""
        return self._task

    @property
    def is_running(self) -> bool:
        """Is the background loop alive? (Tests and diagnostics read this.)"""
        return self._task is not None and not self._task.done()

    def reload(self, config: BrainConfigDocument | None = None) -> None:
        """Pick up a new config (e.g. after the settings UI saves).

        Accepts a document, because that is what a save produces — the scheduler
        only reads fields, it does not need the sources.
        """
        self.config = config or load_config()
        enabled = [job.id for job in self.config.jobs if job.enabled]
        log.info(
            "schedule loaded: %d job(s), %d enabled%s",
            len(self.config.jobs),
            len(enabled),
            f" ({', '.join(enabled)})" if enabled else "",
        )

    def start(self) -> None:
        """Start the tick loop (idempotent, no-op when disabled)."""
        if self._task is not None:
            return
        if not self.config.scheduler.enabled:
            log.info("scheduler disabled: no job will run on its own")
            return
        self._task = asyncio.create_task(self._loop(), name="brain-scheduler")
        log.info(
            "scheduler started: ticking every %ss, %d enabled job(s)",
            self.config.scheduler.tick_seconds,
            sum(1 for job in self.config.jobs if job.enabled),
        )
        for job_id, moment in sorted(self.upcoming().items()):
            log.info("next run: %s at %s", job_id, moment.isoformat())

    async def stop(self) -> None:
        """Cancel the tick loop and wait for it (safe to call when stopped)."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        log.info("scheduler stopped")

    async def _loop(self) -> None:
        tick = self.config.scheduler.tick_seconds
        while True:
            try:
                await self.tick()
            except Exception:  # never let one bad tick kill the loop
                log.exception("scheduler tick failed; continuing")
            await asyncio.sleep(tick)

    # -- scheduling ----------------------------------------------------------
    def _last_run_at(self, job_id: str) -> datetime | None:
        run = self.store.last(job_id)
        if run is None or run.status == "running":
            return None
        try:
            return datetime.fromisoformat(run.started_at)
        except ValueError:
            return None

    def upcoming(self, now: datetime | None = None) -> dict[str, datetime]:
        """Next fire time per enabled job id."""
        moment = now or _now()
        anchored = self.config.scheduler.run_on_start
        out: dict[str, datetime] = {}
        for job in self.config.jobs:
            if not job.enabled:
                continue
            out[job.id] = next_run(
                job, self._last_run_at(job.id), moment, anchored=anchored
            )
        return out

    async def tick(self) -> None:
        """Run every job that is due right now (public for manual ticks)."""
        now = _now()
        due = [job_id for job_id, moment in self.upcoming(now).items() if moment <= now]
        if not due:
            log.debug("tick: nothing due")
            return
        log.info("tick: %d job(s) due: %s", len(due), ", ".join(due))
        for job_id in due:
            await self.run_job(job_id)

    # -- execution -----------------------------------------------------------
    def _job(self, job_id: str) -> JobSpec:
        for job in self.config.jobs:
            if job.id == job_id:
                return job
        raise KeyError(f"unknown job: {job_id!r}")

    async def run_job(self, job_id: str) -> JobRun:
        """Run one job now, recording the outcome. Never raises on agent error.

        Everything the agent does is audited twice over: each mutation is
        recorded by :class:`Librarian` under the ``librarian`` actor as it
        happens, and the run itself gets one summary entry tagged the same way.
        """
        job = self._job(job_id)
        lib = Librarian(self.root, actor=LIBRARIAN_ACTOR)
        if job_id in self.running:
            log.warning("job %s: already running, skipping this trigger", job_id)
            run_id = self.store.start(job_id)
            self.store.finish(run_id, "skipped", "already running")
            self._audit(lib, job.id, "skipped", "already running")
            run = self.store.get(run_id)
            assert run is not None
            return run
        self.running.add(job_id)
        run_id = self.store.start(job_id)
        started = time.perf_counter()
        log.info("job %s: started", job_id)
        try:
            prompt = prompt_for(self.config, job, lib)
            outcome = await run_agent(self.config, lib, prompt, job)
            detail = (
                f"{outcome.requests} request(s), {outcome.tool_calls} tool call(s)\n"
                f"{outcome.output}"
            )
            self.store.finish(run_id, "ok", detail)
            self._audit(lib, job.id, "ok", detail)
            log.info(
                "job %s: ok in %.1fs (%d request(s), %d tool call(s))",
                job_id,
                time.perf_counter() - started,
                outcome.requests,
                outcome.tool_calls,
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            self.store.finish(run_id, "error", detail)
            self._audit(lib, job.id, "error", detail)
            log.exception(
                "job %s: failed after %.1fs — %s",
                job_id,
                time.perf_counter() - started,
                detail,
            )
        finally:
            self.running.discard(job_id)
        next_moment = self.upcoming().get(job_id)
        if next_moment is not None:
            log.info("job %s: next run at %s", job_id, next_moment.isoformat())
        run = self.store.get(run_id)
        assert run is not None
        return run

    def _audit(self, lib: Librarian, job_id: str, status: str, detail: str) -> None:
        """Log one job outcome to the audit trail, tagged with the librarian."""
        first_line = detail.splitlines()[0] if detail else ""
        try:
            lib.audit.append(
                actor=LIBRARIAN_ACTOR,
                action=f"job-{status}",
                detail=f"job:{job_id} — {first_line}",
            )
        except Exception:  # auditing must never break the run
            log.exception("could not audit job %s", job_id)

    def status(self) -> list[JobStatus]:
        """Per-job view for the settings UI: schedule, next/last run."""
        upcoming = self.upcoming()
        out: list[JobStatus] = []
        for job in self.config.jobs:
            last = self.store.last(job.id)
            moment = upcoming.get(job.id)
            out.append(
                {
                    "id": job.id,
                    "name": job.name or job.id,
                    "enabled": job.enabled,
                    "schedule": job.every or job.cron or "",
                    "next_run": _iso(moment) if moment else "",
                    "last_run": last.started_at if last else "",
                    "last_status": last.status if last else "",
                }
            )
        return out


_scheduler: JobScheduler | None = None


def get_scheduler() -> JobScheduler:
    """Process-wide scheduler for the active vault, created on first use."""
    global _scheduler
    if _scheduler is None:
        _scheduler = JobScheduler(vault_root())
    return _scheduler


def reset_scheduler() -> None:
    """Drop the singleton (tests, or after a config path change)."""
    global _scheduler
    _scheduler = None


__all__ = [
    "JobRun",
    "JobScheduler",
    "JobStatus",
    "JobStore",
    "get_scheduler",
    "next_run",
    "reset_scheduler",
]
