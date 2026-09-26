"""Vault ignore rules: ignored paths are invisible and untouchable."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mysharedbrain.app import create_app
from mysharedbrain.config import BrainConfig, VaultConfig
from mysharedbrain.service import Librarian, librarian
from mysharedbrain.vault import InvalidNoteId, NoteNotFound, Vault

RULES = ["secret.md", "drafts/*", "archive/"]


def _vault(root: Path) -> Vault:
    return Vault(root, ignore=RULES)


def _plant(root: Path, note_id: str, content: str = "x") -> None:
    path = root / (note_id + ".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_config_patterns_block_every_write_and_read(vault_dir: Path) -> None:
    vault = _vault(vault_dir)
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.create("secret", "x")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.create("drafts/a", "x")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.create("archive/a", "x")
    # Message names the rule, so users know what to un-ignore.
    with pytest.raises(InvalidNoteId, match="archive/"):
        vault.read("archive/a")
    _plant(vault_dir, "secret", "planted")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.read("secret")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.update("secret", "y")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.delete("secret")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.append("secret", "y")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.patch("secret", "H", "y")
    vault.create("visible", "v")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.move("visible", "secret")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.move("secret", "visible")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.get_frontmatter("secret")


def test_missing_is_not_found_ignored_is_invalid(vault_dir: Path) -> None:
    vault = _vault(vault_dir)
    with pytest.raises(NoteNotFound):
        vault.read("nope")
    _plant(vault_dir, "secret", "planted")
    with pytest.raises(InvalidNoteId):
        vault.read("secret")


def test_visible_notes_still_work(vault_dir: Path) -> None:
    vault = _vault(vault_dir)
    assert vault.create("visible", "hi").id == "visible"
    assert vault.read("visible").content == "hi"
    # Similar names that do NOT match still work: drafts2/ is not drafts/.
    assert vault.create("drafts2/a", "x").id == "drafts2/a"
    assert vault.create("mysecret", "x").id == "mysecret"


def test_listings_and_search_hide_ignored(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    plain = Vault(vault_dir)
    plain.create("visible", "shared word")
    plain.create("secret", "shared word")
    plain.create("drafts/a", "shared word")
    plain.create("archive/a", "shared word")
    vault = _vault(vault_dir)
    assert vault.list_notes() == ["visible"]
    assert vault.list_notes(prefix="archive") == []
    browsing = vault.list_directory("")
    assert browsing["notes"] == ["visible"]
    assert "archive" not in browsing["folders"]
    assert "drafts" not in browsing["folders"]
    assert vault.list_directory("archive") == {"folders": [], "notes": []}
    assert vault.search_names("archive") == []
    assert [h.id for h in vault.search_content("shared word")] == ["visible"]
    # Pure-Python path too (no ripgrep): force the fallback.
    def _no_binary(_name: str) -> None:
        return None

    monkeypatch.setattr(shutil, "which", _no_binary)
    assert [h.id for h in vault.search_content("shared word")] == ["visible"]
    assert vault.search_tags("t") == []
    assert vault.get_backlinks("visible") == []


def test_brainignore_file_unions_with_config(vault_dir: Path) -> None:
    (vault_dir / ".brainignore").write_text(
        "# scratch space\n\ntmp.md\n!keep.md\n", encoding="utf-8"
    )
    vault = Vault(vault_dir, ignore=["secret.md"])
    _plant(vault_dir, "tmp", "x")
    _plant(vault_dir, "keep", "x")
    with pytest.raises(InvalidNoteId, match="ignored"):
        vault.read("tmp")
    with pytest.raises(InvalidNoteId, match=r"secret\.md"):
        vault.read("secret")
    # Negation unsupported: the ! line is skipped, not honored as un-ignore.
    assert vault.read("keep").content == "x"
    assert vault.list_notes() == ["keep"]


def test_restore_into_ignored_path_blocked(vault_dir: Path) -> None:
    plain = Vault(vault_dir)
    plain.create("secret", "v1")
    plain.delete("secret")
    with pytest.raises(InvalidNoteId, match="ignored"):
        _vault(vault_dir).restore("secret")


def test_import_reports_ignored_as_errors(vault_dir: Path) -> None:
    lib = Librarian(vault_dir, ignore=["secret.md", "drop/"])
    result = lib.import_notes([("secret.md", "x"), ("drop/a.md", "y"), ("ok.md", "z")])
    assert result["created"] == ["ok"]
    assert set(result["errors"]) == {"secret.md", "drop/a.md"}
    assert all("ignored" in message for message in result["errors"].values())


def test_config_schema_strips_and_rejects_negation() -> None:
    assert VaultConfig(ignore=["  a.md  ", "", "  "]).ignore == ["a.md"]
    with pytest.raises(ValidationError, match="negation"):
        VaultConfig(ignore=["!keep.md"])
    assert BrainConfig().vault.ignore == []


def test_factory_wires_config_ignore(
    vault_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "brain.yaml"
    config.write_text("vault:\n  ignore:\n    - secret.md\n", encoding="utf-8")
    monkeypatch.setenv("BRAIN_CONFIG", str(config))
    _plant(vault_dir, "secret", "x")
    with pytest.raises(InvalidNoteId, match="ignored"):
        librarian().read_note("secret")


def test_api_reports_ignored_as_400(vault_dir: Path) -> None:
    (vault_dir / ".brainignore").write_text("secret.md\n", encoding="utf-8")
    _plant(vault_dir, "secret", "x")
    client = TestClient(create_app())
    assert (
        client.post("/api/notes", json={"id": "secret", "content": "x"}).status_code
        == 400
    )
    response = client.get("/api/notes/secret")
    assert response.status_code == 400
    assert "ignored" in response.json()["detail"]
    assert client.get("/api/notes").json()["notes"] == []
