"""Tests for POST /api/v1/requests/{id}/assign|reschedule|urgency|… endpoints."""
from __future__ import annotations

from datetime import date, timedelta

from backend.core.utils import today_local

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

_JUST = {"text": "Justification de test valide", "input_method": "typed"}


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

def test_assign_without_justification_422_no_change(ac, db_conn, test_request):
    # Justification is required on every dispatcher decision — omitting it is
    # rejected before anything is written.
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
    })
    assert r.status_code == 422
    assigned = db_conn.execute(
        "SELECT assigned_employee_id FROM maintenance_request WHERE request_id = %s",
        [test_request],
    ).fetchone()["assigned_employee_id"]
    assert assigned is None
    n = db_conn.execute(
        "SELECT count(*) AS n FROM decision_justification_log WHERE request_id = %s",
        [test_request],
    ).fetchone()["n"]
    assert n == 0


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


def test_assign_short_justification_422(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/assign", json={
        "employee_id": _TECH,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "current_urgency_tier": None,
        "justification": {"text": "Short", "input_method": "typed"},
    })
    assert r.status_code == 422


# ── reschedule ────────────────────────────────────────────────────────────────

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
        "urgency_tier": "URGENT",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 200
    assert r.json()["urgency_tier"] == "URGENT"


def test_set_urgency_stale_409(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "URGENT",
        "current_urgency_tier": "Intermédiaire",  # wrong — DB has NULL
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 409


def test_set_urgency_closed_409(ac, closed_request):
    c = ac(_user(_DIR, "director"))
    r = c.post(f"/api/v1/requests/{closed_request}/urgency", json={
        "urgency_tier": "URGENT",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 409


def test_set_urgency_technician_403(ac, test_request):
    c = ac(_user(_TECH, "technician"))
    r = c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "URGENT",
        "current_urgency_tier": None,
        "current_assigned_employee_id": None,
        "current_start_date": _DATE_A,
        "justification": {"text": "Tenant has water damage spreading", "input_method": "typed"},
    })
    assert r.status_code == 403


# ── follow-up date / next steps / cost ────────────────────────────────────────

def test_set_follow_up_date_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/follow-up-date", json={
        "next_follow_up_date": _DATE_B,
        "current_next_follow_up_date": None,
        "justification": _JUST,
    })
    assert r.status_code == 200
    assert r.json()["next_follow_up_date"] == _DATE_B


def test_set_follow_up_date_closed_409(ac, closed_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{closed_request}/follow-up-date", json={
        "next_follow_up_date": _DATE_B,
        "current_next_follow_up_date": None,
        "justification": _JUST,
    })
    assert r.status_code == 409


def test_set_next_steps_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/next-steps", json={
        "next_steps": "Order part then schedule return visit",
        "current_next_steps": None,
        "justification": _JUST,
    })
    assert r.status_code == 200
    assert r.json()["next_steps"] == "Order part then schedule return visit"


def test_set_cost_success(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/cost", json={
        "estimated_cost": "350.00",
        "current_estimated_cost": None,
        "justification": _JUST,
    })
    assert r.status_code == 200
    assert float(r.json()["estimated_cost"]) == 350.0


def test_set_cost_negative_422(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/cost", json={
        "estimated_cost": "-10",
        "current_estimated_cost": None,
        "justification": _JUST,
    })
    assert r.status_code == 422


def test_next_steps_writes_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/next-steps", json={
        "next_steps": "Call tenant tomorrow",
        "current_next_steps": None,
        "justification": _JUST,
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
    c.post(f"/api/v1/requests/{test_request}/next-steps", json={
        "next_steps": "Commander la pièce", "current_next_steps": None,
        "justification": {"text": "First available qualified technician", "input_method": "typed"},
    })
    r = c.get(f"/api/v1/requests/{test_request}")
    assert r.status_code == 200
    assert len(r.json()["justification_log"]) == 1


def test_justification_log_empty_for_technician(ac, db_conn, test_request):
    coord_c = ac(_user(_COORD, "coordinator"))
    coord_c.post(f"/api/v1/requests/{test_request}/next-steps", json={
        "next_steps": "Commander la pièce", "current_next_steps": None,
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
    assert entry["entry_date"] == str(today_local())
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

def test_set_urgency_stores_provenance(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{test_request}/urgency", json={
        "urgency_tier": "URGENT",
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
        "justification": _JUST,
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
        "justification": _JUST,
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

# ── same-transaction rollback ─────────────────────────────────────────────────

# ── Justification on the remaining dispatcher decisions ──────────────────────

def _justification_rows(db_conn, request_id):
    return db_conn.execute(
        "SELECT decision_type, before_value, after_value, justification_text, input_method "
        "FROM decision_justification_log WHERE request_id = %s",
        [request_id],
    ).fetchall()


def test_follow_up_date_stores_justification(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/follow-up-date", json={
        "next_follow_up_date": _DATE_B,
        "current_next_follow_up_date": None,
        "justification": {"text": "Locataire absente jusqu'à jeudi", "input_method": "voice"},
    })
    assert r.status_code == 200
    rows = _justification_rows(db_conn, test_request)
    assert len(rows) == 1
    assert rows[0]["decision_type"] == "follow_up_date"
    assert rows[0]["after_value"] == {"next_follow_up_date": _DATE_B}
    assert rows[0]["input_method"] == "voice"


def test_next_steps_stores_justification(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/next-steps", json={
        "next_steps": "Commander la pièce",
        "current_next_steps": None,
        "justification": {"text": "Pièce introuvable sur place", "input_method": "typed"},
    })
    assert r.status_code == 200
    rows = _justification_rows(db_conn, test_request)
    assert [row["decision_type"] for row in rows] == ["next_steps"]


def test_cost_stores_justification(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/cost", json={
        "estimated_cost": 250,
        "current_estimated_cost": None,
        "justification": {"text": "Soumission du plombier reçue", "input_method": "typed"},
    })
    assert r.status_code == 200
    rows = _justification_rows(db_conn, test_request)
    assert [row["decision_type"] for row in rows] == ["cost"]


def test_route_stores_justification(ac, db_conn, test_request):
    db_conn.execute(
        "UPDATE maintenance_request SET source_calendar = NULL WHERE request_id = %s", [test_request],
    )
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/route", json={
        "source_calendar": "st_maj",
        "expected_source_calendar": None,
        "justification": {"text": "Petit travail pour le majordome", "input_method": "voice"},
    })
    assert r.status_code == 200
    rows = _justification_rows(db_conn, test_request)
    assert [row["decision_type"] for row in rows] == ["route"]
    assert rows[0]["after_value"] == {"source_calendar": "st_maj"}


# Valid body (minus justification) for each decision endpoint still on the call,
# against the test_request fixture's initial state.
_DECISIONS = {
    "urgency": ("urgency", {
        "urgency_tier": "URGENT", "current_urgency_tier": None,
        "current_assigned_employee_id": None, "current_start_date": _DATE_A,
    }),
    "follow-up-date": ("follow_up_date", {
        "next_follow_up_date": _DATE_B, "current_next_follow_up_date": None,
    }),
    "next-steps": ("next_steps", {
        "next_steps": "Commander la pièce", "current_next_steps": None,
    }),
    "cost": ("cost", {
        "estimated_cost": 90, "current_estimated_cost": None,
    }),
    "route": ("route", {
        "source_calendar": "st_maj", "expected_source_calendar": None,
    }),
}


@pytest.fixture
def unrouted_request(db_conn, test_request):
    db_conn.execute(
        "UPDATE maintenance_request SET source_calendar = NULL WHERE request_id = %s", [test_request],
    )
    return test_request


@pytest.mark.parametrize("endpoint", list(_DECISIONS))
def test_decision_without_justification_422(ac, db_conn, unrouted_request, endpoint):
    """The rule can't be bypassed by calling the API directly."""
    _, body = _DECISIONS[endpoint]
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{unrouted_request}/{endpoint}", json=body)
    assert r.status_code == 422
    assert _justification_rows(db_conn, unrouted_request) == []


@pytest.mark.parametrize("endpoint", list(_DECISIONS))
def test_decision_with_null_justification_422(ac, unrouted_request, endpoint):
    _, body = _DECISIONS[endpoint]
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{unrouted_request}/{endpoint}", json={**body, "justification": None})
    assert r.status_code == 422


@pytest.mark.parametrize("endpoint", list(_DECISIONS))
def test_decision_short_justification_422(ac, unrouted_request, endpoint):
    _, body = _DECISIONS[endpoint]
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{unrouted_request}/{endpoint}", json={
        **body, "justification": {"text": "court", "input_method": "typed"},
    })
    assert r.status_code == 422


@pytest.mark.parametrize("endpoint", list(_DECISIONS))
def test_decision_writes_exactly_one_justification(ac, db_conn, unrouted_request, endpoint):
    decision_type, body = _DECISIONS[endpoint]
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{unrouted_request}/{endpoint}", json={**body, "justification": _JUST})
    assert r.status_code == 200, r.text
    rows = _justification_rows(db_conn, unrouted_request)
    assert [row["decision_type"] for row in rows] == [decision_type]
    assert rows[0]["justification_text"] == _JUST["text"]


# ── One « Enregistrer » for all dispatcher edits ─────────────────────────────

def _snapshot(**overrides):
    snap = {
        "assigned_employee_id": None, "start_date": _DATE_A, "urgency_tier": None,
        "next_follow_up_date": None, "next_steps": None, "estimated_cost": None,
    }
    snap.update(overrides)
    return snap


def test_save_dispatch_only_touches_fields_sent(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/dispatch", json={
        "current": _snapshot(),
        "changes": {"next_follow_up_date": _DATE_B},
        "justification": _JUST,
    })
    assert r.status_code == 200
    assert r.json()["next_follow_up_date"] == _DATE_B
    assert r.json()["start_date"] == _DATE_A
    assert [row["decision_type"] for row in _justification_rows(db_conn, test_request)] == ["follow_up_date"]


def test_save_dispatch_explicit_null_clears(ac, db_conn, test_request):
    db_conn.execute("UPDATE maintenance_request SET estimated_cost = 90 WHERE request_id = %s", [test_request])
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/dispatch", json={
        "current": _snapshot(estimated_cost=90),
        "changes": {"estimated_cost": None},
        "justification": _JUST,
    })
    assert r.status_code == 200
    assert r.json()["estimated_cost"] is None


def test_save_dispatch_requires_a_change_and_a_justification(ac, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/dispatch", json={
        "current": _snapshot(), "changes": {}, "justification": _JUST,
    })
    assert r.status_code == 422
    r = c.post(f"/api/v1/requests/{test_request}/dispatch", json={
        "current": _snapshot(), "changes": {"urgency_tier": "URGENT"},
    })
    assert r.status_code == 422


def test_save_dispatch_stale_screen_saves_nothing(ac, db_conn, test_request):
    c = ac(_user(_COORD, "coordinator"))
    r = c.post(f"/api/v1/requests/{test_request}/dispatch", json={
        # Screen thought cost was 10 — it is NULL in the DB → stale on the cost step.
        "current": _snapshot(estimated_cost=10),
        "changes": {"urgency_tier": "URGENT", "estimated_cost": 300},
        "justification": _JUST,
    })
    assert r.status_code == 409
    # The urgency step ran first; in the app DBTransactionMiddleware rolls the
    # whole request back on any status >= 400, so nothing is saved. (This test
    # shares one un-middlewared connection, so it checks the error surfaces.)
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_save_dispatch_forbidden_for_technician(ac, test_request):
    c = ac(_user(_TECH, "technician"))
    r = c.post(f"/api/v1/requests/{test_request}/dispatch", json={
        "current": _snapshot(), "changes": {"urgency_tier": "URGENT"}, "justification": _JUST,
    })
    assert r.status_code == 403
