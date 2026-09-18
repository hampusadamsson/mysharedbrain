"""Tool behaviour the agent depends on.

Two production job failures drove these: a run died with
``NoteNotFound: 'admin/test123.md'`` (the agent wrote the id the way the file is
named) and another with ``SectionNotFound: no heading '# title 1'`` (it passed
the heading with its hashes). Bad arguments are normal — an agent cannot know a
vault by heart — so a tool must answer with something it can act on and let the
run continue, not abort the job.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ModelResponsePart,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from mysharedbrain.agent import run_agent
from mysharedbrain.config import BrainConfigDocument
from mysharedbrain.service import Librarian
from mysharedbrain.tools import TOOLS, build_tools


def _lib(root: Path) -> Librarian:
    return Librarian(root, actor="test")


def _tools(root: Path, only: Sequence[str] | None = None) -> dict[str, object]:
    built = build_tools(_lib(root), {}, list(only) if only else None)
    return {fn.__name__: fn for fn in built}


def _scripted(
    calls: Sequence[tuple[str, dict[str, object]]], reply: str
) -> FunctionModel:
    """Make ``calls`` in order, then answer — TestModel invents unusable args."""
    state = {"n": 0}

    def _run(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        n = state["n"]
        state["n"] += 1
        part: ModelResponsePart
        if n < len(calls):
            name, args = calls[n]
            part = ToolCallPart(tool_name=name, args=args)
        else:
            part = TextPart(content=reply)
        return ModelResponse(parts=[part])

    return FunctionModel(_run)


def test_every_tool_is_wrapped_for_retry(vault_dir: Path) -> None:
    """A bad argument asks the agent to retry; it never aborts the run."""
    tools = _tools(vault_dir, ["read_note", "patch_note"])

    with pytest.raises(ModelRetry):
        tools["read_note"](note_id="missing")  # type: ignore[operator]

    with pytest.raises(ModelRetry):
        tools["patch_note"](note_id="missing", heading="x", content="y")  # type: ignore[operator]


def test_retry_message_carries_the_reason(vault_dir: Path) -> None:
    tools = _tools(vault_dir, ["patch_note"])
    (vault_dir / "doc.md").write_text("## Setup\nold\n", encoding="utf-8")

    with pytest.raises(ModelRetry) as exc:
        tools["patch_note"](note_id="doc", heading="Nope", content="x")  # type: ignore[operator]

    assert "Nope" in str(exc.value)
    assert "doc" in str(exc.value)


def test_unknown_verdict_and_kind_are_retryable(vault_dir: Path) -> None:
    tools = _tools(vault_dir, ["review_capture", "give_feedback"])

    with pytest.raises(ModelRetry):
        tools["give_feedback"](kind="nonsense", body="x")  # type: ignore[operator]
    with pytest.raises(ModelRetry):
        tools["review_capture"](entry_id="nope", verdict="maybe")  # type: ignore[operator]


def test_both_shipped_failures_now_succeed(vault_dir: Path) -> None:
    """The exact arguments from the failing runs."""
    tools = _tools(vault_dir, ["create_note", "read_note", "update_note", "patch_note"])
    tools["create_note"](note_id="admin/test123", content="# title 1\nold\n")  # type: ignore[operator]

    # 'admin/test123.md' (file spelling) and 'patch_note' with a hashed heading
    content = tools["read_note"](note_id="admin/test123.md")  # type: ignore[operator]
    assert content == "# title 1\nold\n"
    tools["patch_note"](note_id="admin/test123.md", heading="# title 1", content="new")  # type: ignore[operator]
    assert tools["read_note"](note_id="admin/test123") == "# title 1\nnew\n"  # type: ignore[operator]


async def test_a_bad_tool_call_does_not_fail_the_run(vault_dir: Path) -> None:
    """A whole run survives a wrong id and answers on the retry."""
    lib = _lib(vault_dir)
    lib.create_note("real", "the answer is 42")
    cfg = BrainConfigDocument()
    model = _scripted(
        [
            ("read_note", {"note_id": "ghost"}),  # wrong id
            ("read_note", {"note_id": "real"}),  # corrected
        ],
        reply="42",
    )

    outcome = await run_agent(cfg, lib, "what is the answer?", cfg.ask, model)

    assert outcome.output.strip() == "42"
    parts = [part for message in outcome.messages for part in message.parts]
    # the failure came back to the model as a retry prompt, not as a crash
    retries = [p for p in parts if p.part_kind == "retry-prompt"]
    assert len(retries) == 1
    assert "ghost" in str(retries[0].content)
    # and the corrected call did reach the vault
    returns = [p for p in parts if p.part_kind == "tool-return"]
    assert any("42" in str(p.content) for p in returns)


def test_tool_registry_and_builder_agree() -> None:
    assert set(TOOLS) == {
        "list_notes",
        "read_note",
        "search_notes",
        "create_note",
        "update_note",
        "append_note",
        "patch_note",
        "delete_note",
        "move_note",
        "list_capture",
        "review_capture",
        "give_feedback",
    }
