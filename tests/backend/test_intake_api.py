"""Tests for POST /api/v1/intake (manual create)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

_COORD = 4
_DIR   = 5
_TECH  = 14
_CONT  = 20


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


def _perigord(db_conn) -> dict:
    """Resolve 1580 Perigord building + a known unit for picker-only create."""
    bldg = db_conn.execute(
        "SELECT building_id, sector_id FROM building WHERE adresse ILIKE '%1580%Perigord%' LIMIT 1"
    ).fetchone()
    assert bldg is not None, "seed building 1580 Perigord required"
    unit = db_conn.execute(
        """
        SELECT unit_id FROM unit
        WHERE building_id = %(bid)s AND numero_appartement = '101'
        LIMIT 1
        """,
        {"bid": bldg["building_id"]},
    ).fetchone()
    return {
        "building_id": bldg["building_id"],
        "sector_id": bldg["sector_id"],
        "unit_id": unit["unit_id"] if unit else None,
    }


def _valid_body(db_conn, **overrides) -> dict:
    loc = _perigord(db_conn)
    body = {
        "caller_name": "Test Caller",
        "phone_1": "418-555-0001",
        "building_id": loc["building_id"],
        "unit_id": loc["unit_id"],
        "access": "yes",
        "animals": "non",
        "problem": "Robinet qui coule dans la cuisine.",
        "category": "Plomberie",
    }
    body.update(overrides)
    return body


def _ensure_coord_sector(db_conn, sector_id: int) -> None:
    """Give coordinator 4 a sector so sector-scoped create succeeds."""
    db_conn.execute(
        "UPDATE employee SET sector_id = %(sid)s WHERE employee_id = %(eid)s",
        {"sid": sector_id, "eid": _COORD},
    )


@pytest.fixture
def ac(app, db_conn):
    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)
    yield _factory
    app.dependency_overrides.clear()


def test_coordinator_can_create(ac, db_conn):
    loc = _perigord(db_conn)
    _ensure_coord_sector(db_conn, loc["sector_id"])
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=_valid_body(db_conn))
    assert r.status_code == 201
    body = r.json()
    assert "request_id" in body
    assert body["match_status"] == "exact"
    assert body["building_id"] == loc["building_id"]
    assert body["unit_id"] == loc["unit_id"]
    row = db_conn.execute(
        "SELECT sector_id, status FROM maintenance_request WHERE request_id = %s",
        [body["request_id"]],
    ).fetchone()
    assert row["sector_id"] == loc["sector_id"]


def test_director_can_create(ac, db_conn):
    r = ac(_user(_DIR, "director")).post("/api/v1/intake", json=_valid_body(db_conn))
    assert r.status_code == 201


def test_technician_cannot_create(ac, db_conn):
    r = ac(_user(_TECH, "technician")).post("/api/v1/intake", json=_valid_body(db_conn))
    assert r.status_code == 403


def test_contractor_cannot_create(ac, db_conn):
    r = ac(_user(_CONT, "contractor")).post("/api/v1/intake", json=_valid_body(db_conn))
    assert r.status_code == 403


def test_missing_problem_422(ac, db_conn):
    body = _valid_body(db_conn)
    del body["problem"]
    loc = _perigord(db_conn)
    _ensure_coord_sector(db_conn, loc["sector_id"])
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=body)
    assert r.status_code == 422


def test_missing_building_id_422(ac, db_conn):
    body = _valid_body(db_conn)
    del body["building_id"]
    r = ac(_user(_DIR, "director")).post("/api/v1/intake", json=body)
    assert r.status_code == 422


def test_coordinator_blocked_outside_sector(ac, db_conn):
    loc = _perigord(db_conn)
    other = db_conn.execute(
        """
        SELECT sector_id FROM sector
        WHERE sector_id IS DISTINCT FROM %(sid)s
        LIMIT 1
        """,
        {"sid": loc["sector_id"]},
    ).fetchone()
    if other is None:
        pytest.skip("need a second sector")
    _ensure_coord_sector(db_conn, other["sector_id"])
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=_valid_body(db_conn))
    assert r.status_code == 403


def test_coordinator_with_no_sector_can_list_all_sectors(ac, db_conn):
    """Coords without employee.sector_id must still see the sector picker."""
    db_conn.execute(
        "UPDATE employee SET sector_id = NULL WHERE employee_id = %(eid)s",
        {"eid": _COORD},
    )
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/lookup/sectors")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_building_only_without_unit(ac, db_conn):
    loc = _perigord(db_conn)
    _ensure_coord_sector(db_conn, loc["sector_id"])
    body = _valid_body(db_conn, unit_id=None)
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=body)
    assert r.status_code == 201
    assert r.json()["match_status"] == "building_only"
    assert r.json()["unit_id"] is None


def test_manual_create_writes_raw_caller_body(ac, db_conn):
    loc = _perigord(db_conn)
    _ensure_coord_sector(db_conn, loc["sector_id"])
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=_valid_body(db_conn))
    assert r.status_code == 201
    rid = r.json()["request_id"]
    row = db_conn.execute(
        "SELECT raw_caller_body FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    body = row["raw_caller_body"]
    assert body is not None
    assert "problems" in body
    assert "entry_permission" in body
    assert "animals" in body


def test_animals_bundled_in_problems(ac, db_conn):
    loc = _perigord(db_conn)
    _ensure_coord_sector(db_conn, loc["sector_id"])
    body = _valid_body(db_conn, animals="oui", animal_details="Un chien de berger")
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=body)
    assert r.status_code == 201
    rid = r.json()["request_id"]
    row = db_conn.execute(
        "SELECT problems, animals FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    assert row["animals"] == "Oui"
    assert "Un chien de berger" in row["problems"]


def test_missing_phone_422(ac, db_conn):
    body = _valid_body(db_conn)
    del body["phone_1"]
    r = ac(_user(_DIR, "director")).post("/api/v1/intake", json=body)
    assert r.status_code == 422


def test_yes_instructions_requires_details(ac, db_conn):
    body = _valid_body(db_conn, access="yes_instructions", access_details=None)
    r = ac(_user(_DIR, "director")).post("/api/v1/intake", json=body)
    assert r.status_code == 422


def test_category_and_secondary_persisted(ac, db_conn):
    loc = _perigord(db_conn)
    _ensure_coord_sector(db_conn, loc["sector_id"])
    body = _valid_body(
        db_conn,
        category="Plomberie",
        secondary_name="Marie",
        secondary_email="marie@example.com",
        phone_2="418-555-0002",
    )
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=body)
    assert r.status_code == 201
    rid = r.json()["request_id"]
    row = db_conn.execute(
        "SELECT category_raw, problems FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    assert row["category_raw"] == "Plomberie"
    assert "Marie" in row["problems"]
    assert "marie@example.com" in row["problems"]
    assert "418-555-0002" in row["problems"]
