"""Storage contracts.

``AuditStore`` and ``CaptureStore`` describe the behaviour the service layer
depends on. The concrete sqlite backends (:class:`mysharedbrain.audit.AuditLog`,
:class:`mysharedbrain.capture.CaptureQueue`) satisfy them structurally, so
``Librarian`` never binds to a storage engine — swap in another implementation
(in-memory, remote) without touching the service.

Both are ``runtime_checkable`` so tests can assert the backends conform.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mysharedbrain.audit import AuditEntry, LogStats
from mysharedbrain.capture import FeedbackEntry, Kind, Status, Verdict

__all__ = [
    "AuditEntry",
    "AuditStore",
    "CaptureStore",
    "FeedbackEntry",
    "Kind",
    "LogStats",
    "Status",
    "Verdict",
]


@runtime_checkable
class AuditStore(Protocol):
    """Append-only interaction history."""

    def append(
        self,
        *,
        actor: str,
        action: str,
        note_id: str = "",
        detail: str = "",
        kind: str | None = None,
    ) -> AuditEntry: ...

    def read_log(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        note_id: str | None = None,
        kind: str | None = None,
    ) -> list[AuditEntry]: ...

    def count(self, *, note_id: str | None = None, kind: str | None = None) -> int: ...

    def stats(self, note_id: str | None = None) -> LogStats: ...


@runtime_checkable
class CaptureStore(Protocol):
    """Feedback inbox with one-way review transitions."""

    def submit(
        self, *, kind: Kind, body: str, note_id: str = "", automated: bool = False
    ) -> FeedbackEntry: ...

    def get(self, entry_id: str) -> FeedbackEntry | None: ...

    def list_entries(
        self, status: Status | None = None, limit: int | None = None, offset: int = 0
    ) -> list[FeedbackEntry]: ...

    def count(self, status: Status | None = None) -> int: ...

    def review(
        self, entry_id: str, verdict: Verdict, reviewer: str, review_note: str = ""
    ) -> FeedbackEntry: ...

    def restate(
        self, entry_id: str, status: Status, reviewer: str, review_note: str = ""
    ) -> FeedbackEntry: ...
