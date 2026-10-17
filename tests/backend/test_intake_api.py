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

_VALID_BODY = {
    "caller_name": "Test Caller",
    "phone_1": "418-555-0001",
    "civic": "1580",
    "street": "Perigord",
    "apartment": "101",
    "city": "Quebec",
    "access": "yes",
    "has_animals": False,
    "problem": "Robinet qui coule dans la cuisine.",
}


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


def test_coordinator_can_create(ac):
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=_VALID_BODY)
    assert r.status_code == 201
    body = r.json()
    assert "request_id" in body
    assert body["match_status"] == "exact"
    assert body["building_id"] is not None
    assert body["unit_id"] is not None


def test_director_can_create(ac):
    r = ac(_user(_DIR, "director")).post("/api/v1/intake", json=_VALID_BODY)
    assert r.status_code == 201


def test_technician_cannot_create(ac):
    r = ac(_user(_TECH, "technician")).post("/api/v1/intake", json=_VALID_BODY)
    assert r.status_code == 403


def test_contractor_cannot_create(ac):
    r = ac(_user(_CONT, "contractor")).post("/api/v1/intake", json=_VALID_BODY)
    assert r.status_code == 403


def test_missing_problem_422(ac):
    body = {**_VALID_BODY}
    del body["problem"]
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=body)
    assert r.status_code == 422


def test_no_match_address_returns_201(ac):
    payload = {**_VALID_BODY, "civic": "9999", "street": "Inventee", "apartment": None}
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=payload)
    assert r.status_code == 201
    resp = r.json()
    assert resp["match_status"] == "no_match"
    assert resp["building_id"] is None
    assert resp["unit_id"] is None


def test_manual_create_writes_raw_caller_body(ac, db_conn):
    """Manual intake stores raw_caller_body jsonb with original caller-provided values."""
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=_VALID_BODY)
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
    body = {**_VALID_BODY, "has_animals": True, "animal_details": "Un chien de berger"}
    r = ac(_user(_COORD, "coordinator")).post("/api/v1/intake", json=body)
    assert r.status_code == 201
    rid = r.json()["request_id"]
    row = db_conn.execute(
        "SELECT problems, animals FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    assert row["animals"] == "Oui"
    assert "Un chien de berger" in row["problems"]
