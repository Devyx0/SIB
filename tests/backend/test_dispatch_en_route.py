"""Dispatch actions while a task is en route (fix ticket 2026-10-19, ported to tasks):
reassign/reschedule of the en-route task blocked; assigning a tech who is en
route elsewhere blocked with ASSIGNEE_EN_ROUTE; call-level actions still
allowed and leave the open visit untouched."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.core.utils import today_local
from backend.modules.tasks.repository import insert_task

_TECH = 24
_OTHER_TECH = 14
_COORD = 4

_JUSTIF = {"text": "Justification de test valide", "input_method": "typed"}
_DUE = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat()


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


@pytest.fixture
def ac(app, db_conn):
    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_storage(monkeypatch):
    monkeypatch.setattr("backend.modules.requests.storage.upload_photo",
                        lambda path, content, mime: None)
    monkeypatch.setattr("backend.modules.requests.storage.create_signed_url",
                        lambda path, expires_in_seconds=300: f"https://signed.local/{path}")


@pytest.fixture
def building(db_conn):
    return db_conn.execute(
        "SELECT building_id FROM building WHERE adresse IS NOT NULL LIMIT 1"
    ).fetchone()


def _mk_call(db_conn, building_id, title="Appel en cours") -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, raw_title) "
        "VALUES ('open', %s, %s) RETURNING request_id",
        [building_id, title],
    ).fetchone()["request_id"]


def _mk_task(db_conn, rid, *, emp=_TECH, status="scheduled") -> int:
    now = datetime.now(timezone.utc)
    return insert_task(
        db_conn, request_id=rid, description="Plomberie", status=status,
        assigned_employee_id=emp, due_at=now if emp else None,
        source="dispatcher", accepted_at=now,
    )["task_id"]


def _go(ac, tech_id, tid):
    r = ac(_user(tech_id, "technician")).post(f"/api/v1/tasks/{tid}/en-route", json={})
    assert r.status_code == 200, r.text


@pytest.fixture
def en_route_call(ac, db_conn, building):
    """Task taken en route by tech 24 — open visit. Returns (coord_client, rid, tid)."""
    rid = _mk_call(db_conn, building["building_id"])
    tid = _mk_task(db_conn, rid)
    _go(ac, _TECH, tid)
    return ac(_user(_COORD, "coordinator")), rid, tid


def _visit_still_open(db_conn, tid) -> bool:
    row = db_conn.execute(
        "SELECT closeout_at FROM request_visit WHERE task_id = %s", [tid]
    ).fetchone()
    return row is not None and row["closeout_at"] is None


# ── Blocked: move the en-route task ────────────────────────────────────────────

def test_reassign_en_route_task_is_409(en_route_call, db_conn):
    coord, _, tid = en_route_call
    r = coord.post(f"/api/v1/tasks/{tid}/assign", json={
        "assigned_employee_id": _OTHER_TECH, "justification": _JUSTIF,
    })
    assert r.status_code == 409
    assert db_conn.execute(
        "SELECT assigned_employee_id FROM dispatch_task WHERE task_id = %s", [tid],
    ).fetchone()["assigned_employee_id"] == _TECH
    assert _visit_still_open(db_conn, tid)


def test_reschedule_en_route_task_is_409(en_route_call, db_conn):
    coord, _, tid = en_route_call
    r = coord.post(f"/api/v1/tasks/{tid}/schedule", json={
        "due_at": _DUE, "justification": _JUSTIF,
    })
    assert r.status_code == 409
    assert _visit_still_open(db_conn, tid)


# ── Still allowed on the call ──────────────────────────────────────────────────

def test_set_urgency_en_route_allowed(en_route_call, db_conn):
    coord, rid, tid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "URGENT", "current_urgency_tier": None,
        "current_assigned_employee_id": None, "current_start_date": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, tid)


def test_set_follow_up_date_en_route_allowed(en_route_call, db_conn):
    coord, rid, tid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/follow-up-date", json={
        "next_follow_up_date": str(today_local()), "current_next_follow_up_date": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, tid)


def test_set_next_steps_en_route_allowed(en_route_call, db_conn):
    coord, rid, tid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/next-steps", json={
        "next_steps": "Vérifier le drain", "current_next_steps": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, tid)


def test_set_cost_en_route_allowed(en_route_call, db_conn):
    coord, rid, tid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/cost", json={
        "estimated_cost": 125.5, "current_estimated_cost": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, tid)


def test_add_log_en_route_allowed(en_route_call, db_conn):
    coord, rid, tid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/log", json={"entry_text": "Note du coordonnateur"})
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, tid)


def test_route_en_route_allowed(en_route_call, db_conn):
    coord, rid, tid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/route", json={
        "source_calendar": "main", "expected_source_calendar": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, tid)


# ── Blocked: assign TO a tech who is en route elsewhere ────────────────────────

def test_assign_task_to_en_route_tech_is_409(en_route_call, ac, db_conn, building):
    coord, _, busy_tid = en_route_call
    other_tid = _mk_task(db_conn, _mk_call(db_conn, building["building_id"], "Autre"), emp=None,
                         status="queued")
    r = coord.post(f"/api/v1/tasks/{other_tid}/assign", json={
        "assigned_employee_id": _TECH, "justification": _JUSTIF,
    })
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "ASSIGNEE_EN_ROUTE"
    assert "en route" in err["message"].lower()
    assert db_conn.execute(
        "SELECT assigned_employee_id FROM dispatch_task WHERE task_id = %s", [other_tid],
    ).fetchone()["assigned_employee_id"] is None

    # Unassign is never blocked.
    r = coord.post(f"/api/v1/tasks/{other_tid}/assign", json={
        "assigned_employee_id": None, "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text


def test_create_task_for_en_route_tech_is_409(en_route_call, db_conn, building):
    coord, _, _ = en_route_call
    rid = _mk_call(db_conn, building["building_id"], "Nouvel appel")
    r = coord.post("/api/v1/tasks", json={
        "request_id": rid, "description": "Peinture", "assigned_employee_id": _TECH,
        "due_at": _DUE, "justification": _JUSTIF,
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ASSIGNEE_EN_ROUTE"


def test_assign_other_tech_while_one_en_route_ok(en_route_call, db_conn, building):
    coord, _, _ = en_route_call
    other_tid = _mk_task(db_conn, _mk_call(db_conn, building["building_id"], "Autre"), emp=None,
                         status="queued")
    r = coord.post(f"/api/v1/tasks/{other_tid}/assign", json={
        "assigned_employee_id": _OTHER_TECH, "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text


# ── Unblocked after closeout ───────────────────────────────────────────────────

def test_assign_works_after_closeout(en_route_call, ac, db_conn, building):
    _, rid, tid = en_route_call
    tech = ac(_user(_TECH, "technician"))
    assert tech.post(f"/api/v1/tasks/{tid}/arrived", json={}).status_code == 200
    pid = tech.post(f"/api/v1/requests/{rid}/photos", content=b"x" * 64,
                    headers={"Content-Type": "image/jpeg"}).json()["attachment_id"]
    r = tech.post(f"/api/v1/tasks/{tid}/closeout", json={
        "outcome": "partial_reschedule", "comment": "Je reviens demain finir le travail.",
        "input_method": "typed", "attachment_ids": [pid],
        "next_date": str(today_local()), "urgent": False, "lat": None, "lng": None,
    })
    assert r.status_code == 200, r.text
    follow_up_id = r.json()["follow_up_task"]["task_id"]

    # Re-create the coordinator client: the ac factory's user override is
    # app-global, and the tech client above replaced it.
    coord = ac(_user(_COORD, "coordinator"))
    other_tid = _mk_task(db_conn, _mk_call(db_conn, building["building_id"], "Autre"), emp=None,
                         status="queued")
    r = coord.post(f"/api/v1/tasks/{other_tid}/assign", json={
        "assigned_employee_id": _TECH, "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    # The spawned follow-up can be handed to someone else.
    r = coord.post(f"/api/v1/tasks/{follow_up_id}/assign", json={
        "assigned_employee_id": _OTHER_TECH, "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert r.json()["assigned_employee_id"] == _OTHER_TECH
