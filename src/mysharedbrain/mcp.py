"""MCP server: the only remote mutation path into the vault.

Tools: create / read / update / delete / move notes, ripgrep search,
feedback (corrections, missing info, requests) and questions. Every tool
delegates to :class:`Librarian`, so every change is audited.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mysharedbrain.app import librarian
from mysharedbrain.vault import InvalidNoteId, NoteExists, NoteNotFound

mcp = FastMCP("mysharedbrain")


@mcp.tool
def create_note(note_id: str, content: str = "") -> dict[str, str]:
    """Create a new markdown note. Folders are created from the id path."""
    try:
        note = librarian(actor="mcp").create_note(note_id, content)
    except NoteExists as exc:
        return {"ok": "false", "error": str(exc)}
    except InvalidNoteId as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note.id}


@mcp.tool
def read_note(note_id: str) -> dict[str, str]:
    """Read a note by id."""
    try:
        note = librarian(actor="mcp").read_note(note_id)
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note.id, "content": note.content}


@mcp.tool
def update_note(note_id: str, content: str) -> dict[str, str]:
    """Replace a note's content by id."""
    try:
        note = librarian(actor="mcp").update_note(note_id, content)
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note.id}


@mcp.tool
def delete_note(note_id: str) -> dict[str, str]:
    """Delete a note by id."""
    try:
        librarian(actor="mcp").delete_note(note_id)
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note_id}


@mcp.tool
def move_note(note_id: str, new_id: str) -> dict[str, str]:
    """Move/rename a note."""
    try:
        note = librarian(actor="mcp").move_note(note_id, new_id)
    except (NoteNotFound, NoteExists, InvalidNoteId) as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note.id}


@mcp.tool
def search_notes(query: str, limit: int = 20) -> dict[str, object]:
    """Search notes by name and content (ripgrep)."""
    result = librarian(actor="mcp").search(query, limit)
    return {
        "names": result["names"],
        "content": [{"id": h.id, "excerpts": h.excerpts} for h in result["content"]],
    }


@mcp.tool
def give_feedback(kind: str, body: str, note_id: str = "") -> dict[str, str]:
    """Queue feedback: correct info, flag missing info, or file a request.

    kind is one of: correction | missing | request.
    """
    try:
        entry = librarian(actor="mcp").give_feedback(kind, body, note_id)  # type: ignore[arg-type]
    except ValueError as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": entry.id, "status": entry.status}


@mcp.tool
def ask_question(question: str) -> dict[str, object]:
    """Ask the librarian. Answered from the vault when possible, otherwise
    logged as missing information for future retrieval."""
    try:
        answer = librarian(actor="mcp").ask(question)
    except ValueError as exc:
        return {"ok": "false", "error": str(exc)}
    return {
        "ok": "true",
        "found": answer.found,
        "note_ids": answer.note_ids,
        "hits": [{"id": h.id, "excerpts": h.excerpts} for h in answer.hits],
        "entry_id": answer.entry_id,
        "message": answer.message,
    }
