"""Audit log: append-only JSONL history of every vault and capture change.

Like git log for the brain — who changed what, when, and why.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

AUDIT_FILE = Path(".brain/audit.jsonl")


@dataclass(frozen=True)
class AuditEntry:
    ts: str
    actor: str
    action: str
    note_id: str
    detail: str


def _audit_path(root: Path) -> Path:
    path = root / AUDIT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append(
    root: Path, *, actor: str, action: str, note_id: str = "", detail: str = ""
) -> AuditEntry:
    """Append one entry and return it."""
    entry = AuditEntry(
        ts=datetime.now(UTC).isoformat(),
        actor=actor,
        action=action,
        note_id=note_id,
        detail=detail,
    )
    with _audit_path(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(entry)) + "\n")
    return entry


def read_log(root: Path, limit: int = 100) -> list[AuditEntry]:
    """Newest-first. Empty log when nothing was ever recorded."""
    path = root / AUDIT_FILE
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = [AuditEntry(**json.loads(line)) for line in lines if line.strip()]
    return list(reversed(entries))[:limit]
