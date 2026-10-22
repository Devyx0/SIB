"""GET /api/v1/analytics/dashboard — coord/dir only, real aggregates."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.core.utils import today_local
from backend.modules.analytics.constants import UNTRIAGED_STATUSES
from backend.modules.tasks.repository import insert_task

_TECH = 24
_COORD = 4
_DIRECTOR = 5
_CONTRACTOR = 20


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


def _due(day):
    return datetime.combine(day, time(10, 0), tzinfo=ZoneInfo(settings.TIMEZONE))


def _open_request(db_conn, building) -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, raw_title) "
        "VALUES ('open', %(b)s, %(s)s, 'Dash task') RETURNING request_id",
        {"b": building["building_id"], "s": building["sector_id"]},
    ).fetchone()["request_id"]


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
    rid = _open_request(db_conn, building)
    insert_task(
        db_conn, request_id=rid, description="Dash today", status="scheduled",
        assigned_employee_id=_TECH, due_at=_due(today), source="dispatcher",
        accepted_at=datetime.now(timezone.utc),
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
    assert body["queue_counts"]["a_redispatcher_link"] == "/tasks?redispatch=1"


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


def _load_row(body: dict) -> dict:
    return next(
        (x for x in body["load_today"] if x["employee_id"] == _TECH),
        {"assigned_count": 0, "en_route_count": 0, "minutes_worked": 0},
    )


def _status_count(body: dict, status: str) -> int:
    return next((x["count"] for x in body["today_by_status"] if x["status"] == status), 0)


def test_today_counts_accepted_tasks_not_request_columns(ac, db_conn, building):
    """start_date / request status do not move today's board; an accepted task does."""
    c = ac(_user(_COORD, "coordinator"))
    today = today_local()
    before = _status_count(c.get("/api/v1/analytics/dashboard").json(), "scheduled")
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date) "
        "VALUES ('scheduled', %(b)s, %(s)s, %(e)s, 'Request only', %(d)s)",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    )
    assert _status_count(c.get("/api/v1/analytics/dashboard").json(), "scheduled") == before
    rid = _open_request(db_conn, building)
    insert_task(
        db_conn, request_id=rid, description="Due today", status="scheduled",
        assigned_employee_id=_TECH, due_at=_due(today), source="dispatcher",
        accepted_at=datetime.now(timezone.utc),
    )
    assert _status_count(c.get("/api/v1/analytics/dashboard").json(), "scheduled") == before + 1
    insert_task(
        db_conn, request_id=rid, description="Proposal", status="scheduled",
        due_at=_due(today), source="ai_recommended", accepted_at=None,
    )
    assert _status_count(c.get("/api/v1/analytics/dashboard").json(), "scheduled") == before + 1


def test_redispatch_count_is_unfollowed_tasks(ac, db_conn, building):
    c = ac(_user(_COORD, "coordinator"))
    before = c.get("/api/v1/analytics/dashboard").json()["queue_counts"]["a_redispatcher"]
    rid = _open_request(db_conn, building)
    now = datetime.now(timezone.utc)
    parent = insert_task(
        db_conn, request_id=rid, description="Expertise", status="needs_expertise",
        source="dispatcher", accepted_at=now,
    )
    assert c.get("/api/v1/analytics/dashboard").json()["queue_counts"]["a_redispatcher"] == before + 1
    insert_task(
        db_conn, request_id=rid, description="Suivi", status="queued",
        source="follow_up", accepted_at=now, parent_task_id=parent["task_id"],
    )
    assert c.get("/api/v1/analytics/dashboard").json()["queue_counts"]["a_redispatcher"] == before
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, raw_title) "
        "VALUES ('awaiting_redispatch', %(b)s, %(s)s, 'Legacy chip')",
        {"b": building["building_id"], "s": building["sector_id"]},
    )
    body = c.get("/api/v1/analytics/dashboard").json()
    assert body["queue_counts"]["a_redispatcher"] == before
    assert body["queue_counts"]["a_redispatcher_link"] == "/tasks?redispatch=1"


def test_load_today_en_route_and_minutes_scoped_to_task_due(ac, db_conn, building):
    """En route and assigned counts follow the task's due day, not the call."""
    today = today_local()
    yesterday = today - timedelta(days=1)
    now = datetime.now(timezone.utc)
    c = ac(_user(_COORD, "coordinator"))
    before = _load_row(c.get("/api/v1/analytics/dashboard").json())

    y_rid = _open_request(db_conn, building)
    insert_task(
        db_conn, request_id=y_rid, description="Yesterday", status="en_route",
        assigned_employee_id=_TECH, due_at=_due(yesterday), source="dispatcher",
        accepted_at=now,
    )
    rid = _open_request(db_conn, building)
    tid = insert_task(
        db_conn, request_id=rid, description="Assigned today", status="scheduled",
        assigned_employee_id=_TECH, due_at=_due(today), source="dispatcher",
        accepted_at=now,
    )["task_id"]
    db_conn.execute(
        "INSERT INTO request_visit (request_id, task_id, employee_id, en_route_at, closeout_at, "
        "duration_minutes, outcome) "
        "VALUES (%(r)s, %(t)s, %(e)s, %(era)s, %(ca)s, 45, 'complete')",
        {"r": rid, "t": tid, "e": _TECH, "era": now - timedelta(hours=2),
         "ca": now - timedelta(hours=1, minutes=15)},
    )
    open_rid = _open_request(db_conn, building)
    open_tid = insert_task(
        db_conn, request_id=open_rid, description="En route today", status="en_route",
        assigned_employee_id=_TECH, due_at=_due(today), source="dispatcher",
        accepted_at=now,
    )["task_id"]
    db_conn.execute(
        "INSERT INTO request_visit (request_id, task_id, employee_id, en_route_at) "
        "VALUES (%(r)s, %(t)s, %(e)s, %(era)s)",
        {"r": open_rid, "t": open_tid, "e": _TECH, "era": now - timedelta(minutes=12)},
    )
    db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, sector_id, assigned_employee_id, "
        "raw_title, start_date) "
        "VALUES ('en_route', %(b)s, %(s)s, %(e)s, 'Request en route', %(d)s)",
        {"b": building["building_id"], "s": building["sector_id"], "e": _TECH, "d": today},
    )

    r = c.get("/api/v1/analytics/dashboard")
    assert r.status_code == 200, r.text
    row = _load_row(r.json())
    assert row["en_route_count"] == before["en_route_count"] + 1
    assert row["assigned_count"] == before["assigned_count"] + 2
    assert row["minutes_worked"] >= before["minutes_worked"] + 45 + 12


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
