"""TDD: MCP tools — full CRUD + search + feedback + question over stdio-free client."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from mysharedbrain.mcp import mcp


async def call(tool: str, args: dict[str, object]) -> dict[str, object]:
    from fastmcp import Client

    async with Client(mcp) as client:
        result = await client.call_tool(tool, args)
    assert isinstance(result.data, dict)
    return cast("dict[str, object]", result.data)


async def test_mcp_crud_and_search(vault_dir: Path) -> None:
    assert await call("create_note", {"note_id": "todo", "content": "milk"}) == {
        "ok": "true",
        "id": "todo",
    }
    assert (await call("create_note", {"note_id": "todo"}))["ok"] == "false"
    assert await call("read_note", {"note_id": "todo"}) == {
        "ok": "true",
        "id": "todo",
        "content": "milk",
    }
    assert await call("update_note", {"note_id": "todo", "content": "oat"}) == {
        "ok": "true",
        "id": "todo",
    }
    assert (await call("read_note", {"note_id": "missing"}))["ok"] == "false"
    search = await call("search_notes", {"query": "oat"})
    assert search["names"] == []  # name search matches ids only
    assert [h["id"] for h in search["content"]] == ["todo"]  # type: ignore[union-attr]
    assert (await call("move_note", {"note_id": "todo", "new_id": "shopping"}))[
        "id"
    ] == "shopping"
    assert await call("delete_note", {"note_id": "shopping"}) == {
        "ok": "true",
        "id": "shopping",
    }


async def test_mcp_feedback_and_question(vault_dir: Path) -> None:
    await call("create_note", {"note_id": "homelab", "content": "k3s on elitedesk"})
    fb = await call(
        "give_feedback", {"kind": "correction", "body": "new ip", "note_id": "homelab"}
    )
    assert fb == {"ok": "true", "id": fb["id"], "status": "pending"}
    bad = await call("give_feedback", {"kind": "bogus", "body": "x"})
    assert bad["ok"] == "false"
    found = await call("ask_question", {"question": "elitedesk"})
    assert found["found"] is True
    missing = await call("ask_question", {"question": "absent topic xyz"})
    assert missing["found"] is False
    assert missing["entry_id"]
