"""Capture queue: the feedback inbox.

Corrections, missing-information notes and requests land here as ``pending``
entries. The librarian reviews each one (double-check) — ``applied`` (vault
updated), ``approved`` (endorsed, no vault change needed) or ``rejected`` —
never silently dropped.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

CAPTURE_FILE = Path(".brain/capture.jsonl")

Kind = Literal["edit", "missing", "request"]
Status = Literal["pending", "applied", "approved", "rejected"]
Verdict = Literal["applied", "approved", "rejected"]


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


def _capture_path(root: Path) -> Path:
    path = root / CAPTURE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_all(root: Path) -> list[FeedbackEntry]:
    path = root / CAPTURE_FILE
    if not path.is_file():
        return []
    entries: list[FeedbackEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(FeedbackEntry(**json.loads(line)))
    return entries


def _write_all(root: Path, entries: list[FeedbackEntry]) -> None:
    path = _capture_path(root)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(asdict(entry)) + "\n")


def submit(root: Path, *, kind: Kind, body: str, note_id: str = "") -> FeedbackEntry:
    """Queue a new feedback entry as ``pending``."""
    if not body.strip():
        raise ValueError("feedback body must not be empty")
    if kind not in ("edit", "missing", "request"):
        raise ValueError(f"unknown feedback kind: {kind!r}")
    entry = FeedbackEntry(
        id=uuid.uuid4().hex[:12],
        ts=datetime.now(UTC).isoformat(),
        kind=kind,
        body=body.strip(),
        note_id=note_id.strip(),
        status="pending",
    )
    entries = _read_all(root)
    entries.append(entry)
    _write_all(root, entries)
    return entry


def list_entries(root: Path, status: Status | None = None) -> list[FeedbackEntry]:
    """Oldest-first. Filter by status when given."""
    entries = _read_all(root)
    if status is not None:
        entries = [e for e in entries if e.status == status]
    return entries


class EntryNotFound(Exception):
    """No capture entry with this id."""


class EntryAlreadyReviewed(Exception):
    """The entry was already applied or rejected."""


def review(
    root: Path, entry_id: str, verdict: Verdict, reviewer: str, review_note: str = ""
) -> FeedbackEntry:
    """Mark a pending entry as applied/approved/rejected. The vault change
    itself (applied only) is performed by the caller (librarian)."""
    if verdict not in ("applied", "approved", "rejected"):
        raise ValueError(f"unknown verdict: {verdict!r}")
    entries = _read_all(root)
    for entry in entries:
        if entry.id == entry_id:
            if entry.status != "pending":
                raise EntryAlreadyReviewed(
                    f"entry {entry_id!r} is already {entry.status}"
                )
            entry.status = verdict
            entry.reviewer = reviewer
            entry.review_note = review_note
            _write_all(root, entries)
            return entry
    raise EntryNotFound(f"capture entry not found: {entry_id!r}")
