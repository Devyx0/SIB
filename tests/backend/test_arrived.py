"""POST /tasks/{id}/arrived — on-site stamp between en_route and closeout."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.tasks.repository import insert_task

_TECH = 24
_OTHER_TECH = 14
_COORD = 4


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


@pytest.fixture
def building(db_conn):
    return db_conn.execute(
        "SELECT building_id FROM building WHERE adresse IS NOT NULL LIMIT 1"
    ).fetchone()


def _mk_task(db_conn, building_id, *, status="scheduled") -> int:
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, raw_title) "
        "VALUES ('open', %s, 'Arrivée test') RETURNING request_id",
        [building_id],
    ).fetchone()["request_id"]
    now = datetime.now(timezone.utc)
    return insert_task(
        db_conn, request_id=rid, description="Plomberie", status=status,
        assigned_employee_id=_TECH, due_at=now, source="dispatcher", accepted_at=now,
    )["task_id"]


def test_arrived_from_en_route(ac, db_conn, building):
    tid = _mk_task(db_conn, building["building_id"])
    tech = ac(_user(_TECH, "technician"))
    assert tech.post(f"/api/v1/tasks/{tid}/en-route", json={
        "current_status": "scheduled", "lat": 45.5, "lng": -73.5,
    }).status_code == 200

    r = tech.post(f"/api/v1/tasks/{tid}/arrived", json={
        "current_status": "en_route", "lat": 45.51, "lng": -73.51,
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "arrived"

    v = db_conn.execute(
        "SELECT arrived_at, arrived_lat, arrived_lng FROM request_visit WHERE task_id = %s",
        [tid],
    ).fetchone()
    assert v["arrived_at"] is not None
    assert float(v["arrived_lat"]) == pytest.approx(45.51)
    assert float(v["arrived_lng"]) == pytest.approx(-73.51)

    prov = db_conn.execute(
        "SELECT previous_value, ingested_value FROM data_provenance "
        "WHERE target_table = 'dispatch_task' AND target_pk = %s AND target_column = 'status' "
        "ORDER BY provenance_id DESC LIMIT 1", [str(tid)],
    ).fetchone()
    assert (prov["previous_value"], prov["ingested_value"]) == ("en_route", "arrived")


def test_arrived_not_en_route_409(ac, db_conn, building):
    tid = _mk_task(db_conn, building["building_id"])
    r = ac(_user(_TECH, "technician")).post(f"/api/v1/tasks/{tid}/arrived", json={})
    assert r.status_code == 409


def test_arrived_without_open_visit_409(ac, db_conn, building):
    tid = _mk_task(db_conn, building["building_id"], status="en_route")
    r = ac(_user(_TECH, "technician")).post(f"/api/v1/tasks/{tid}/arrived", json={})
    assert r.status_code == 409
    assert "Aucune visite en cours" in r.json()["error"]["message"]


def test_arrived_stale_status_409(ac, db_conn, building):
    tid = _mk_task(db_conn, building["building_id"])
    tech = ac(_user(_TECH, "technician"))
    assert tech.post(f"/api/v1/tasks/{tid}/en-route", json={}).status_code == 200
    r = tech.post(f"/api/v1/tasks/{tid}/arrived", json={"current_status": "scheduled"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_arrived_coordinator_403(ac, db_conn, building):
    tid = _mk_task(db_conn, building["building_id"], status="en_route")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/tasks/{tid}/arrived", json={})
    assert r.status_code == 403


def test_arrived_other_tech_403(ac, db_conn, building):
    tid = _mk_task(db_conn, building["building_id"], status="en_route")
    r = ac(_user(_OTHER_TECH, "technician")).post(f"/api/v1/tasks/{tid}/arrived", json={})
    assert r.status_code == 403
