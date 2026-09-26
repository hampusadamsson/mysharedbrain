"""SQLite storage: one database per vault, forward-only migrations.

Notes stay markdown files on disk — that *is* the product. SQLite holds the
sidecar state (audit log, capture queue) where partial writes, concurrent
readers and real ``UPDATE`` semantics (reviewing a queue entry) want
transactions rather than an append-only text fold.

Layout: ``<root>/.brain/brain.db``. WAL mode adds ``-wal``/``-shm`` sidecars;
all three live under ``.brain/`` and are never notes.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DB_FILE = Path(".brain/brain.db")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def vault_root() -> Path:
    """The vault directory: ``$VAULT_DIR`` (default ``./vault``), resolved.

    Lives here because it decides where ``.brain/brain.db`` goes, and both the
    service layer and the settings store need the same answer.
    """
    return Path(os.environ.get("VAULT_DIR", "vault")).resolve()


_KEEPERS: dict[str, sqlite3.Connection] = {}
_KEEPERS_LOCK = threading.Lock()


def _memory_uri(root: Path) -> str:
    """Shared-cache memory URI, one cache per vault root."""
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return f"file:mysharedbrain-{digest}?mode=memory&cache=shared"


class Database:
    """Handle to one vault's database file. Migrates on every connect.

    Connections are cheap and short-lived: open, use, close. This keeps the
    service layer free of connection lifecycle and safe under threads.

    When the file database cannot be opened (read-only filesystem, a file
    blocking ``.brain/``, …) every operation falls back to a shared
    in-memory database instead of failing. The fallback is loud (a warning)
    and pinned: once engaged it stays for the process, so state never splits
    between disk and memory. Memory state dies with the process — this is a
    survival path for sidecar state (audit, capture, settings), not storage.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / DB_FILE
        self._memory = False

    @property
    def in_memory(self) -> bool:
        """Has this handle pinned to the memory fallback?"""
        return self._memory

    def connect(self) -> sqlite3.Connection:
        """Open a tuned connection and bring the schema up to date."""
        if self._memory:
            return self._mem_connect()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, isolation_level=None)
        except (OSError, sqlite3.Error) as exc:
            log.warning(
                "database %s unavailable (%s): using in-memory state, lost on restart",
                self.path,
                exc,
            )
            self._memory = True
            return self._mem_connect()
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        migrate(conn)
        return conn

    def _mem_connect(self) -> sqlite3.Connection:
        """A connection into this vault's shared memory cache.

        ``:memory:`` dies with its connection, so a process-wide keeper per
        vault root holds the shared cache open; per-operation connections
        come and go like the file ones. (WAL is a no-op on memory tables —
        the pragma just reports back ``memory``.)
        """
        uri = _memory_uri(self.root)
        with _KEEPERS_LOCK:
            keeper = _KEEPERS.get(uri)
            if keeper is None:
                keeper = sqlite3.connect(uri, uri=True, isolation_level=None)
                _KEEPERS[uri] = keeper
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        migrate(conn)
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        """Read path: autocommitted statements, no explicit transaction."""
        conn = self.connect()
        try:
            yield conn
        finally:
            self._close(conn)

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Write path: all-or-nothing."""
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    @staticmethod
    def _close(conn: sqlite3.Connection) -> None:
        """Hand the connection back, keeping the planner's statistics fresh.

        ``PRAGMA optimize`` is SQLite's own recommendation for a long-lived
        database: it re-runs ANALYZE only where the data has changed enough to
        matter, so index choice does not degrade as the log grows. It is usually
        a no-op, and never fatal — a read must not fail because of it.
        """
        with contextlib.suppress(sqlite3.Error):
            conn.execute("PRAGMA optimize")
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    """Apply pending ``NNNN_name.sql`` migrations in order, forward-only.

    Every file runs exactly once; the applied version is recorded so the next
    connect skips it. Never edit a shipped migration — add a new one.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_version"
    ).fetchone()
    current = int(row["version"])
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        # One transaction per file: DDL is transactional in SQLite, so a
        # failure leaves nothing half-applied.
        conn.executescript(f"BEGIN;\n{sql}\nCOMMIT;")
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (version, _now()),
        )
