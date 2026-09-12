"""Markdown vault: one note = one ``.md`` file, folders = real directories.

Note ids are vault-relative POSIX paths without the ``.md`` suffix, e.g.
``"todo"`` or ``"projects/homelab"``. Flat or nested — both are just paths.
Dot-directories (``.brain/``) hold internal state and are never notes.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

NOTE_SUFFIX = ".md"
INTERNAL_DIRS = {".brain"}


class VaultError(Exception):
    """Base error for vault operations."""


class NoteNotFound(VaultError):
    """The requested note does not exist."""


class NoteExists(VaultError):
    """A note already exists at this id."""


class InvalidNoteId(VaultError):
    """The note id is unsafe or malformed."""


@dataclass(frozen=True)
class Note:
    id: str
    content: str


@dataclass(frozen=True)
class SearchHit:
    id: str
    excerpts: list[str]


def _validate(note_id: str) -> str:
    """Normalise and validate a note id. Returns the POSIX relative path."""
    if not note_id or not note_id.strip():
        raise InvalidNoteId("note id must not be empty")
    text = note_id.strip().replace("\\", "/")
    if text.startswith("/"):
        raise InvalidNoteId(f"absolute paths are not allowed: {note_id!r}")
    parts = text.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise InvalidNoteId(f"unsafe path segment in: {note_id!r}")
    if any(p.startswith(".") for p in parts):
        raise InvalidNoteId(f"hidden segments are reserved: {note_id!r}")
    if any(ord(c) < 32 for c in note_id):
        raise InvalidNoteId(f"control characters are not allowed: {note_id!r}")
    return "/".join(parts)


class Vault:
    """CRUD + search over a directory of markdown files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, note_id: str) -> Path:
        rel = _validate(note_id)
        return self.root / (rel + NOTE_SUFFIX)

    def create(self, note_id: str, content: str) -> Note:
        path = self._path(note_id)
        if path.exists():
            raise NoteExists(f"note already exists: {note_id!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return Note(id="/".join(Path(_validate(note_id)).parts), content=content)

    def read(self, note_id: str) -> Note:
        path = self._path(note_id)
        if not path.is_file():
            raise NoteNotFound(f"note not found: {note_id!r}")
        return Note(
            id="/".join(Path(_validate(note_id)).parts),
            content=path.read_text(encoding="utf-8"),
        )

    def update(self, note_id: str, content: str) -> Note:
        path = self._path(note_id)
        if not path.is_file():
            raise NoteNotFound(f"note not found: {note_id!r}")
        path.write_text(content, encoding="utf-8")
        return Note(id="/".join(Path(_validate(note_id)).parts), content=content)

    def delete(self, note_id: str) -> None:
        path = self._path(note_id)
        if not path.is_file():
            raise NoteNotFound(f"note not found: {note_id!r}")
        path.unlink()
        self._prune_empty_parents(path.parent)

    def move(self, note_id: str, new_id: str) -> Note:
        src = self._path(note_id)
        if not src.is_file():
            raise NoteNotFound(f"note not found: {note_id!r}")
        dst = self._path(new_id)
        if dst.exists():
            raise NoteExists(f"note already exists: {new_id!r}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        self._prune_empty_parents(src.parent)
        return self.read(new_id)

    def _prune_empty_parents(self, directory: Path) -> None:
        while directory != self.root and directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent

    def list_notes(self, prefix: str = "") -> list[str]:
        """All note ids, sorted. Optional path-prefix filter."""
        ids = sorted(
            p.relative_to(self.root).as_posix()[: -len(NOTE_SUFFIX)]
            for p in self.root.rglob(f"*{NOTE_SUFFIX}")
            if p.is_file() and not self._is_internal(p)
        )
        if prefix:
            norm = prefix.strip().replace("\\", "/").rstrip("/")
            ids = [i for i in ids if i == norm or i.startswith(norm + "/")]
        return ids

    def _is_internal(self, path: Path) -> bool:
        return any(
            part in INTERNAL_DIRS for part in path.relative_to(self.root).parts[:-1]
        ) or path.name.startswith(".")

    def search_names(self, query: str) -> list[str]:
        """Case-insensitive substring match on note ids."""
        needle = query.strip().lower()
        if not needle:
            return []
        return [i for i in self.list_notes() if needle in i.lower()]

    def search_content(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Full-text search via ripgrep, with a pure-Python fallback."""
        needle = query.strip()
        if not needle:
            return []
        if shutil.which("rg") is not None:
            try:
                return self._search_ripgrep(needle, limit)
            except (OSError, subprocess.SubprocessError):
                pass
        return self._search_fallback(needle, limit)

    def _search_ripgrep(self, query: str, limit: int) -> list[SearchHit]:
        proc = subprocess.run(
            [
                "rg",
                "--no-heading",
                "--line-number",
                "--max-count",
                "3",
                "--",
                query,
                ".",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        hits: dict[str, list[str]] = {}
        for line in proc.stdout.splitlines():
            path_part, _, excerpt = line.partition(":")
            file_path = self.root / path_part.split(":")[0]
            if file_path.suffix != NOTE_SUFFIX or self._is_internal(file_path):
                continue
            note_id = file_path.relative_to(self.root).as_posix()[: -len(NOTE_SUFFIX)]
            hits.setdefault(note_id, []).append(excerpt.strip()[:200])
            if len(hits) >= limit:
                break
        return [SearchHit(id=k, excerpts=v) for k, v in list(hits.items())[:limit]]

    def _search_fallback(self, query: str, limit: int) -> list[SearchHit]:
        needle = query.lower()
        hits: list[SearchHit] = []
        for note_id in self.list_notes():
            content = (self.root / (note_id + NOTE_SUFFIX)).read_text(encoding="utf-8")
            excerpts = [
                ln.strip()[:200] for ln in content.splitlines() if needle in ln.lower()
            ][:3]
            if excerpts:
                hits.append(SearchHit(id=note_id, excerpts=excerpts))
            if len(hits) >= limit:
                break
        return hits
