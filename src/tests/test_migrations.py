"""TDD: forward-only migrations, including upgrades of existing databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mysharedbrain.db import DB_FILE, Database

_LEGACY_AUDIT = """
CREATE TABLE audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    note_id TEXT NOT NULL DEFAULT '',
    detail  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE capture_entries (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT NOT NULL UNIQUE,
    ts          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    body        TEXT NOT NULL,
    note_id     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    reviewer    TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
INSERT INTO schema_version (version, applied_at) VALUES (1, 't'), (2, 't');
INSERT INTO audit_log (ts, actor, action, note_id, detail) VALUES
    ('t', 'api', 'read', 'a', ''),
    ('t', 'api', 'find', 'a', 'query:x'),
    ('t', 'api', 'update', 'a', ''),
    ('t', 'api', 'move', 'a', 'from b'),
    ('t', 'api', 'delete', 'a', ''),
    ('t', 'mcp', 'capture-applied', 'a', ''),
    ('t', 'librarian', 'job-ok', '', 'job:sweep'),
    ('t', 'api', 'mystery', 'a', '');
INSERT INTO capture_entries (id, ts, kind, body, status) VALUES
    ('auto1', 't', 'request', 'Unanswered question: what is argo?', 'pending'),
    ('human1', 't', 'request', 'please document argo', 'pending');
"""


_MIGRATION_COUNT = len(
    list(
        (Path(__file__).resolve().parents[1] / "mysharedbrain" / "migrations").glob(
            "*.sql"
        )
    )
)


def test_fresh_database_gets_the_full_schema(tmp_path: Path) -> None:
    with Database(tmp_path).connection() as conn:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        version = conn.execute(
            "SELECT MAX(version) AS v FROM schema_version"
        ).fetchone()
    assert {
        "audit_log",
        "capture_entries",
        "job_runs",
        "schema_version",
        "settings",
    } <= tables
    assert int(version["v"]) == _MIGRATION_COUNT


def test_settings_table_holds_exactly_one_document(tmp_path: Path) -> None:
    """The CHECK keeps the store to a single row, so there is never a "which
    settings row wins?" question."""
    from mysharedbrain.settings_store import SettingsStore

    store = SettingsStore(tmp_path)
    store.save({"agent": {"model": "first"}})
    store.save({"agent": {"model": "second"}})

    with Database(tmp_path).connection() as conn:
        rows = conn.execute("SELECT id, document FROM settings").fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO settings (id, document, updated_at) VALUES (2, '{}', 't')"
            )
    assert store.get().document["agent"]["model"] == "second"  # type: ignore[union-attr]


def test_stored_settings_are_json_in_one_column(tmp_path: Path) -> None:
    """Not a file, not jsonl: one row of JSON that a transaction protects."""
    import json

    from mysharedbrain.settings_store import SettingsStore

    SettingsStore(tmp_path).save({"agent": {"model": "m"}, "jobs": []})
    with Database(tmp_path).connection() as conn:
        raw = conn.execute("SELECT document, updated_at FROM settings").fetchone()
    assert json.loads(str(raw["document"])) == {"agent": {"model": "m"}, "jobs": []}
    assert raw["updated_at"]


def test_0003_backfills_kind_for_rows_written_before_it(tmp_path: Path) -> None:
    path = tmp_path / DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_LEGACY_AUDIT)
    conn.commit()
    conn.close()

    with Database(tmp_path).connection() as upgraded:
        rows = upgraded.execute(
            "SELECT action, kind FROM audit_log ORDER BY id"
        ).fetchall()
    assert [(r["action"], r["kind"]) for r in rows] == [
        ("read", "read"),
        ("find", "find"),
        ("update", "write"),
        ("move", "move"),
        ("delete", "delete"),
        ("capture-applied", "capture"),
        ("job-ok", "job"),
        ("mystery", "other"),
    ]


def test_0004_reclassifies_automated_questions(tmp_path: Path) -> None:
    """Open questions filed before the 'question' kind are migrated and tagged."""
    path = tmp_path / DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_LEGACY_AUDIT)
    conn.commit()
    conn.close()

    with Database(tmp_path).connection() as upgraded:
        rows = upgraded.execute(
            "SELECT id, kind, automated FROM capture_entries ORDER BY id"
        ).fetchall()
    # the machine-filed question is reclassified and tagged ...
    assert (rows[0]["id"], rows[0]["kind"], rows[0]["automated"]) == (
        "auto1",
        "question",
        1,
    )
    # ... a person's request is left exactly as it was
    assert (rows[1]["id"], rows[1]["kind"], rows[1]["automated"]) == (
        "human1",
        "request",
        0,
    )


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    """Connecting twice must not re-apply anything (or blow up on ALTER)."""
    for _ in range(3):
        with Database(tmp_path).connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, actor, action, kind, note_id, detail)"
                " VALUES ('t', 'api', 'read', 'read', 'a', '')"
            )
    with Database(tmp_path).connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()
        versions = conn.execute("SELECT COUNT(*) AS n FROM schema_version").fetchone()
    assert int(row["n"]) == 3
    assert int(versions["n"]) == _MIGRATION_COUNT  # one row per applied migration
