"""TDD: capture queue lifecycle + audit trail (sqlite-backed stores)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mysharedbrain import tools as tools_module
from mysharedbrain.audit import KINDS as AUDIT_KINDS
from mysharedbrain.audit import AuditLog, kind_for
from mysharedbrain.capture import (
    KINDS,
    CaptureQueue,
    EntryAlreadyReviewed,
    EntryNotFound,
)
from mysharedbrain.protocols import AuditStore, CaptureStore
from mysharedbrain.tools import SCOPES, TOOLS


@pytest.fixture()
def queue(vault_dir: Path) -> CaptureQueue:
    return CaptureQueue(vault_dir)


@pytest.fixture()
def log(vault_dir: Path) -> AuditLog:
    return AuditLog(vault_dir)


def test_submit_queues_pending_entry(queue: CaptureQueue) -> None:
    entry = queue.submit(kind="edit", body="fix ip", note_id="homelab")
    assert entry.status == "pending"
    assert entry.kind == "edit"
    assert entry.id
    assert queue.list_entries() == [entry]


def test_submit_rejects_empty_body(queue: CaptureQueue) -> None:
    with pytest.raises(ValueError):
        queue.submit(kind="missing", body="  ")


def test_submit_rejects_unknown_kind(queue: CaptureQueue) -> None:
    with pytest.raises(ValueError):
        queue.submit(kind="nope", body="x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        # old name for the "edit" kind
        queue.submit(kind="correction", body="x")  # type: ignore[arg-type]


def test_question_is_a_kind_and_automated_is_metadata(queue: CaptureQueue) -> None:
    entry = queue.submit(kind="question", body="what is argo?", automated=True)
    assert (entry.kind, entry.automated) == ("question", True)
    assert set(KINDS) == {"edit", "missing", "request", "question"}
    # the flag round-trips as a real bool, not sqlite's 1
    stored = queue.get(entry.id)
    assert stored is not None
    assert stored.automated is True
    assert queue.list_entries()[0].automated is True


def test_automated_defaults_to_false(queue: CaptureQueue) -> None:
    entry = queue.submit(kind="edit", body="fix ip")
    assert entry.automated is False
    assert entry.kind == "edit"


def test_get_returns_none_for_unknown(queue: CaptureQueue) -> None:
    assert queue.get("missing") is None


def test_list_entries_filters_by_status(queue: CaptureQueue) -> None:
    first = queue.submit(kind="missing", body="need gpu docs")
    queue.review(first.id, "rejected", "curator")
    queue.submit(kind="request", body="what is argo?")
    assert len(queue.list_entries("pending")) == 1
    assert len(queue.list_entries("rejected")) == 1


def test_review_updates_status_in_place(queue: CaptureQueue) -> None:
    first = queue.submit(kind="request", body="q1")
    second = queue.submit(kind="request", body="q2")
    queue.review(first.id, "approved", "curator")
    assert [(e.id, e.status) for e in queue.list_entries()] == [
        (first.id, "approved"),
        (second.id, "pending"),
    ]


def test_restate_overrides_any_state(queue: CaptureQueue) -> None:
    entry = queue.submit(kind="edit", body="fix ip")
    queue.review(entry.id, "rejected", "curator")

    # resolved → resolved is exactly what review() forbids
    assert (
        queue.restate(entry.id, "applied", "curator", "reconsidered").status
        == "applied"
    )
    back = queue.restate(entry.id, "pending", "curator", "reopen")
    assert (back.status, back.reviewer, back.review_note) == (
        "pending",
        "curator",
        "reopen",
    )
    assert queue.count("pending") == 1


def test_restate_rejects_unknown_entry_and_status(queue: CaptureQueue) -> None:
    with pytest.raises(EntryNotFound):
        queue.restate("missing", "pending", "curator")
    entry = queue.submit(kind="edit", body="x")
    with pytest.raises(ValueError):
        queue.restate(entry.id, "nope", "curator")  # type: ignore[arg-type]


def test_check_kind_and_status_narrow_plain_strings() -> None:
    from mysharedbrain.capture import check_kind, check_status

    assert check_status("approved") == "approved"
    assert check_kind("question") == "question"
    with pytest.raises(ValueError, match="unknown status"):
        check_status("done")
    with pytest.raises(ValueError, match="unknown feedback kind"):
        check_kind("note")


def test_review_supports_approved_verdict(queue: CaptureQueue) -> None:
    entry = queue.submit(kind="request", body="fetch x")
    reviewed = queue.review(entry.id, "approved", "curator", "valid, fetch later")
    assert reviewed.status == "approved"
    assert queue.list_entries("approved") == [reviewed]


def test_review_rejects_unknown_and_double_review(queue: CaptureQueue) -> None:
    with pytest.raises(EntryNotFound):
        queue.review("missing", "applied", "curator")
    entry = queue.submit(kind="request", body="q")
    queue.review(entry.id, "applied", "curator", "looks right")
    with pytest.raises(EntryAlreadyReviewed):
        queue.review(entry.id, "rejected", "curator")


def test_review_rejects_unknown_verdict(queue: CaptureQueue) -> None:
    entry = queue.submit(kind="request", body="q")
    with pytest.raises(ValueError):
        queue.review(entry.id, "maybe", "curator")  # type: ignore[arg-type]


def test_list_entries_pages_and_counts(queue: CaptureQueue) -> None:
    ids = [queue.submit(kind="request", body=f"q{i}").id for i in range(5)]
    assert queue.count() == 5
    assert [e.id for e in queue.list_entries(limit=2)] == ids[:2]
    assert [e.id for e in queue.list_entries(limit=2, offset=2)] == ids[2:4]
    assert [e.id for e in queue.list_entries(limit=2, offset=4)] == ids[4:]
    assert queue.list_entries(limit=2, offset=99) == []


def test_count_respects_status_filter(queue: CaptureQueue) -> None:
    first = queue.submit(kind="request", body="q1")
    queue.submit(kind="request", body="q2")
    queue.review(first.id, "rejected", "curator")
    assert queue.count("pending") == 1
    assert queue.count("rejected") == 1
    assert [e.id for e in queue.list_entries("rejected", limit=1)] == [first.id]


def test_audit_appends_and_reads_newest_first(log: AuditLog) -> None:
    assert log.read_log() == []
    log.append(actor="mcp", action="create", note_id="a")
    log.append(actor="curator", action="update", note_id="a", detail="fix")
    entries = log.read_log()
    assert [e.action for e in entries] == ["update", "create"]
    assert entries[0].actor == "curator"
    assert all(e.ts for e in entries)


def test_audit_respects_limit(log: AuditLog) -> None:
    for i in range(5):
        log.append(actor="mcp", action="create", note_id=f"n{i}")
    assert len(log.read_log(limit=2)) == 2


def test_audit_pages_and_counts(log: AuditLog) -> None:
    for i in range(5):
        log.append(actor="mcp", action="create", note_id=f"n{i}")
    assert log.count() == 5
    first = log.read_log(limit=2)
    second = log.read_log(limit=2, offset=2)
    assert [e.note_id for e in first] == ["n4", "n3"]  # newest first
    assert [e.note_id for e in second] == ["n2", "n1"]
    assert log.read_log(limit=2, offset=99) == []


def test_kind_is_derived_from_action() -> None:
    assert kind_for("read") == "read"
    assert kind_for("find") == "find"
    assert kind_for("patch") == "write"
    assert kind_for("move") == "move"
    assert kind_for("restore") == "delete"
    assert kind_for("capture-applied") == "capture"
    assert kind_for("feedback") == "capture"
    assert kind_for("job-ok") == "job"
    assert kind_for("something-new") == "other"
    assert set(AUDIT_KINDS) == {
        "read",
        "find",
        "write",
        "move",
        "delete",
        "capture",
        "job",
        "other",
    }


def test_entries_carry_the_file_connection(log: AuditLog) -> None:
    entry = log.append(actor="api", action="read", note_id="projects/homelab")
    assert (entry.kind, entry.note_id) == ("read", "projects/homelab")
    assert log.read_log(note_id="projects/homelab") == [entry]
    assert log.read_log(note_id="other") == []
    assert log.count(note_id="projects/homelab") == 1


def test_log_filters_by_kind(log: AuditLog) -> None:
    log.append(actor="api", action="read", note_id="a")
    log.append(actor="api", action="update", note_id="a")
    log.append(actor="api", action="read", note_id="b")
    assert [e.action for e in log.read_log(kind="read")] == ["read", "read"]
    assert [e.action for e in log.read_log(kind="write")] == ["update"]
    assert log.count(kind="write") == 1
    assert log.read_log(note_id="a", kind="read")[0].note_id == "a"


def test_stats_group_by_kind_for_one_note(log: AuditLog) -> None:
    for _ in range(3):
        log.append(actor="api", action="read", note_id="a")
    log.append(actor="api", action="find", note_id="a")
    log.append(actor="api", action="patch", note_id="a")
    log.append(actor="api", action="read", note_id="b")
    stats = log.stats("a")
    assert stats.counts == {"read": 3, "find": 1, "write": 1}
    assert stats.total == 5
    assert stats.note_id == "a"
    assert log.stats("untouched").counts == {}


def test_stats_are_not_scoped_to_one_note_by_default(log: AuditLog) -> None:
    """Omitting the note is the whole-log view Activity uses."""
    log.append(actor="api", action="read", note_id="a")
    log.append(actor="api", action="read", note_id="b")
    log.append(actor="api", action="job-ok", note_id="")
    whole = log.stats()
    assert whole.note_id == ""
    assert whole.counts == {"read": 2, "job": 1}
    assert whole.total == 3
    assert whole.first_seen and whole.last_seen <= whole.last_seen


def test_state_survives_reconnect(queue: CaptureQueue, vault_dir: Path) -> None:
    entry = queue.submit(kind="request", body="q")
    reopened = CaptureQueue(vault_dir)
    assert reopened.get(entry.id) == entry


def test_backends_satisfy_protocols(vault_dir: Path) -> None:
    assert isinstance(AuditLog(vault_dir), AuditStore)
    assert isinstance(CaptureQueue(vault_dir), CaptureStore)


def test_every_tool_declares_a_vault_local_scope() -> None:
    """The librarian's reach is declared, not implied.

    A built-in tool may touch the notes or the vault's own capture queue
    (``.brain/brain.db``) — nothing else. If someone adds a tool that reaches
    further, it has to declare a scope this list does not contain, and this fails.
    """
    assert set(SCOPES) == {"vault", "capture"}
    assert TOOLS, "the registry should not be empty"
    for spec in TOOLS.values():
        assert spec.scope in SCOPES, f"{spec.name} has scope {spec.scope!r}"
        assert spec.description, f"{spec.name} needs a description for the UI"


def test_capture_tools_are_the_only_non_note_tools() -> None:
    capture = {name for name, spec in TOOLS.items() if spec.scope == "capture"}
    assert capture == {"list_capture", "review_capture", "give_feedback"}


def test_no_tool_runs_a_command() -> None:
    """No shell: the built-in tools are vault/capture calls, nothing else.

    The only ``subprocess`` in the package is ripgrep, in ``vault.py``.
    """
    import mysharedbrain

    package = Path(mysharedbrain.__file__).parent
    offenders = [
        path.name
        for path in package.glob("*.py")
        if "subprocess" in path.read_text(encoding="utf-8")
    ]
    assert offenders == ["vault.py"]
    assert "subprocess" not in Path(tools_module.__file__).read_text(encoding="utf-8")
