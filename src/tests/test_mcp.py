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
        "ok": True,
        "id": "todo",
    }
    assert (await call("create_note", {"note_id": "todo"}))["ok"] is False
    assert await call("read_note", {"note_id": "todo"}) == {
        "ok": True,
        "id": "todo",
        "content": "milk",
    }
    assert await call("update_note", {"note_id": "todo", "content": "oat"}) == {
        "ok": True,
        "id": "todo",
    }
    assert (await call("read_note", {"note_id": "missing"}))["ok"] is False
    search = await call("search_notes", {"query": "oat"})
    assert search["names"] == []  # name search matches ids only
    assert [h["id"] for h in search["content"]] == ["todo"]  # type: ignore[union-attr]
    assert (await call("move_note", {"note_id": "todo", "new_id": "shopping"}))[
        "id"
    ] == "shopping"
    assert await call("delete_note", {"note_id": "shopping"}) == {
        "ok": True,
        "id": "shopping",
    }
    assert (await call("read_note", {"note_id": "shopping"}))["ok"] is False
    assert await call("restore_note", {"note_id": "shopping"}) == {
        "ok": True,
        "id": "shopping",
    }
    assert (await call("read_note", {"note_id": "shopping"}))["ok"] is True


async def test_mcp_feedback_and_question(vault_dir: Path) -> None:
    await call("create_note", {"note_id": "homelab", "content": "k3s on elitedesk"})
    fb = await call(
        "give_feedback", {"kind": "edit", "body": "new ip", "note_id": "homelab"}
    )
    assert fb == {"ok": True, "id": fb["id"], "status": "pending"}
    bad = await call("give_feedback", {"kind": "bogus", "body": "x"})
    assert bad["ok"] is False
    rev = await call(
        "review_capture",
        {"entry_id": fb["id"], "verdict": "approved", "reviewer": "curator"},
    )
    assert rev == {"ok": True, "id": fb["id"], "status": "approved"}
    dup = await call("review_capture", {"entry_id": fb["id"], "verdict": "rejected"})
    assert dup["ok"] is False
    listed = await call("list_capture", {"status": "approved"})
    found_ids = [e["id"] for e in cast("list[dict[str, str]]", listed["entries"])]
    assert fb["id"] in found_ids
    assert "error" in await call("list_capture", {"status": "bogus"})
    found = await call("ask_question", {"question": "elitedesk"})
    assert found["found"] is True
    missing = await call("ask_question", {"question": "absent topic xyz"})
    assert missing["found"] is False
    assert missing["entry_id"]


async def test_mcp_obsidian_parity_tools(vault_dir: Path) -> None:
    await call(
        "create_note",
        {"note_id": "doc", "content": "## A\nold\n\n## Links\nSee [[other]]."},
    )
    await call("create_note", {"note_id": "other", "content": "o"})
    assert await call("append_note", {"note_id": "doc", "content": "tail"}) == {
        "ok": True,
        "id": "doc",
    }
    assert (await call("append_note", {"note_id": "gone", "content": "x"}))[
        "ok"
    ] is False
    assert await call(
        "patch_note", {"note_id": "doc", "heading": "A", "content": "new"}
    ) == {
        "ok": True,
        "id": "doc",
    }
    no_section = await call(
        "patch_note", {"note_id": "doc", "heading": "Nope", "content": "x"}
    )
    assert no_section["ok"] is False
    assert await call("list_notes", {"limit": 1}) == {"ok": True, "notes": ["doc"]}
    batch = await call("read_notes", {"note_ids": ["doc", "gone"]})
    found = cast("list[dict[str, str]]", batch["notes"])
    assert [n["id"] for n in found] == ["doc"]
    assert batch["missing"] == ["gone"]
    assert await call("list_directory", {}) == {
        "ok": True,
        "folders": [],
        "notes": ["doc", "other"],
    }
    updated = await call(
        "set_frontmatter", {"note_id": "doc", "updates": {"tags": ["t1"]}}
    )
    assert updated == {"ok": True, "id": "doc"}
    assert await call("get_frontmatter", {"note_id": "doc"}) == {
        "ok": True,
        "tags": ["t1"],
    }
    assert await call("search_by_tag", {"tag": "T1"}) == {"ok": True, "notes": ["doc"]}
    assert await call("get_backlinks", {"note_id": "other"}) == {
        "ok": True,
        "backlinks": ["doc"],
    }
    assert await call("get_outgoing", {"note_id": "doc"}) == {
        "ok": True,
        "links": ["other"],
    }
    changes = await call("recent_changes", {"limit": 5})
    assert len(cast("list[object]", changes["changes"])) > 0


async def test_mcp_resources_and_prompts(vault_dir: Path) -> None:
    from fastmcp import Client

    await call("create_note", {"note_id": "doc", "content": "hello"})
    async with Client(mcp) as client:
        res = await client.read_resource("vault://doc")
        assert getattr(res[0], "text", "") == "hello"
        idx = await client.read_resource("vault://index")
        assert "doc" in str(getattr(idx[0], "text", ""))
        prompt = await client.get_prompt("ask_librarian", {"question": "what?"})
        assert "what?" in str(getattr(prompt.messages[0].content, "text", ""))
        feedback = await client.get_prompt(
            "file_feedback", {"kind": "edit", "body": "b", "note_id": "doc"}
        )
        assert "give_feedback" in str(getattr(feedback.messages[0].content, "text", ""))
