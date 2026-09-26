"""In-memory fallback: sidecar state survives a broken file database."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mysharedbrain.db import Database
from mysharedbrain.service import Librarian


def _break_brain_dir(root: Path) -> None:
    """Block `<root>/.brain` with a regular file, so mkdir fails deterministically."""
    (root / ".brain").write_text("in the way", encoding="utf-8")


def test_file_failure_falls_back_to_memory_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    _break_brain_dir(root)
    with caplog.at_level(logging.WARNING, logger="mysharedbrain.db"):
        conn = Database(root).connect()
    assert "in-memory" in caplog.text
    conn.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO probe (v) VALUES ('kept')")
    conn.close()


def test_memory_state_shared_across_instances(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    _break_brain_dir(root)
    first = Database(root)
    conn = first.connect()
    conn.execute("CREATE TABLE shared_probe (v TEXT)")
    conn.execute("INSERT INTO shared_probe (v) VALUES ('here')")
    conn.close()
    assert first.in_memory is True  # pinned: file never retried by this instance
    # A fresh instance hits the same broken file, lands in the same cache.
    rows = Database(root).connect().execute("SELECT v FROM shared_probe").fetchall()
    assert [r["v"] for r in rows] == ["here"]


def test_librarian_works_with_broken_file_db(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    _break_brain_dir(root)
    lib = Librarian(root, actor="test")
    lib.create_note("todo", "milk")
    assert lib.read_note("todo").content == "milk"
    actions = [e.action for e in lib.file_history("todo")]
    assert "create" in actions and "read" in actions
    entry = lib.give_feedback("edit", "more milk", note_id="todo")
    stored = lib.capture.get(entry.id)
    assert stored is not None
    assert stored.status == "pending"
