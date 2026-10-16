"""Tests for POST /api/v1/requests/{id}/assign|reschedule|urgency|… endpoints."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user


# Real employee IDs present in the test DB.
_COORD = 4    # coordinator
_DIR   = 5    # director
_TECH  = 14   # Jean-Frédéric Menada — technician, sector 1
_CONT  = 20   # Mahmoud Chachia — contractor

# Building 3 is in sector 1 (matches _TECH's sector).
_BLDG = 3
_SECTOR = 1

# A valid "future" date for reschedule tests.
_DATE_A = str(date.today() + timedelta(days=5))
_DATE_B = str(date.today() + timedelta(days=10))


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


@pytest.fixture
def ac(app, db_conn):
    """Return a factory: ac(user) → TestClient with that user injected."""
    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)
    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def test_request(db_conn):
    """Insert a triaged request, return its request_id. Rolled back at teardown."""
    row = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, start_date)
        VALUES ('triaged', %(bldg)s, %(sector)s, %(start_date)s)
        RETURNING request_id
        """,
        {"bldg": _BLDG, "sector": _SECTOR, "start_date": _DATE_A},
    ).fetchone()
    return row["request_id"]


@pytest.fixture
def closed_request(db_conn):
    """Insert a closed request, return its request_id."""
    row = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, start_date)
        VALUES ('closed', %(bldg)s, %(sector)s, %(start_date)s)
        RETURNING request_id
        """,
        {"bldg": _BLDG, "sector": _SECTOR, "start_date": _DATE_A},
    ).fetchone()
    return row["request_id"]


# ── assign ────────────────────────────────────────────────────────────────────

def test_assign_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Technician is closest to the building", "input_method": "typed"},
    })
    assert r.status_code == 200
    assert r.json()["assigned_employee_id"] == _TECH


def test_assign_stores_justification(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Available this afternoon for sector 1", "input_method": "typed"},
    })
    rows = db_conn.execute(
        "SELECT decision_type, justification_text FROM decision_justification_log WHERE request_id = %s",
        [test_request],
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["decision_type"] == "assign"


def test_assign_stores_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Nearest available technician now", "input_method": "typed"},
    })
    row = db_conn.execute(
        "SELECT source_type, employee_id, target_column FROM data_provenance WHERE target_pk = %s",
        [str(test_request)],
    ).fetchone()
    assert row is not None
    assert row["source_type"] == "app"
    assert row["employee_id"] == _COORD
    assert row["target_column"] == "assigned_employee_id"


def test_assign_stale_409(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": 999,  # wrong — DB has NULL
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Technician available and confirmed", "input_method": "typed"},
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_assign_closed_409(ac, closed_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{closed_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Technician available and confirmed", "input_method": "typed"},
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REQUEST_CLOSED"


def test_assign_technician_403(ac, test_request):
    c = ac(_user(_TECH, "technician"))
    r = c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Technician available and confirmed", "input_method": "typed"},
    })
    assert r.status_code == 403


def test_assign_no_justification_422(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Short", "input_method": "typed"},
    })
    assert r.status_code == 422


def test_assign_stale_no_justification_written(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": 999,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Technician available and confirmed", "input_method": "typed"},
    })
    count = db_conn.execute(
        "SELECT count(*) AS n FROM decision_justification_log WHERE request_id = %s",
        [test_request],
    ).fetchone()["n"]
    assert count == 0


# ── reschedule ────────────────────────────────────────────────────────────────

def test_reschedule_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/reschedule", json={
        "start_date": _DATE_B,
        "current_start_date": _DATE_A,
        "current_assigned_employee_id": None,
        "current_urgency_tier": None,
        "justification": {"text": "Tenant requested a later date", "input_method": "typed"},
    })
    assert r.status_code == 200
    assert r.json()["start_date"] == _DATE_B


def test_reschedule_stale_409(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/reschedule", json={
        "start_date": _DATE_B,
        "current_start_date": "2020-01-01",  # wrong
        "current_assigned_employee_id": None,
        "current_urgency_tier": None,
        "justification": {"text": "Tenant requested a later date", "input_method": "typed"},
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_reschedule_closed_409(ac, closed_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{closed_request}/reschedule", json={
        "start_date": _DATE_B,
        "current_start_date": _DATE_A,
        "current_assigned_employee_id": None,
        "current_urgency_tier": None,
        "justification": {"text": "Tenant requested a later date", "input_method": "typed"},
    })
    assert r.status_code == 409


def test_reschedule_technician_403(ac, test_request):
    c = ac(_user(_TECH, "technician"))
    r = c.post(f"/api/v1/requests/{test_request}/reschedule", json={
        "start_date": _DATE_B,
        "current_start_date": _DATE_A,
        "current_assigned_employee_id": None,
        "current_urgency_tier": None,
        "justification": {"text": "Tenant requested a later date", "input_method": "typed"},
    })
    assert r.status_code == 403


# ── urgency ───────────────────────────────────────────────────────────────────

def test_set_urgency_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "AJD",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 200
    assert r.json()["urgency_tier"] == "AJD"


def test_set_urgency_stale_409(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "AJD",
        "current_urgency_tier": "ajd",  # wrong — DB has NULL
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 409


def test_set_urgency_closed_409(ac, closed_request):
    c = ac(_user(_DIR, "director"))
    r = c.post(f"/api/v1/requests/{closed_request}/urgency", json={
        "urgency_tier": "AJD",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 409


def test_set_urgency_technician_403(ac, test_request):
    c = ac(_user(_TECH, "technician"))
    r = c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "AJD",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 403


# ── unjustified edits ─────────────────────────────────────────────────────────

def test_set_follow_up_date_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/follow-up-date", json={
        "next_follow_up_date": _DATE_B,
        "current_next_follow_up_date": None,
    })
    assert r.status_code == 200
    assert r.json()["next_follow_up_date"] == _DATE_B


def test_set_follow_up_date_closed_409(ac, closed_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{closed_request}/follow-up-date", json={
        "next_follow_up_date": _DATE_B,
        "current_next_follow_up_date": None,
    })
    assert r.status_code == 409


def test_set_next_steps_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/next-steps", json={
        "next_steps": "Order part then schedule return visit",
        "current_next_steps": None,
    })
    assert r.status_code == 200
    assert r.json()["next_steps"] == "Order part then schedule return visit"


def test_set_cost_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/cost", json={
        "estimated_cost": "350.00",
        "current_estimated_cost": None,
    })
    assert r.status_code == 200
    assert float(r.json()["estimated_cost"]) == 350.0


def test_set_cost_negative_422(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/cost", json={
        "estimated_cost": "-10",
        "current_estimated_cost": None,
    })
    assert r.status_code == 422


def test_unjustified_edits_write_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/next-steps", json={
        "next_steps": "Call tenant tomorrow",
        "current_next_steps": None,
    })
    row = db_conn.execute(
        "SELECT source_type, employee_id, target_column, previous_value, ingested_value "
        "FROM data_provenance WHERE target_pk = %s AND target_column = 'next_steps'",
        [str(test_request)],
    ).fetchone()
    assert row is not None
    assert row["source_type"] == "app"
    assert row["employee_id"] == _COORD
    assert row["previous_value"] is None
    assert row["ingested_value"] == "Call tenant tomorrow"


# ── log entry ─────────────────────────────────────────────────────────────────

def test_add_log_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/log", json={"entry_text": "Called tenant, no answer."})
    assert r.status_code == 200
    log = r.json()["followup_log"]
    assert any(e["entry_text"] == "Called tenant, no answer." for e in log)


def test_add_log_allowed_on_closed(ac, closed_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{closed_request}/log", json={"entry_text": "Post-closure note added."})
    assert r.status_code == 200


def test_add_log_technician_403(ac, test_request):
    c = ac(_user(_TECH, "technician"))
    r = c.post(f"/api/v1/requests/{test_request}/log", json={"entry_text": "Note from tech."})
    assert r.status_code == 403


def test_add_log_writes_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/log", json={"entry_text": "Provenance check entry."})
    row = db_conn.execute(
        "SELECT source_type, target_table, employee_id FROM data_provenance "
        "WHERE target_table = 'maintenance_followup_entry' AND employee_id = %s",
        [_COORD],
    ).fetchone()
    assert row is not None
    assert row["source_type"] == "app"


# ── justification_log in detail response ─────────────────────────────────────

def test_justification_log_visible_to_coordinator(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "First available qualified technician", "input_method": "typed"},
    })
    r = c.get(f"/api/v1/requests/{test_request}")
    assert r.status_code == 200
    assert len(r.json()["justification_log"]) == 1


def test_justification_log_empty_for_technician(ac, db_conn, test_request):
    coord_c = ac(_user(_COORD, "coordinator"))
    coord_c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Technician closest to building today", "input_method": "typed"},
    })
    app = coord_c.app
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: _user(_TECH, "technician")
    tech_c = TestClient(app, raise_server_exceptions=False)
    r = tech_c.get(f"/api/v1/requests/{test_request}")
    assert r.status_code == 200
    assert r.json()["justification_log"] == []


# ── server-side fields ────────────────────────────────────────────────────────

def test_add_log_sets_initials_and_date(ac, test_request):
    """entered_by_initials and entry_date are set server-side, not from client."""
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/log", json={"entry_text": "Server-side field check."})
    assert r.status_code == 200
    entry = next(e for e in r.json()["followup_log"] if e["entry_text"] == "Server-side field check.")
    assert entry["entry_date"] == str(date.today())
    assert entry["entered_by_initials"]  # non-empty; derived from emp name server-side


# ── timezone: today_local() drives entry_date ─────────────────────────────────

def test_add_log_uses_today_local(ac, test_request, monkeypatch):
    """action_add_log must use today_local(), not date.today()."""
    import backend.modules.requests.service as svc
    monkeypatch.setattr(svc, "today_local", lambda: date(2026, 10, 15))
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/log", json={"entry_text": "Timezone probe entry."})
    assert r.status_code == 200
    entry = next(e for e in r.json()["followup_log"] if e["entry_text"] == "Timezone probe entry.")
    assert entry["entry_date"] == "2026-10-15"


# ── provenance for all 7 actions ──────────────────────────────────────────────

def test_reschedule_stores_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/reschedule", json={
        "start_date": _DATE_B,
        "current_start_date": _DATE_A,
        "current_assigned_employee_id": None,
        "current_urgency_tier": None,
        "justification": {"text": "Tenant requested a later appointment", "input_method": "typed"},
    })
    row = db_conn.execute(
        "SELECT source_type, employee_id, target_column FROM data_provenance "
        "WHERE target_pk = %s AND target_column = 'start_date'",
        [str(test_request)],
    ).fetchone()
    assert row is not None
    assert row["source_type"] == "app"
    assert row["employee_id"] == _COORD


def test_set_urgency_stores_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "AJD",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Life-safety risk escalated to urgent", "input_method": "typed"},
    })
    row = db_conn.execute(
        "SELECT source_type, employee_id, target_column FROM data_provenance "
        "WHERE target_pk = %s AND target_column = 'urgency_tier'",
        [str(test_request)],
    ).fetchone()
    assert row is not None
    assert row["source_type"] == "app"
    assert row["employee_id"] == _COORD


def test_set_follow_up_date_stores_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/follow-up-date", json={
        "next_follow_up_date": _DATE_B,
        "current_next_follow_up_date": None,
    })
    row = db_conn.execute(
        "SELECT source_type, employee_id, target_column FROM data_provenance "
        "WHERE target_pk = %s AND target_column = 'next_follow_up_date'",
        [str(test_request)],
    ).fetchone()
    assert row is not None
    assert row["source_type"] == "app"
    assert row["employee_id"] == _COORD


def test_set_cost_stores_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/cost", json={
        "estimated_cost": "500.00",
        "current_estimated_cost": None,
    })
    row = db_conn.execute(
        "SELECT source_type, employee_id, target_column FROM data_provenance "
        "WHERE target_pk = %s AND target_column = 'estimated_cost'",
        [str(test_request)],
    ).fetchone()
    assert row is not None
    assert row["source_type"] == "app"
    assert row["employee_id"] == _COORD


# ── concurrency: stale on any of the three justified fields ───────────────────

def test_concurrency_stale_on_cross_field(ac, test_request):
    """Assign succeeds; urgency with a stale current_assigned_employee_id must 409."""
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Nearest technician confirmed available", "input_method": "typed"},
    })
    assert r.status_code == 200

    # DB now has assigned_employee_id = _TECH; client still thinks it's None → stale
    r2 = c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "AJD",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,  # stale — DB now has _TECH
        "current_start_date": _DATE_A,
        "justification": {"text": "Water damage spreading rapidly", "input_method": "typed"},
    })
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "STALE_DATA"


# ── same-transaction rollback ─────────────────────────────────────────────────

def test_assign_rolls_back_on_failed_justification(monkeypatch):
    """
    UPDATE + write_justification + write_provenance are one transaction.
    If write_justification raises after the UPDATE, the middleware must roll
    back — assigned_employee_id unchanged, no justification row, no provenance row.

    Uses a real pool connection (not the db_conn test fixture) so the
    middleware's own rollback is the thing being tested — not fixture teardown.
    """
    import backend.modules.requests.repository as repo_module
    from backend.core.db import get_pool
    from backend.core.security import get_current_user
    from backend.main import create_app

    fresh_app = create_app()
    # Inject coordinator but leave get_db_conn alone — middleware owns the connection.
    fresh_app.dependency_overrides[get_current_user] = lambda: _user(_COORD, "coordinator")

    # Insert a real committed request so the route can lock and update it.
    with get_pool().connection() as setup:
        row = setup.execute(
            "INSERT INTO maintenance_request (status, building_id, sector_id, start_date) "
            "VALUES ('triaged', %s, %s, %s) RETURNING request_id",
            [_BLDG, _SECTOR, _DATE_A],
        ).fetchone()
        request_id = row["request_id"]
        setup.commit()

    # Patch write_justification to raise after update_field has already run.
    monkeypatch.setattr(repo_module, "write_justification", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("injected failure")))

    try:
        with TestClient(fresh_app, raise_server_exceptions=False) as c:
            r = c.post(f"/api/v1/requests/{request_id}/assign", json={
                "employee_id": _TECH,
                "current_assigned_employee_id": None,
                "current_start_date": _DATE_A,
                "current_urgency_tier": None,
                "justification": {"text": "Rollback test — should not persist", "input_method": "typed"},
            })

        assert r.status_code == 500

        with get_pool().connection() as verify:
            mreq = verify.execute(
                "SELECT assigned_employee_id FROM maintenance_request WHERE request_id = %s",
                [request_id],
            ).fetchone()
            assert mreq["assigned_employee_id"] is None, "UPDATE must be rolled back when justification write fails"

            jcount = verify.execute(
                "SELECT count(*) AS n FROM decision_justification_log WHERE request_id = %s",
                [request_id],
            ).fetchone()["n"]
            assert jcount == 0, "No justification row must survive a rollback"

            pcount = verify.execute(
                "SELECT count(*) AS n FROM data_provenance WHERE target_pk = %s AND source_type = 'app'",
                [str(request_id)],
            ).fetchone()["n"]
            assert pcount == 0, "No provenance row must survive a rollback"

    finally:
        with get_pool().connection() as cleanup:
            cleanup.execute("DELETE FROM maintenance_request WHERE request_id = %s", [request_id])
            cleanup.commit()
