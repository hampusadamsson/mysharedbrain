"""Import: uploading files/folders as notes.

The feature landed without tests, which is how the UI gap (upload controls only
rendered when the vault already had pages — i.e. never for the case they exist
for) and the `.txt` handling slipped through. These pin the behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain.service import MAX_IMPORT_FILES, Librarian, filename_to_note_id
from mysharedbrain.vault import InvalidNoteId


def _lib(root: Path) -> Librarian:
    return Librarian(root, actor="api")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("note.md", "note"),
        ("note.markdown", "note"),
        ("note.txt", "note"),
        ("NOTE.MD", "NOTE"),
        ("./note.md", "note"),
        ("/note.md", "note"),
        ("a/b/note.md", "a/b/note"),
        ("note", "note"),
        ("  spaced.md  ", "spaced"),
    ],
)
def test_filename_to_note_id(filename: str, expected: str) -> None:
    assert filename_to_note_id(filename) == expected


def test_filename_to_note_id_applies_prefix() -> None:
    assert filename_to_note_id("a.md", "imports") == "imports/a"
    assert filename_to_note_id("sub/a.md", "imports/") == "imports/sub/a"


def test_filename_to_note_id_rejects_an_empty_name() -> None:
    with pytest.raises(InvalidNoteId):
        filename_to_note_id("   ")


def test_import_creates_notes_and_audits_each_write(vault_dir: Path) -> None:
    lib = _lib(vault_dir)

    result = lib.import_notes([("one.md", "# One\n"), ("sub/two.md", "# Two\n")])

    assert result["created"] == ["one", "sub/two"]
    assert (
        result["updated"] == [] and result["skipped"] == [] and result["errors"] == {}
    )
    assert lib.read_note("one").content == "# One\n"
    assert lib.read_note("sub/two").content == "# Two\n"
    actions = [(e.action, e.note_id, e.detail) for e in lib.recent_changes(limit=10)]
    assert ("create", "one", "via import") in actions
    assert ("create", "sub/two", "via import") in actions


def test_import_updates_or_skips_an_existing_note(vault_dir: Path) -> None:
    lib = _lib(vault_dir)
    lib.create_note("one", "old")

    updated = lib.import_notes([("one.md", "new")])
    assert updated["updated"] == ["one"] and lib.read_note("one").content == "new"

    skipped = lib.import_notes([("one.md", "newer")], overwrite=False)
    assert skipped["skipped"] == ["one"] and lib.read_note("one").content == "new"


def test_import_reports_bad_names_without_failing_the_batch(vault_dir: Path) -> None:
    lib = _lib(vault_dir)

    result = lib.import_notes([("../escape.md", "nope"), ("fine.md", "ok")])

    assert result["created"] == ["fine"]
    assert list(result["errors"]) == ["../escape.md"]
    assert not (vault_dir.parent / "escape.md").exists()


def test_import_caps_the_batch(vault_dir: Path) -> None:
    lib = _lib(vault_dir)
    too_many = [(f"n{i}.md", "x") for i in range(MAX_IMPORT_FILES + 1)]

    with pytest.raises(ValueError, match="too many files"):
        lib.import_notes(too_many)


def test_import_applies_a_prefix(vault_dir: Path) -> None:
    lib = _lib(vault_dir)

    result = lib.import_notes([("a.md", "x")], prefix="imports")

    assert result["created"] == ["imports/a"]
    assert lib.list_notes() == ["imports/a"]
