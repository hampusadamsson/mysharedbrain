"""The librarian: single mutation path for vault + capture changes.

Every write goes through here so it is audited. The MCP server and the REST
API are thin adapters over this service — the vault is never mutated behind
its back.
"""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from mysharedbrain.audit import AuditEntry, AuditLog, LogStats
from mysharedbrain.capture import (
    CaptureQueue,
    EntryAlreadyReviewed,
    EntryNotFound,
    FeedbackEntry,
    Kind,
    Status,
    Verdict,
)
from mysharedbrain.protocols import AuditStore, CaptureStore
from mysharedbrain.vault import Note, NoteNotFound, SearchHit, Vault, VaultError


class SearchResult(TypedDict):
    names: list[str]
    content: list[SearchHit]


class BatchRead(TypedDict):
    notes: list[Note]
    missing: list[str]


_STOP_WORDS = frozenset(
    [
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "is",
        "are",
        "was",
        "were",
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "in",
        "on",
        "and",
        "or",
        "it",
        "its",
        "this",
        "that",
        "with",
        "by",
        "from",
        "as",
        "at",
        "be",
        "do",
        "does",
        "me",
        "my",
        "you",
        "your",
        "we",
        "our",
    ]
)


LIBRARIAN_ACTOR = "librarian"
"""Audit actor for anything the librarian agent does on its own.

Every mutation the agent makes runs through :class:`Librarian` with this actor,
so the audit log can answer "what did the librarian change?" with one filter —
scheduled or not. The REST/MCP adapters use their own actors (``api``, ``mcp``)
because a human or client asked for those.
"""


def _tokens(question: str) -> list[str]:
    """Searchable tokens: alphanumerics, len>=3, no stop words, order kept."""
    out: list[str] = []
    for word in re.findall(r"[A-Za-z0-9_#-]+", question.lower()):
        word = word.strip("#")
        if len(word) >= 3 and word not in _STOP_WORDS and word not in out:
            out.append(word)
    return out


def vault_root() -> Path:
    return Path(os.environ.get("VAULT_DIR", "vault")).resolve()


@dataclass(frozen=True)
class Answer:
    found: bool
    question: str
    note_ids: list[str]
    hits: list[SearchHit]
    entry_id: str = ""
    message: str = ""


class Librarian:
    """Ask for information; an unanswered question is filed as an automated
    ``question`` capture entry for future action."""

    def __init__(self, root: Path, actor: str = LIBRARIAN_ACTOR) -> None:
        self.root = root
        self.vault = Vault(root)
        self.audit: AuditStore = AuditLog(root)
        self.capture: CaptureStore = CaptureQueue(root)
        self.actor = actor

    # -- notes (CRUD + move) -------------------------------------------------
    def create_note(self, note_id: str, content: str) -> Note:
        note = self.vault.create(note_id, content)
        self.audit.append(actor=self.actor, action="create", note_id=note.id)
        return note

    def read_note(self, note_id: str) -> Note:
        note = self.vault.read(note_id)
        self._seen(note.id)
        return note

    def update_note(self, note_id: str, content: str) -> Note:
        note = self.vault.update(note_id, content)
        self.audit.append(actor=self.actor, action="update", note_id=note.id)
        return note

    def delete_note(self, note_id: str) -> None:
        self.vault.delete(note_id)
        self.audit.append(
            actor=self.actor,
            action="delete",
            note_id=note_id,
            detail=f"trash:.brain/trash/{note_id}",
        )

    def restore_note(self, note_id: str) -> Note:
        note = self.vault.restore(note_id)
        self.audit.append(actor=self.actor, action="restore", note_id=note.id)
        return note

    def move_note(self, note_id: str, new_id: str) -> Note:
        note = self.vault.move(note_id, new_id)
        # Logged against the *old* id: that is the file whose log must show the
        # handoff, and where the destination is worth naming.
        self.audit.append(
            actor=self.actor,
            action="move",
            note_id=note_id,
            detail=f"to {note.id}",
        )
        return note

    def list_notes(
        self, prefix: str = "", limit: int | None = None, offset: int = 0
    ) -> list[str]:
        return self.vault.list_notes(prefix, limit, offset)

    def read_notes(self, note_ids: list[str]) -> BatchRead:
        found: list[Note] = []
        missing: list[str] = []
        for nid in note_ids:
            try:
                found.append(self.vault.read(nid))
            except VaultError:
                missing.append(nid)
        for note in found:
            self._seen(note.id, detail="batch")
        return BatchRead(notes=found, missing=missing)

    def append_note(self, note_id: str, content: str) -> Note:
        note = self.vault.append(note_id, content)
        self.audit.append(actor=self.actor, action="append", note_id=note.id)
        return note

    def patch_note(
        self, note_id: str, heading: str, content: str, mode: str = "replace"
    ) -> Note:
        note = self.vault.patch(note_id, heading, content, mode)
        self.audit.append(
            actor=self.actor,
            action="patch",
            note_id=note.id,
            detail=f"section:{heading}",
        )
        return note

    def list_directory(self, prefix: str = "") -> dict[str, list[str]]:
        return self.vault.list_directory(prefix)

    def get_frontmatter(self, note_id: str) -> dict[str, object]:
        return self.vault.get_frontmatter(note_id)

    def set_frontmatter(self, note_id: str, updates: dict[str, object | None]) -> Note:
        note = self.vault.set_frontmatter(note_id, updates)
        self.audit.append(actor=self.actor, action="frontmatter", note_id=note.id)
        return note

    def get_tags(self, note_id: str) -> list[str]:
        return self.vault.get_tags(note_id)

    def search_tags(self, tag: str) -> list[str]:
        return self.vault.search_tags(tag)

    def get_outgoing(self, note_id: str) -> list[str]:
        return self.vault.get_outgoing(note_id)

    def get_backlinks(self, note_id: str) -> list[str]:
        return self.vault.get_backlinks(note_id)

    def recent_changes(
        self,
        limit: int = 20,
        offset: int = 0,
        kind: str | None = None,
        note_id: str | None = None,
    ) -> list[AuditEntry]:
        return self.audit.read_log(limit, offset, note_id=note_id, kind=kind)

    def count_changes(self, kind: str | None = None, note_id: str | None = None) -> int:
        return self.audit.count(note_id=note_id, kind=kind)

    def file_history(
        self,
        note_id: str,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Every logged interaction with one note, newest first."""
        return self.audit.read_log(limit, offset, note_id=note_id, kind=kind)

    def file_stats(self, note_id: str | None = None) -> LogStats:
        """Interaction counts for one note — or the whole log when omitted."""
        return self.audit.stats(note_id)

    def search(
        self, query: str, limit: int = 20, offset: int = 0, track: bool = True
    ) -> SearchResult:
        """Search names and content.

        ``track`` logs a ``find`` per matching note, which is what powers
        "how often was this file surfaced by a keyword?" in the file log.
        Transient searches (type-ahead) pass ``track=False`` to keep the log
        meaningful rather than a keystroke record.
        """
        result = SearchResult(
            names=self.vault.search_names(query),
            content=self.vault.search_content(query, limit, offset),
        )
        if track:
            seen = list(result["names"])
            for hit in result["content"]:
                if hit.id not in seen:
                    seen.append(hit.id)
            for note_id in seen:
                self._seen(note_id, action="find", detail=f"query:{query.strip()}")
        return result

    # -- interaction logging -------------------------------------------------
    def _seen(self, note_id: str, *, action: str = "read", detail: str = "") -> None:
        """Log an access to ``note_id`` (best-effort; never breaks a read)."""
        with contextlib.suppress(Exception):
            self.audit.append(
                actor=self.actor, action=action, note_id=note_id, detail=detail
            )

    # -- feedback / capture --------------------------------------------------
    def list_capture(
        self, status: Status | None = None, limit: int | None = None, offset: int = 0
    ) -> list[FeedbackEntry]:
        return self.capture.list_entries(status, limit, offset)

    def restate_capture(
        self, entry_id: str, status: Status, reviewer: str, review_note: str = ""
    ) -> FeedbackEntry:
        """Override a capture entry's state (any → any), audited as a restatement.

        Distinct from :meth:`process_capture`: no vault change happens here, which
        is why the audit action is ``capture-<status>`` with a ``restate:`` detail
        rather than the reviewed ``capture-<verdict>``.
        """
        entry = self.capture.restate(entry_id, status, reviewer, review_note)
        self.audit.append(
            actor=reviewer,
            action=f"capture-{entry.status}",
            note_id=entry.note_id,
            detail=f"restate:{entry.kind}:{entry.id}",
        )
        return entry

    def count_capture(self, status: Status | None = None) -> int:
        return self.capture.count(status)

    def give_feedback(
        self, kind: Kind, body: str, note_id: str = "", automated: bool = False
    ) -> FeedbackEntry:
        entry = self.capture.submit(
            kind=kind, body=body, note_id=note_id, automated=automated
        )
        self.audit.append(
            actor=self.actor,
            action="feedback",
            note_id=note_id,
            detail=f"{kind}:{entry.id}" + (" (automated)" if automated else ""),
        )
        return entry

    def process_capture(
        self,
        entry_id: str,
        verdict: Verdict,
        reviewer: str,
        content: str | None = None,
        review_note: str = "",
    ) -> FeedbackEntry:
        """Review one queue entry (double-check) before it updates the vault.

        ``applied`` with ``content`` upserts the entry's ``note_id``;
        ``approved`` endorses the entry without touching the vault;
        ``rejected`` only records the verdict. All paths are audited.
        """
        entry = self.capture.get(entry_id)
        if entry is None:
            raise EntryNotFound(f"capture entry not found: {entry_id!r}")
        if entry.status != "pending":
            raise EntryAlreadyReviewed(f"entry {entry_id!r} is already {entry.status}")
        if verdict == "applied" and entry.note_id and content is None:
            raise ValueError(
                "applied requires content for entries with a note; "
                "use approved to endorse without changes"
            )
        if verdict == "applied" and content is not None and entry.note_id:
            # Vault first, review second: re-applying identical content converges,
            # so a crash between the two is retried, not lost.
            try:
                self.vault.read(entry.note_id)
                self.vault.update(entry.note_id, content)
                action = "update"
            except NoteNotFound:
                self.vault.create(entry.note_id, content)
                action = "create"
            self.audit.append(
                actor=reviewer,
                action=action,
                note_id=entry.note_id,
                detail=f"via capture:{entry.id}",
            )
        reviewed = self.capture.review(entry_id, verdict, reviewer, review_note)
        self.audit.append(
            actor=reviewer,
            action=f"capture-{verdict}",
            note_id=entry.note_id,
            detail=f"{entry.kind}:{entry.id}",
        )
        return reviewed

    # -- questions -----------------------------------------------------------
    def ask(self, question: str) -> Answer:
        """Answer from the vault when possible; otherwise log it as missing
        information (a ``request`` entry) for future retrieval."""
        clean = question.strip()
        if not clean:
            raise ValueError("question must not be empty")
        names: list[str] = []
        hits: list[SearchHit] = []
        for token in _tokens(clean):
            for nid in self.vault.search_names(token):
                if nid not in names:
                    names.append(nid)
            for hit in self.vault.search_content(token, limit=5):
                if hit.id not in names:
                    names.append(hit.id)
                if all(h.id != hit.id for h in hits):
                    hits.append(hit)
        if names:
            return Answer(
                found=True,
                question=question,
                note_ids=names,
                hits=hits,
                message=f"Found {len(names)} matching note(s).",
            )
        body = f"Unanswered question: {clean}"
        # Open questions are their own kind, and filed by the system (automated).
        for existing in self.capture.list_entries("pending"):
            if existing.body == body and existing.kind in ("question", "request"):
                return Answer(
                    found=False,
                    question=question,
                    note_ids=[],
                    hits=[],
                    entry_id=existing.id,
                    message="No matching notes. Already filed as an automated question.",
                )
        entry = self.give_feedback("question", body, automated=True)
        return Answer(
            found=False,
            question=question,
            note_ids=[],
            hits=[],
            entry_id=entry.id,
            message=(
                "No matching notes. Filed an automated question for future retrieval."
            ),
        )


def librarian(actor: str = "api") -> Librarian:
    """Shared factory: both adapters (REST, MCP) build Librarians here."""
    return Librarian(vault_root(), actor=actor)
