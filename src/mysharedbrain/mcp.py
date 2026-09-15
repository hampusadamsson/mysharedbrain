"""MCP server: the only remote mutation path into the vault.

Tools: create / read / update / delete / move notes, ripgrep search,
feedback (edits, missing info, requests) and questions. Every tool
delegates to :class:`Librarian`, so every change is audited.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mysharedbrain import capture
from mysharedbrain.app import librarian
from mysharedbrain.vault import InvalidNoteId, NoteExists, NoteNotFound, SectionNotFound

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
def list_notes(
    prefix: str = "", limit: int | None = None, offset: int = 0
) -> dict[str, object]:
    """List note ids, sorted, with optional folder prefix and pagination."""
    return {"notes": librarian(actor="mcp").list_notes(prefix, limit, offset)}


@mcp.tool
def read_notes(note_ids: list[str]) -> dict[str, object]:
    """Read several notes at once; missing ids are reported, not fatal."""
    batch = librarian(actor="mcp").read_notes(note_ids)
    return {
        "notes": [{"id": n.id, "content": n.content} for n in batch["notes"]],
        "missing": batch["missing"],
    }


@mcp.tool
def append_note(note_id: str, content: str) -> dict[str, str]:
    """Append content to the end of a note. Prefer over full rewrites."""
    try:
        note = librarian(actor="mcp").append_note(note_id, content)
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note.id}


@mcp.tool
def patch_note(
    note_id: str, heading: str, content: str, mode: str = "replace"
) -> dict[str, str]:
    """Replace (or append to) the section under a heading. Surgical edits."""
    try:
        note = librarian(actor="mcp").patch_note(note_id, heading, content, mode)
    except (NoteNotFound, SectionNotFound, InvalidNoteId) as exc:
        return {"ok": "false", "error": str(exc)}
    except ValueError as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note.id}


@mcp.tool
def list_directory(prefix: str = "") -> dict[str, object]:
    """Direct children of a folder: subfolders and note ids."""
    return librarian(actor="mcp").list_directory(prefix)  # type: ignore[return-value]


@mcp.tool
def get_frontmatter(note_id: str) -> dict[str, object]:
    """A note's YAML frontmatter (tags, etc.)."""
    try:
        return librarian(actor="mcp").get_frontmatter(note_id)
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"error": str(exc)}


@mcp.tool
def set_frontmatter(note_id: str, updates: dict[str, object]) -> dict[str, str]:
    """Merge keys into frontmatter (null value deletes a key)."""
    try:
        note = librarian(actor="mcp").set_frontmatter(note_id, updates)  # type: ignore[arg-type]
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": note.id}


@mcp.tool
def search_by_tag(tag: str) -> dict[str, object]:
    """Notes carrying a frontmatter tag."""
    return {"notes": librarian(actor="mcp").search_tags(tag)}


@mcp.tool
def get_backlinks(note_id: str) -> dict[str, object]:
    """Notes linking to this one via [[links]]."""
    try:
        return {"backlinks": librarian(actor="mcp").get_backlinks(note_id)}
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"error": str(exc)}


@mcp.tool
def get_outgoing(note_id: str) -> dict[str, object]:
    """[[Link]] targets a note points to."""
    try:
        return {"links": librarian(actor="mcp").get_outgoing(note_id)}
    except (NoteNotFound, InvalidNoteId) as exc:
        return {"error": str(exc)}


@mcp.tool
def recent_changes(limit: int = 20) -> dict[str, object]:
    """Latest audited vault and capture changes, newest first."""
    entries = librarian(actor="mcp").recent_changes(limit)
    return {"changes": [e.__dict__ for e in entries]}


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

    kind is one of: edit | missing | request.
    """
    try:
        entry = librarian(actor="mcp").give_feedback(kind, body, note_id)  # type: ignore[arg-type]
    except ValueError as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": entry.id, "status": entry.status}


@mcp.tool
def review_capture(
    entry_id: str,
    verdict: str,
    reviewer: str = "mcp",
    content: str | None = None,
    review_note: str = "",
) -> dict[str, str]:
    """Review a capture queue entry: applied (upserts the note with content),
    approved (endorsed, no vault change) or rejected."""
    if verdict not in ("applied", "approved", "rejected"):
        return {"ok": "false", "error": f"unknown verdict: {verdict!r}"}
    try:
        entry = librarian(actor="mcp").process_capture(
            entry_id, verdict, reviewer, content, review_note
        )
    except (capture.EntryNotFound, capture.EntryAlreadyReviewed, ValueError) as exc:
        return {"ok": "false", "error": str(exc)}
    return {"ok": "true", "id": entry.id, "status": entry.status}


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
    """Queue vault feedback for librarian review (edit/missing/request)."""
    return (
        f"File this feedback with give_feedback(kind='{kind}', note_id='{note_id}'): {body}. "
        "It lands in the capture queue as pending; the librarian reviews "
        "(applied/approved/rejected) before anything touches the vault."
    )


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
