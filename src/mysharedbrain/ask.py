"""Ask the librarian: one interactive agent run per question.

Jobs own the scheduled loop (:mod:`mysharedbrain.jobs`); this module owns the
interactive one. Same shape — the run's tools, servers, step budget and
instructions note come from the ``ask:`` config section — but there is no
schedule: one question in, one run, one answer out.

The agent answers from the vault and files capture entries itself (via the
``give_feedback`` tool) when the vault cannot answer, so "no answer" is never
silent: it lands in the capture queue for review, exactly like a job's misses.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic_ai.messages import (
    ModelRequestPart,
    ModelResponsePart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import Model

from mysharedbrain.agent import run_agent
from mysharedbrain.config import BrainConfigDocument
from mysharedbrain.service import Librarian

#: Built-in tools whose call args name the note they touch.
_NOTE_ARG_TOOLS = frozenset(
    {
        "read_note",
        "create_note",
        "update_note",
        "append_note",
        "patch_note",
        "delete_note",
        "move_note",
    }
)


@dataclass(frozen=True)
class AskAnswer:
    """What one question produced: the agent's answer plus its evidence."""

    found: bool
    question: str
    note_ids: list[str]
    hits: list[Any]
    entry_id: str
    message: str


def evidence(
    parts: Sequence[ModelRequestPart | ModelResponsePart],
) -> tuple[list[str], str]:
    """Note ids the run touched, and the capture entry it filed (if any).

    ``read_*``/write call args name their notes in order; ``search_notes``
    returns name them. A ``give_feedback`` return carries the queue entry id —
    the run's way of saying the vault could not answer.
    """
    note_ids: list[str] = []
    entry_id = ""
    for part in parts:
        if isinstance(part, ToolCallPart):
            if part.tool_name in _NOTE_ARG_TOOLS and isinstance(part.args, dict):
                for key in ("note_id", "new_id"):
                    value = part.args.get(key)
                    if isinstance(value, str) and value and value not in note_ids:
                        note_ids.append(value)
        elif isinstance(part, ToolReturnPart):
            if part.tool_name == "search_notes" and isinstance(part.content, list):
                content = cast("list[object]", part.content)
                for value in content:
                    if isinstance(value, str) and value and value not in note_ids:
                        note_ids.append(value)
            elif part.tool_name == "give_feedback" and isinstance(part.content, str):
                entry_id = part.content
    return note_ids, entry_id


def ask_prompt(cfg: BrainConfigDocument, lib: Librarian, question: str) -> str:
    """The user prompt for one question: the ask note (if any) + the question."""
    chunks: list[str] = []
    if cfg.ask.instructions_file:
        try:
            chunks.append(lib.read_note(cfg.ask.instructions_file).content.strip())
        except Exception:
            chunks.append(
                f"(instructions note {cfg.ask.instructions_file!r} not found)"
            )
    chunks.append(f"Question: {question.strip()}")
    chunks.append(
        "Answer from the vault using your tools. If the vault cannot answer, "
        "file the question with give_feedback (kind 'question') so it lands in "
        "the capture queue, and say so in your reply."
    )
    return "\n\n".join(c for c in chunks if c)


async def run_ask(
    cfg: BrainConfigDocument,
    lib: Librarian,
    question: str,
    model: Model | None = None,
) -> AskAnswer:
    """Run one interactive librarian run for ``question``.

    ``model`` overrides the configured model — tests pass a ``TestModel`` so a
    full run can be exercised without credentials. Raises ``ValueError`` on an
    empty question or when ``ask.enabled`` is off.
    """
    clean = question.strip()
    if not clean:
        raise ValueError("question must not be empty")
    if not cfg.ask.enabled:
        raise ValueError("ask the librarian is disabled in the config")
    outcome = await run_agent(cfg, lib, ask_prompt(cfg, lib, clean), cfg.ask, model)
    parts: list[ModelRequestPart | ModelResponsePart] = [
        part for message in outcome.messages for part in message.parts
    ]
    note_ids, entry_id = evidence(parts)
    return AskAnswer(
        found=not entry_id,
        question=clean,
        note_ids=note_ids,
        hits=[],
        entry_id=entry_id,
        message=outcome.output.strip(),
    )


__all__ = ["AskAnswer", "ask_prompt", "evidence", "run_ask"]
