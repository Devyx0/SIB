"""Dispatch actions against an en_route call (fix ticket 2026-10-19):
assign/unassign blocked with REQUEST_EN_ROUTE; everything else allowed and
leaves the open visit untouched."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.core.utils import today_local

_TECH = 24
_OTHER_TECH = 14
_COORD = 4

_EN_ROUTE_MSG = "Appel en cours — le technicien doit d'abord clôturer"
_JUSTIF = {"text": "Justification de test valide", "input_method": "typed"}


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


@pytest.fixture
def en_route_call(ac, db_conn, building):
    """Request taken en route by tech 24 — open visit. Returns (coord_client, rid)."""
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, assigned_employee_id, raw_title) "
        "VALUES ('triaged', %s, %s, 'Appel en cours') RETURNING request_id",
        [building["building_id"], _TECH],
    ).fetchone()["request_id"]
    tech = ac(_user(_TECH, "technician"))
    r = tech.post(f"/api/v1/requests/{rid}/en-route",
                  json={"current_status": "triaged", "current_start_date": None,
                        "lat": None, "lng": None})
    assert r.status_code == 200
    return ac(_user(_COORD, "coordinator")), rid


def _visit_still_open(db_conn, rid) -> bool:
    row = db_conn.execute(
        "SELECT closeout_at FROM request_visit WHERE request_id = %s", [rid]
    ).fetchone()
    return row is not None and row["closeout_at"] is None


# ── Blocked: assign / unassign ─────────────────────────────────────────────────

def test_reassign_en_route_is_409(en_route_call):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/assign", json={
        "employee_id": _OTHER_TECH, "current_assigned_employee_id": _TECH,
        "current_start_date": None, "current_urgency_tier": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "REQUEST_EN_ROUTE"
    assert err["message"] == _EN_ROUTE_MSG


def test_unassign_en_route_is_409(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/assign", json={
        "employee_id": None, "current_assigned_employee_id": _TECH,
        "current_start_date": None, "current_urgency_tier": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REQUEST_EN_ROUTE"
    # Assignment untouched, visit still open.
    row = db_conn.execute(
        "SELECT assigned_employee_id FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    assert row["assigned_employee_id"] == _TECH
    assert _visit_still_open(db_conn, rid)


# ── Still allowed on en_route ──────────────────────────────────────────────────

def test_reschedule_en_route_allowed(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/reschedule", json={
        "start_date": str(today_local()), "current_start_date": None,
        "current_assigned_employee_id": _TECH, "current_urgency_tier": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, rid)


def test_set_urgency_en_route_allowed(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "AJD", "current_urgency_tier": None,
        "current_assigned_employee_id": _TECH, "current_start_date": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, rid)


def test_set_follow_up_date_en_route_allowed(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/follow-up-date", json={
        "next_follow_up_date": str(today_local()), "current_next_follow_up_date": None,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, rid)


def test_set_next_steps_en_route_allowed(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/next-steps", json={
        "next_steps": "Vérifier le drain", "current_next_steps": None,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, rid)


def test_set_cost_en_route_allowed(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/cost", json={
        "estimated_cost": 125.5, "current_estimated_cost": None,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, rid)


def test_add_log_en_route_allowed(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/log", json={"entry_text": "Note du coordonnateur"})
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, rid)


def test_route_en_route_allowed(en_route_call, db_conn):
    coord, rid = en_route_call
    r = coord.post(f"/api/v1/requests/{rid}/route", json={
        "source_calendar": "main", "expected_source_calendar": None,
    })
    assert r.status_code == 200, r.text
    assert _visit_still_open(db_conn, rid)


# ── Unblocked after closeout ───────────────────────────────────────────────────

def test_reassign_works_after_closeout(en_route_call, ac, db_conn):
    coord, rid = en_route_call
    tech = ac(_user(_TECH, "technician"))
    pid = tech.post(f"/api/v1/requests/{rid}/photos", content=b"x" * 64,
                    headers={"Content-Type": "image/jpeg"}).json()["attachment_id"]
    # Outcome 2 keeps the call his and returns status to triaged.
    r = tech.post(f"/api/v1/requests/{rid}/closeout", json={
        "outcome": "partial_reschedule", "comment": "Je reviens demain finir le travail.",
        "input_method": "typed", "attachment_ids": [pid],
        "next_date": str(today_local()), "urgent": False,
        "current_status": "en_route", "lat": None, "lng": None,
    })
    assert r.status_code == 200, r.text

    # Re-create the coordinator client: the ac factory's user override is
    # app-global, and the tech client above replaced it.
    coord = ac(_user(_COORD, "coordinator"))
    r = coord.post(f"/api/v1/requests/{rid}/assign", json={
        "employee_id": _OTHER_TECH, "current_assigned_employee_id": _TECH,
        "current_start_date": str(today_local()), "current_urgency_tier": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    assert r.json()["assigned_employee_id"] == _OTHER_TECH
