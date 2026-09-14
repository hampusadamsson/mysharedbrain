"""TDD: librarian — audited mutations, questions, capture processing."""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain import audit, capture
from mysharedbrain.service import Librarian
from mysharedbrain.vault import NoteNotFound


def test_mutations_are_audited(vault_dir: Path) -> None:
    lib = Librarian(vault_dir, actor="test")
    lib.create_note("a", "1")
    lib.update_note("a", "2")
    lib.move_note("a", "b")
    lib.delete_note("b")
    actions = [e.action for e in audit.read_log(vault_dir)]
    assert actions == ["delete", "move", "update", "create"]
    with pytest.raises(NoteNotFound):
        lib.read_note("b")


def test_ask_returns_hits_when_found(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "k3s runs on elitedesk")
    answer = lib.ask("elitedesk")
    assert answer.found is True
    assert "homelab" in answer.note_ids
    assert capture.list_entries(vault_dir) == []


def test_ask_logs_missing_information_when_not_found(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    answer = lib.ask("obscure topic nobody wrote down")
    assert answer.found is False
    assert answer.entry_id
    pending = capture.list_entries(vault_dir, "pending")
    assert len(pending) == 1
    assert pending[0].kind == "request"


def test_ask_rejects_empty_question(vault_dir: Path) -> None:
    with pytest.raises(ValueError):
        Librarian(vault_dir).ask("  ")


def test_process_capture_applies_correction_to_vault(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "old ip")
    entry = lib.give_feedback("correction", "new ip is 10.0.0.2", note_id="homelab")
    reviewed = lib.process_capture(
        entry.id, "applied", "curator", content="new ip is 10.0.0.2"
    )
    assert reviewed.status == "applied"
    assert lib.read_note("homelab").content == "new ip is 10.0.0.2"
    assert "capture-applied" in [e.action for e in audit.read_log(vault_dir)]


def test_process_capture_can_create_missing_note(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    entry = lib.give_feedback("missing", "we lack gpu docs", note_id="gpu")
    lib.process_capture(entry.id, "applied", "curator", content="# GPU\n")
    assert lib.read_note("gpu").content == "# GPU\n"


def test_process_capture_approve_endorses_without_vault_change(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "old ip")
    entry = lib.give_feedback("request", "fetch new ip", note_id="homelab")
    reviewed = lib.process_capture(
        entry.id, "approved", "curator", review_note="valid, fetch later"
    )
    assert reviewed.status == "approved"
    assert lib.read_note("homelab").content == "old ip"
    assert "capture-approved" in [e.action for e in audit.read_log(vault_dir)]


def test_process_capture_reject_leaves_vault_alone(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "old ip")
    entry = lib.give_feedback("correction", "bogus", note_id="homelab")
    reviewed = lib.process_capture(entry.id, "rejected", "curator", review_note="wrong")
    assert reviewed.status == "rejected"
    assert lib.read_note("homelab").content == "old ip"


def test_process_capture_unknown_entry_raises(vault_dir: Path) -> None:
    with pytest.raises(capture.EntryNotFound):
        Librarian(vault_dir).process_capture("nope", "rejected", "curator")
