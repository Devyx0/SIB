"""GET /api/v1/analytics/utilization — closed via closed_at, else start_date for imports."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.core.utils import today_local

_TECH = 24
_COORD = 4
_CONTRACTOR = 20


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
        "SELECT building_id, sector_id FROM building WHERE sector_id IS NOT NULL LIMIT 1"
    ).fetchone()


def _range_q():
    today = today_local()
    start = today - timedelta(days=6)
    return f"start_date={start.isoformat()}&end_date={today.isoformat()}"


def test_utilization_403_technician(ac):
    r = ac(_user(_TECH, "technician")).get(f"/api/v1/analytics/utilization?{_range_q()}")
    assert r.status_code == 403


def test_utilization_requires_dates(ac):
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/utilization")
    assert r.status_code == 422 or r.status_code == 400


def test_utilization_rejects_over_31_days(ac):
    today = today_local()
    start = today - timedelta(days=40)
    r = ac(_user(_COORD, "coordinator")).get(
        f"/api/v1/analytics/utilization?start_date={start.isoformat()}&end_date={today.isoformat()}"
    )
    assert r.status_code in (400, 422)


def test_import_closed_counts_via_start_date(ac, db_conn, building):
    """Gravity/import closed rows (closed_at NULL) count via start_date."""
    today = today_local()
    before = db_conn.execute(
        "SELECT count(*)::int AS n FROM maintenance_request "
        "WHERE assigned_employee_id = %(e)s AND status::text = 'closed' "
        "AND start_date BETWEEN %(a)s AND %(b)s AND closed_at IS NULL",
        {"e": _TECH, "a": today - timedelta(days=6), "b": today},
    ).fetchone()["n"]
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date, closed_at) "
        "VALUES ('closed', %(b)s, %(s)s, %(e)s, 'Import closed', %(d)s, NULL)",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    )
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/analytics/utilization?{_range_q()}")
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["employee_id"] == _TECH)
    assert row["calls_closed"] >= before + 1
    assert row["calls_assigned"] >= 1


def test_closed_at_counts(ac, db_conn, building):
    today = today_local()
    now = datetime.now(timezone.utc)
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date, closed_at) "
        "VALUES ('closed', %(b)s, %(s)s, %(e)s, 'App closeout', %(d)s, %(ca)s)",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH,
         "d": today, "ca": now},
    )
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/analytics/utilization?{_range_q()}")
    row = next(x for x in r.json()["rows"] if x["employee_id"] == _TECH)
    assert row["calls_closed"] >= 1


def test_planned_midpoints_and_footnote(ac, db_conn, building):
    today = today_local()
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date, time_estimate_bucket) "
        "VALUES ('triaged', %(b)s, %(s)s, %(e)s, 'Plan mid', %(d)s, 'UNDER_30_MIN')",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    )
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/analytics/utilization?{_range_q()}")
    body = r.json()
    assert body["planned_footnote"] == "estimation provisoire"
    assert body["capacity_enabled"] is False
    assert body["capacity_hours_per_day"] is None
    row = next(x for x in body["rows"] if x["employee_id"] == _TECH)
    assert row["planned_minutes"] >= 20
    assert row["utilization_pct"] is None
    assert row["capacity_minutes"] is None


def test_visit_minutes_and_outcome_mix(ac, db_conn, building):
    today = today_local()
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date) "
        "VALUES ('closed', %(b)s, %(s)s, %(e)s, 'Visit util', %(d)s) RETURNING request_id",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    ).fetchone()["request_id"]
    en = datetime.now(timezone.utc) - timedelta(hours=2)
    clo = datetime.now(timezone.utc) - timedelta(hours=1)
    db_conn.execute(
        "INSERT INTO request_visit (request_id, employee_id, en_route_at, closeout_at, outcome) "
        "VALUES (%(r)s, %(e)s, %(era)s, %(ca)s, 'complete')",
        {"r": rid, "e": _TECH, "era": en, "ca": clo},
    )
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/analytics/utilization?{_range_q()}")
    row = next(x for x in r.json()["rows"] if x["employee_id"] == _TECH)
    assert row["visits_count"] >= 1
    assert row["visit_minutes"] >= 50  # ~60 min
    assert row["outcome_mix"]["complete"] >= 1


def test_includes_active_techs_with_zeros(ac):
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/analytics/utilization?{_range_q()}")
    assert r.status_code == 200
    ids = {x["employee_id"] for x in r.json()["rows"]}
    assert _TECH in ids  # active technician in sib_test


def test_no_tenant_fields(ac):
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/analytics/utilization?{_range_q()}")
    blob = r.text.lower()
    assert "caller" not in blob
    assert "appartement" not in blob
    assert "phone" not in blob
