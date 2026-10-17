"""Tests for POST /api/v1/requests/{id}/route."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

_COORD = 4
_TECH  = 14
_CONT  = 20
_BLDG  = 3
_SECTOR = 1
_DATE_A = str(date.today() + timedelta(days=5))


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


def _insert(db_conn, status="triaged", source_calendar=None) -> int:
    row = db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, sector_id, start_date, source_calendar)
        VALUES (%(s)s, %(b)s, %(sec)s, %(d)s, %(cal)s)
        RETURNING request_id
        """,
        {"s": status, "b": _BLDG, "sec": _SECTOR, "d": _DATE_A, "cal": source_calendar},
    ).fetchone()
    return row["request_id"]


def test_route_to_st_maj_returns_200(ac, db_conn):
    rid = _insert(db_conn)
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj"},
    )
    assert r.status_code == 200
    assert r.json()["source_calendar"] == "st_maj"


def test_route_to_main_returns_200(ac, db_conn):
    rid = _insert(db_conn)
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "main"},
    )
    assert r.status_code == 200
    assert r.json()["source_calendar"] == "main"


def test_route_writes_provenance(ac, db_conn):
    rid = _insert(db_conn, source_calendar=None)
    ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj"},
    )
    row = db_conn.execute(
        "SELECT target_column, previous_value, ingested_value FROM data_provenance WHERE target_pk = %s AND target_column = 'source_calendar'",
        [str(rid)],
    ).fetchone()
    assert row is not None
    assert row["previous_value"] is None
    assert row["ingested_value"] == "st_maj"


def test_closed_route_returns_409(ac, db_conn):
    rid = _insert(db_conn, status="closed")
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REQUEST_CLOSED"


def test_reroute_allowed(ac, db_conn):
    """Re-routing from main → st_maj on already-routed request is allowed."""
    rid = _insert(db_conn, source_calendar="main")
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj"},
    )
    assert r.status_code == 200


def test_expected_calendar_stale_409(ac, db_conn):
    """expected_source_calendar mismatch → 409 STALE_DATA."""
    rid = _insert(db_conn, source_calendar="main")
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj", "expected_source_calendar": "st_maj"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_expected_calendar_matches_passes(ac, db_conn):
    rid = _insert(db_conn, source_calendar="main")
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj", "expected_source_calendar": "main"},
    )
    assert r.status_code == 200


def test_technician_returns_403(ac, db_conn):
    rid = _insert(db_conn)
    r = ac(_user(_TECH, "technician")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj"},
    )
    assert r.status_code == 403


def test_contractor_returns_403(ac, db_conn):
    rid = _insert(db_conn)
    r = ac(_user(_CONT, "contractor")).post(
        f"/api/v1/requests/{rid}/route",
        json={"source_calendar": "st_maj"},
    )
    assert r.status_code == 403


def test_board_search_accent_insensitive(db_conn):
    """unaccent(): 'Belanger' and 'Bélanger' must return identical row counts."""
    from backend.modules.requests.repository import list_requests

    db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, raw_title)
        VALUES ('intake_received', %(b)s, %(sec)s, 'Demande Bélanger')
        """,
        {"b": _BLDG, "sec": _SECTOR},
    )

    kwargs = dict(
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
        status=[],
        building_id=None,
        sector_id=None,
        assigned_employee_id=None,
        urgency=None,
        source_calendar="unrouted",
        sort_by="start_date",
        sort_dir="asc",
        limit=200,
        offset=0,
        scope_sql="",
        scope_params={},
    )

    total_plain, _ = list_requests(db_conn, q="Belanger", **kwargs)
    total_accented, _ = list_requests(db_conn, q="Bélanger", **kwargs)

    assert total_plain >= 1
    assert total_accented == total_plain
