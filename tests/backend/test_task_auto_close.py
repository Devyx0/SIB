"""Task repository + auto-close of the Service Call (maintenance_request)."""
from __future__ import annotations

import pytest

from backend.modules.tasks.repository import (
    get_task,
    insert_task,
    list_tasks_for_request,
    maybe_close_request,
    update_task_status,
)


def _mk_request(db_conn, status="open") -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, raw_title) "
        "VALUES (%(s)s::request_status, 'Appel auto-close') RETURNING request_id",
        {"s": status},
    ).fetchone()["request_id"]


def _status(db_conn, request_id) -> str:
    return db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %(r)s",
        {"r": request_id},
    ).fetchone()["s"]


def _accepted(db_conn, request_id, description="Réparer", **kw) -> int:
    kw.setdefault("accepted_at", "2026-10-22T12:00:00Z")
    return insert_task(db_conn, request_id=request_id, description=description, **kw)["task_id"]


@pytest.fixture
def open_call_with_one_task(db_conn):
    rid = _mk_request(db_conn)
    return rid, _accepted(db_conn, rid)


@pytest.fixture
def open_call_with_two_tasks(db_conn):
    rid = _mk_request(db_conn)
    return rid, _accepted(db_conn, rid, "Plomberie", sort_order=0), _accepted(
        db_conn, rid, "Plancher", sort_order=1
    )


# ── repository ────────────────────────────────────────────────────────────────

def test_insert_get_list_update(db_conn):
    rid = _mk_request(db_conn)
    b = insert_task(db_conn, request_id=rid, description="B", sort_order=1)
    a = insert_task(db_conn, request_id=rid, description="A", sort_order=0, source="ai_recommended")
    assert b["status"] == "queued" and b["accepted_at"] is None and b["source"] == "dispatcher"
    assert get_task(db_conn, a["task_id"])["source"] == "ai_recommended"
    assert get_task(db_conn, 0) is None
    assert [t["description"] for t in list_tasks_for_request(db_conn, rid)] == ["A", "B"]
    assert update_task_status(db_conn, a["task_id"], "scheduled")["status"] == "scheduled"


def test_insert_rejects_unknown_field(db_conn):
    rid = _mk_request(db_conn)
    with pytest.raises(ValueError):
        insert_task(db_conn, request_id=rid, description="x", bogus=1)


def test_update_missing_task_raises(db_conn):
    with pytest.raises(KeyError):
        update_task_status(db_conn, 0, "done")


# ── auto-close ────────────────────────────────────────────────────────────────

def test_one_done_one_open_keeps_call_open(db_conn, open_call_with_two_tasks):
    rid, a, _b = open_call_with_two_tasks
    update_task_status(db_conn, a, "done")
    assert maybe_close_request(db_conn, rid) is False
    assert _status(db_conn, rid) == "open"


def test_all_done_closes_call(db_conn, open_call_with_two_tasks):
    rid, a, b = open_call_with_two_tasks
    update_task_status(db_conn, a, "done")
    update_task_status(db_conn, b, "done")
    assert maybe_close_request(db_conn, rid) is True
    assert _status(db_conn, rid) == "closed"
    assert db_conn.execute(
        "SELECT closed_at FROM maintenance_request WHERE request_id = %(r)s", {"r": rid}
    ).fetchone()["closed_at"] is not None
    assert maybe_close_request(db_conn, rid) is False  # already closed


def test_done_plus_cancelled_closes(db_conn, open_call_with_two_tasks):
    rid, a, b = open_call_with_two_tasks
    update_task_status(db_conn, a, "done")
    update_task_status(db_conn, b, "cancelled")
    assert maybe_close_request(db_conn, rid) is True


def test_all_cancelled_closes(db_conn, open_call_with_one_task):
    rid, a = open_call_with_one_task
    update_task_status(db_conn, a, "cancelled")
    assert maybe_close_request(db_conn, rid) is True


@pytest.mark.parametrize("blocking", ["needs_expertise", "return_visit"])
def test_blocking_status_prevents_close(db_conn, open_call_with_one_task, blocking):
    rid, a = open_call_with_one_task
    update_task_status(db_conn, a, blocking)
    assert maybe_close_request(db_conn, rid) is False
    assert _status(db_conn, rid) == "open"


@pytest.mark.parametrize("parent_status", ["needs_expertise", "return_visit"])
def test_followed_up_parent_resolved_when_child_done(db_conn, open_call_with_one_task, parent_status):
    rid, a = open_call_with_one_task
    update_task_status(db_conn, a, parent_status)
    child = _accepted(db_conn, rid, "Suivi", parent_task_id=a, source="follow_up")
    assert maybe_close_request(db_conn, rid) is False  # child still queued
    update_task_status(db_conn, child, "done")
    assert maybe_close_request(db_conn, rid) is True
    assert _status(db_conn, rid) == "closed"


def test_followed_up_parent_resolved_when_child_cancelled(db_conn, open_call_with_one_task):
    rid, a = open_call_with_one_task
    update_task_status(db_conn, a, "needs_expertise")
    child = _accepted(db_conn, rid, "Remplacement", parent_task_id=a)
    update_task_status(db_conn, child, "cancelled")
    assert maybe_close_request(db_conn, rid) is True


def test_follow_up_chain_closes_when_last_done(db_conn, open_call_with_one_task):
    rid, a = open_call_with_one_task
    update_task_status(db_conn, a, "return_visit")
    b = _accepted(db_conn, rid, "Retour 1", parent_task_id=a, source="follow_up")
    update_task_status(db_conn, b, "return_visit")
    assert maybe_close_request(db_conn, rid) is False  # b has no child yet
    c = _accepted(db_conn, rid, "Retour 2", parent_task_id=b, source="follow_up")
    update_task_status(db_conn, c, "done")
    assert maybe_close_request(db_conn, rid) is True


def test_proposal_child_does_not_resolve_parent(db_conn, open_call_with_one_task):
    rid, a = open_call_with_one_task
    update_task_status(db_conn, a, "return_visit")
    insert_task(db_conn, request_id=rid, description="Draft suivi", parent_task_id=a,
                source="ai_recommended")
    # Only a proposal points at the parent: still blocking (proposals block too).
    assert maybe_close_request(db_conn, rid) is False


def test_child_resolves_only_its_parent(db_conn, open_call_with_two_tasks):
    rid, a, b = open_call_with_two_tasks
    update_task_status(db_conn, a, "return_visit")
    update_task_status(db_conn, b, "needs_expertise")
    child = _accepted(db_conn, rid, "Suivi A", parent_task_id=a, source="follow_up")
    update_task_status(db_conn, child, "done")
    assert maybe_close_request(db_conn, rid) is False  # b never followed up


def test_remaining_proposal_blocks_close(db_conn, open_call_with_one_task):
    rid, a = open_call_with_one_task
    insert_task(db_conn, request_id=rid, description="Proposition", source="ai_recommended")
    update_task_status(db_conn, a, "done")
    assert maybe_close_request(db_conn, rid) is False


def test_proposals_only_does_not_close(db_conn):
    rid = _mk_request(db_conn)
    t = insert_task(db_conn, request_id=rid, description="Draft", status="cancelled")
    assert t["accepted_at"] is None
    assert maybe_close_request(db_conn, rid) is False


def test_no_tasks_does_not_close(db_conn):
    assert maybe_close_request(db_conn, _mk_request(db_conn)) is False


def test_non_open_call_untouched(db_conn):
    rid = _mk_request(db_conn, status="triage_proposal")
    update_task_status(db_conn, _accepted(db_conn, rid), "done")
    assert maybe_close_request(db_conn, rid) is False
    assert _status(db_conn, rid) == "triage_proposal"


def test_missing_request_returns_false(db_conn):
    assert maybe_close_request(db_conn, 0) is False
