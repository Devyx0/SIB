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
            " VALUES ('triaged', %s, %s, CURRENT_DATE, %s, %s) RETURNING request_id",
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
    assert service.suggestion_direction(None, "URGENT") == "higher"
    assert service.suggestion_direction("Intermédiaire", "URGENT") == "higher"


def test_direction_lower():
    assert service.suggestion_direction("URGENT", "Intermédiaire") == "lower"
    assert service.suggestion_direction("URGENT", None) == "lower"


def test_direction_equal():
    assert service.suggestion_direction("Intermédiaire", "Intermédiaire") == "equal"
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
    rid = mkreq(urgency="Intermédiaire")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["status"] == "ok"
    assert r["band_name"] == "critical"
    assert r["suggested_tier"] == "URGENT"
    assert r["direction"] == "higher"
    assert r["is_critical"] is True


def test_suggestion_lower_is_neutral(ac, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(15)))
    rid = mkreq(urgency="URGENT")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["band_name"] == "normal"
    assert r["suggested_tier"] is None
    assert r["direction"] == "lower"


def test_suggestion_equal_context_only(ac, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-20)))
    rid = mkreq(urgency="URGENT")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["band_name"] == "critical"
    assert r["direction"] == "equal"


def test_cache_reuse_no_second_fetch(ac, mkreq, weather_on, monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-20), counter))
    rid = mkreq(urgency="Intermédiaire")
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{rid}/weather-check")
    c.post(f"/api/v1/requests/{rid}/weather-check")
    assert counter["n"] == 1


# ── get_request: latest weather evaluation surfaced on the detail ──────────────

def test_detail_includes_latest_weather_evaluation(ac, mkreq, weather_on, monkeypatch):
    rid = mkreq()
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))
    ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check")
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{rid}").json()
    ev = r["weather_evaluation"]
    assert ev["status"] == "ok"
    assert ev["band_name"] == "critical"
    assert ev["is_critical"] is True
    assert ev["min_forecast_temp_24h_c"] == -18.0


def test_detail_weather_evaluation_null_when_never_evaluated(ac, mkreq):
    rid = mkreq()
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{rid}").json()
    assert r["weather_evaluation"] is None


def test_detail_hides_weather_evaluation_from_technician(ac, db_conn, mkreq, weather_on, monkeypatch):
    rid = mkreq()
    db_conn.execute(
        "UPDATE maintenance_request SET assigned_employee_id = %s WHERE request_id = %s",
        [_TECH, rid],
    )
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))
    ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check")
    r = ac(_user(_TECH, "technician")).get(f"/api/v1/requests/{rid}")
    assert r.status_code == 200
    assert r.json()["weather_evaluation"] is None


# ── Accept flow: justification after_value + 'app' provenance ──────────────────

def test_accept_records_justification_and_app_provenance(ac, db_conn, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-22)))
    rid = mkreq(urgency="Intermédiaire")
    c = ac(_user(_COORD, "coordinator"))
    ev = c.post(f"/api/v1/requests/{rid}/weather-check").json()
    eval_id = ev["evaluation_id"]
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]

    r = c.post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "URGENT", "current_urgency_tier": "Intermédiaire",
        "current_assigned_employee_id": None, "current_start_date": start,
        "justification": _JUST, "weather_evaluation_id": eval_id,
    })
    assert r.status_code == 200

    av = db_conn.execute(
        "SELECT after_value FROM decision_justification_log"
        " WHERE request_id=%s AND decision_type='urgency' ORDER BY id DESC LIMIT 1", [rid]
    ).fetchone()["after_value"]
    assert av["urgency_tier"] == "URGENT"
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
    rid = mkreq(urgency="Intermédiaire")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/weather-check").json()
    assert r["current_tier_at_eval"] == "Intermédiaire"
    assert r["forecast_time_local"]  # non-empty HH:MM


_STALE_MSG = "Suggestion périmée — revérifiez la météo"


def test_accept_stale_after_urgency_change_409(ac, db_conn, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-22)))
    rid = mkreq(urgency="Intermédiaire")
    c = ac(_user(_COORD, "coordinator"))
    ev = c.post(f"/api/v1/requests/{rid}/weather-check").json()
    # urgency changes after the evaluation was computed
    db_conn.execute(
        "UPDATE maintenance_request SET urgency_tier='URGENT' WHERE request_id=%s", [rid]
    )
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]
    r = c.post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "URGENT", "current_urgency_tier": "URGENT",  # live tier → generic stale passes
        "current_assigned_employee_id": None, "current_start_date": start,
        "justification": _JUST, "weather_evaluation_id": ev["evaluation_id"],
    })
    assert r.status_code == 409
    assert r.json()["error"]["message"] == _STALE_MSG


def test_accept_twice_second_409(ac, db_conn, mkreq, weather_on, monkeypatch):
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-22)))
    rid = mkreq(urgency="Intermédiaire")
    c = ac(_user(_COORD, "coordinator"))
    ev = c.post(f"/api/v1/requests/{rid}/weather-check").json()
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]
    base = {
        "urgency_tier": "URGENT", "current_assigned_employee_id": None,
        "current_start_date": start, "justification": _JUST,
        "weather_evaluation_id": ev["evaluation_id"],
    }
    r1 = c.post(f"/api/v1/requests/{rid}/urgency", json={**base, "current_urgency_tier": "Intermédiaire"})
    assert r1.status_code == 200
    r2 = c.post(f"/api/v1/requests/{rid}/urgency", json={**base, "current_urgency_tier": "URGENT"})
    assert r2.status_code == 409
    assert r2.json()["error"]["message"] == _STALE_MSG


def test_accept_stale_current_tier_409(ac, db_conn, mkreq, weather_on):
    rid = mkreq(urgency="Intermédiaire")
    start = db_conn.execute(
        "SELECT start_date::text AS d FROM maintenance_request WHERE request_id=%s", [rid]
    ).fetchone()["d"]
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/urgency", json={
        "urgency_tier": "URGENT", "current_urgency_tier": "URGENT",  # wrong: actual is 'Intermédiaire'
        "current_assigned_employee_id": None, "current_start_date": start,
        "justification": _JUST, "weather_evaluation_id": None,
    })
    assert r.status_code == 409


# ── Triage integration: automatic escalation (no button) ───────────────────────

@pytest.fixture
def esc_conn(db_conn, monkeypatch):
    """Route the escalation hook's own pool connection to the rolled-back test conn."""
    from contextlib import contextmanager

    @contextmanager
    def _fake():
        yield db_conn

    monkeypatch.setattr(service, "_escalation_conn", _fake)


def _parsed(urgency=None, heating=True, notes=None):
    return {"urgency_tier": urgency, "heating_failure": heating, "other_notes": notes}


def _eval_rows(db_conn, rid):
    return db_conn.execute(
        "SELECT * FROM weather_evaluation WHERE request_id = %s", [rid]
    ).fetchall()


def test_escalation_floors_urgency_and_cites_civil_code(db_conn, mkreq, weather_on, esc_conn, monkeypatch):
    rid = mkreq()
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))
    parsed = _parsed(urgency=None)
    service.apply_triage_escalation(parsed, rid)
    assert parsed["urgency_tier"] == "URGENT"
    assert "1864" in parsed["other_notes"] and "1865" in parsed["other_notes"]
    assert any("1864" in n for n in (parsed.get("ai_important_notes") or []))
    rows = _eval_rows(db_conn, rid)
    assert len(rows) == 1
    ev = rows[0]
    assert ev["status"] == "ok" and ev["is_critical"] is True
    assert ev["evaluated_by"] is None  # system evaluation, no human


def test_escalation_appends_note_after_existing_notes(mkreq, weather_on, esc_conn, monkeypatch):
    rid = mkreq()
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))
    parsed = _parsed(urgency=None, notes="Note existante.")
    service.apply_triage_escalation(parsed, rid)
    assert parsed["other_notes"].startswith("Note existante.")
    assert "1864" in parsed["other_notes"]


def test_escalation_never_lowers(db_conn, mkreq, weather_on, esc_conn, monkeypatch):
    rid = mkreq()
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(15.0)))  # normal band
    parsed = _parsed(urgency="URGENT")
    service.apply_triage_escalation(parsed, rid)
    assert parsed["urgency_tier"] == "URGENT"
    assert parsed["other_notes"] is None
    assert len(_eval_rows(db_conn, rid)) == 1  # audit trail still recorded


def test_escalation_equal_tier_no_note(db_conn, mkreq, weather_on, esc_conn, monkeypatch):
    rid = mkreq()
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))  # suggests URGENT
    parsed = _parsed(urgency="URGENT")
    service.apply_triage_escalation(parsed, rid)
    assert parsed["urgency_tier"] == "URGENT"
    assert parsed["other_notes"] is None


@pytest.mark.parametrize("flag", [None, False])
def test_escalation_requires_model_flag(db_conn, mkreq, weather_on, esc_conn, monkeypatch, flag):
    rid = mkreq()
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))
    parsed = _parsed(urgency=None, heating=flag)
    service.apply_triage_escalation(parsed, rid)
    assert parsed["urgency_tier"] is None
    assert parsed["other_notes"] is None
    assert len(_eval_rows(db_conn, rid)) == 0


def test_escalation_feature_off_noop(db_conn, mkreq, esc_conn, monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_ESCALATION_ENABLED", False)
    rid = mkreq()
    parsed = _parsed(urgency=None)
    service.apply_triage_escalation(parsed, rid)
    assert parsed["urgency_tier"] is None
    assert len(_eval_rows(db_conn, rid)) == 0


def test_escalation_source_failure_never_blocks(db_conn, mkreq, weather_on, esc_conn, monkeypatch):
    rid = mkreq()

    def _boom(location):
        raise RuntimeError("MSC down")

    monkeypatch.setattr(service, "fetch_forecast", _boom)
    parsed = _parsed(urgency=None)
    service.apply_triage_escalation(parsed, rid)  # must not raise
    assert parsed["urgency_tier"] is None
    assert parsed["other_notes"] is None
    rows = _eval_rows(db_conn, rid)
    assert len(rows) == 1 and rows[0]["status"] == "source_failed"


def test_escalation_unknown_location_noop(db_conn, mkreq, weather_on, esc_conn, monkeypatch):
    rid = mkreq(building_id=None)
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))
    parsed = _parsed(urgency=None)
    service.apply_triage_escalation(parsed, rid)
    assert parsed["urgency_tier"] is None
    rows = _eval_rows(db_conn, rid)
    assert len(rows) == 1 and rows[0]["status"] == "location_unknown"


_MODEL_JSON = {
    "verdict": "single", "duplicate_of_request_id": None, "addition_to_request_id": None,
    "title": "Pas de chauffage", "problems": ["Aucun chauffage dans le logement"],
    "entry_permission": None, "animals": None, "urgency_tier": None,
    "heating_failure": True,
    "complexity_tier": "C2", "congestion_level": "N1",
    "time_estimate_bucket": "H1_TO_2H", "delegable_status": "NO",
    "report_status": "CANNOT_WAIT", "routing_rule": "A0", "subcontractor_name": None,
    "vendor_id": None, "synergy_request_ids": [], "other_notes": None,
    "recommended_tasks": [{"description": "Diagnostiquer le chauffage"}],
}


def test_triage_run_applies_weather_escalation(db_conn, mkreq, weather_on, esc_conn, monkeypatch):
    """End-to-end wiring: triage() with a canned model response floors urgency.

    The request row is committed via psycopg2 (triage runs on a legacy conn and
    commits internally); weather reads/writes ride the rolled-back db_conn via
    esc_conn. Cleanup deletes the committed rows.
    """
    import json as _json
    import psycopg2
    from types import SimpleNamespace

    import backend.triage.service as tsvc

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test", raising=False)

    class _FakeClient:
        def __init__(self, **kw):
            self.messages = SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
                content=[SimpleNamespace(text=_json.dumps(_MODEL_JSON))],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ))

    monkeypatch.setattr(tsvc.anthropic, "Anthropic", _FakeClient)
    monkeypatch.setattr(service, "fetch_forecast", _fetcher(_reading(-18.0)))

    mkreq()  # pins building location on db_conn (visible to the hook via esc_conn)

    c2 = psycopg2.connect(
        host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
        user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
        dbname=settings.LOCAL_DB_NAME,
    )
    rid = None
    try:
        with c2.cursor() as cur:
            cur.execute(
                "INSERT INTO maintenance_request (status, building_id, sector_id, start_date)"
                " VALUES ('intake_received', %s, %s, CURRENT_DATE) RETURNING request_id",
                [_BLDG, _SECTOR],
            )
            rid = cur.fetchone()[0]
        c2.commit()

        result = tsvc.triage(c2, rid)
        assert result["result"] == "triaged", result

        with c2.cursor() as cur:
            cur.execute(
                "SELECT status, urgency_tier::text, other_notes FROM maintenance_request WHERE request_id = %s",
                [rid],
            )
            status, urgency, notes = cur.fetchone()
        assert status == "triage_proposal"
        assert urgency == "URGENT"
        assert "1864" in notes
        assert len(_eval_rows(db_conn, rid)) == 1
    finally:
        db_conn.rollback()  # drop uncommitted weather rows before deleting the request
        if rid is not None:
            with c2.cursor() as cur:
                cur.execute("DELETE FROM dispatch_task WHERE request_id = %s", [rid])
                cur.execute("DELETE FROM triage_log WHERE request_id = %s", [rid])
                cur.execute("DELETE FROM data_provenance WHERE target_table = 'maintenance_request' AND target_pk = %s", [str(rid)])
                cur.execute("DELETE FROM maintenance_request WHERE request_id = %s", [rid])
            c2.commit()
        c2.close()


# ── RLS ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("table", [
    "weather_threshold_band", "weather_forecast_snapshot", "weather_evaluation",
])
def test_rls_enabled(db_conn, table):
    row = db_conn.execute(
        "SELECT relrowsecurity FROM pg_class WHERE relname = %s", [table]
    ).fetchone()
    assert row["relrowsecurity"] is True
