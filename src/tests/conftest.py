"""Shared fixtures: isolated vault per test via VAULT_DIR."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def vault_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setenv("VAULT_DIR", str(root))
    return root


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read a developer's ./brain.yaml from the repo root.

    ``config_path()`` falls back to the working directory, so without this a
    local config file (git-ignored, edited by hand or by the settings UI) would
    change unit-test behaviour. Tests that want a file set BRAIN_CONFIG
    themselves, which lands after this fixture.
    """
    monkeypatch.setenv("BRAIN_CONFIG", str(tmp_path / "isolated-brain.yaml"))


@pytest.fixture(autouse=True)
def _scheduler_off(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No background scheduler in tests, and no singleton leakage."""
    from mysharedbrain.jobs import reset_scheduler

    reset_scheduler()
    yield
    reset_scheduler()
