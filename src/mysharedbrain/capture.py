"""Capture queue: the feedback inbox, sqlite-backed.

Corrections, missing-information notes, requests and open questions land here as
``pending`` entries. The librarian reviews each one (double-check) — ``applied``
(vault updated), ``approved`` (endorsed, no vault change needed) or ``rejected``
— never silently dropped. Review is a guarded ``UPDATE``, so an entry can never
be reviewed twice.

Entries the system files on its own (an unanswered question the librarian could
not resolve) are marked ``automated``, so a reviewer can tell machine-filed work
from a person's.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from mysharedbrain.db import Database

Kind = Literal["edit", "missing", "request", "question"]
Status = Literal["pending", "applied", "approved", "rejected"]
Verdict = Literal["applied", "approved", "rejected"]

#: Valid kinds, in the order the UI offers them.
KINDS: tuple[str, ...] = ("edit", "missing", "request", "question")

#: Valid statuses. Presentation order is the UI's business — capture orders them
#: pending → approved → applied → rejected.
STATUSES: tuple[str, ...] = ("pending", "approved", "applied", "rejected")


def check_kind(value: str) -> Kind:
    """Validate a kind string and narrow it to the ``Kind`` literal.

    Lets HTTP/MCP adapters accept a plain ``str`` and hand the service a typed
    value without a cast at every call site.
    """
    if value not in KINDS:
        raise ValueError(f"unknown feedback kind: {value!r}")
    return cast("Kind", value)


def check_status(value: str) -> Status:
    """Validate a status string and narrow it to the ``Status`` literal."""
    if value not in STATUSES:
        raise ValueError(f"unknown status: {value!r}")
    return cast("Status", value)


_COLUMNS = "id, ts, kind, body, note_id, status, reviewer, review_note, automated"


@dataclass
class FeedbackEntry:
    id: str
    ts: str
    kind: str
    body: str
    note_id: str
    status: str
    reviewer: str = ""
    review_note: str = ""
    automated: bool = False


def _entry(row: Mapping[str, object]) -> FeedbackEntry:
    """Row → entry, coercing the stored 0/1 flag back to a real bool."""
    data = dict(row)
    data["automated"] = bool(data.get("automated", 0))
    return FeedbackEntry(**data)  # type: ignore[arg-type]


class EntryNotFound(Exception):
    """No capture entry with this id."""


class EntryAlreadyReviewed(Exception):
    """The entry was already applied, approved or rejected."""


class CaptureQueue:
    """Feedback inbox for one vault."""

    def __init__(self, root: Path) -> None:
        self.db = Database(root)

    def submit(
        self, *, kind: Kind, body: str, note_id: str = "", automated: bool = False
    ) -> FeedbackEntry:
        """Queue a new feedback entry as ``pending``.

        ``automated`` marks an entry the system filed on its own (an unanswered
        question) rather than a person.
        """
        if not body.strip():
            raise ValueError("feedback body must not be empty")
        if kind not in KINDS:
            raise ValueError(f"unknown feedback kind: {kind!r}")
        entry = FeedbackEntry(
            id=uuid.uuid4().hex[:12],
            ts=datetime.now(UTC).isoformat(),
            kind=kind,
            body=body.strip(),
            note_id=note_id.strip(),
            status="pending",
            automated=automated,
        )
        with self.db.transaction() as conn:
            conn.execute(
                f"INSERT INTO capture_entries ({_COLUMNS})"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.ts,
                    entry.kind,
                    entry.body,
                    entry.note_id,
                    entry.status,
                    entry.reviewer,
                    entry.review_note,
                    int(entry.automated),
                ),
            )
        return entry

    def get(self, entry_id: str) -> FeedbackEntry | None:
        """One entry by id, or ``None``."""
        with self.db.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM capture_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return _entry(row) if row is not None else None

    def list_entries(
        self, status: Status | None = None, limit: int | None = None, offset: int = 0
    ) -> list[FeedbackEntry]:
        """Oldest-first. Filter by status, page with limit/offset when given."""
        sql = f"SELECT {_COLUMNS} FROM capture_entries"
        params: list[object] = []
        if status is not None:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY seq"
        if limit is not None or offset:
            # SQLite needs a LIMIT before OFFSET; -1 means "no limit".
            sql += " LIMIT ? OFFSET ?"
            params.extend((limit if limit is not None else -1, offset))
        with self.db.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_entry(row) for row in rows]

    def count(self, status: Status | None = None) -> int:
        """How many entries exist, so the UI can paginate honestly."""
        sql = "SELECT COUNT(*) AS n FROM capture_entries"
        params: tuple[object, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        with self.db.connection() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["n"])

    def restate(
        self, entry_id: str, status: Status, reviewer: str, review_note: str = ""
    ) -> FeedbackEntry:
        """Set an entry's state outright, whatever it was before.

        Unlike :meth:`review` this is an administrative override — it allows any
        transition (including back to ``pending``, or re-reviewing a resolved
        entry). The caller audits it, so an override is never anonymous.
        """
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status!r}")
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT status FROM capture_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                raise EntryNotFound(f"capture entry not found: {entry_id!r}")
            conn.execute(
                "UPDATE capture_entries SET status = ?, reviewer = ?, review_note = ?"
                " WHERE id = ?",
                (status, reviewer, review_note, entry_id),
            )
        entry = self.get(entry_id)
        assert entry is not None  # just wrote it
        return entry

    def review(
        self, entry_id: str, verdict: Verdict, reviewer: str, review_note: str = ""
    ) -> FeedbackEntry:
        """Mark a pending entry as applied/approved/rejected.

        The vault change itself (applied only) is performed by the caller
        (librarian). The status check and the write share one transaction, so
        two reviewers racing on the same entry can never both win.
        """
        if verdict not in ("applied", "approved", "rejected"):
            raise ValueError(f"unknown verdict: {verdict!r}")
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT status FROM capture_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                raise EntryNotFound(f"capture entry not found: {entry_id!r}")
            if row["status"] != "pending":
                raise EntryAlreadyReviewed(
                    f"entry {entry_id!r} is already {row['status']}"
                )
            conn.execute(
                "UPDATE capture_entries SET status = ?, reviewer = ?, review_note = ?"
                " WHERE id = ?",
                (verdict, reviewer, review_note, entry_id),
            )
        entry = self.get(entry_id)
        assert entry is not None  # just wrote it
        return entry
