"""TDD: scheduler — next-run maths, run records, the loop, and its logs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar, cast

import pytest

from mysharedbrain.agent import AgentOutcome
from mysharedbrain.audit import AuditLog
from mysharedbrain.config import BrainConfig, JobSpec, SchedulerConfig
from mysharedbrain.jobs import JobScheduler, JobStore, next_run
from mysharedbrain.service import LIBRARIAN_ACTOR, Librarian

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_interval_first_run_depends_on_run_on_start() -> None:
    job = JobSpec(id="a", every="4h")
    assert next_run(job, None, NOW, anchored=False) == NOW + timedelta(hours=4)
    assert next_run(job, None, NOW, anchored=True) == NOW


def test_interval_counts_from_last_run() -> None:
    job = JobSpec(id="a", every="4h")
    last = NOW - timedelta(hours=1)
    assert next_run(job, last, NOW, anchored=False) == last + timedelta(hours=4)


def test_cron_next_run_is_after_base() -> None:
    job = JobSpec(id="a", cron="0 */6 * * *")
    computed = next_run(job, None, NOW, anchored=False)
    assert computed > NOW
    assert computed.hour % 6 == 0
    assert computed.minute == 0


def test_store_records_run_lifecycle(vault_dir: Path) -> None:
    store = JobStore(vault_dir)
    run_id = store.start("sweep")
    store.finish(run_id, "ok", "all good")
    run = store.get(run_id)
    assert run is not None
    assert (run.job_id, run.status, run.detail) == ("sweep", "ok", "all good")
    assert run.finished_at
    assert store.last("sweep") == run
    assert store.last("other") is None


def _scheduler(
    vault_dir: Path, *, scheduler_enabled: bool = False, **job: object
) -> JobScheduler:
    """A scheduler with one job.

    The scheduler itself is off unless asked for: most tests call `tick()` or
    `run_job()` directly and must not leave a loop running behind them.
    """
    spec = JobSpec(id="sweep", every="2d", **job)  # type: ignore[arg-type]
    return JobScheduler(
        vault_dir,
        BrainConfig(jobs=[spec], scheduler=SchedulerConfig(enabled=scheduler_enabled)),
    )


def test_run_job_records_success(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="consolidated 3 notes", requests=2, tool_calls=5)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    scheduler = _scheduler(vault_dir)
    run = asyncio_run(scheduler.run_job("sweep"))
    assert run.status == "ok"
    assert "consolidated 3 notes" in run.detail
    assert "2 request(s)" in run.detail
    assert scheduler.store.last("sweep").status == "ok"  # type: ignore[union-attr]


def test_agent_writes_are_tagged_with_the_librarian(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent's own mutations are audited under the librarian actor."""
    seen: list[str] = []

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        used = cast("Librarian", lib)
        seen.append(used.actor)
        used.create_note("swept", "written by the agent")
        return AgentOutcome(output="done", requests=1, tool_calls=1)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    asyncio_run(_scheduler(vault_dir).run_job("sweep"))

    assert seen == [LIBRARIAN_ACTOR]
    entries = AuditLog(vault_dir).read_log()
    assert [e.actor for e in entries] == [LIBRARIAN_ACTOR, LIBRARIAN_ACTOR]
    assert "create" in [e.action for e in entries]


def test_run_outcome_is_audited_with_job_id(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No name set: the audit trail falls back to the job id."""

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="all good", requests=1, tool_calls=0)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    asyncio_run(_scheduler(vault_dir).run_job("sweep"))

    entry = AuditLog(vault_dir).read_log()[0]
    assert (entry.action, entry.actor) == ("job-ok", LIBRARIAN_ACTOR)
    assert entry.detail == "job:sweep — 1 request(s), 0 tool call(s)"


def test_run_outcome_is_audited_with_the_job_name_not_its_id(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The settings page identifies a job by its Name; the audit trail should
    read the same way, not by the internal id."""

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="all good", requests=1, tool_calls=0)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    scheduler = _scheduler(vault_dir, name="Nightly vault sweep")
    asyncio_run(scheduler.run_job("sweep"))

    entry = AuditLog(vault_dir).read_log()[0]
    assert entry.detail == "job:Nightly vault sweep — 1 request(s), 0 tool call(s)"


def test_skipped_and_error_audits_also_use_the_job_name(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: object, **kwargs: object) -> AgentOutcome:
        raise RuntimeError("model unreachable")

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", boom)
    scheduler = _scheduler(vault_dir, name="Nightly vault sweep")
    asyncio_run(scheduler.run_job("sweep"))

    entry = AuditLog(vault_dir).read_log()[0]
    assert entry.action == "job-error"
    assert entry.detail.startswith("job:Nightly vault sweep — ")


def test_failed_run_is_audited(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: object, **kwargs: object) -> AgentOutcome:
        raise RuntimeError("model unreachable")

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", boom)
    asyncio_run(_scheduler(vault_dir).run_job("sweep"))

    entry = AuditLog(vault_dir).read_log()[0]
    assert entry.action == "job-error"
    assert entry.actor == LIBRARIAN_ACTOR
    assert "RuntimeError: model unreachable" in entry.detail


def test_concurrent_run_is_audited_as_skipped(vault_dir: Path) -> None:
    scheduler = _scheduler(vault_dir)
    scheduler.running.add("sweep")  # pretend a run is already in flight
    run = asyncio_run(scheduler.run_job("sweep"))
    assert run.status == "skipped"
    entry = AuditLog(vault_dir).read_log()[0]
    assert (entry.action, entry.actor) == ("job-skipped", LIBRARIAN_ACTOR)


def test_run_job_records_failure_as_error(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: object, **kwargs: object) -> AgentOutcome:
        raise RuntimeError("model unreachable")

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", boom)
    scheduler = _scheduler(vault_dir)
    run = asyncio_run(scheduler.run_job("sweep"))
    assert run.status == "error"
    assert "RuntimeError: model unreachable" in run.detail


def test_run_unknown_job_raises_keyerror(vault_dir: Path) -> None:
    with pytest.raises(KeyError):
        asyncio_run(_scheduler(vault_dir).run_job("ghost"))


def test_status_reports_schedule_and_last_run(vault_dir: Path) -> None:
    scheduler = _scheduler(vault_dir, enabled=True)
    store = JobStore(vault_dir)
    store.finish(store.start("sweep"), "ok", "done")
    row = scheduler.status()[0]
    assert row["id"] == "sweep"
    assert row["schedule"] == "2d"
    assert row["enabled"] is True
    assert row["last_status"] == "ok"
    assert row["next_run"]


def test_disabled_job_has_no_next_run(vault_dir: Path) -> None:
    scheduler = _scheduler(vault_dir, enabled=False)
    assert scheduler.upcoming() == {}
    assert scheduler.status()[0]["next_run"] == ""


def test_reload_picks_up_new_config(vault_dir: Path) -> None:
    scheduler = _scheduler(vault_dir, enabled=True)
    scheduler.reload(
        BrainConfig(
            jobs=[JobSpec(id="other", every="1h")],
            scheduler=SchedulerConfig(enabled=False),
        )
    )
    assert [row["id"] for row in scheduler.status()] == ["other"]


def test_due_jobs_run_on_tick(vault_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        calls.append("ran")
        return AgentOutcome(output="ok", requests=1, tool_calls=0)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    scheduler = _scheduler(vault_dir, enabled=True)
    scheduler.config.scheduler.run_on_start = True  # due immediately
    asyncio_run(scheduler.tick())
    assert calls == ["ran"]


def test_the_loop_actually_fires_a_due_job(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: start the loop, let it tick, see the run recorded.

    The tick interval is one second (the minimum), so this waits ~1.3s and the
    job has to fire on its own — no manual `tick()` call.
    """
    calls: list[str] = []

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        calls.append(str(getattr(job, "id", "")))
        return AgentOutcome(output="fired", requests=1, tool_calls=0)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    scheduler = JobScheduler(
        vault_dir,
        BrainConfig(
            jobs=[JobSpec(id="sweep", every="1h", enabled=True)],
            scheduler=SchedulerConfig(enabled=True, tick_seconds=1, run_on_start=True),
        ),
    )

    async def scenario() -> None:
        scheduler.start()
        assert scheduler.is_running is True
        await asyncio.sleep(1.4)
        await scheduler.stop()
        assert scheduler.is_running is False

    asyncio.run(scenario())

    assert calls == ["sweep"], "the loop should have run the due job once"
    assert JobStore(vault_dir).last("sweep").status == "ok"  # type: ignore[union-attr]


def test_start_is_idempotent_and_stop_is_safe(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starting twice must not run two loops (two loops = double runs)."""

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="x", requests=1, tool_calls=0)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    scheduler = _scheduler(vault_dir, scheduler_enabled=True, enabled=True)

    async def scenario() -> None:
        scheduler.start()
        first = scheduler.task
        scheduler.start()
        assert scheduler.task is first, "a second start must be a no-op"
        await scheduler.stop()
        await scheduler.stop()  # already stopped: still safe
        assert scheduler.is_running is False

    asyncio.run(scenario())


def test_a_disabled_scheduler_never_starts(vault_dir: Path) -> None:
    scheduler = _scheduler(vault_dir, enabled=False)
    scheduler.start()
    assert scheduler.is_running is False


def test_a_failing_tick_does_not_kill_the_loop(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One bad tick is logged and survived, not fatal."""

    async def broken(self: JobScheduler) -> None:
        raise RuntimeError("database gone")

    monkeypatch.setattr(JobScheduler, "tick", broken)
    scheduler = _scheduler(vault_dir, scheduler_enabled=True, enabled=True)

    async def scenario() -> None:
        scheduler.start()
        await asyncio.sleep(0.1)
        assert scheduler.is_running is True, "the loop should still be alive"
        await scheduler.stop()

    asyncio.run(scenario())


def test_lifecycle_and_runs_are_logged(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The scheduler has to be observable: start, run, outcome, next run."""

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="triage done", requests=2, tool_calls=3)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    scheduler = _scheduler(vault_dir, scheduler_enabled=True, enabled=True)
    scheduler.config.scheduler.run_on_start = True  # due immediately

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="mysharedbrain.jobs"):
            scheduler.start()
            await scheduler.tick()
            await scheduler.stop()

    asyncio.run(scenario())
    text = caplog.text
    assert "scheduler started: ticking every" in text
    assert "next run: sweep at" in text
    assert "job sweep: started" in text
    assert "job sweep: ok in" in text
    assert "job sweep: next run at" in text
    assert "scheduler stopped" in text


def test_a_skipped_run_is_logged_as_a_warning(
    vault_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    scheduler = _scheduler(vault_dir, enabled=True)
    scheduler.running.add("sweep")  # pretend a run is in flight

    with caplog.at_level(logging.WARNING, logger="mysharedbrain.jobs"):
        asyncio_run(scheduler.run_job("sweep"))

    assert "already running, skipping this trigger" in caplog.text


def test_a_failed_job_logs_the_traceback(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom(*args: object, **kwargs: object) -> AgentOutcome:
        raise RuntimeError("model unreachable")

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", boom)
    scheduler = _scheduler(vault_dir, enabled=True)

    with caplog.at_level(logging.ERROR, logger="mysharedbrain.jobs"):
        asyncio_run(scheduler.run_job("sweep"))

    assert "job sweep: failed after" in caplog.text
    assert "RuntimeError: model unreachable" in caplog.text
    assert caplog.records[-1].exc_info is not None, "a failure needs the traceback"


def test_a_quiet_tick_says_so_at_debug(
    vault_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Nothing due is normal; it should not be INFO noise on every tick."""
    scheduler = _scheduler(vault_dir, enabled=True)

    with caplog.at_level(logging.DEBUG, logger="mysharedbrain.jobs"):
        asyncio_run(scheduler.tick())

    assert "tick: nothing due" in caplog.text


def test_reload_reports_the_schedule_it_loaded(
    vault_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    scheduler = _scheduler(vault_dir, enabled=True)

    with caplog.at_level(logging.INFO, logger="mysharedbrain.jobs"):
        scheduler.reload(BrainConfig(jobs=[JobSpec(id="other", every="1h")]))

    assert "schedule loaded: 1 job(s), 1 enabled (other)" in caplog.text


def asyncio_run(coro: Coroutine[Any, Any, T]) -> T:
    """Tiny shim so the sync test bodies read cleanly."""

    return asyncio.run(coro)


T = TypeVar("T")
