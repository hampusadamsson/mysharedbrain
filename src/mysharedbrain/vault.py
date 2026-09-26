"""Markdown vault: one note = one ``.md`` file, folders = real directories.

Note ids are vault-relative POSIX paths without the ``.md`` suffix, e.g.
``"todo"`` or ``"projects/homelab"``. Flat or nested — both are just paths.
Dot-directories (``.brain/``) hold internal state and are never notes.

Every id is validated twice: as a path (no ``..``, no absolute, no hidden
segments) *and* by resolving it, so a symlink inside the vault cannot be used to
read or write outside it. The agent chooses its own note ids, so the vault is the
only thing it can reach — enforced, not assumed.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, cast

import yaml

NOTE_SUFFIX = ".md"
INTERNAL_DIRS = {".brain"}
TRASH_DIR = Path(".brain/trash")
BRAINIGNORE_FILE = ".brainignore"

log = logging.getLogger(__name__)


class VaultError(Exception):
    """Base error for vault operations."""


class NoteNotFound(VaultError):
    """The requested note does not exist."""


class NoteExists(VaultError):
    """A note already exists at this id."""


class InvalidNoteId(VaultError):
    """The note id is unsafe or malformed."""


class SectionNotFound(VaultError):
    """No heading with this text in the note."""


@dataclass(frozen=True)
class Note:
    id: str
    content: str


@dataclass(frozen=True)
class SearchHit:
    id: str
    excerpts: list[str]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_RG_LINE_RE = re.compile(r"^(.+?):(\d+):(.*)$")


def split_frontmatter(content: str) -> tuple[dict[str, object], str]:
    """Split ``---`` YAML frontmatter from the body. Never raises."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, content
    for i in range(1, min(len(lines), 200)):
        if lines[i].strip() == "---":
            try:
                loaded: Any = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError:
                return {}, content
            if not isinstance(loaded, dict):
                return {}, content
            meta: dict[str, object] = cast("dict[str, object]", loaded)
            return meta, "\n".join(lines[i + 1 :])
    return {}, content


def _validate(note_id: str) -> str:
    """Normalise and validate a note id. Returns the POSIX relative path.

    An id is a path without a suffix, but agents (and people) write it the way
    the file is named — ``admin/test.md``. The trailing ``.md`` is stripped so
    both spellings address the same note instead of failing a whole job run.
    """
    if not note_id or not note_id.strip():
        raise InvalidNoteId("note id must not be empty")
    text = note_id.strip().replace("\\", "/")
    if text.lower().endswith(NOTE_SUFFIX):
        text = text[: -len(NOTE_SUFFIX)]
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


def normalize_patterns(patterns: Iterable[str]) -> list[str]:
    """Strip + drop empties. Shared by config lists and the ignore file."""
    return [p for p in (str(p).strip() for p in patterns) if p]


def load_brainignore(root: Path) -> list[str]:
    """Patterns from ``<vault>/.brainignore`` (missing file = no rules).

    One pattern per line, ``#`` comments and blanks skipped. ``!`` negation
    is not supported (blocklist only) — such lines are skipped with a warning
    instead of failing every vault operation.
    """
    path = root / BRAINIGNORE_FILE
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
        return []
    kept = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    negated = [ln for ln in kept if ln.startswith("!")]
    if negated:
        log.warning("%s: negation (!) is not supported, skipping: %s", path, negated)
    return [ln for ln in kept if not ln.startswith("!")]


def pattern_matches(pattern: str, rel: str) -> bool:
    """Does a gitignore-style pattern match a vault-relative file path?

    ``rel`` always carries the ``.md`` suffix (``todo.md``, ``a/b.md``).
    A trailing ``/`` matches a whole directory; otherwise :class:`PurePath`
    matching applies (``*``, ``?``, ``[...]`` per segment, ``**`` across).
    No negation — blocklist only.
    """
    if pattern.endswith("/"):
        directory = pattern.rstrip("/")
        return rel == directory or rel.startswith(directory + "/")
    return PurePath(rel).match(pattern)


class Vault:
    """CRUD + search over a directory of markdown files."""

    def __init__(self, root: Path, ignore: Iterable[str] = ()) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # Union of config rules and the vault's own .brainignore file.
        # Re-read per construction (a Vault lives as long as one request),
        # so editing the file takes effect without a restart.
        self._ignore = normalize_patterns(ignore) + load_brainignore(root)

    def ignored_by(self, note_id: str) -> str | None:
        """First matching ignore rule for a note id, or ``None``."""
        rel = _validate(note_id) + NOTE_SUFFIX
        for pattern in self._ignore:
            if pattern_matches(pattern, rel):
                return pattern
        return None

    def _path(self, note_id: str) -> Path:
        rel = _validate(note_id)
        if (rule := self.ignored_by(note_id)) is not None:
            raise InvalidNoteId(
                f"note {note_id!r} is ignored "
                f"by vault ignore rule {rule!r}: un-ignore it to interact"
            )
        return self._contained(self.root / (rel + NOTE_SUFFIX))

    def _trash_path(self, note_id: str) -> Path:
        rel = _validate(note_id)
        return self._contained(self.root / TRASH_DIR / (rel + NOTE_SUFFIX))

    def _contained(self, path: Path) -> Path:
        """Reject a path that resolves outside the vault.

        ``_validate`` rejects ``..``, absolute and hidden segments, but it cannot
        see a symlink: ``sub/link -> /tmp`` made ``sub/link/note`` write *outside*
        the vault, and ``list_notes`` never showed it, so the note was real on
        disk yet invisible in the brain. The agent picks its own note ids, so
        "only act on the vault" has to be enforced here, not assumed.
        """
        target = path.resolve()
        root = self.root.resolve()
        if target != root and not target.is_relative_to(root):
            raise InvalidNoteId(f"{path.name!r} resolves outside the vault: {target}")
        return path

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
        """Soft-delete: move the note to ``.brain/trash/`` (restorable)."""
        path = self._path(note_id)
        if not path.is_file():
            raise NoteNotFound(f"note not found: {note_id!r}")
        target = self._trash_path(note_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)
        self._prune_empty_parents(path.parent)

    def restore(self, note_id: str) -> Note:
        """Move a trashed note back into the vault."""
        target = self._trash_path(note_id)
        if not target.is_file():
            raise NoteNotFound(f"no trashed note: {note_id!r}")
        dst = self._path(note_id)
        if dst.exists():
            raise NoteExists(f"note already exists: {note_id!r}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        target.rename(dst)
        self._prune_empty_parents(target.parent)
        return self.read(note_id)

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

    def append(self, note_id: str, content: str) -> Note:
        """Append content to the end of an existing note."""
        path = self._path(note_id)
        if not path.is_file():
            raise NoteNotFound(f"note not found: {note_id!r}")
        current = path.read_text(encoding="utf-8")
        glue = "" if current == "" or current.endswith("\n") else "\n"
        return self.update(note_id, current + glue + content)

    def patch(
        self, note_id: str, heading: str, content: str, mode: str = "replace"
    ) -> Note:
        """Replace (or append to) the section under an ATX heading.

        The section runs until the next heading of the same or higher level.
        """
        if mode not in ("replace", "append"):
            raise ValueError(f"unknown patch mode: {mode!r}")
        # Tool callers pass the heading as it appears in the file ("## Setup");
        # compare on the text, so the hashes are optional. Hashes inside a name
        # ("C# setup") survive: only a leading run is removed.
        name = heading.strip().lstrip("#").strip()
        if not name:
            raise ValueError("heading must not be empty")
        note = self.read(note_id)
        lines = note.content.split("\n")
        head_idx = -1
        level = 0
        for i, line in enumerate(lines):
            match = _HEADING_RE.match(line)
            if match and match.group(2).strip() == name:
                head_idx = i
                level = len(match.group(1))
                break
        if head_idx < 0:
            raise SectionNotFound(f"no heading {name!r} in {note_id!r}")
        end = len(lines)
        for j in range(head_idx + 1, len(lines)):
            match = _HEADING_RE.match(lines[j])
            if match and len(match.group(1)) <= level:
                end = j
                break
        new_body = content.split("\n")
        if new_body and new_body[-1] == "":
            new_body.pop()
        section = (
            new_body if mode == "replace" else lines[head_idx + 1 : end] + new_body
        )
        text = "\n".join(lines[: head_idx + 1] + section + lines[end:])
        if not text.endswith("\n"):
            text += "\n"
        return self.update(note_id, text)

    def get_frontmatter(self, note_id: str) -> dict[str, object]:
        """The note's YAML frontmatter (``{}`` when absent)."""
        meta, _ = split_frontmatter(self.read(note_id).content)
        return meta

    def set_frontmatter(self, note_id: str, updates: dict[str, object | None]) -> Note:
        """Merge keys into the frontmatter (``None`` deletes a key)."""
        note = self.read(note_id)
        meta, body = split_frontmatter(note.content)
        for key, value in updates.items():
            if value is None:
                meta.pop(key, None)
            else:
                meta[key] = value
        if meta:
            text = (
                "---\n"
                + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
                + "---\n"
                + body
            )
        else:
            text = body
        return self.update(note_id, text)

    def get_tags(self, note_id: str) -> list[str]:
        """Frontmatter tags, ``#``-stripped. Supports lists and strings."""
        raw: object = self.get_frontmatter(note_id).get("tags", [])
        if isinstance(raw, list):
            items: list[Any] = cast("list[Any]", raw)
        else:
            items = re.split(r"[,\s]+", str(raw))
        return [str(t).lstrip("#").strip() for t in items if str(t).strip(" #")]

    def search_tags(self, tag: str) -> list[str]:
        """Notes carrying a frontmatter tag (case-insensitive)."""
        needle = tag.strip().lstrip("#").lower()
        if not needle:
            return []
        return [
            i
            for i in self.list_notes()
            if needle in [t.lower() for t in self.get_tags(i)]
        ]

    def get_outgoing(self, note_id: str) -> list[str]:
        """``[[link]]`` targets used by a note (``alias`` part dropped)."""
        content = self.read(note_id).content
        return sorted({m.group(1).strip() for m in _LINK_RE.finditer(content)})

    def get_backlinks(self, note_id: str) -> list[str]:
        """Notes linking to this one (exact id or trailing-segment match)."""
        target = "/".join(Path(_validate(note_id)).parts)
        found: list[str] = []
        for cand in self.list_notes():
            if cand == target:
                continue
            for link in self.get_outgoing(cand):
                if link == target or target.endswith("/" + link):
                    found.append(cand)
                    break
        return sorted(found)

    def _prune_empty_parents(self, directory: Path) -> None:
        while directory != self.root and directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent

    def list_notes(
        self, prefix: str = "", limit: int | None = None, offset: int = 0
    ) -> list[str]:
        """All note ids, sorted. Optional path-prefix filter and pagination."""
        ids = sorted(
            p.relative_to(self.root).as_posix()[: -len(NOTE_SUFFIX)]
            for p in self.root.rglob(f"*{NOTE_SUFFIX}")
            if p.is_file()
            and not self._is_internal(p)
            and not self._ignored_file(p.relative_to(self.root).as_posix())
        )
        if prefix:
            norm = prefix.strip().replace("\\", "/").rstrip("/")
            ids = [i for i in ids if i == norm or i.startswith(norm + "/")]
        if offset:
            ids = ids[offset:]
        if limit is not None:
            ids = ids[:limit]
        return ids

    def list_directory(self, prefix: str = "") -> dict[str, list[str]]:
        """Direct children of a folder: subfolder paths + note ids."""
        norm = prefix.strip().replace("\\", "/").rstrip("/")
        if norm:
            _validate(norm + "/x")
        base = self.root if not norm else self.root / norm
        folders: list[str] = []
        notes: list[str] = []
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.name.startswith("."):
                    continue
                rel = child.relative_to(self.root).as_posix()
                if child.is_dir():
                    # A folder is hidden when its contents would be: probe it.
                    if self._ignored_file(rel + "/.ignore-probe" + NOTE_SUFFIX):
                        continue
                    folders.append(rel)
                elif child.suffix == NOTE_SUFFIX:
                    if self._ignored_file(rel):
                        continue
                    notes.append(rel[: -len(NOTE_SUFFIX)])
        return {"folders": folders, "notes": notes}

    def _ignored_file(self, rel: str) -> bool:
        """Match a vault-relative file path (with suffix) against the rules."""
        return any(pattern_matches(p, rel) for p in self._ignore)

    def _is_internal(self, path: Path) -> bool:
        parts = path.relative_to(self.root).parts
        return any(
            part in INTERNAL_DIRS or part.startswith(".") for part in parts[:-1]
        ) or path.name.startswith(".")

    def search_names(self, query: str) -> list[str]:
        """Case-insensitive substring match on note ids."""
        needle = query.strip().lower()
        if not needle:
            return []
        return [i for i in self.list_notes() if needle in i.lower()]

    def search_content(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> list[SearchHit]:
        """Full-text search via ripgrep, with a pure-Python fallback."""
        needle = query.strip()
        if not needle:
            return []
        if shutil.which("rg") is not None:
            try:
                return self._search_ripgrep(needle, limit + offset)[offset:]
            except (OSError, subprocess.SubprocessError):
                pass
        return self._search_fallback(needle, limit + offset)[offset:]

    def _ignore_globs(self) -> list[str]:
        """Ignore rules as ripgrep ``--glob`` exclusions (prefilter; the
        post-filter below stays authoritative, so glob dialect differences
        cannot leak an ignored note)."""
        globs: list[str] = []
        for pattern in self._ignore:
            if pattern.endswith("/"):
                globs.append(pattern + "**")
            else:
                globs.append(pattern)
        return globs

    def _search_ripgrep(self, query: str, limit: int) -> list[SearchHit]:
        args = [
            "rg",
            "--no-heading",
            "--line-number",
            "--max-count",
            "3",
            "--glob",
            "*.md",
            "--glob",
            "!.brain/**",
        ]
        for glob in self._ignore_globs():
            args += ["--glob", "!" + glob]
        proc = subprocess.run(
            [
                *args,
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
            match = _RG_LINE_RE.match(line)
            if not match:
                continue
            file_path = self.root / match.group(1)
            if file_path.suffix != NOTE_SUFFIX or self._is_internal(file_path):
                continue
            rel = file_path.relative_to(self.root).as_posix()
            if self._ignored_file(rel):
                continue
            note_id = rel[: -len(NOTE_SUFFIX)]
            hits.setdefault(note_id, []).append(match.group(3).strip()[:200])
            if len(hits) >= limit:
                break
        ordered = sorted(hits.items())[:limit]
        return [SearchHit(id=k, excerpts=v) for k, v in ordered]

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
