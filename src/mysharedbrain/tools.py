"""Built-in librarian tools: file + capture operations, nothing else.

The agent can only touch the vault and the capture queue, and only through
:class:`~mysharedbrain.service.Librarian` — so every agent action is audited
and constrained to the note surface. Remote MCP tools are a separate, opt-in
source (:mod:`mysharedbrain.agent`); these are the always-local defaults.

Each tool is a closure binding a librarian (actor-tagged per job), so one run
cannot impersonate another. Names map 1:1 to :data:`TOOLS` and to the
``tools:`` section of the config file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from mysharedbrain.capture import Kind, Status, Verdict
from mysharedbrain.service import Librarian

#: Everything a librarian tool is allowed to reach — notes, or the vault's own
#: capture queue. Nothing here can leave the vault.
Scope = Literal["vault", "capture"]
SCOPES: tuple[Scope, ...] = ("vault", "capture")


@dataclass(frozen=True)
class ToolSpec:
    """One built-in tool: builder, description, and what it may touch."""

    name: str
    description: str
    scope: Scope
    build: Callable[[Librarian], Callable[..., Any]]


def _list_notes(lib: Librarian) -> Callable[..., Any]:
    def list_notes(prefix: str = "", limit: int = 100) -> list[str]:
        """List note ids, optionally filtered by folder prefix."""
        return lib.list_notes(prefix, limit)

    return list_notes


def _read_note(lib: Librarian) -> Callable[..., Any]:
    def read_note(note_id: str) -> str:
        """Read the full markdown of a note by id."""
        return lib.read_note(note_id).content

    return read_note


def _search_notes(lib: Librarian) -> Callable[..., Any]:
    def search_notes(query: str, limit: int = 10) -> list[str]:
        """Search names and content; returns matching note ids."""
        result = lib.search(query, limit)
        ids = list(result["names"])
        for hit in result["content"]:
            if hit.id not in ids:
                ids.append(hit.id)
        return ids

    return search_notes


def _create_note(lib: Librarian) -> Callable[..., Any]:
    def create_note(note_id: str, content: str = "") -> str:
        """Create a new note; fails if it already exists."""
        return lib.create_note(note_id, content).id

    return create_note


def _update_note(lib: Librarian) -> Callable[..., Any]:
    def update_note(note_id: str, content: str) -> str:
        """Replace a note's whole content."""
        return lib.update_note(note_id, content).id

    return update_note


def _append_note(lib: Librarian) -> Callable[..., Any]:
    def append_note(note_id: str, content: str) -> str:
        """Append markdown to the end of a note (creates it if missing)."""
        return lib.append_note(note_id, content).id

    return append_note


def _patch_note(lib: Librarian) -> Callable[..., Any]:
    def patch_note(
        note_id: str, heading: str, content: str, mode: str = "replace"
    ) -> str:
        """Replace (or append to) the section under a heading."""
        return lib.patch_note(note_id, heading, content, mode).id

    return patch_note


def _delete_note(lib: Librarian) -> Callable[..., Any]:
    def delete_note(note_id: str) -> str:
        """Soft-delete a note to trash (restorable)."""
        lib.delete_note(note_id)
        return note_id

    return delete_note


def _move_note(lib: Librarian) -> Callable[..., Any]:
    def move_note(note_id: str, new_id: str) -> str:
        """Move/rename a note."""
        return lib.move_note(note_id, new_id).id

    return move_note


def _list_capture(lib: Librarian) -> Callable[..., Any]:
    def list_capture(status: str | None = None) -> list[dict[str, str]]:
        """List capture queue entries; status is pending|applied|approved|rejected."""
        entries = lib.list_capture(_as_status(status))
        return [e.__dict__ for e in entries]

    return list_capture


def _review_capture(lib: Librarian) -> Callable[..., Any]:
    def review_capture(
        entry_id: str,
        verdict: str,
        content: str | None = None,
        review_note: str = "",
    ) -> str:
        """Resolve a capture entry: applied (with content), approved or rejected.

        Every request you drop must be reviewed — these entries are the
        vault's feedback loop, not a scratchpad.
        """
        if verdict not in ("applied", "approved", "rejected"):
            raise ValueError(f"unknown verdict: {verdict!r}")
        entry = lib.process_capture(
            entry_id,
            verdict,  # type: ignore[arg-type]
            lib.actor,
            content,
            review_note,
        )
        return entry.status

    return review_capture


def _give_feedback(lib: Librarian) -> Callable[..., Any]:
    def give_feedback(kind: str, body: str, note_id: str = "") -> str:
        """File feedback for review: an edit, a missing note, a request — or
        an unanswered question. Lands in the capture queue as pending; the
        librarian reviews (applied/approved/rejected) before anything touches
        the vault. Returns the queue entry id."""
        if kind not in ("edit", "missing", "request", "question"):
            raise ValueError(f"unknown kind: {kind!r}")
        return lib.give_feedback(kind, body, note_id).id  # type: ignore[arg-type]

    return give_feedback


def _as_status(status: str | None) -> Status | None:
    if status is None:
        return None
    if status not in ("pending", "applied", "approved", "rejected"):
        raise ValueError(f"unknown status: {status!r}")
    return status  # type: ignore[return-value]


_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "list_notes", "List note ids (folder prefix filter)", "vault", _list_notes
    ),
    ToolSpec("read_note", "Read a note's markdown", "vault", _read_note),
    ToolSpec(
        "search_notes", "Search notes by name and content", "vault", _search_notes
    ),
    ToolSpec("create_note", "Create a new note", "vault", _create_note),
    ToolSpec("update_note", "Replace a note's content", "vault", _update_note),
    ToolSpec("append_note", "Append markdown to a note", "vault", _append_note),
    ToolSpec(
        "patch_note",
        "Replace/append a section under a heading",
        "vault",
        _patch_note,
    ),
    ToolSpec("delete_note", "Soft-delete a note to trash", "vault", _delete_note),
    ToolSpec("move_note", "Move or rename a note", "vault", _move_note),
    ToolSpec("list_capture", "List capture queue entries", "capture", _list_capture),
    ToolSpec("review_capture", "Review a capture entry", "capture", _review_capture),
    ToolSpec(
        "give_feedback",
        "File feedback for review (returns the queue entry id)",
        "capture",
        _give_feedback,
    ),
)

TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in _TOOLS}
TOOL_NAMES: tuple[str, ...] = tuple(TOOLS)


def build_tools(
    lib: Librarian,
    enabled: dict[str, bool],
    only: list[str] | None = None,
) -> list[Callable[..., Any]]:
    """Enabled built-in tools, optionally restricted to ``only``.

    ``enabled`` maps tool name → on/off (absent name = on). Raises
    ``ValueError`` on unknown names so config typos fail loudly.
    """
    unknown = set(enabled) - set(TOOLS)
    if unknown:
        raise ValueError(f"unknown tool(s): {sorted(unknown)}")
    if only is not None:
        unknown = set(only) - set(TOOLS)
        if unknown:
            raise ValueError(f"unknown tool(s) in job: {sorted(unknown)}")
    names = only if only is not None else list(TOOL_NAMES)
    return [
        TOOLS[name].build(lib)
        for name in names
        if name in TOOLS and enabled.get(name, True)
    ]


__all__ = [
    "SCOPES",
    "TOOLS",
    "TOOL_NAMES",
    "Kind",
    "ToolSpec",
    "Verdict",
    "build_tools",
]
