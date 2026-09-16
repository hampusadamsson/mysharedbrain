"""TDD: logging setup — the app's own logs must reach a handler."""

from __future__ import annotations

import logging

import pytest

from mysharedbrain.logging_setup import LOG_LEVEL_ENV, configure_logging


def test_level_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A container can turn the volume up without a code change."""
    monkeypatch.setenv(LOG_LEVEL_ENV, "DEBUG")
    configure_logging()
    assert logging.getLogger("mysharedbrain").level == logging.DEBUG


def test_an_explicit_level_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LOG_LEVEL_ENV, "DEBUG")
    configure_logging("WARNING")
    assert logging.getLogger("mysharedbrain").level == logging.WARNING


def test_scheduler_logs_survive_the_default_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: INFO had no handler anywhere, so the scheduler was silent."""
    monkeypatch.delenv(LOG_LEVEL_ENV, raising=False)
    configure_logging()
    assert logging.getLogger("mysharedbrain.jobs").isEnabledFor(logging.INFO)


def test_existing_handlers_are_left_alone() -> None:
    """force=False: whatever started the process decided first."""
    root = logging.getLogger()
    before = list(root.handlers)
    configure_logging()
    assert root.handlers == before
