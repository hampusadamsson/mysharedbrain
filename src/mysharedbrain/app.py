"""MySharedBrain backend: FastAPI fronting the librarian service.

Decoupling contract: the UI (``frontend/``) and any MCP client talk to the
librarian only through HTTP JSON (this app) or MCP tools (``mcp.py``). Both
adapters delegate to :class:`Librarian` — the single audited mutation path.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mysharedbrain import audit, capture
from mysharedbrain.service import Librarian
from mysharedbrain.vault import InvalidNoteId, NoteExists, NoteNotFound

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def vault_root() -> Path:
    return Path(os.environ.get("VAULT_DIR", "vault")).resolve()


def librarian(actor: str = "api") -> Librarian:
    return Librarian(vault_root(), actor=actor)


class NoteIn(BaseModel):
    id: str
    content: str = ""


class ContentIn(BaseModel):
    content: str = ""


class MoveIn(BaseModel):
    to: str


class FeedbackIn(BaseModel):
    kind: capture.Kind = "correction"
    body: str
    note_id: str = ""


class ReviewIn(BaseModel):
    verdict: capture.Verdict
    reviewer: str = "reviewer"
    content: str | None = None
    review_note: str = ""


class QuestionIn(BaseModel):
    question: str


def create_app() -> FastAPI:
    app = FastAPI(title="MySharedBrain", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/notes")
    def list_notes(prefix: str = "", q: str = "") -> dict[str, list[str]]:
        lib = librarian()
        if q.strip():
            return {"notes": lib.vault.search_names(q)}
        return {"notes": lib.list_notes(prefix)}

    @app.post("/api/notes", status_code=201)
    def create_note(payload: NoteIn) -> dict[str, str]:
        try:
            note = librarian().create_note(payload.id, payload.content)
        except NoteExists as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidNoteId as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": note.id, "content": note.content}

    @app.get("/api/notes/{note_id:path}")
    def read_note(note_id: str) -> dict[str, str]:
        try:
            note = librarian().read_note(note_id)
        except (NoteNotFound, InvalidNoteId) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"id": note.id, "content": note.content}

    @app.put("/api/notes/{note_id:path}")
    def update_note(note_id: str, payload: ContentIn) -> dict[str, str]:
        try:
            note = librarian().update_note(note_id, payload.content)
        except NoteNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidNoteId as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": note.id, "content": note.content}

    @app.delete("/api/notes/{note_id:path}", status_code=204)
    def delete_note(note_id: str) -> None:
        try:
            librarian().delete_note(note_id)
        except (NoteNotFound, InvalidNoteId) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/notes/{note_id:path}/move")
    def move_note(note_id: str, payload: MoveIn) -> dict[str, str]:
        try:
            note = librarian().move_note(note_id, payload.to)
        except NoteNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (NoteExists, InvalidNoteId) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": note.id, "content": note.content}

    @app.get("/api/search")
    def search(q: str, limit: int = 20) -> dict[str, object]:
        result = librarian().search(q, limit)
        return {
            "names": result["names"],
            "content": [
                {"id": h.id, "excerpts": h.excerpts} for h in result["content"]
            ],
        }

    @app.post("/api/feedback", status_code=201)
    def give_feedback(payload: FeedbackIn) -> dict[str, str]:
        try:
            entry = librarian().give_feedback(
                payload.kind, payload.body, payload.note_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": entry.id, "status": entry.status}

    @app.get("/api/capture")
    def list_capture(status: capture.Status | None = None) -> dict[str, object]:
        entries = capture.list_entries(vault_root(), status)
        return {"entries": [e.__dict__ for e in entries]}

    @app.post("/api/capture/{entry_id}/review")
    def review_capture(entry_id: str, payload: ReviewIn) -> dict[str, str]:
        try:
            entry = librarian().process_capture(
                entry_id,
                payload.verdict,
                payload.reviewer,
                payload.content,
                payload.review_note,
            )
        except capture.EntryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (capture.EntryAlreadyReviewed, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": entry.id, "status": entry.status}

    @app.post("/api/request")
    def ask_question(payload: QuestionIn) -> dict[str, object]:
        try:
            answer = librarian().ask(payload.question)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "found": answer.found,
            "question": answer.question,
            "note_ids": answer.note_ids,
            "hits": [{"id": h.id, "excerpts": h.excerpts} for h in answer.hits],
            "entry_id": answer.entry_id,
            "message": answer.message,
        }

    @app.get("/api/audit")
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
