"""Indexes are a performance contract: assert the plans, not the index names.

Every query the service issues should stay a seek (or, for the two counter
summaries, be answered by an index alone). If a migration drops, reorders or
replaces an index, the plan changes — these tests fail instead of the vault
quietly getting slower as the log grows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain.db import Database


def plan(root: Path, sql: str, params: tuple[object, ...] = ()) -> str:
    """One line of EXPLAIN QUERY PLAN output, or all of them joined."""
    with Database(root).connection() as conn:
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return " / ".join(str(row["detail"]) for row in rows)


def indexes(root: Path, table: str) -> set[str]:
    with Database(root).connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
            (table,),
        ).fetchall()
    return {
        str(row["name"]) for row in rows if not str(row["name"]).startswith("sqlite_")
    }


def test_audit_indexes_ship_with_the_schema(tmp_path: Path) -> None:
    assert {
        "idx_audit_note",  # unfiltered file log, ordered
        "idx_audit_note_kind",  # file log filtered by kind + its count
        "idx_audit_kind",  # whole-log list filtered by kind
        "idx_audit_kind_ts",  # whole-log counter summary
    } <= indexes(tmp_path, "audit_log")


def test_capture_status_filter_stays_a_seek(tmp_path: Path) -> None:
    got = plan(
        tmp_path,
        "SELECT id FROM capture_entries WHERE status = ? ORDER BY seq LIMIT 20",
        ("pending",),
    )
    assert "USING INDEX idx_capture_status" in got
    assert "TEMP B-TREE" not in got, "status-filtered listing must not need a sort"


def test_file_log_with_kind_filter_seeks_both_columns(tmp_path: Path) -> None:
    got = plan(
        tmp_path,
        "SELECT ts FROM audit_log WHERE note_id = ? AND kind = ?"
        " ORDER BY id DESC LIMIT 20",
        ("a", "read"),
    )
    assert "idx_audit_note_kind" in got
    assert "note_id=? AND kind=?" in got, "must not filter one column then scan"


def test_file_log_counts_are_covered_by_the_index(tmp_path: Path) -> None:
    got = plan(
        tmp_path,
        "SELECT COUNT(*) FROM audit_log WHERE note_id = ? AND kind = ?",
        ("a", "read"),
    )
    assert "COVERING INDEX idx_audit_note_kind" in got


def test_per_file_counter_summary_needs_no_temp_btree(tmp_path: Path) -> None:
    got = plan(
        tmp_path,
        "SELECT kind, COUNT(*) FROM audit_log WHERE note_id = ? GROUP BY kind",
        ("a",),
    )
    assert "TEMP B-TREE" not in got, "GROUP BY kind is satisfied by the index order"


def test_whole_log_counter_summary_is_index_only(tmp_path: Path) -> None:
    got = plan(
        tmp_path,
        "SELECT kind, COUNT(*) AS n, MIN(ts) AS lo, MAX(ts) AS hi"
        " FROM audit_log GROUP BY kind",
    )
    assert "COVERING INDEX idx_audit_kind_ts" in got


def test_ordered_pages_do_not_sort(tmp_path: Path) -> None:
    """The two list views are `ORDER BY id DESC LIMIT`, served by the key/index."""
    for sql, params in (
        ("SELECT ts FROM audit_log ORDER BY id DESC LIMIT 20 OFFSET 40", ()),
        (
            "SELECT ts FROM audit_log WHERE note_id = ? ORDER BY id DESC LIMIT 20",
            ("a",),
        ),
        (
            "SELECT ts FROM audit_log WHERE kind = ? ORDER BY id DESC LIMIT 20",
            ("read",),
        ),
    ):
        got = plan(tmp_path, sql, params)
        assert "TEMP B-TREE" not in got, f"{sql} should not sort: {got}"


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        (
            "SELECT ts FROM audit_log WHERE note_id = ? ORDER BY id DESC LIMIT 20",
            ("a",),
        ),
        (
            "SELECT ts FROM audit_log WHERE kind = ? ORDER BY id DESC LIMIT 20",
            ("read",),
        ),
    ],
)
def test_no_full_table_scan_for_filtered_logs(
    tmp_path: Path, sql: str, params: tuple[object, ...]
) -> None:
    assert "SCAN audit_log" not in plan(tmp_path, sql, params)
