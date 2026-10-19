"""Tests for the weather-escalation feature (SoW 3.4).

The MSC fetcher is ALWAYS mocked (monkeypatch service.fetch_forecast) — no network.
All writes use the rolled-back db_conn fixture; run against sib_test only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.weather import service
from backend.modules.weather.keywords import matches_heating_keywords
from backend.modules.weather.location import resolve_location
from backend.modules.weather.source import parse_citypage_xml

_COORD = 4
_DIR   = 5
_TECH  = 14
_CONT  = 20
_BLDG   = 3
_SECTOR = 1
_JUST = {"text": "Météo: -22 °C prévu sur 24 h.", "input_method": "typed"}


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
def weather_on(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_ESCALATION_ENABLED", True)


@pytest.fixture
def mkreq(db_conn):
    """Insert a triaged request. municipality pins the resolved location."""
    def _mk(urgency=None, building_id=_BLDG, municipality="Quebec", problem="Problème générique"):
        if building_id is not None and municipality is not None:
            db_conn.execute(
                "UPDATE building SET ville=%s, municipality=%s, sib_territory=%s WHERE building_id=%s",
                ["Québec" if municipality == "Quebec" else municipality, municipality,
                 "Quebec-Est" if municipality == "Quebec" else "Levis-Est", building_id],
            )
        row = db_conn.execute(
            "INSERT INTO maintenance_request (status, building_id, sector_id, start_date, urgency_tier, problem_summary)"
            " VALUES ('triaged', %s, %s, CURRENT_DATE, %s::public.urgency_tier, %s) RETURNING request_id",
            [building_id, _SECTOR, urgency, problem],
        ).fetchone()
        return row["request_id"]
    return _mk


def _reading(min_temp, current=5.0, wind=None, url="https://dd.weather.gc.ca/x.xml"):
    return {
        "current_temp_c": current, "wind_chill_c": wind,
        "min_forecast_temp_24h_c": min_temp,
        "source": "msc_citypage", "source_url": url,
    }


def _fetcher(reading, counter=None):
    def _f(location):
        if counter is not None:
            counter["n"] += 1
        return dict(reading)
    return _f


# ── Pure helpers ────────────────────────────────────────────────────────────

def test_resolve_location_levis():
    assert resolve_location("Lévis", "Levis", "Levis-Est") == "levis"
    assert resolve_location(None, None, "Levis-Ouest") == "levis"


def test_resolve_location_quebec():
    assert resolve_location("Québec", "Quebec", "Quebec-Est") == "quebec"
    assert resolve_location(None, "Saint-Augustin-de-Desmaures", None) == "quebec"


def test_resolve_location_unknown():
    assert resolve_location(None, None, None) is None
    assert resolve_location("", "  ", "") is None


def test_band_boundary_minus15_is_emergency(db_conn):
    bands = service.list_bands(db_conn)
    assert service.pick_band(bands, -15)["name"] == "emergency"


def test_band_boundary_minus5_is_priority(db_conn):
    bands = service.list_bands(db_conn)
    assert service.pick_band(bands, -5)["name"] == "priority"


def test_band_boundary_plus10_is_normal(db_conn):
    bands = service.list_bands(db_conn)
    assert service.pick_band(bands, 10)["name"] == "normal"


def test_band_below_minus15_is_critical(db_conn):
    bands = service.list_bands(db_conn)
    b = service.pick_band(bands, -15.1)
    assert b["name"] == "critical" and b["is_critical"] is True


def test_direction_higher():
    assert service.suggestion_direction(None, "AJD") == "higher"
    assert service.suggestion_direction("ajd", "AJD") == "higher"


def test_direction_lower():
    assert service.suggestion_direction("AJD", "ajd") == "lower"
    assert service.suggestion_direction("AJD", None) == "lower"


def test_direction_equal():
    assert service.suggestion_direction("ajd", "ajd") == "equal"
    assert service.suggestion_direction(None, None) == "equal"


def test_parse_citypage_xml_min_and_windchill():
    xml = (
        "<siteData><currentConditions><temperature units='C'>5.2</temperature>"
        "</currentConditions><hourlyForecastGroup>"
        "<hourlyForecast><temperature units='C'>8</temperature></hourlyForecast>"
        "<hourlyForecast><temperature units='C'>-3</temperature><windChill>-9</windChill></hourlyForecast>"
        "<hourlyForecast><temperature units='C'>2</temperature></hourlyForecast>"
        "</hourlyForecastGroup></siteData>"
    )
    r = parse_citypage_xml(xml)
    assert r["current_temp_c"] == 5.2
    assert r["min_forecast_temp_24h_c"] == -3
    assert r["wind_chill_c"] == -9


def test_keyword_hint_matches():
    assert matches_heating_keywords("Locataire signale: pas de chauffage depuis hier") is True
    assert matches_heating_keywords("Panne de chauffage au 3e") is True


def test_keyword_hint_no_match():
    assert matches_heating_keywords("Robinet qui fuit sous l'évier") is False
    assert matches_heating_keywords("") is False


# ── Endpoint: feature flag ────────────────────────────────────────────────────

def test_feature_off_returns_404_and_writes_nothing(ac, db_conn, mkreq, monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_ESCALATION_ENABLED", False)
    rid = mkreq()
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check")
    assert r.status_code == 404
    n = db_conn.execute(
        "SELECT count(*) AS n FROM weather_evaluation WHERE request_id = %s", [rid]
    ).fetchone()["n"]
    assert n == 0


# ── Endpoint: role gating ──────────────────────────────────────────────────────

def test_technician_403(ac, mkreq, weather_on):
    rid = mkreq()
    r = ac(_user(_TECH, "technician")).post(f"/api/v1/requests/{rid}/weather-check")
    assert r.status_code == 403


def test_contractor_403(ac, mkreq, weather_on):
    rid = mkreq()
    r = ac(_user(_CONT, "contractor")).post(f"/api/v1/requests/{rid}/weather-check")
    assert r.status_code == 403


# ── Endpoint: evaluation outcomes ──────────────────────────────────────────────

def test_unknown_location(ac, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-20)))
    rid = mkreq(building_id=None, municipality=None)  # no building -> unknown
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check")
    assert r.status_code == 200
    assert r.json()["status"] == "location_unknown"


def test_source_failure_does_not_block(ac, db_conn, mkreq, weather_on, monkeypatch):
    def boom(location):
        raise RuntimeError("source down")
    monkeypatch.setattr(service, "fetch_forecast", boom)
    rid = mkreq()
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check")
    assert r.status_code == 200
    assert r.json()["status"] == "source_failed"
    # no snapshot written on failure
    n = db_conn.execute("SELECT count(*) AS n FROM weather_forecast_snapshot").fetchone()["n"]
    assert n == 0


def test_suggestion_higher(ac, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-20)))
    rid = mkreq(urgency="ajd")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["status"] == "ok"
    assert r["band_name"] == "critical"
    assert r["suggested_tier"] == "AJD"
    assert r["direction"] == "higher"
    assert r["is_critical"] is True


def test_suggestion_lower_is_neutral(ac, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(15)))
    rid = mkreq(urgency="AJD")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["band_name"] == "normal"
    assert r["suggested_tier"] is None
    assert r["direction"] == "lower"


def test_suggestion_equal_context_only(ac, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-20)))
    rid = mkreq(urgency="AJD")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["band_name"] == "critical"
    assert r["direction"] == "equal"


def test_cache_reuse_no_second_fetch(ac, mkreq, weather_on, monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-20), counter))
    rid = mkreq(urgency="ajd")
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{rid}/weather-check")
    c.post(f"/api/v1/requests/{rid}/weather-check")
    assert counter["n"] == 1


# ── get_request: keyword hint surfaced on the detail ───────────────────────────

def test_detail_exposes_heating_hint_true(ac, mkreq):
    rid = mkreq(problem="Pas de chauffage dans l'appartement")
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{rid}").json()
    assert r["heating_keyword_hint"] is True


def test_detail_exposes_heating_hint_false(ac, mkreq):
    rid = mkreq(problem="Robinet qui fuit")
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{rid}").json()
    assert r["heating_keyword_hint"] is False


# ── Accept flow: justification after_value + 'app' provenance ──────────────────

def test_accept_records_justification_and_app_provenance(ac, db_conn, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-22)))
    rid = mkreq(urgency="ajd")
    c = ac(_user(_COORD, "coordinator"))
    ev = c.post(f"/api/v1/requests/{rid}/weather-check").json()
    eval_id = ev["evaluation_id"]
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]

    r = c.post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "AJD", "current_urgency_tier": "ajd",
        "current_assigned_employee_id": None, "current_start_date": start,
        "justification": _JUST, "weather_evaluation_id": eval_id,
    })
    assert r.status_code == 200

    av = db_conn.execute(
        "SELECT after_value FROM decision_justification_log"
        " WHERE request_id=%s AND decision_type='urgency' ORDER BY id DESC LIMIT 1", [rid]
    ).fetchone()["after_value"]
    assert av["urgency_tier"] == "AJD"
    assert av["weather"]["evaluation_id"] == eval_id
    assert "min_forecast_temp_24h_c" in av["weather"]
    assert av["weather"]["band"] == "critical"
    assert "source_url" in av["weather"]

    prov = db_conn.execute(
        "SELECT source_type FROM data_provenance WHERE target_table='maintenance_request'"
        " AND target_column='urgency_tier' AND target_pk=%s ORDER BY ingested_at DESC LIMIT 1",
        [str(rid)],
    ).fetchone()
    assert prov["source_type"] == "app"


def test_eval_stores_current_tier_and_forecast_time(ac, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-20)))
    rid = mkreq(urgency="ajd")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["current_tier_at_eval"] == "ajd"
    assert r["forecast_time_local"]  # non-empty HH:MM


_STALE_MSG = "Suggestion périmée — revérifiez la météo"


def test_accept_stale_after_urgency_change_409(ac, db_conn, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-22)))
    rid = mkreq(urgency="ajd")
    c = ac(_user(_COORD, "coordinator"))
    ev = c.post(f"/api/v1/requests/{rid}/weather-check").json()
    # urgency changes after the evaluation was computed
    db_conn.execute(
        "UPDATE maintenance_request SET urgency_tier='AJD'::public.urgency_tier WHERE request_id=%s", [rid]
    )
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]
    r = c.post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "AJD", "current_urgency_tier": "AJD",  # live tier → generic stale passes
        "current_assigned_employee_id": None, "current_start_date": start,
        "justification": _JUST, "weather_evaluation_id": ev["evaluation_id"],
    })
    assert r.status_code == 409
    assert r.json()["error"]["message"] == _STALE_MSG


def test_accept_twice_second_409(ac, db_conn, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-22)))
    rid = mkreq(urgency="ajd")
    c = ac(_user(_COORD, "coordinator"))
    ev = c.post(f"/api/v1/requests/{rid}/weather-check").json()
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]
    base = {
        "urgency_tier": "AJD", "current_assigned_employee_id": None,
        "current_start_date": start, "justification": _JUST,
        "weather_evaluation_id": ev["evaluation_id"],
    }
    r1 = c.post(f"/api/v1/requests/{rid}/urgency", json={**base, "current_urgency_tier": "ajd"})
    assert r1.status_code == 200
    r2 = c.post(f"/api/v1/requests/{rid}/urgency", json={**base, "current_urgency_tier": "AJD"})
    assert r2.status_code == 409
    assert r2.json()["error"]["message"] == _STALE_MSG


def test_accept_stale_current_tier_409(ac, db_conn, mkreq, weather_on):
    rid = mkreq(urgency="ajd")
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "AJD", "current_urgency_tier": "AJD",  # wrong: actual is 'ajd'
        "current_assigned_employee_id": None, "current_start_date": start,
        "justification": _JUST, "weather_evaluation_id": None,
    })
    assert r.status_code == 409


# ── RLS ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("table", [
    "weather_threshold_band", "weather_forecast_snapshot", "weather_evaluation",
])
def test_rls_enabled(db_conn, table):
    row = db_conn.execute(
        "SELECT relrowsecurity FROM pg_class WHERE relname = %s", [table]
    ).fetchone()
    assert row["relrowsecurity"] is True
