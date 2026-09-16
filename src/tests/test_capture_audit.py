"""TDD: capture queue lifecycle + audit trail."""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain import audit, capture


def test_submit_queues_pending_entry(vault_dir: Path) -> None:
    entry = capture.submit(vault_dir, kind="edit", body="fix ip", note_id="homelab")
    assert entry.status == "pending"
    assert entry.kind == "edit"
    assert entry.id
    assert capture.list_entries(vault_dir) == [entry]


def test_submit_rejects_empty_body(vault_dir: Path) -> None:
    with pytest.raises(ValueError):
        capture.submit(vault_dir, kind="missing", body="  ")


def test_submit_rejects_unknown_kind(vault_dir: Path) -> None:
    with pytest.raises(ValueError):
        capture.submit(vault_dir, kind="nope", body="x")  # type: ignore[typeddict-item]
    with pytest.raises(ValueError):
        # old name for the "edit" kind
        capture.submit(vault_dir, kind="correction", body="x")  # type: ignore[typeddict-item]


def test_list_entries_filters_by_status(vault_dir: Path) -> None:
    first = capture.submit(vault_dir, kind="missing", body="need gpu docs")
    capture.review(vault_dir, first.id, "rejected", "curator")
    capture.submit(vault_dir, kind="request", body="what is argo?")
    assert len(capture.list_entries(vault_dir, "pending")) == 1
    assert len(capture.list_entries(vault_dir, "rejected")) == 1


def test_review_supports_approved_verdict(vault_dir: Path) -> None:
    entry = capture.submit(vault_dir, kind="request", body="fetch x")
    reviewed = capture.review(
        vault_dir, entry.id, "approved", "curator", "valid, fetch later"
    )
    assert reviewed.status == "approved"
    assert capture.list_entries(vault_dir, "approved") == [reviewed]


def test_review_rejects_unknown_and_double_review(vault_dir: Path) -> None:
    with pytest.raises(capture.EntryNotFound):
        capture.review(vault_dir, "missing", "applied", "curator")
    entry = capture.submit(vault_dir, kind="request", body="q")
    capture.review(vault_dir, entry.id, "applied", "curator", "looks right")
    with pytest.raises(capture.EntryAlreadyReviewed):
        capture.review(vault_dir, entry.id, "rejected", "curator")


def test_capture_log_is_append_only(vault_dir: Path) -> None:
    first = capture.submit(vault_dir, kind="request", body="q1")
    second = capture.submit(vault_dir, kind="request", body="q2")
    capture.review(vault_dir, first.id, "approved", "curator")
    entries = capture.list_entries(vault_dir)
    assert [(e.id, e.status) for e in entries] == [
        (first.id, "approved"),
        (second.id, "pending"),
    ]
    # legacy single-line format (pre-append-only) still folds
    legacy = vault_dir / ".brain" / "capture.jsonl"
    with legacy.open("a", encoding="utf-8") as fh:
        fh.write(
            '{"id": "old1", "ts": "t", "kind": "request", "body": "old", "note_id": "", "status": "applied", "reviewer": "c", "review_note": ""}\n'
        )
    assert capture.list_entries(vault_dir, "applied")[0].id == "old1"


def test_audit_appends_and_reads_newest_first(vault_dir: Path) -> None:
    assert audit.read_log(vault_dir) == []
    audit.append(vault_dir, actor="mcp", action="create", note_id="a")
    audit.append(vault_dir, actor="curator", action="update", note_id="a", detail="fix")
    log = audit.read_log(vault_dir)
    assert [e.action for e in log] == ["update", "create"]
    assert log[0].actor == "curator"
    assert all(e.ts for e in log)
