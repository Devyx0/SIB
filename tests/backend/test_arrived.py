"""POST /requests/{id}/arrived — on-site stamp between en_route and closeout."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

_TECH = 24
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


def test_arrived_from_en_route(ac, db_conn, building):
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, assigned_employee_id, raw_title) "
        "VALUES ('scheduled', %s, %s, 'Arrivée test') RETURNING request_id",
        [building["building_id"], _TECH],
    ).fetchone()["request_id"]
    tech = ac(_user(_TECH, "technician"))
    assert tech.post(f"/api/v1/requests/{rid}/en-route", json={
        "current_status": "scheduled", "current_start_date": None,
        "lat": 45.5, "lng": -73.5,
    }).status_code == 200

    r = tech.post(f"/api/v1/requests/{rid}/arrived", json={
        "current_status": "en_route", "lat": 45.51, "lng": -73.51,
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "arrived"
    assert r.json()["arrived_at"] is not None

    v = db_conn.execute(
        "SELECT arrived_at, arrived_lat, arrived_lng FROM request_visit WHERE request_id = %s",
        [rid],
    ).fetchone()
    assert v["arrived_at"] is not None
    assert float(v["arrived_lat"]) == pytest.approx(45.51)
    assert float(v["arrived_lng"]) == pytest.approx(-73.51)


def test_arrived_not_en_route_409(ac, db_conn, building):
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, assigned_employee_id, raw_title) "
        "VALUES ('scheduled', %s, %s, 'Pas en route') RETURNING request_id",
        [building["building_id"], _TECH],
    ).fetchone()["request_id"]
    r = ac(_user(_TECH, "technician")).post(f"/api/v1/requests/{rid}/arrived", json={
        "current_status": "scheduled", "lat": None, "lng": None,
    })
    assert r.status_code == 409


def test_arrived_coordinator_403(ac, db_conn, building):
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, assigned_employee_id, raw_title) "
        "VALUES ('en_route', %s, %s, 'Coord') RETURNING request_id",
        [building["building_id"], _TECH],
    ).fetchone()["request_id"]
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/arrived", json={
        "current_status": "en_route", "lat": None, "lng": None,
    })
    assert r.status_code == 403
