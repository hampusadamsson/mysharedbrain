"""TDD: REST API — CRUD, search, feedback, capture review, request, audit."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from mysharedbrain import app as app_module
from mysharedbrain.app import create_app


def client(vault_dir: Path) -> TestClient:
    return TestClient(create_app())


def _leaf_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Expand ``include_router`` placeholders (FastAPI >=0.140)."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _leaf_routes(original.routes)
        else:
            yield route


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


def test_delete_trashes_and_restore_endpoint(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "gone", "content": "data"})
    assert c.delete("/api/notes/gone").status_code == 204
    assert c.get("/api/notes/gone").status_code == 404
    assert c.get("/api/notes").json() == {"notes": []}
    restored = c.post("/api/notes/gone/restore").json()
    assert restored == {"id": "gone", "content": "data"}
    assert c.post("/api/notes/gone/restore").status_code == 404
    assert c.post("/api/notes/never/restore").status_code == 404


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
        == 409
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


def test_request_runs_one_ask_run(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``POST /api/request`` delegates to the ask loop (no model in tests)."""
    from mysharedbrain.ask import AskAnswer

    async def fake(
        cfg: object, lib: object, question: str, model: object = None
    ) -> AskAnswer:
        return AskAnswer(
            found=True,
            question=question,
            note_ids=["homelab"],
            hits=[],
            entry_id="",
            message="homelab runs k3s.",
        )

    monkeypatch.setattr(app_module, "run_ask", fake)
    c = client(vault_dir)
    found = c.post("/api/request", json={"question": "k3s"}).json()
    assert found["found"] is True
    assert found["note_ids"] == ["homelab"]
    assert found["message"] == "homelab runs k3s."


def test_request_reports_a_timeout_as_504(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run cut short by ask.timeout_seconds must not look like a bad request."""
    from mysharedbrain.ask import AskTimeout

    async def fake(*args: object, **kwargs: object) -> None:
        raise AskTimeout("the librarian did not finish within 60s")

    monkeypatch.setattr(app_module, "run_ask", fake)
    c = client(vault_dir)
    res = c.post("/api/request", json={"question": "k3s"})
    assert res.status_code == 504
    assert "did not finish within 60s" in res.json()["detail"]


def test_request_refuses_when_ask_is_disabled(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mysharedbrain.config import AskConfig, BrainConfigDocument

    def _disabled() -> BrainConfigDocument:
        return BrainConfigDocument(ask=AskConfig(enabled=False))

    monkeypatch.setattr(app_module, "load_config", _disabled)
    c = client(vault_dir)
    res = c.post("/api/request", json={"question": "k3s"})
    assert res.status_code == 404
    assert res.json()["detail"] == "ask the librarian is disabled"


def test_feedback_accepts_question_kind_and_automated_flag(vault_dir: Path) -> None:
    c = client(vault_dir)
    created = c.post(
        "/api/feedback",
        json={"kind": "question", "body": "what is argo?", "automated": True},
    ).json()
    entry = c.get("/api/capture").json()["entries"][0]
    assert entry["id"] == created["id"]
    assert (entry["kind"], entry["automated"]) == ("question", True)


def test_plain_feedback_is_not_automated(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/feedback", json={"kind": "edit", "body": "fix ip"})
    entry = c.get("/api/capture").json()["entries"][0]
    assert (entry["kind"], entry["automated"]) == ("edit", False)


def test_capture_status_can_be_set_regardless_of_current_state(vault_dir: Path) -> None:
    c = client(vault_dir)
    entry_id = c.post("/api/feedback", json={"kind": "edit", "body": "fix ip"}).json()[
        "id"
    ]
    # resolve it, then override it twice — including back to pending
    c.post(f"/api/capture/{entry_id}/review", json={"verdict": "rejected"})
    for wanted in ("applied", "pending", "approved"):
        res = c.put(
            f"/api/capture/{entry_id}/status",
            json={"status": wanted, "reviewer": "curator", "review_note": "override"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == wanted
        assert c.get("/api/capture", params={"status": wanted}).json()["total"] == 1
    # and it left an auditable trail: one entry per override, marked as such
    audit = c.get("/api/audit").json()["entries"]
    assert sorted(e["action"] for e in audit) == [
        "capture-applied",
        "capture-approved",
        "capture-pending",
        "capture-rejected",  # the original review
        "feedback",
    ]
    restates = [e for e in audit if e["detail"].startswith("restate:")]
    assert {e["action"] for e in restates} == {
        "capture-applied",
        "capture-pending",
        "capture-approved",
    }
    assert {e["actor"] for e in restates} == {"curator"}


def test_capture_status_rejects_unknown_status_and_entry(vault_dir: Path) -> None:
    c = client(vault_dir)
    entry_id = c.post("/api/feedback", json={"kind": "edit", "body": "x"}).json()["id"]
    assert (
        c.put(f"/api/capture/{entry_id}/status", json={"status": "done"}).status_code
        == 422
    )
    assert (
        c.put("/api/capture/nope/status", json={"status": "pending"}).status_code == 404
    )


def test_audit_records_mutations(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "a", "content": "1"})
    body = c.get("/api/audit").json()
    assert body["entries"][0]["action"] == "create"
    assert body["entries"][0]["note_id"] == "a"
    assert body["total"] == 1


def test_capture_endpoint_paginates(vault_dir: Path) -> None:
    c = client(vault_dir)
    for i in range(5):
        c.post("/api/feedback", json={"kind": "request", "body": f"q{i}"})

    first = c.get("/api/capture", params={"limit": 2}).json()
    assert len(first["entries"]) == 2
    assert (first["total"], first["limit"], first["offset"]) == (5, 2, 0)
    second = c.get("/api/capture", params={"limit": 2, "offset": 2}).json()
    assert [e["body"] for e in second["entries"]] == ["q2", "q3"]
    past_end = c.get("/api/capture", params={"limit": 2, "offset": 99}).json()
    assert past_end["entries"] == []
    assert past_end["total"] == 5


def test_capture_total_respects_status_filter(vault_dir: Path) -> None:
    c = client(vault_dir)
    entry_id = c.post("/api/feedback", json={"kind": "request", "body": "q"}).json()[
        "id"
    ]
    c.post(f"/api/capture/{entry_id}/review", json={"verdict": "rejected"})
    assert c.get("/api/capture", params={"status": "pending"}).json()["total"] == 0
    assert c.get("/api/capture", params={"status": "rejected"}).json()["total"] == 1


def test_audit_endpoint_paginates(vault_dir: Path) -> None:
    c = client(vault_dir)
    for i in range(4):
        c.post("/api/notes", json={"id": f"n{i}", "content": "x"})
    body = c.get("/api/audit", params={"limit": 2}).json()
    assert len(body["entries"]) == 2
    assert body["total"] == 4
    page2 = c.get("/api/audit", params={"limit": 2, "offset": 2}).json()
    assert len(page2["entries"]) == 2
    assert {e["note_id"] for e in body["entries"]} & {
        e["note_id"] for e in page2["entries"]
    } == set()
    assert (
        c.get("/api/audit", params={"limit": 2, "offset": 99}).json()["entries"] == []
    )


def test_pagination_params_are_bounded(vault_dir: Path) -> None:
    c = client(vault_dir)
    assert c.get("/api/audit", params={"limit": 0}).status_code == 422
    assert c.get("/api/audit", params={"limit": 500}).status_code == 422
    assert c.get("/api/audit", params={"offset": -1}).status_code == 422
    assert c.get("/api/capture", params={"limit": 0}).status_code == 422


def test_file_history_records_reads_and_edits(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "projects/homelab", "content": "k3s"})
    c.get("/api/notes/projects/homelab")
    c.get("/api/notes/projects/homelab")
    c.put("/api/notes/projects/homelab", json={"content": "k3s + caddy"})
    # a second file must not leak into the first file's log
    c.post("/api/notes", json={"id": "other", "content": "x"})

    body = c.get("/api/notes/projects/homelab/history").json()
    assert [e["action"] for e in body["entries"]] == [
        "update",
        "read",
        "read",
        "create",
    ]
    assert {e["note_id"] for e in body["entries"]} == {"projects/homelab"}
    assert body["total"] == 4
    assert body["stats"]["note_id"] == "projects/homelab"
    assert body["stats"]["counts"] == {"read": 2, "write": 2}
    assert body["stats"]["total"] == 4
    assert body["stats"]["first_seen"] <= body["stats"]["last_seen"]


def test_file_history_filters_by_kind(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "a", "content": "findable keyword"})
    c.get("/api/notes/a")
    c.get("/api/search", params={"q": "findable"})

    reads = c.get("/api/notes/a/history", params={"kind": "read"}).json()
    assert [e["action"] for e in reads["entries"]] == ["read"]
    finds = c.get("/api/notes/a/history", params={"kind": "find"}).json()
    assert [e["action"] for e in finds["entries"]] == ["find"]
    assert finds["entries"][0]["detail"] == "query:findable"
    # the counter stays whole even while a filter is applied
    assert finds["stats"]["counts"]["read"] == 1
    assert finds["total"] == 1


def test_file_history_rejects_unknown_kind(vault_dir: Path) -> None:
    res = client(vault_dir).get("/api/notes/a/history", params={"kind": "nope"})
    assert res.status_code == 400
    assert "unknown kind" in res.json()["detail"]


def test_audit_endpoint_returns_scope_stats(vault_dir: Path) -> None:
    """Activity and the file log share one stats shape, so one UI component fits."""
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "a", "content": "x"})
    c.post("/api/notes", json={"id": "b", "content": "y"})
    c.get("/api/notes/a")

    whole = c.get("/api/audit").json()["stats"]
    assert whole["note_id"] == ""
    assert whole["counts"] == {"write": 2, "read": 1}
    assert whole["total"] == 3
    # a kind filter narrows the entries, never the counters
    filtered = c.get("/api/audit", params={"kind": "read"}).json()
    assert filtered["total"] == 1
    assert filtered["stats"] == whole

    one_file = c.get("/api/notes/a/history").json()["stats"]
    assert one_file["note_id"] == "a"
    assert one_file["counts"] == {"write": 1, "read": 1}


def test_audit_endpoint_filters_by_kind(vault_dir: Path) -> None:
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "a", "content": "x"})
    c.get("/api/notes/a")
    reads = c.get("/api/audit", params={"kind": "read"}).json()
    assert reads["total"] == 1
    assert [e["kind"] for e in reads["entries"]] == ["read"]
    assert c.get("/api/audit", params={"kind": "write"}).json()["total"] == 1


def test_reads_are_not_logged_for_the_pages_listing(vault_dir: Path) -> None:
    """Listing and browsing are not per-file interactions."""
    c = client(vault_dir)
    c.post("/api/notes", json={"id": "a", "content": "x"})
    c.get("/api/notes")
    c.get("/api/browse")
    assert c.get("/api/notes/a/history").json()["total"] == 1  # only the create


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
    for r in _leaf_routes(create_app().routes):
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


def test_spa_fallback_serves_index_for_page_and_view_urls(
    vault_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a built UI present: real files win, SPA routes boot index.html,
    unknown API paths stay JSON 404s."""
    static = tmp_path / "static"
    (static / "_app" / "immutable").mkdir(parents=True)
    (static / "index.html").write_text("<title>MySharedBrain</title>", encoding="utf-8")
    (static / "_app" / "immutable" / "app.js").write_text(
        "console.log(1)", encoding="utf-8"
    )
    (static / "robots.txt").write_text("User-agent: *", encoding="utf-8")
    monkeypatch.setattr(app_module, "STATIC_DIR", static)
    c = client(vault_dir)

    for path in ("/p/projects/homelab", "/ask", "/capture", "/activity", "/search"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert "MySharedBrain" in r.text

    assert c.get("/robots.txt").status_code == 200
    assert c.get("/_app/immutable/app.js").status_code == 200
    assert c.get("/api/no-such-endpoint").status_code == 404


def test_api_only_without_built_ui(
    vault_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No static dir (local dev): API works, SPA routes are 404."""
    monkeypatch.setattr(app_module, "STATIC_DIR", tmp_path / "missing")
    c = client(vault_dir)
    assert c.get("/health").status_code == 200
    assert c.get("/api/notes").status_code == 200
    assert c.get("/p/some/page").status_code == 404


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
