"""TDD: REST API — CRUD, search, feedback, capture review, request, audit."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.routing import Route

from mysharedbrain.app import create_app


def client(vault_dir: Path) -> TestClient:
    return TestClient(create_app())


def test_health(vault_dir: Path) -> None:
    assert client(vault_dir).get("/health").json() == {"status": "ok"}


def test_notes_crud_roundtrip(vault_dir: Path) -> None:
    c = client(vault_dir)
    assert (
        c.post("/api/notes", json={"id": "todo", "content": "# Todo"}).status_code
        == 201
    )
    assert c.post("/api/notes", json={"id": "todo", "content": "x"}).status_code == 409
    assert c.get("/api/notes/todo").json()["content"] == "# Todo"
    assert (
        c.put("/api/notes/todo", json={"content": "done"}).json()["content"] == "done"
    )
    assert c.get("/api/notes").json() == {"notes": ["todo"]}
    assert c.delete("/api/notes/todo").status_code == 204
    assert c.get("/api/notes/todo").status_code == 404


def test_notes_move_and_search(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "old", "content": "elitedesk ip"})
    assert (
        c.post("/api/notes/old/move", json={"to": "infra/host"}).json()["id"]
        == "infra/host"
    )
    assert c.get("/api/notes/old").status_code == 404
    body = c.get("/api/search", params={"q": "elitedesk"}).json()
    assert body["names"] == []  # name search matches ids only
    assert [h["id"] for h in body["content"]] == ["infra/host"]
    assert c.get("/api/notes", params={"q": "infra"}).json() == {
        "notes": ["infra/host"]
    }


def test_feedback_capture_review_flow(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "homelab", "content": "old"})
    entry_id = c.post(
        "/api/feedback",
        json={"kind": "edit", "body": "new", "note_id": "homelab"},
    ).json()["id"]
    assert c.get("/api/capture").json()["entries"][0]["status"] == "pending"
    reviewed = c.post(
        f"/api/capture/{entry_id}/review",
        json={"verdict": "applied", "reviewer": "curator", "content": "new"},
    ).json()
    assert reviewed["status"] == "applied"
    assert c.get("/api/notes/homelab").json()["content"] == "new"
    assert (
        c.post(
            f"/api/capture/{entry_id}/review", json={"verdict": "rejected"}
        ).status_code
        == 400
    )
    assert (
        c.post("/api/capture/nope/review", json={"verdict": "rejected"}).status_code
        == 404
    )


def test_capture_approve_flow(vault_dir: Path) -> None:
    c = client(vault_dir)
    entry_id = c.post(
        "/api/feedback", json={"kind": "request", "body": "need x"}
    ).json()["id"]
    reviewed = c.post(
        f"/api/capture/{entry_id}/review",
        json={"verdict": "approved", "reviewer": "curator"},
    ).json()
    assert reviewed["status"] == "approved"
    entries = c.get("/api/capture", params={"status": "approved"}).json()["entries"]
    assert [e["id"] for e in entries] == [entry_id]


def test_request_found_and_missing(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "homelab", "content": "k3s"})
    found = c.post("/api/request", json={"question": "k3s"}).json()
    assert found["found"] is True
    assert "homelab" in found["note_ids"]
    missing = c.post(
        "/api/request", json={"question": "totally absent topic xyz"}
    ).json()
    assert missing["found"] is False
    assert missing["entry_id"]
    assert c.get("/api/capture", params={"status": "pending"}).json()["entries"]


def test_audit_records_mutations(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "a", "content": "1"})
    entries = c.get("/api/audit").json()["entries"]
    assert entries[0]["action"] == "create"
    assert entries[0]["note_id"] == "a"


def test_openapi_docs_cover_every_api_route(vault_dir: Path) -> None:
    c = client(vault_dir)
    assert c.get("/docs").status_code == 200
    assert c.get("/redoc").status_code == 200
    spec = c.get("/openapi.json").json()
    assert spec["info"]["title"] == "MySharedBrain"
    documented = {
        (method, path)
        for path, ops in spec["paths"].items()
        if path.startswith("/api")
        for method in ops
    }
    routes: set[tuple[str, str]] = set()
    for r in create_app().routes:
        # OpenAPI normalizes Starlette's {param:path} converters to {param}.
        if isinstance(r, Route) and r.methods and r.path.startswith("/api"):
            path = re.sub(r":path(?=})", "", r.path)
            routes.update((m.lower(), path) for m in sorted(r.methods))
    assert documented == routes
    for path, ops in spec["paths"].items():
        if path.startswith("/api"):
            for method, op in ops.items():
                assert op.get("summary"), f"{method} {path} lacks a summary"
                assert op.get("tags"), f"{method} {path} lacks tags"


def test_spa_fallback_serves_index_for_page_and_view_urls(vault_dir: Path) -> None:
    c = client(vault_dir)
    for path in ("/p/projects/homelab", "/ask", "/capture", "/activity"):
        r = c.get(path)
        assert r.status_code == 200
        assert "MySharedBrain" in r.text
    assert c.get("/api/no-such-endpoint").status_code == 404


def test_invalid_id_rejected(vault_dir: Path) -> None:
    c = client(vault_dir)
    assert (
        c.post("/api/notes", json={"id": "../escape", "content": "x"}).status_code
        == 400
    )


def test_append_patch_frontmatter_links_endpoints(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post(
        "/api/notes",
        json={"id": "doc", "content": "## A\nold\n\n## Links\nSee [[other]]."},
    )
    c.post("/api/notes", json={"id": "other", "content": "o"})
    appended = c.post("/api/notes/doc/append", json={"content": "tail"}).json()
    assert appended["content"].endswith("tail")
    assert c.post("/api/notes/missing/append", json={"content": "x"}).status_code == 404
    patched = c.patch("/api/notes/doc", json={"heading": "A", "content": "new"}).json()
    assert "new" in patched["content"] and "old" not in patched["content"]
    assert (
        c.patch("/api/notes/doc", json={"heading": "Nope", "content": "x"}).status_code
        == 404
    )
    bad = c.patch(
        "/api/notes/doc", json={"heading": "A", "content": "x", "mode": "bogus"}
    )
    assert bad.status_code == 400
    updated = c.put("/api/notes/doc/meta", json={"updates": {"tags": ["t1"]}}).json()
    assert updated["id"] == "doc"
    assert c.get("/api/notes/doc/meta").json() == {"tags": ["t1"]}
    assert c.get("/api/tags/t1").json() == {"notes": ["doc"]}
    assert c.get("/api/notes/doc/outgoing").json() == {"links": ["other"]}
    assert c.get("/api/notes/other/backlinks").json() == {"links": ["doc"]}
    assert c.get("/api/browse").json() == {"folders": [], "notes": ["doc", "other"]}
    batch = c.post("/api/notes/batch", json={"note_ids": ["doc", "gone"]}).json()
    assert [n["id"] for n in batch["notes"]] == ["doc"]
    assert batch["missing"] == ["gone"]
    assert c.get("/api/notes", params={"limit": 1}).json() == {"notes": ["doc"]}
