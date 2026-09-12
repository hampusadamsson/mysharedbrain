"""TDD: vault CRUD, move, list, name/content search, id safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain.vault import (
    InvalidNoteId,
    NoteExists,
    NoteNotFound,
    Vault,
)


def test_create_and_read_flat_note(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("todo", "# Todo\n")
    note = vault.read("todo")
    assert note.id == "todo"
    assert note.content == "# Todo\n"
    assert (vault_dir / "todo.md").is_file()


def test_create_nested_note_creates_folders(vault_dir: Path) -> None:
    Vault(vault_dir).create("projects/homelab", "k3s")
    assert (vault_dir / "projects" / "homelab.md").is_file()


def test_create_duplicate_raises(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("todo", "a")
    with pytest.raises(NoteExists):
        vault.create("todo", "b")


def test_read_missing_raises(vault_dir: Path) -> None:
    with pytest.raises(NoteNotFound):
        Vault(vault_dir).read("nope")


def test_update_replaces_content(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("todo", "a")
    updated = vault.update("todo", "b")
    assert updated.content == "b"
    assert vault.read("todo").content == "b"


def test_update_missing_raises(vault_dir: Path) -> None:
    with pytest.raises(NoteNotFound):
        Vault(vault_dir).update("nope", "x")


def test_delete_removes_file_and_prunes_empty_dirs(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("projects/homelab", "k3s")
    vault.delete("projects/homelab")
    assert not (vault_dir / "projects" / "homelab.md").exists()
    assert not (vault_dir / "projects").exists()


def test_delete_missing_raises(vault_dir: Path) -> None:
    with pytest.raises(NoteNotFound):
        Vault(vault_dir).delete("nope")


def test_move_renames_note(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("old", "content")
    moved = vault.move("old", "new/location")
    assert moved.id == "new/location"
    with pytest.raises(NoteNotFound):
        vault.read("old")
    assert vault.read("new/location").content == "content"


def test_move_onto_existing_raises(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("a", "1")
    vault.create("b", "2")
    with pytest.raises(NoteExists):
        vault.move("a", "b")


def test_list_notes_sorted_flat_and_nested(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("b", "1")
    vault.create("a/c", "2")
    vault.create("a", "3")
    assert vault.list_notes() == ["a", "a/c", "b"]


def test_list_notes_prefix_filter(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("projects/a", "1")
    vault.create("projects/b", "2")
    vault.create("other", "3")
    assert vault.list_notes("projects") == ["projects/a", "projects/b"]


def test_internal_dot_dirs_are_not_notes(vault_dir: Path) -> None:
    brain = vault_dir / ".brain"
    brain.mkdir()
    (brain / "audit.jsonl").write_text("{}\n", encoding="utf-8")
    assert Vault(vault_dir).list_notes() == []


def test_search_names_case_insensitive(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("projects/Homelab", "x")
    vault.create("todo", "y")
    assert vault.search_names("home") == ["projects/Homelab"]


@pytest.mark.parametrize(
    "evil", ["", "../escape", "/abs", ".hidden", "a/../../x", "a/./b"]
)
def test_unsafe_ids_rejected(vault_dir: Path, evil: str) -> None:
    with pytest.raises(InvalidNoteId):
        Vault(vault_dir).create(evil, "x")


def test_search_content_finds_excerpts(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("k3s", "runs on elitedesk node\nsecond line\n")
    vault.create("other", "nothing relevant\n")
    hits = vault.search_content("elitedesk")
    assert [h.id for h in hits] == ["k3s"]
    assert any("elitedesk" in e for h in hits for e in h.excerpts)


def test_search_content_fallback_without_ripgrep(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")  # shutil.which finds no rg -> pure-Python fallback
    vault = Vault(vault_dir)
    vault.create("k3s", "runs on elitedesk\n")
    hits = vault.search_content("elitedesk")
    assert [h.id for h in hits] == ["k3s"]


def test_search_empty_query_returns_nothing(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("a", "hello")
    assert vault.search_content("  ") == []
    assert vault.search_names("  ") == []
