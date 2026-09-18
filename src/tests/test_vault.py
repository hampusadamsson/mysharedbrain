"""TDD: vault CRUD, move, list, name/content search, id safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain.vault import (
    InvalidNoteId,
    NoteExists,
    NoteNotFound,
    SectionNotFound,
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
    (brain / "brain.db").write_text("{}", encoding="utf-8")
    assert Vault(vault_dir).list_notes() == []


def test_symlinked_folder_cannot_escape_the_vault(
    vault_dir: Path, tmp_path: Path
) -> None:
    """A symlink inside the vault must not be a way out of it.

    Regression: ``sub/link -> elsewhere`` let a note id write outside the vault,
    and ``list_notes`` never showed the result — a real file, invisible to the
    brain. The agent picks its own note ids, so this is its reach, not a detail.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault_dir / "sub").mkdir()
    (vault_dir / "sub" / "link").symlink_to(outside, target_is_directory=True)
    vault = Vault(vault_dir)

    for action in (
        lambda: vault.create("sub/link/pwned", "x"),
        lambda: vault.read("sub/link/pwned"),
        lambda: vault.update("sub/link/pwned", "x"),
        lambda: vault.delete("sub/link/pwned"),
        lambda: vault.move("sub/link/pwned", "moved"),
    ):
        with pytest.raises(InvalidNoteId, match="outside the vault"):
            action()
    assert list(outside.iterdir()) == []


def test_symlinked_note_file_cannot_escape_the_vault(
    vault_dir: Path, tmp_path: Path
) -> None:
    """A note id pointing at a symlinked file would read/write its target."""
    secret = tmp_path / "secret.md"
    secret.write_text("not yours", encoding="utf-8")
    (vault_dir / "linked.md").symlink_to(secret)
    vault = Vault(vault_dir)

    with pytest.raises(InvalidNoteId, match="outside the vault"):
        vault.read("linked")
    with pytest.raises(InvalidNoteId, match="outside the vault"):
        vault.update("linked", "overwritten")
    with pytest.raises(InvalidNoteId, match="outside the vault"):
        vault.delete("linked")
    assert secret.read_text(encoding="utf-8") == "not yours"


def test_symlinked_trash_directory_cannot_escape_the_vault(
    vault_dir: Path, tmp_path: Path
) -> None:
    """Deleting must not move a note outside either — trash lives in .brain."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault_dir / ".brain").symlink_to(outside, target_is_directory=True)
    vault = Vault(vault_dir)
    vault.root.mkdir(parents=True, exist_ok=True)
    (vault_dir / "note.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidNoteId, match="outside the vault"):
        vault.delete("note")
    assert list(outside.iterdir()) == []


def test_a_normal_vault_is_unaffected(vault_dir: Path) -> None:
    """The guard must not get in the way of ordinary use."""
    vault = Vault(vault_dir)
    vault.create("projects/homelab", "k3s")
    assert vault.read("projects/homelab").content == "k3s"
    vault.delete("projects/homelab")
    assert vault.restore("projects/homelab").content == "k3s"
    assert vault.list_notes() == ["projects/homelab"]


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


def test_ids_accept_a_md_suffix(vault_dir: Path) -> None:
    """Agents write note ids the way files are named; that must not 404."""
    vault = Vault(vault_dir)
    vault.create("admin/test.md", "body")
    # one file, named once — not admin/test.md.md
    assert (vault_dir / "admin" / "test.md").is_file()
    assert vault.list_notes() == ["admin/test"]
    assert vault.read("admin/test.md").content == "body"
    assert vault.read("admin/test").content == "body"
    vault.update("admin/test.md", "new")
    assert vault.read("admin/test").content == "new"


def test_ids_tolerate_surrounding_whitespace(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("  spaced  ", "x")
    assert vault.list_notes() == ["spaced"]


def test_patch_accepts_a_heading_written_with_hashes(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("doc", "## title 1\nold\n\n## other\nkeep\n")
    for written in ("title 1", "# title 1", "## title 1", "  ## title 1  "):
        vault.update("doc", "## title 1\nold\n\n## other\nkeep\n")
        patched = vault.patch("doc", written, "new")
        assert patched.content == "## title 1\nnew\n## other\nkeep\n", written


def test_patch_keeps_hashes_inside_a_heading_name(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("doc", "## C# setup\nold\n")
    assert "new" in vault.patch("doc", "# C# setup", "new").content


def test_append_adds_to_existing_note(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("log", "first")
    assert vault.append("log", "second").content == "first\nsecond"
    assert vault.read("log").content == "first\nsecond"


def test_append_missing_raises(vault_dir: Path) -> None:
    with pytest.raises(NoteNotFound):
        Vault(vault_dir).append("nope", "x")


def test_patch_replaces_section(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("doc", "# Title\n\n## A\nold a\n\n## B\nold b\n")
    patched = vault.patch("doc", "A", "new a")
    assert patched.content == "# Title\n\n## A\nnew a\n## B\nold b\n"


def test_patch_appends_to_section(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("doc", "## A\none\n\n## B\ntwo\n")
    patched = vault.patch("doc", "A", "two", mode="append")
    assert patched.content == "## A\none\n\ntwo\n## B\ntwo\n"


def test_patch_errors(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("doc", "## A\nold\n")
    with pytest.raises(SectionNotFound):
        vault.patch("doc", "Nope", "x")
    with pytest.raises(ValueError):
        vault.patch("doc", "A", "x", mode="bogus")
    with pytest.raises(ValueError):
        vault.patch("doc", "  ", "x")
    with pytest.raises(NoteNotFound):
        vault.patch("missing", "A", "x")


def test_frontmatter_roundtrip(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("doc", "# Hi\n")
    assert vault.get_frontmatter("doc") == {}
    vault.set_frontmatter("doc", {"tags": ["a", "b"], "title": "Hi"})
    assert vault.get_frontmatter("doc") == {"tags": ["a", "b"], "title": "Hi"}
    assert vault.read("doc").content.startswith("---\n")
    assert "# Hi" in vault.read("doc").content
    vault.set_frontmatter("doc", {"title": None})
    assert vault.get_frontmatter("doc") == {"tags": ["a", "b"]}
    vault.set_frontmatter("doc", {"tags": None})
    assert vault.read("doc").content == "# Hi\n"


def test_tags_and_search(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("a", "---\ntags: [K3s, homelab]\n---\nbody\n")
    vault.create("b", "---\ntags: gardening\n---\nbody\n")
    vault.create("c", "plain\n")
    assert vault.get_tags("a") == ["K3s", "homelab"]
    assert vault.search_tags("k3s") == ["a"]
    assert vault.search_tags("#homelab") == ["a"]
    assert vault.search_tags("nope") == []


def test_outgoing_and_backlinks(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("index", "See [[projects/a]] and [[b|Bee]].\n")
    vault.create("projects/a", "child\n")
    vault.create("b", "bee\n")
    assert vault.get_outgoing("index") == ["b", "projects/a"]
    assert vault.get_backlinks("projects/a") == ["index"]
    assert vault.get_backlinks("b") == ["index"]
    assert vault.get_backlinks("index") == []


def test_list_directory(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("projects/a", "1")
    vault.create("todo", "2")
    assert vault.list_directory("") == {"folders": ["projects"], "notes": ["todo"]}
    assert vault.list_directory("projects") == {"folders": [], "notes": ["projects/a"]}
    assert vault.list_directory("missing") == {"folders": [], "notes": []}


def test_list_pagination(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    for i in range(5):
        vault.create(f"n{i}", "x")
    assert vault.list_notes(limit=2) == ["n0", "n1"]
    assert vault.list_notes(limit=2, offset=2) == ["n2", "n3"]
    assert vault.list_notes(offset=4) == ["n4"]


def test_search_excerpts_have_no_line_numbers(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.create("net", "first line\nthe elitedesk ip is here\nlast line\n")
    hits = vault.search_content("elitedesk")
    assert [h.id for h in hits] == ["net"]
    assert hits[0].excerpts == ["the elitedesk ip is here"]


def test_search_content_offset(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")  # deterministic order via fallback
    vault = Vault(vault_dir)
    for i in range(3):
        vault.create(f"n{i}", "shared needle\n")
    hits = vault.search_content("needle", limit=1, offset=1)
    assert [h.id for h in hits] == ["n1"]
