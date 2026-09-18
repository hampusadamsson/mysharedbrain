"""TDD: ask the librarian — an agent run scoped by the ask config.

Asking goes through the librarian agent (same model/tools plumbing as jobs),
not the token-search shortcut: the run answers from the vault and files
capture entries itself when something is missing. The whole function is
gated by ``ask.enabled``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ModelResponsePart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from mysharedbrain.ask import AskAnswer, evidence, run_ask
from mysharedbrain.config import AskConfig, BrainConfig, BrainConfigDocument
from mysharedbrain.service import Librarian


def _lib(root: Path) -> Librarian:
    return Librarian(root, actor="test")


def _cfg(**ask: object) -> BrainConfigDocument:
    return BrainConfigDocument(ask=AskConfig(**ask))  # type: ignore[arg-type]


def _scripted_model(
    calls: Sequence[tuple[str, dict[str, object]]], reply: str
) -> FunctionModel:
    """A model that makes ``calls`` (tool name + args) in order, then answers.

    ``TestModel`` invents its own tool args, which cannot satisfy domain
    shapes like a feedback kind — so tests that need a tool call script it.
    """
    state = {"n": 0}

    def _run(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        n = state["n"]
        state["n"] += 1
        if n < len(calls):
            name, args = calls[n]
            part: ModelResponsePart = ToolCallPart(tool_name=name, args=args)
        else:
            part = TextPart(content=reply)
        return ModelResponse(parts=[part])

    return FunctionModel(_run)


def test_ask_defaults_to_enabled_with_no_restrictions() -> None:
    ask = BrainConfigDocument().ask
    assert ask.enabled is True
    assert ask.tools is None
    assert ask.mcp_servers is None
    assert ask.max_steps is None
    assert ask.instructions_file is None


def test_ask_can_be_disabled_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRAIN__ASK__ENABLED", "false")
    assert BrainConfig().ask.enabled is False


def test_ask_rejects_an_unknown_mcp_server() -> None:
    with pytest.raises(ValueError, match="unknown mcp server"):
        _cfg(mcp_servers=["ghost"])


async def test_run_ask_rejects_an_empty_question(vault_dir: Path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        await run_ask(_cfg(), _lib(vault_dir), "  ")


async def test_run_ask_refuses_when_disabled(vault_dir: Path) -> None:
    with pytest.raises(ValueError, match="disabled"):
        await run_ask(_cfg(enabled=False), _lib(vault_dir), "anything?")


async def test_run_ask_answers_without_filing_capture(vault_dir: Path) -> None:
    lib = _lib(vault_dir)
    lib.create_note("homelab", "k3s runs on elitedesk")
    model = TestModel(call_tools=[], custom_output_text="elitedesk runs k3s.")
    answer = await run_ask(_cfg(), lib, "what runs on elitedesk?", model=model)
    assert isinstance(answer, AskAnswer)
    assert answer.found is True
    assert answer.entry_id == ""
    assert answer.message == "elitedesk runs k3s."
    assert lib.capture.list_entries() == []


async def test_run_ask_files_capture_when_the_agent_cannot_answer(
    vault_dir: Path,
) -> None:
    lib = _lib(vault_dir)
    model = _scripted_model(
        [("give_feedback", {"kind": "question", "body": "Unanswered: xyz"})],
        "I filed it for review.",
    )
    answer = await run_ask(_cfg(), lib, "obscure topic nobody wrote down", model=model)
    assert answer.found is False
    assert answer.entry_id
    pending = lib.capture.list_entries("pending")
    assert [e.id for e in pending] == [answer.entry_id]


async def test_run_ask_reads_the_instructions_note(vault_dir: Path) -> None:
    """The ask instructions note scopes the run, like a job's note does."""
    lib = _lib(vault_dir)
    lib.create_note("ask-policy", "Always answer in one sentence.")
    model = _scripted_model([("read_note", {"note_id": "ask-policy"})], "noted.")
    answer = await run_ask(
        _cfg(instructions_file="ask-policy", tools=["read_note"]),
        lib,
        "hi?",
        model=model,
    )
    assert answer.found is True
    assert "ask-policy" in answer.note_ids


def test_evidence_collects_read_notes_in_order() -> None:
    parts = [
        ToolCallPart(tool_name="read_note", args={"note_id": "b"}),
        ToolReturnPart(tool_name="read_note", content="B"),
        ToolCallPart(tool_name="read_note", args={"note_id": "a"}),
        ToolReturnPart(tool_name="read_note", content="A"),
        ToolCallPart(tool_name="read_note", args={"note_id": "b"}),
        ToolReturnPart(tool_name="read_note", content="B"),
    ]
    note_ids, entry_id = evidence(parts)  # type: ignore[arg-type]
    assert note_ids == ["b", "a"]
    assert entry_id == ""


def test_evidence_collects_search_hits_and_feedback() -> None:
    parts = [
        ToolCallPart(tool_name="search_notes", args={"query": "k3s"}),
        ToolReturnPart(tool_name="search_notes", content=["homelab"]),
        ToolCallPart(
            tool_name="give_feedback",
            args={"kind": "question", "body": "Unanswered question: xyz"},
        ),
        ToolReturnPart(tool_name="give_feedback", content="entry-1"),
    ]
    note_ids, entry_id = evidence(parts)  # type: ignore[arg-type]
    assert note_ids == ["homelab"]
    assert entry_id == "entry-1"
