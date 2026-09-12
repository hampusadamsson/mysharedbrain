"""TDD: REST API — CRUD, search, feedback, capture review, request, audit."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

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
        json={"kind": "correction", "body": "new", "note_id": "homelab"},
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


def test_invalid_id_rejected(vault_dir: Path) -> None:
    c = client(vault_dir)
    assert (
        c.post("/api/notes", json={"id": "../escape", "content": "x"}).status_code
        == 400
    )
