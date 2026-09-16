"""Audit log: every interaction with the vault, sqlite-backed.

Like git log for the brain — who touched which note, when, and why. Rows live in
the vault's database (``.brain/brain.db``); reads are newest-first.

Each entry carries the note it concerns (``note_id``) plus two levels of
vocabulary:

``action``
    The precise verb: ``read``, ``find``, ``create``, ``patch``,
    ``capture-applied``, ``job-ok``, …
``kind``
    The coarse category a filter offers — ``read`` / ``find`` / ``write`` /
    ``delete`` / ``move`` / ``capture`` / ``job`` / ``other``. Derived from the
    action by :func:`kind_for`, so callers only ever name the action.

That split is what makes a per-file log cheap to render: filter by ``note_id``,
group by ``kind``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mysharedbrain.db import Database

READ = "read"
FIND = "find"
WRITE = "write"
DELETE = "delete"
MOVE = "move"
CAPTURE = "capture"
JOB = "job"
OTHER = "other"

#: Filterable categories, in the order the UI lists them.
KINDS: tuple[str, ...] = (READ, FIND, WRITE, MOVE, DELETE, CAPTURE, JOB, OTHER)

_ACTION_KINDS: dict[str, str] = {
    READ: READ,
    FIND: FIND,
    "create": WRITE,
    "update": WRITE,
    "append": WRITE,
    "patch": WRITE,
    "frontmatter": WRITE,
    "delete": DELETE,
    "restore": DELETE,
    "move": MOVE,
    "feedback": CAPTURE,
}


def kind_for(action: str) -> str:
    """Category for an action name (``capture-*``/``job-*`` by prefix)."""
    known = _ACTION_KINDS.get(action)
    if known is not None:
        return known
    if action.startswith("capture-"):
        return CAPTURE
    if action.startswith("job-"):
        return JOB
    return OTHER


@dataclass(frozen=True)
class AuditEntry:
    ts: str
    actor: str
    action: str
    kind: str = OTHER
    note_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class LogStats:
    """Interaction counts for one scope: a single note, or the whole log.

    ``note_id`` is empty when the scope is everything — that is what the
    Activity view shows, and the file view shows a single note's slice.
    """

    note_id: str
    counts: dict[str, int]
    first_seen: str = ""
    last_seen: str = ""

    @property
    def total(self) -> int:
        return sum(self.counts.values())


_COLUMNS = "ts, actor, action, kind, note_id, detail"


class AuditLog:
    """Append-only interaction history for one vault."""

    def __init__(self, root: Path) -> None:
        self.db = Database(root)

    def append(
        self,
        *,
        actor: str,
        action: str,
        note_id: str = "",
        detail: str = "",
        kind: str | None = None,
    ) -> AuditEntry:
        """Record one entry and return it. ``kind`` defaults from ``action``."""
        entry = AuditEntry(
            ts=datetime.now(UTC).isoformat(),
            actor=actor,
            action=action,
            kind=kind or kind_for(action),
            note_id=note_id,
            detail=detail,
        )
        with self.db.transaction() as conn:
            conn.execute(
                f"INSERT INTO audit_log ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry.ts,
                    entry.actor,
                    entry.action,
                    entry.kind,
                    entry.note_id,
                    entry.detail,
                ),
            )
        return entry

    def read_log(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        note_id: str | None = None,
        kind: str | None = None,
    ) -> list[AuditEntry]:
        """Newest-first page, optionally scoped to one note and/or one kind."""
        where, params = _filters(note_id, kind)
        params.extend((limit, offset))
        with self.db.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM audit_log{where}"
                " ORDER BY id DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [AuditEntry(**dict(row)) for row in rows]

    def count(self, *, note_id: str | None = None, kind: str | None = None) -> int:
        """Matching rows, so the UI can paginate honestly."""
        where, params = _filters(note_id, kind)
        with self.db.connection() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM audit_log{where}", params
            ).fetchone()
        return int(row["n"])

    def stats(self, note_id: str | None = None) -> LogStats:
        """Interaction counts grouped by kind, for one note or the whole log.

        This is the "how many reads / finds / edits" summary above a list, both
        for a file and for Activity. Counts always cover the whole scope, so a
        kind filter never changes the numbers next to the filters.
        """
        where = ""
        params: tuple[object, ...] = ()
        if note_id is not None:
            where = " WHERE note_id = ?"
            params = (note_id,)
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT kind, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts"
                f" FROM audit_log{where} GROUP BY kind",
                params,
            ).fetchall()
        counts = {str(row["kind"]): int(row["n"]) for row in rows}
        return LogStats(
            note_id=note_id or "",
            counts=counts,
            first_seen=min((str(r["first_ts"]) for r in rows), default=""),
            last_seen=max((str(r["last_ts"]) for r in rows), default=""),
        )


def _filters(note_id: str | None, kind: str | None) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if note_id is not None:
        clauses.append("note_id = ?")
        params.append(note_id)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params
