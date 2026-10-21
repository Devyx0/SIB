"""GET /api/v1/analytics/dashboard — coord/dir only, real aggregates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.core.utils import today_local
from backend.modules.analytics.constants import UNTRIAGED_STATUSES

_TECH = 24
_COORD = 4
_DIRECTOR = 5
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


def test_dashboard_403_technician(ac):
    r = ac(_user(_TECH, "technician")).get("/api/v1/analytics/dashboard")
    assert r.status_code == 403


def test_dashboard_403_contractor(ac):
    r = ac(_user(_CONTRACTOR, "contractor")).get("/api/v1/analytics/dashboard")
    assert r.status_code == 403


def test_dashboard_200_coordinator_shape(ac, db_conn, building, monkeypatch):
    from backend.core import config
    monkeypatch.setattr(config.settings, "WEATHER_ESCALATION_ENABLED", False)
    today = today_local()
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date, urgency_tier) "
        "VALUES ('scheduled', %(b)s, %(s)s, %(e)s, 'Dash today', %(d)s, 'URGENT')",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    )
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["as_of_date"] == today.isoformat()
    assert "today_by_status" in body
    assert any(x["status"] == "scheduled" and x["count"] >= 1 for x in body["today_by_status"])
    assert body["after_hours"] is None
    assert body["satisfaction"] is None
    assert body["weather"] is None  # flag forced off
    assert set(body["untriaged_statuses"]) == set(UNTRIAGED_STATUSES)
    # No tenant PII
    blob = r.text.lower()
    assert "caller" not in blob
    assert "phone" not in blob
    assert "loyer" not in blob


def test_dashboard_zero_vs_null_sources(ac):
    """Real zero stays 0; absent sources stay null (not 'Données non disponibles' in JSON)."""
    r = ac(_user(_DIRECTOR, "director")).get("/api/v1/analytics/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["queue_counts"]["a_router"] >= 0
    assert body["queue_counts"]["a_redispatcher"] >= 0
    assert body["after_hours"] is None
    assert body["satisfaction"] is None


def test_dashboard_queue_links(ac):
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    body = r.json()
    assert body["queue_counts"]["a_router_link"] == "/board?source_calendar=unrouted"
    assert body["queue_counts"]["a_redispatcher_link"] == "/board?redispatch=1"


def test_dashboard_territory_board_links(ac, db_conn, building):
    today = today_local()
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, raw_title, start_date) "
        "VALUES ('triaged', %(b)s, %(s)s, 'Terr link', %(d)s)",
        {"b": building["building_id"], "s": building["sector_id"], "d": today},
    )
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    body = r.json()
    row = next(x for x in body["by_territory"] if x["sector_id"] == building["sector_id"])
    assert f"sector_id={building['sector_id']}" in row["board_link"]
    assert "start_date=" in row["board_link"]
    assert "end_date=" in row["board_link"]
    assert row["board_link"].startswith("/board?")


def test_dashboard_active_includes_en_route(ac, db_conn, building):
    today = today_local()
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date) "
        "VALUES ('en_route', %(b)s, %(s)s, %(e)s, 'En route active', %(d)s)",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    )
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    row = next(x for x in r.json()["by_territory"] if x["sector_id"] == building["sector_id"])
    assert row["active"] >= 1


def test_load_today_en_route_and_minutes_scoped_to_start_date(ac, db_conn, building):
    """Board + dashboard share start_date; minutes = closed duration + open elapsed."""
    today = today_local()
    yesterday = today - timedelta(days=1)
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date) "
        "VALUES ('en_route', %(b)s, %(s)s, %(e)s, 'Old en route', %(d)s)",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": yesterday},
    )
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date) "
        "VALUES ('triaged', %(b)s, %(s)s, %(e)s, 'Load today mins', %(d)s) "
        "RETURNING request_id",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    ).fetchone()["request_id"]
    now = datetime.now(timezone.utc)
    db_conn.execute(
        "INSERT INTO request_visit (request_id, employee_id, en_route_at, closeout_at, "
        "duration_minutes, outcome) "
        "VALUES (%(r)s, %(e)s, %(era)s, %(ca)s, 45, 'complete')",
        {
            "r": rid, "e": _TECH,
            "era": now - timedelta(hours=2),
            "ca": now - timedelta(hours=1, minutes=15),
        },
    )
    open_rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date) "
        "VALUES ('en_route', %(b)s, %(s)s, %(e)s, 'Open visit', %(d)s) "
        "RETURNING request_id",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    ).fetchone()["request_id"]
    db_conn.execute(
        "INSERT INTO request_visit (request_id, employee_id, en_route_at) "
        "VALUES (%(r)s, %(e)s, %(era)s)",
        {"r": open_rid, "e": _TECH, "era": now - timedelta(minutes=12)},
    )

    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["load_today"] if x["employee_id"] == _TECH)
    assert row["en_route_count"] >= 1
    assert row["assigned_count"] >= 2
    assert row["minutes_worked"] >= 45 + 12


def test_dashboard_weather_null_when_flag_off(ac, monkeypatch):
    from backend.core import config
    monkeypatch.setattr(config.settings, "WEATHER_ESCALATION_ENABLED", False)
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    assert r.json()["weather"] is None


def test_dashboard_weather_null_on_source_failure(ac, monkeypatch):
    from backend.core import config
    from backend.modules.analytics import service as dash_service

    monkeypatch.setattr(config.settings, "WEATHER_ESCALATION_ENABLED", True)

    def boom(_loc):
        raise RuntimeError("MSC down")

    monkeypatch.setattr(dash_service, "fetch_forecast", boom)
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    assert r.status_code == 200
    assert r.json()["weather"] is None


def test_dashboard_weather_ok_when_flag_on(ac, monkeypatch, db_conn):
    from backend.core import config
    from backend.modules.analytics import service as dash_service

    monkeypatch.setattr(config.settings, "WEATHER_ESCALATION_ENABLED", True)
    monkeypatch.setattr(
        dash_service, "fetch_forecast",
        lambda _loc: {
            "current_temp_c": 5.2,
            "wind_chill_c": None,
            "min_forecast_temp_24h_c": 3.0,
            "source": "msc_citypage",
            "source_url": "https://example.test/wx",
        },
    )
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/analytics/dashboard")
    assert r.status_code == 200
    wx = r.json()["weather"]
    assert wx is not None
    assert wx["current_temp_c"] == 5.2
    assert wx["min_forecast_temp_24h_c"] == 3.0
    assert "Environnement" in wx["source_credit"]


def test_untriaged_statuses_single_source():
    assert UNTRIAGED_STATUSES == frozenset({
        "intake_received", "triage_pending", "triage_failed", "triage_clarify",
    })
