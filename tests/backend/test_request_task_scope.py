"""Request read scope + tenant PII follow accepted dispatch_task assignees."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.tasks.repository import insert_task

_TECH_OTHER_SECTOR = 11   # sector 6 — building 3 (sector 1) is outside their scope
_CONT = 20                # contractor


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
def call(db_conn) -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, raw_title, building_id, sector_id, "
        "caller_name, caller_phone, caller_email) "
        "VALUES ('open', 'Appel portée', 3, 1, 'Locataire Test', '418-555-0101', 'loc@example.com') "
        "RETURNING request_id",
    ).fetchone()["request_id"]


def _task(db_conn, rid: int, employee_id: int, *, accepted: bool = True) -> None:
    insert_task(
        db_conn, request_id=rid, description="Plomberie", assigned_employee_id=employee_id,
        source="dispatcher" if accepted else "ai_recommended",
        accepted_at="2026-10-22T12:00:00Z" if accepted else None,
    )


def test_contractor_with_accepted_task_sees_call_and_contacts(ac, db_conn, call):
    _task(db_conn, call, _CONT)
    r = ac(_user(_CONT, "contractor")).get(f"/api/v1/requests/{call}")
    assert r.status_code == 200
    body = r.json()
    assert body["caller_phone"] == "418-555-0101"
    assert body["caller_email"] == "loc@example.com"


def test_contractor_task_call_in_list(ac, db_conn, call):
    _task(db_conn, call, _CONT)
    r = ac(_user(_CONT, "contractor")).get("/api/v1/requests?status=open&limit=200")
    assert r.status_code == 200
    ids = {i["request_id"] for i in r.json()["items"] + r.json()["unscheduled_items"]}
    assert call in ids


def test_contractor_proposal_task_does_not_grant_scope(ac, db_conn, call):
    _task(db_conn, call, _CONT, accepted=False)
    r = ac(_user(_CONT, "contractor")).get(f"/api/v1/requests/{call}")
    assert r.status_code == 404


def test_contractor_without_task_is_404(ac, call):
    r = ac(_user(_CONT, "contractor")).get(f"/api/v1/requests/{call}")
    assert r.status_code == 404


def test_technician_task_assignee_outside_sector_sees_call_and_contacts(ac, db_conn, call):
    _task(db_conn, call, _TECH_OTHER_SECTOR)
    r = ac(_user(_TECH_OTHER_SECTOR, "technician")).get(f"/api/v1/requests/{call}")
    assert r.status_code == 200
    assert r.json()["caller_name"] == "Locataire Test"


def test_technician_without_task_outside_sector_is_404(ac, call):
    r = ac(_user(_TECH_OTHER_SECTOR, "technician")).get(f"/api/v1/requests/{call}")
    assert r.status_code == 404


def test_task_assignee_can_add_log(ac, db_conn, call):
    _task(db_conn, call, _CONT)
    r = ac(_user(_CONT, "contractor")).post(
        f"/api/v1/requests/{call}/log", json={"entry_text": "Note du sous-traitant"},
    )
    assert r.status_code == 200
