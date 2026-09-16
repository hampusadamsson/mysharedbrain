"""TDD: librarian — audited mutations, questions, capture processing."""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain import capture
from mysharedbrain.service import Librarian
from mysharedbrain.vault import NoteExists, NoteNotFound


def test_mutations_are_audited(vault_dir: Path) -> None:
    lib = Librarian(vault_dir, actor="test")
    lib.create_note("a", "1")
    lib.update_note("a", "2")
    lib.move_note("a", "b")
    lib.delete_note("b")
    actions = [e.action for e in lib.audit.read_log()]
    assert actions == ["delete", "move", "update", "create"]
    with pytest.raises(NoteNotFound):
        lib.read_note("b")


def test_ask_returns_hits_when_found(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "k3s runs on elitedesk")
    answer = lib.ask("elitedesk")
    assert answer.found is True
    assert "homelab" in answer.note_ids
    assert lib.capture.list_entries() == []


def test_ask_logs_missing_information_when_not_found(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    answer = lib.ask("obscure topic nobody wrote down")
    assert answer.found is False
    assert answer.entry_id
    pending = lib.capture.list_entries("pending")
    assert len(pending) == 1
    assert pending[0].kind == "question"
    assert pending[0].automated is True
    assert pending[0].body.startswith("Unanswered question:")


def test_ask_rejects_empty_question(vault_dir: Path) -> None:
    with pytest.raises(ValueError):
        Librarian(vault_dir).ask("  ")


def test_process_capture_applies_edit_to_vault(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "old ip")
    entry = lib.give_feedback("edit", "new ip is 10.0.0.2", note_id="homelab")
    reviewed = lib.process_capture(
        entry.id, "applied", "curator", content="new ip is 10.0.0.2"
    )
    assert reviewed.status == "applied"
    assert lib.read_note("homelab").content == "new ip is 10.0.0.2"
    assert "capture-applied" in [e.action for e in lib.audit.read_log()]


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
    assert "capture-approved" in [e.action for e in lib.audit.read_log()]


def test_process_capture_reject_leaves_vault_alone(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "old ip")
    entry = lib.give_feedback("edit", "bogus", note_id="homelab")
    reviewed = lib.process_capture(entry.id, "rejected", "curator", review_note="wrong")
    assert reviewed.status == "rejected"
    assert lib.read_note("homelab").content == "old ip"


def test_ask_tokenizes_natural_language(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "k3s runs on elitedesk")
    answer = lib.ask("what is the IP of elitedesk?")
    assert answer.found is True
    assert "homelab" in answer.note_ids


def test_ask_dedupes_pending_requests(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    first = lib.ask("obscure topic nobody wrote down")
    second = lib.ask("obscure topic nobody wrote down")
    assert first.entry_id == second.entry_id
    assert len(lib.capture.list_entries("pending")) == 1


def test_process_capture_applied_requires_content(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    entry = lib.give_feedback("edit", "fix it", note_id="homelab")
    with pytest.raises(ValueError, match="requires content"):
        lib.process_capture(entry.id, "applied", "curator")
    assert lib.capture.list_entries("pending")[0].id == entry.id


def test_delete_trashes_and_restores(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("projects/a", "content")
    lib.delete_note("projects/a")
    assert lib.list_notes() == []
    assert (vault_dir / ".brain" / "trash" / "projects" / "a.md").is_file()
    with pytest.raises(NoteNotFound):
        lib.delete_note("projects/a")
    restored = lib.restore_note("projects/a")
    assert restored.content == "content"
    assert lib.list_notes() == ["projects/a"]
    with pytest.raises(NoteNotFound):
        lib.restore_note("never-existed")


def test_restore_conflicts_with_existing(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("a", "v1")
    lib.delete_note("a")
    lib.create_note("a", "v2")
    with pytest.raises(NoteExists):
        lib.restore_note("a")
    assert lib.read_note("a").content == "v2"


def test_process_capture_unknown_entry_raises(vault_dir: Path) -> None:
    with pytest.raises(capture.EntryNotFound):
        Librarian(vault_dir).process_capture("nope", "rejected", "curator")


def test_append_patch_frontmatter_audited(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("doc", "## A\nold\n")
    lib.append_note("doc", "more")
    lib.patch_note("doc", "A", "new")
    lib.set_frontmatter("doc", {"tags": ["x"]})
    actions = [e.action for e in lib.audit.read_log()]
    assert actions == ["frontmatter", "patch", "append", "create"]
    assert lib.get_tags("doc") == ["x"]


def test_read_notes_batch_and_recent_changes(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("a", "1")
    batch = lib.read_notes(["a", "missing"])
    assert [n.id for n in batch["notes"]] == ["a"]
    assert batch["missing"] == ["missing"]
    # missing ids are not interactions, so they leave no trace
    assert [e.action for e in lib.recent_changes(2)] == ["read", "create"]
    assert lib.recent_changes(1, kind="read")[0].note_id == "a"
    assert lib.list_directory("") == {"folders": [], "notes": ["a"]}
    assert lib.search_tags("x") == []


def test_reading_a_note_is_logged_against_the_file(vault_dir: Path) -> None:
    lib = Librarian(vault_dir, actor="curator")
    lib.create_note("projects/homelab", "k3s")
    lib.read_note("projects/homelab")
    entries = lib.file_history("projects/homelab")
    assert [(e.action, e.kind, e.actor, e.note_id) for e in entries] == [
        ("read", "read", "curator", "projects/homelab"),
        ("create", "write", "curator", "projects/homelab"),
    ]


def test_file_history_ignores_other_notes(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("a", "1")
    lib.create_note("b", "2")
    assert [e.note_id for e in lib.file_history("a")] == ["a"]
    assert lib.file_history("never-touched") == []


def test_move_is_logged_on_the_old_path_with_the_destination(
    vault_dir: Path,
) -> None:
    """A moved file's log must still show where it went."""
    lib = Librarian(vault_dir)
    lib.create_note("projects/homelab", "k3s")
    lib.move_note("projects/homelab", "infra/homelab")
    moves = lib.file_history("projects/homelab", kind="move")
    assert [(e.action, e.note_id, e.detail) for e in moves] == [
        ("move", "projects/homelab", "to infra/homelab")
    ]


def test_search_logs_a_find_per_matching_file(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "k3s runs on elitedesk")
    lib.search("elitedesk")
    finds = lib.file_history("homelab", kind="find")
    assert len(finds) == 1
    assert finds[0].detail == "query:elitedesk"


def test_untracked_search_leaves_no_trace(vault_dir: Path) -> None:
    """Type-ahead searches must not turn the log into a keystroke record."""
    lib = Librarian(vault_dir)
    lib.create_note("homelab", "k3s runs on elitedesk")
    lib.search("elitedesk", track=False)
    assert lib.file_history("homelab", kind="find") == []


def test_file_stats_count_kinds(vault_dir: Path) -> None:
    lib = Librarian(vault_dir)
    lib.create_note("a", "1")
    lib.read_note("a")
    lib.read_note("a")
    lib.update_note("a", "2")
    stats = lib.file_stats("a")
    assert stats.note_id == "a"
    assert stats.total == 4
    assert stats.counts == {"read": 2, "write": 2}
    assert stats.first_seen and stats.last_seen
    assert stats.first_seen <= stats.last_seen
