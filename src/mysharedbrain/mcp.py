"""MCP server: the agent-facing adapter over the librarian service.

Every tool returns ``{"ok": True, ...}`` or ``{"ok": False, "error": ...}``
via the ``@_errors`` decorator — one mapping, no per-tool try/except.
Resources (``vault://``) and prompts guide browsing and feedback.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from fastapi import HTTPException
from fastmcp import FastMCP

from mysharedbrain import capture
from mysharedbrain.audit import KINDS
from mysharedbrain.service import librarian
from mysharedbrain.vault import (
    InvalidNoteId,
    NoteExists,
    NoteNotFound,
    SectionNotFound,
)

_BRAIN_INSTRUCTIONS = """MySharedBrain is a shared brain: a markdown vault an AI
assistant reads, writes and tends. Use it to gather information (read, search,
browse), add to it (create, append), edit it (update, patch, frontmatter) and
remove from it (soft-delete to trash, move/rename, restore).

Feedback is the critical loop: this brain learns from interaction. Whenever
something is wrong, missing or worth fetching, file it with give_feedback —
either the information itself or where to get it. The entry lands in the
capture queue as pending and the librarian reviews it
(applied/approved/rejected) before the vault changes, so teaching the brain is
always safe and never silent."""

mcp = FastMCP("mysharedbrain", instructions=_BRAIN_INSTRUCTIONS)

_ERRORS = (
    NoteNotFound,
    SectionNotFound,
    NoteExists,
    InvalidNoteId,
    capture.EntryNotFound,
    capture.EntryAlreadyReviewed,
    HTTPException,
    ValueError,
)


P = ParamSpec("P")
T = TypeVar("T")


def _errors(  # noqa: UP047 -- bare decorator needs classic TypeVars
    fn: Callable[P, T],
) -> Callable[P, T | dict[str, object]]:
    """Map domain errors to the ``{"ok": False, "error"}`` envelope."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | dict[str, object]:
        try:
            result = fn(*args, **kwargs)
            assert isinstance(result, dict)
            return {"ok": True, **result}
        except _ERRORS as exc:
            return {"ok": False, "error": str(exc)}

    return wrapper


@mcp.tool
@_errors
def create_note(note_id: str, content: str = "") -> dict[str, object]:
    """Create a new markdown note. Folders are created from the id path."""
    note = librarian(actor="mcp").create_note(note_id, content)
    return {"id": note.id}


@mcp.tool
@_errors
def read_note(note_id: str) -> dict[str, object]:
    """Read a note by id."""
    note = librarian(actor="mcp").read_note(note_id)
    return {"id": note.id, "content": note.content}


@mcp.tool
@_errors
def update_note(note_id: str, content: str) -> dict[str, object]:
    """Replace a note's content by id."""
    note = librarian(actor="mcp").update_note(note_id, content)
    return {"id": note.id}


@mcp.tool
@_errors
def delete_note(note_id: str) -> dict[str, object]:
    """Soft-delete a note to trash (restorable with restore_note)."""
    librarian(actor="mcp").delete_note(note_id)
    return {"id": note_id}


@mcp.tool
@_errors
def restore_note(note_id: str) -> dict[str, object]:
    """Restore a trashed note back into the vault."""
    note = librarian(actor="mcp").restore_note(note_id)
    return {"id": note.id}


@mcp.tool
@_errors
def move_note(note_id: str, new_id: str) -> dict[str, object]:
    """Move/rename a note."""
    note = librarian(actor="mcp").move_note(note_id, new_id)
    return {"id": note.id}


@mcp.tool
@_errors
def list_notes(
    prefix: str = "", limit: int | None = None, offset: int = 0
) -> dict[str, object]:
    """List note ids, sorted, with optional folder prefix and pagination."""
    return {"notes": librarian(actor="mcp").list_notes(prefix, limit, offset)}


@mcp.tool
@_errors
def read_notes(note_ids: list[str]) -> dict[str, object]:
    """Read several notes at once; missing ids are reported, not fatal."""
    batch = librarian(actor="mcp").read_notes(note_ids)
    return {
        "notes": [{"id": n.id, "content": n.content} for n in batch["notes"]],
        "missing": batch["missing"],
    }


@mcp.tool
@_errors
def append_note(note_id: str, content: str) -> dict[str, object]:
    """Append content to the end of a note. Prefer over full rewrites."""
    note = librarian(actor="mcp").append_note(note_id, content)
    return {"id": note.id}


@mcp.tool
@_errors
def patch_note(
    note_id: str, heading: str, content: str, mode: str = "replace"
) -> dict[str, object]:
    """Replace (or append to) the section under a heading. Surgical edits."""
    note = librarian(actor="mcp").patch_note(note_id, heading, content, mode)
    return {"id": note.id}


@mcp.tool
@_errors
def list_directory(prefix: str = "") -> dict[str, object]:
    """Direct children of a folder: subfolders and note ids."""
    lib = librarian(actor="mcp")
    out = lib.list_directory(prefix)
    return {"folders": out["folders"], "notes": out["notes"]}


@mcp.tool
@_errors
def get_frontmatter(note_id: str) -> dict[str, object]:
    """A note's YAML frontmatter (tags, etc.)."""
    return librarian(actor="mcp").get_frontmatter(note_id)


@mcp.tool
@_errors
def set_frontmatter(note_id: str, updates: dict[str, object]) -> dict[str, object]:
    """Merge keys into frontmatter (null value deletes a key)."""
    lib = librarian(actor="mcp")
    note = lib.set_frontmatter(note_id, updates)  # type: ignore[arg-type]
    return {"id": note.id}


@mcp.tool
@_errors
def search_by_tag(tag: str) -> dict[str, object]:
    """Notes carrying a frontmatter tag."""
    return {"notes": librarian(actor="mcp").search_tags(tag)}


@mcp.tool
@_errors
def note_history(
    note_id: str, kind: str | None = None, limit: int = 50, offset: int = 0
) -> dict[str, object]:
    """Every logged interaction with one note (reads, finds, edits …).

    kind filters to one category: read | find | write | move | delete |
    capture | job | other. Returned with per-kind counts for that file.
    """
    if kind is not None and kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    lib = librarian(actor="mcp")
    stats = lib.file_stats(note_id)
    return {
        "entries": [e.__dict__ for e in lib.file_history(note_id, kind, limit, offset)],
        "total": lib.count_changes(kind=kind, note_id=note_id),
        "limit": limit,
        "offset": offset,
        "stats": {
            "note_id": stats.note_id,
            "counts": stats.counts,
            "first_seen": stats.first_seen,
            "last_seen": stats.last_seen,
            "total": stats.total,
        },
    }


@mcp.tool
@_errors
def get_backlinks(note_id: str) -> dict[str, object]:
    """Notes linking to this one via [[links]]."""
    return {"backlinks": librarian(actor="mcp").get_backlinks(note_id)}


@mcp.tool
@_errors
def get_outgoing(note_id: str) -> dict[str, object]:
    """[[Link]] targets a note points to."""
    return {"links": librarian(actor="mcp").get_outgoing(note_id)}


@mcp.tool
@_errors
def recent_changes(limit: int = 20, offset: int = 0) -> dict[str, object]:
    """Latest audited vault and capture changes, newest first (paged).

    Returned with per-kind counts for the whole log, the same shape the per-note
    history reports for one file.
    """
    lib = librarian(actor="mcp")
    stats = lib.file_stats()
    return {
        "changes": [e.__dict__ for e in lib.recent_changes(limit, offset)],
        "total": lib.count_changes(),
        "limit": limit,
        "offset": offset,
        "stats": {
            "note_id": stats.note_id,
            "counts": stats.counts,
            "first_seen": stats.first_seen,
            "last_seen": stats.last_seen,
            "total": stats.total,
        },
    }


@mcp.tool
@_errors
def search_notes(query: str, limit: int = 20, offset: int = 0) -> dict[str, object]:
    """Search notes by name and content (ripgrep)."""
    result = librarian(actor="mcp").search(query, limit, offset)
    return {
        "names": result["names"],
        "content": [{"id": h.id, "excerpts": h.excerpts} for h in result["content"]],
    }


@mcp.tool
@_errors
def give_feedback(kind: str, body: str, note_id: str = "") -> dict[str, object]:
    """Teach the brain: queue feedback the librarian applies later.

    This is the self-learning loop — the single most important tool here.
    Either hand over the information itself (a correction, a fact, content for
    a missing note) or say where to get it (a source to check, what is
    missing). The entry lands in the capture queue as pending and the
    librarian reviews it (applied/approved/rejected) before the vault changes.

    "kind is one of: edit | missing | request | question.
    """
    lib = librarian(actor="mcp")
    entry = lib.give_feedback(kind, body, note_id)  # type: ignore[arg-type]
    return {"id": entry.id, "status": entry.status}


@mcp.resource("vault://{note_id}")
def vault_note(note_id: str) -> str:
    """A vault note's markdown by id — browse without tool calls."""
    try:
        return librarian(actor="mcp").read_note(note_id).content
    except (NoteNotFound, InvalidNoteId) as exc:
        return f"Error: {exc}"


@mcp.resource("vault://index")
def vault_index() -> str:
    """All note ids in the vault, sorted."""
    return "\n".join(librarian(actor="mcp").list_notes())


@mcp.prompt()
def ask_librarian(question: str) -> str:
    """Ask the librarian; misses are queued for future retrieval."""
    return (
        "Ask the MySharedBrain librarian this question with ask_question: "
        f"{question}. If it is already answered, present the matching notes. "
        "If not found, the miss is logged as a request — "
        "use give_feedback(kind='request', ...) only for follow-up context."
    )


@mcp.prompt()
def file_feedback(kind: str, body: str, note_id: str = "") -> str:
    """Teach the brain: queue feedback the librarian applies later."""
    kinds = {
        "edit": "correct something the vault gets wrong",
        "missing": "note a gap and supply the content or where to find it",
        "request": "ask the librarian to fetch or do something",
        "question": "leave an open question for future retrieval",
    }
    hint = kinds.get(kind, "describe what the vault should learn")
    return (
        f"File this feedback with give_feedback(kind='{kind}', note_id='{note_id}'): {body}. "
        f"Purpose: {hint}. Either carry the information itself or say where "
        "to get it — both teach the brain. It lands in the capture queue as "
        "pending; the librarian reviews (applied/approved/rejected) before "
        "anything touches the vault."
    )


@mcp.tool
@_errors
def ask_question(question: str) -> dict[str, object]:
    """Ask the librarian. Answered from the vault when possible, otherwise
    filed as an automated question for future retrieval."""
    answer = librarian(actor="mcp").ask(question)
    return {
        "found": answer.found,
        "note_ids": answer.note_ids,
        "hits": [{"id": h.id, "excerpts": h.excerpts} for h in answer.hits],
        "entry_id": answer.entry_id,
        "message": answer.message,
    }
