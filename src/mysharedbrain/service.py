"""The librarian: single mutation path for vault + capture changes.

Every write goes through here so it is audited. The MCP server and the REST
API are thin adapters over this service — the vault is never mutated behind
its back.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from mysharedbrain import audit, capture
from mysharedbrain.capture import FeedbackEntry
from mysharedbrain.vault import Note, SearchHit, Vault


class SearchResult(TypedDict):
    names: list[str]
    content: list[SearchHit]


@dataclass(frozen=True)
class Answer:
    found: bool
    question: str
    note_ids: list[str]
    hits: list[SearchHit]
    entry_id: str = ""
    message: str = ""


class Librarian:
    """Ask for information; missing information is logged for future action."""

    def __init__(self, root: Path, actor: str = "librarian") -> None:
        self.root = root
        self.vault = Vault(root)
        self.actor = actor

    # -- notes (CRUD + move) -------------------------------------------------
    def create_note(self, note_id: str, content: str) -> Note:
        note = self.vault.create(note_id, content)
        audit.append(self.root, actor=self.actor, action="create", note_id=note.id)
        return note

    def read_note(self, note_id: str) -> Note:
        return self.vault.read(note_id)

    def update_note(self, note_id: str, content: str) -> Note:
        note = self.vault.update(note_id, content)
        audit.append(self.root, actor=self.actor, action="update", note_id=note.id)
        return note

    def delete_note(self, note_id: str) -> None:
        self.vault.delete(note_id)
        audit.append(self.root, actor=self.actor, action="delete", note_id=note_id)

    def move_note(self, note_id: str, new_id: str) -> Note:
        note = self.vault.move(note_id, new_id)
        audit.append(
            self.root,
            actor=self.actor,
            action="move",
            note_id=note.id,
            detail=f"from {note_id}",
        )
        return note

    def list_notes(self, prefix: str = "") -> list[str]:
        return self.vault.list_notes(prefix)

    def search(self, query: str, limit: int = 20) -> SearchResult:
        return SearchResult(
            names=self.vault.search_names(query),
            content=self.vault.search_content(query, limit),
        )

    # -- feedback / capture --------------------------------------------------
    def give_feedback(
        self, kind: capture.Kind, body: str, note_id: str = ""
    ) -> FeedbackEntry:
        entry = capture.submit(self.root, kind=kind, body=body, note_id=note_id)
        audit.append(
            self.root,
            actor=self.actor,
            action="feedback",
            note_id=note_id,
            detail=f"{kind}:{entry.id}",
        )
        return entry

    def process_capture(
        self,
        entry_id: str,
        verdict: capture.Verdict,
        reviewer: str,
        content: str | None = None,
        review_note: str = "",
    ) -> FeedbackEntry:
        """Review one queue entry (double-check) before it updates the vault.

        ``applied`` with ``content`` upserts the entry's ``note_id``;
        ``rejected`` only records the verdict. Both paths are audited.
        """
        pending = [
            e for e in capture.list_entries(self.root, "pending") if e.id == entry_id
        ]
        if not pending:
            existing = [e for e in capture.list_entries(self.root) if e.id == entry_id]
            if existing:
                raise capture.EntryAlreadyReviewed(
                    f"entry {entry_id!r} is already {existing[0].status}"
                )
            raise capture.EntryNotFound(f"capture entry not found: {entry_id!r}")
        entry = pending[0]
        if verdict == "applied" and content is not None and entry.note_id:
            try:
                self.vault.read(entry.note_id)
                self.vault.update(entry.note_id, content)
                audit.append(
                    self.root,
                    actor=reviewer,
                    action="update",
                    note_id=entry.note_id,
                    detail=f"via capture:{entry.id}",
                )
            except Exception:
                self.vault.create(entry.note_id, content)
                audit.append(
                    self.root,
                    actor=reviewer,
                    action="create",
                    note_id=entry.note_id,
                    detail=f"via capture:{entry.id}",
                )
        reviewed = capture.review(self.root, entry_id, verdict, reviewer, review_note)
        audit.append(
            self.root,
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
        if not question.strip():
            raise ValueError("question must not be empty")
        names = self.vault.search_names(question)
        hits = self.vault.search_content(question)
        for hit in hits:
            if hit.id not in names:
                names.append(hit.id)
        if names:
            return Answer(
                found=True,
                question=question,
                note_ids=names,
                hits=hits,
                message=f"Found {len(names)} matching note(s).",
            )
        entry = self.give_feedback(
            "request", f"Unanswered question: {question.strip()}"
        )
        return Answer(
            found=False,
            question=question,
            note_ids=[],
            hits=[],
            entry_id=entry.id,
            message="No matching notes. Logged as missing information for future retrieval.",
        )
