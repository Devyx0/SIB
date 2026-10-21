"""POST /api/v1/tasks/{id}/follow-up — coordinator-spawned follow-up task."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.tasks.repository import get_task, insert_task, maybe_close_request

_COORD = 4
_TECH = 14


@pytest.fixture
def ac(app, db_conn):
    def _factory(employee_id: int, *roles: str) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            employee_id=employee_id, roles=frozenset(roles))
        return TestClient(app, raise_server_exceptions=False)
    yield _factory
    app.dependency_overrides.clear()


def _mk_request(db_conn, status="open") -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, raw_title, building_id, sector_id) "
        "VALUES (%(s)s::request_status, 'Appel suivi', 3, 1) RETURNING request_id",
        {"s": status},
    ).fetchone()["request_id"]


def _parent(db_conn, rid, status="needs_expertise", **kw) -> dict:
    return insert_task(
        db_conn, request_id=rid, description="Fuite toiture", status=status,
        source="dispatcher", accepted_at="2026-10-22T12:00:00Z", **kw,
    )


def _post(ac, task_id, body=None, employee=_COORD, role="coordinator"):
    return ac(employee, role).post(f"/api/v1/tasks/{task_id}/follow-up", json=body or {})


@pytest.mark.parametrize("status", ["needs_expertise", "return_visit", "done"])
def test_follow_up_defaults(ac, db_conn, status):
    rid = _mk_request(db_conn)
    parent = _parent(db_conn, rid, status)
    before = datetime.now(timezone.utc)
    r = _post(ac, parent["task_id"])
    assert r.status_code == 200, r.text
    child = r.json()
    assert child["source"] == "follow_up"
    assert child["parent_task_id"] == parent["task_id"]
    assert child["request_id"] == rid
    assert child["description"] == "Fuite toiture"
    assert child["status"] == "queued"
    assert child["accepted_at"] is not None
    due = datetime.fromisoformat(child["due_at"])
    assert timedelta(days=13, hours=23) < due - before < timedelta(days=14, minutes=1)
    assert get_task(db_conn, parent["task_id"])["status"] == status  # unchanged


def test_follow_up_custom_body(ac, db_conn):
    rid = _mk_request(db_conn)
    parent = _parent(db_conn, rid)
    due = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    r = _post(ac, parent["task_id"], {"due_at": due.isoformat(), "description": "  Revoir le solin "})
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Revoir le solin"
    assert datetime.fromisoformat(r.json()["due_at"]) == due


def test_follow_up_resolves_parent_for_auto_close(ac, db_conn):
    rid = _mk_request(db_conn)
    parent = _parent(db_conn, rid)
    assert maybe_close_request(db_conn, rid) is False
    child = _post(ac, parent["task_id"]).json()
    assert maybe_close_request(db_conn, rid) is False  # child is open
    db_conn.execute("UPDATE dispatch_task SET status='done' WHERE task_id=%s", [child["task_id"]])
    assert maybe_close_request(db_conn, rid) is True


@pytest.mark.parametrize("status", ["queued", "scheduled", "en_route", "arrived", "working", "cancelled"])
def test_follow_up_refused_for_other_statuses(ac, db_conn, status):
    rid = _mk_request(db_conn)
    parent = _parent(db_conn, rid, status)
    r = _post(ac, parent["task_id"])
    assert r.status_code == 409
    assert get_task(db_conn, parent["task_id"])["status"] == status


def test_follow_up_unknown_and_proposal(ac, db_conn):
    assert _post(ac, 999_999).status_code == 404
    rid = _mk_request(db_conn)
    proposal = insert_task(db_conn, request_id=rid, description="IA", source="ai_recommended",
                           accepted_at=None, status="needs_expertise")
    assert _post(ac, proposal["task_id"]).status_code == 404


def test_follow_up_on_closed_call(ac, db_conn):
    rid = _mk_request(db_conn, "closed")
    parent = _parent(db_conn, rid, "done")
    assert _post(ac, parent["task_id"]).status_code == 409


def test_follow_up_coordinator_only(ac, db_conn):
    rid = _mk_request(db_conn)
    parent = _parent(db_conn, rid)
    assert _post(ac, parent["task_id"], employee=_TECH, role="technician").status_code == 403


def test_follow_up_blank_description_rejected(ac, db_conn):
    rid = _mk_request(db_conn)
    parent = _parent(db_conn, rid)
    assert _post(ac, parent["task_id"], {"description": "   "}).status_code == 422


def test_follow_up_writes_provenance(ac, db_conn):
    rid = _mk_request(db_conn)
    parent = _parent(db_conn, rid)
    child = _post(ac, parent["task_id"]).json()
    cols = {r["target_column"] for r in db_conn.execute(
        "SELECT target_column FROM data_provenance WHERE target_table='dispatch_task' "
        "AND target_pk=%s", [str(child["task_id"])]).fetchall()}
    assert {"due_at", "status"} <= cols
