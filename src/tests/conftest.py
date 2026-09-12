"""Shared fixtures: isolated vault per test via VAULT_DIR."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def vault_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setenv("VAULT_DIR", str(root))
    return root
