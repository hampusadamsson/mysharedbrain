"""MySharedBrain backend: FastAPI fronting the librarian service.

Decoupling contract: the UI (``frontend/``) and any MCP client talk to the
librarian only through HTTP JSON (this app) or MCP tools (``mcp.py``). Both
adapters delegate to :class:`Librarian` — the single audited mutation path.

Domain errors map to HTTP codes in one place (``_STATUS``); handlers stay
three lines each.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mysharedbrain import audit, capture
from mysharedbrain.service import librarian, vault_root
from mysharedbrain.vault import (
    InvalidNoteId,
    NoteExists,
    NoteNotFound,
    SectionNotFound,
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

_NOT_FOUND = (NoteNotFound, SectionNotFound, capture.EntryNotFound)
_CONFLICT = (NoteExists, capture.EntryAlreadyReviewed)


def _http_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, _NOT_FOUND):
        code = 404
    elif isinstance(exc, _CONFLICT):
        code = 409
    else:
        code = 400  # InvalidNoteId, ValueError: caller-supplied values
    return JSONResponse(status_code=code, content={"detail": str(exc)})


class NoteIn(BaseModel):
    id: str
    content: str = ""


class ContentIn(BaseModel):
    content: str = ""


class MoveIn(BaseModel):
    to: str


class FeedbackIn(BaseModel):
    kind: capture.Kind = "edit"
    body: str
    note_id: str = ""


class ReviewIn(BaseModel):
    verdict: capture.Verdict
    reviewer: str = "reviewer"
    content: str | None = None
    review_note: str = ""


class QuestionIn(BaseModel):
    question: str


class AppendIn(BaseModel):
    content: str = ""


class PatchIn(BaseModel):
    heading: str
    content: str = ""
    mode: str = "replace"


class FrontmatterIn(BaseModel):
    updates: dict[str, object]


class BatchIn(BaseModel):
    note_ids: list[str]


class NoteOut(BaseModel):
    id: str
    content: str


class NotesOut(BaseModel):
    notes: list[str]


class BatchOut(BaseModel):
    notes: list[NoteOut]
    missing: list[str]


class BrowseOut(BaseModel):
    folders: list[str]
    notes: list[str]


class LinksOut(BaseModel):
    links: list[str]


class TagsOut(BaseModel):
    notes: list[str]


class SearchHitOut(BaseModel):
    id: str
    excerpts: list[str]


class SearchOut(BaseModel):
    names: list[str]
    content: list[SearchHitOut]


class FeedbackOut(BaseModel):
    id: str
    status: str


class CaptureEntryOut(BaseModel):
    id: str
    ts: str
    kind: str
    body: str
    note_id: str
    status: str
    reviewer: str = ""
    review_note: str = ""


class CaptureListOut(BaseModel):
    entries: list[CaptureEntryOut]


class AuditEntryOut(BaseModel):
    ts: str
    actor: str
    action: str
    note_id: str
    detail: str


class AuditListOut(BaseModel):
    entries: list[AuditEntryOut]


class AskOut(BaseModel):
    found: bool
    question: str
    note_ids: list[str]
    hits: list[SearchHitOut]
    entry_id: str
    message: str


class HealthOut(BaseModel):
    status: str


def _note(note_id: str, content: str) -> dict[str, str]:
    return {"id": note_id, "content": content}


def create_app() -> FastAPI:
    app = FastAPI(
        title="MySharedBrain",
        version="0.1.0",
        description=(
            "AI-native markdown wiki vault: notes CRUD, ripgrep search, "
            "feedback capture queue, audit log and a librarian Q&A endpoint. "
            "Interactive docs here; MCP tools mirror every route."
        ),
    )
    for exc in (*_NOT_FOUND, *_CONFLICT, InvalidNoteId, ValueError):
        app.exception_handler(exc)(_http_error)

    @app.get(
        "/health",
        response_model=HealthOut,
        tags=["system"],
        summary="Health check",
    )
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/api/notes",
        response_model=NotesOut,
        tags=["notes"],
        summary="List notes (prefix filter + pagination)",
    )
    def list_notes(
        prefix: str = "", q: str = "", limit: int | None = None, offset: int = 0
    ) -> dict[str, list[str]]:
        lib = librarian()
        if q.strip():
            return {"notes": lib.vault.search_names(q)}
        return {"notes": lib.list_notes(prefix, limit, offset)}

    @app.post(
        "/api/notes/batch",
        response_model=BatchOut,
        tags=["notes"],
        summary="Read several notes at once",
    )
    def read_batch(payload: BatchIn) -> dict[str, object]:
        batch = librarian().read_notes(payload.note_ids)
        return {
            "notes": [{"id": n.id, "content": n.content} for n in batch["notes"]],
            "missing": batch["missing"],
        }

    @app.get(
        "/api/browse",
        response_model=BrowseOut,
        tags=["notes"],
        summary="Direct children of a folder",
    )
    def browse(prefix: str = "") -> dict[str, list[str]]:
        return librarian().list_directory(prefix)

    @app.patch(
        "/api/notes/{note_id:path}",
        response_model=NoteOut,
        tags=["notes"],
        summary="Replace/append a section under a heading",
    )
    def patch_note(note_id: str, payload: PatchIn) -> dict[str, str]:
        note = librarian().patch_note(
            note_id, payload.heading, payload.content, payload.mode
        )
        return _note(note.id, note.content)

    @app.post(
        "/api/notes/{note_id:path}/append",
        response_model=NoteOut,
        tags=["notes"],
        summary="Append content to a note",
    )
    def append_note(note_id: str, payload: AppendIn) -> dict[str, str]:
        note = librarian().append_note(note_id, payload.content)
        return _note(note.id, note.content)

    @app.get(
        "/api/notes/{note_id:path}/meta",
        tags=["notes"],
        summary="A note's YAML frontmatter",
    )
    def get_frontmatter(note_id: str) -> dict[str, object]:
        return librarian().get_frontmatter(note_id)

    @app.put(
        "/api/notes/{note_id:path}/meta",
        response_model=NoteOut,
        tags=["notes"],
        summary="Merge keys into frontmatter",
    )
    def set_frontmatter(note_id: str, payload: FrontmatterIn) -> dict[str, str]:
        note = librarian().set_frontmatter(note_id, payload.updates)
        return _note(note.id, note.content)

    @app.get(
        "/api/notes/{note_id:path}/outgoing",
        response_model=LinksOut,
        tags=["notes"],
        summary="[[Link]] targets of a note",
    )
    def get_outgoing(note_id: str) -> dict[str, list[str]]:
        return {"links": librarian().get_outgoing(note_id)}

    @app.get(
        "/api/notes/{note_id:path}/backlinks",
        response_model=LinksOut,
        tags=["notes"],
        summary="Notes linking to this one",
    )
    def get_backlinks(note_id: str) -> dict[str, list[str]]:
        return {"links": librarian().get_backlinks(note_id)}

    @app.get(
        "/api/tags/{tag}",
        response_model=TagsOut,
        tags=["notes"],
        summary="Notes carrying a frontmatter tag",
    )
    def search_tags(tag: str) -> dict[str, list[str]]:
        return {"notes": librarian().search_tags(tag)}

    @app.post(
        "/api/notes",
        status_code=201,
        response_model=NoteOut,
        tags=["notes"],
        summary="Create a note",
    )
    def create_note(payload: NoteIn) -> dict[str, str]:
        note = librarian().create_note(payload.id, payload.content)
        return _note(note.id, note.content)

    @app.get(
        "/api/notes/{note_id:path}",
        response_model=NoteOut,
        tags=["notes"],
        summary="Read a note by id",
    )
    def read_note(note_id: str) -> dict[str, str]:
        note = librarian().read_note(note_id)
        return _note(note.id, note.content)

    @app.put(
        "/api/notes/{note_id:path}",
        response_model=NoteOut,
        tags=["notes"],
        summary="Replace a note's content",
    )
    def update_note(note_id: str, payload: ContentIn) -> dict[str, str]:
        note = librarian().update_note(note_id, payload.content)
        return _note(note.id, note.content)

    @app.delete(
        "/api/notes/{note_id:path}",
        status_code=204,
        tags=["notes"],
        summary="Soft-delete a note (restorable from trash)",
    )
    def delete_note(note_id: str) -> None:
        librarian().delete_note(note_id)

    @app.post(
        "/api/notes/{note_id:path}/restore",
        response_model=NoteOut,
        tags=["notes"],
        summary="Restore a trashed note",
    )
    def restore_note(note_id: str) -> dict[str, str]:
        note = librarian().restore_note(note_id)
        return _note(note.id, note.content)

    @app.post(
        "/api/notes/{note_id:path}/move",
        response_model=NoteOut,
        tags=["notes"],
        summary="Move/rename a note",
    )
    def move_note(note_id: str, payload: MoveIn) -> dict[str, str]:
        note = librarian().move_note(note_id, payload.to)
        return _note(note.id, note.content)

    @app.get(
        "/api/search",
        response_model=SearchOut,
        tags=["notes"],
        summary="Search names + content (ripgrep)",
    )
    def search(q: str, limit: int = 20, offset: int = 0) -> dict[str, object]:
        result = librarian().search(q, limit, offset)
        return {
            "names": result["names"],
            "content": [
                {"id": h.id, "excerpts": h.excerpts} for h in result["content"]
            ],
        }

    @app.post(
        "/api/feedback",
        status_code=201,
        response_model=FeedbackOut,
        tags=["capture"],
        summary="Queue feedback (edit/missing/request)",
    )
    def give_feedback(payload: FeedbackIn) -> dict[str, str]:
        entry = librarian().give_feedback(payload.kind, payload.body, payload.note_id)
        return {"id": entry.id, "status": entry.status}

    @app.get(
        "/api/capture",
        response_model=CaptureListOut,
        tags=["capture"],
        summary="List queue entries (status filter)",
    )
    def list_capture(status: capture.Status | None = None) -> dict[str, object]:
        entries = capture.list_entries(vault_root(), status)
        return {"entries": [e.__dict__ for e in entries]}

    @app.post(
        "/api/capture/{entry_id}/review",
        response_model=FeedbackOut,
        tags=["capture"],
        summary="Review an entry: applied/approved/rejected",
    )
    def review_capture(entry_id: str, payload: ReviewIn) -> dict[str, str]:
        entry = librarian().process_capture(
            entry_id,
            payload.verdict,
            payload.reviewer,
            payload.content,
            payload.review_note,
        )
        return {"id": entry.id, "status": entry.status}

    @app.post(
        "/api/request",
        response_model=AskOut,
        tags=["librarian"],
        summary="Ask the librarian (misses are logged)",
    )
    def ask_question(payload: QuestionIn) -> dict[str, object]:
        answer = librarian().ask(payload.question)
        return {
            "found": answer.found,
            "question": answer.question,
            "note_ids": answer.note_ids,
            "hits": [{"id": h.id, "excerpts": h.excerpts} for h in answer.hits],
            "entry_id": answer.entry_id,
            "message": answer.message,
        }

    @app.get(
        "/api/audit",
        response_model=AuditListOut,
        tags=["librarian"],
        summary="Latest audited changes, newest first",
    )
    def read_audit(limit: int = 100) -> dict[str, object]:
        return {"entries": [e.__dict__ for e in audit.read_log(vault_root(), limit)]}

    if FRONTEND_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            # Unique page/view URLs (e.g. /p/<id>, /ask) all boot the SPA;
            # API, health, docs and static routes above take precedence.
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(str(FRONTEND_DIR / "index.html"))

    return app


app = create_app()
