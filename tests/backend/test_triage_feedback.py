"""Tests for POST/GET /api/v1/requests/{id}/feedback.

All writes use the rolled-back db_conn fixture — no rows survive past teardown.
Tests run against sib_test only (enforced by root conftest).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

# Real employee IDs in sib_test (verified from DB before writing this file).
_COORD = 4    # Charles Antoine Lessard — coordinator
_DIR   = 5    # Charles Bergeron — director
_TECH  = 14   # Jean-Frédéric Menada — technician
_CONT  = 20   # Mahmoud Chachia — contractor

# Building 3 (690-692 Saint-Augustin), sector 1 — both present in sib_test.
_BLDG   = 3
_SECTOR = 1

# Reason long enough to satisfy the 10-char minimum.
_LONG = "Résumé clair mais urgence sous-estimée dans ce contexte local."


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


@pytest.fixture
def ac(app, db_conn):
    """Factory: ac(user) → TestClient with that user injected."""
    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)
    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def triaged(db_conn):
    """Request with triage_model_version set — necessary for feedback to be allowed."""
    row = db_conn.execute(
        """INSERT INTO maintenance_request
               (status, building_id, sector_id, start_date,
                triage_model_version, problem_summary)
           VALUES ('triaged', %(bldg)s, %(sector)s, CURRENT_DATE,
                   'claude-sonnet-4-6', 'Robinet qui fuit sous l''évier')
           RETURNING request_id""",
        {"bldg": _BLDG, "sector": _SECTOR},
    ).fetchone()
    return row["request_id"]


@pytest.fixture
def untriaged(db_conn):
    """Request without triage_model_version — feedback must be rejected."""
    row = db_conn.execute(
        """INSERT INTO maintenance_request
               (status, building_id, sector_id, start_date)
           VALUES ('intake_received', %(bldg)s, %(sector)s, CURRENT_DATE)
           RETURNING request_id""",
        {"bldg": _BLDG, "sector": _SECTOR},
    ).fetchone()
    return row["request_id"]


# ── 403 for tech/contractor ───────────────────────────────────────────────────

def test_technician_post_403(ac, triaged):
    r = ac(_user(_TECH, "technician")).post(
        f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"}
    )
    assert r.status_code == 403


def test_contractor_post_403(ac, triaged):
    r = ac(_user(_CONT, "contractor")).post(
        f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"}
    )
    assert r.status_code == 403


def test_technician_get_403(ac, triaged):
    r = ac(_user(_TECH, "technician")).get(f"/api/v1/requests/{triaged}/feedback")
    assert r.status_code == 403


# ── Level validation ──────────────────────────────────────────────────────────

def test_utile_no_reason_succeeds(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["level"] == "utile"
    assert data["reason"] is None


def test_utile_feedback_does_not_auto_accept(ac, db_conn):
    """Feedback alone does not dispatch — accept is a separate gated step."""
    from backend.modules.tasks.repository import insert_task

    rid = db_conn.execute(
        """INSERT INTO maintenance_request
               (status, building_id, sector_id, start_date,
                triage_model_version, problem_summary)
           VALUES ('triage_proposal', %(bldg)s, %(sector)s, CURRENT_DATE,
                   'claude-sonnet-4-6', 'Fuite')
           RETURNING request_id""",
        {"bldg": _BLDG, "sector": _SECTOR},
    ).fetchone()["request_id"]
    a = insert_task(
        db_conn, request_id=rid, description="Réparer", source="ai_recommended",
        accepted_at=None, assigned_employee_id=_TECH, urgency_tier="URGENT",
    )["task_id"]
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{rid}/feedback", json={"level": "utile"},
    )
    assert r.status_code == 200, r.text
    assert db_conn.execute(
        "SELECT accepted_at FROM dispatch_task WHERE task_id = %s", [a],
    ).fetchone()["accepted_at"] is None
    assert db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid],
    ).fetchone()["s"] == "triage_proposal"


def test_utile_with_reason_stored(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "utile", "reason": "Tout à fait correct."},
    )
    assert r.status_code == 200
    assert r.json()["reason"] == "Tout à fait correct."


def test_partiellement_utile_no_reason_422(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "partiellement utile"},
    )
    assert r.status_code == 422


def test_partiellement_utile_short_reason_422(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "partiellement utile", "reason": "Court"},
    )
    assert r.status_code == 422


def test_reason_all_spaces_422(ac, triaged):
    """Whitespace-only reason must count as missing — stripped length < 10."""
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "partiellement utile", "reason": "          "},
    )
    assert r.status_code == 422


def test_partiellement_utile_long_reason_succeeds(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "partiellement utile", "reason": _LONG},
    )
    assert r.status_code == 200


def test_pas_utile_no_reason_422(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback", json={"level": "pas utile"}
    )
    assert r.status_code == 422


def test_pas_utile_long_reason_succeeds(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": _LONG},
    )
    assert r.status_code == 200


# ── Triage guard ──────────────────────────────────────────────────────────────

def test_untriaged_request_422(ac, untriaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{untriaged}/feedback", json={"level": "utile"}
    )
    assert r.status_code == 422


def test_nonexistent_request_404(ac):
    r = ac(_user(_COORD, "coordinator")).post(
        "/api/v1/requests/999999/feedback", json={"level": "utile"}
    )
    assert r.status_code == 404


# ── One per employee per call (upsert) ────────────────────────────────────────

def test_second_post_updates_not_duplicates(ac, db_conn, triaged):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})
    r = c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": _LONG},
    )
    assert r.status_code == 200
    n = db_conn.execute(
        "SELECT count(*) AS n FROM triage_notes_feedback"
        " WHERE request_id = %s AND employee_id = %s",
        [triaged, _COORD],
    ).fetchone()["n"]
    assert n == 1


# ── Edit history tracks OLD state ─────────────────────────────────────────────

def test_edit_history_records_old_level(ac, triaged):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})
    r = c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": _LONG},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["edit_history"]) == 1
    entry = data["edit_history"][0]
    assert entry["old_level"] == "utile"
    assert entry["new_level"] == "pas utile"
    assert entry["old_reason"] is None
    assert entry["new_reason"] == _LONG
    assert entry["edited_by"] == _COORD
    assert "edited_at" in entry
    assert "old_triage_output" in entry
    assert "old_triage_model_version" in entry


def test_edit_history_old_reason_survives_edit(ac, triaged):
    """First reason must appear as old_reason in the next history entry."""
    c = ac(_user(_COORD, "coordinator"))
    c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "partiellement utile", "reason": _LONG},
    )
    r = c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": "Complètement inexact dans ce dossier."},
    )
    entry = r.json()["edit_history"][0]
    assert entry["old_reason"] == _LONG
    assert entry["new_reason"] == "Complètement inexact dans ce dossier."


def test_edit_history_has_old_snapshot(ac, triaged):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})
    r = c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": _LONG},
    )
    entry = r.json()["edit_history"][0]
    assert entry["old_triage_output"]["triage_model_version"] == "claude-sonnet-4-6"
    assert entry["old_triage_model_version"] == "claude-sonnet-4-6"


def test_retriage_snapshot_in_history(ac, db_conn, triaged):
    """After triage re-runs (new model version), edit shows old snapshot in
    history and new snapshot on the main row."""
    c = ac(_user(_COORD, "coordinator"))
    # First feedback with v1
    c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})

    # Simulate triage re-run: update triage_model_version on the request
    db_conn.execute(
        "UPDATE maintenance_request SET triage_model_version = 'claude-opus-4-8'"
        " WHERE request_id = %s",
        [triaged],
    )

    # Second feedback — snapshot should now show the new model version
    r = c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": _LONG},
    )
    data = r.json()
    # Main row snapshot reflects the NEW triage run
    assert data["triage_output"]["triage_model_version"] == "claude-opus-4-8"
    assert data["triage_model_version"] == "claude-opus-4-8"
    # History entry captures the OLD snapshot (v1)
    assert data["edit_history"][0]["old_triage_model_version"] == "claude-sonnet-4-6"
    assert data["edit_history"][0]["old_triage_output"]["triage_model_version"] == "claude-sonnet-4-6"


def test_noop_edit_produces_no_history(ac, triaged):
    """Submitting the exact same level, reason, and snapshot twice must not
    append a history entry."""
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})
    r = c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})
    assert r.status_code == 200
    assert r.json()["edit_history"] == []


def test_three_edits_history_length(ac, triaged):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})
    c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": _LONG},
    )
    r = c.post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "partiellement utile", "reason": _LONG},
    )
    assert len(r.json()["edit_history"]) == 2


# ── Two employees, independent ────────────────────────────────────────────────

def test_two_employees_independent(ac, db_conn, triaged):
    ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"}
    )
    ac(_user(_DIR, "director")).post(
        f"/api/v1/requests/{triaged}/feedback",
        json={"level": "pas utile", "reason": _LONG},
    )
    n = db_conn.execute(
        "SELECT count(*) AS n FROM triage_notes_feedback WHERE request_id = %s",
        [triaged],
    ).fetchone()["n"]
    assert n == 2


# ── GET own feedback ──────────────────────────────────────────────────────────

def test_get_before_feedback_404(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{triaged}/feedback")
    assert r.status_code == 404


def test_get_returns_own_feedback(ac, triaged):
    c = ac(_user(_COORD, "coordinator"))
    c.post(f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"})
    r = c.get(f"/api/v1/requests/{triaged}/feedback")
    assert r.status_code == 200
    assert r.json()["employee_id"] == _COORD


def test_coord_cannot_see_director_feedback(ac, triaged):
    """GET is scoped to the requesting employee — director's row is invisible."""
    ac(_user(_DIR, "director")).post(
        f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"}
    )
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{triaged}/feedback")
    assert r.status_code == 404


# ── Creation snapshot ─────────────────────────────────────────────────────────

def test_creation_snapshot_stored(ac, triaged):
    r = ac(_user(_COORD, "coordinator")).post(
        f"/api/v1/requests/{triaged}/feedback", json={"level": "utile"}
    )
    snapshot = r.json()["triage_output"]
    assert snapshot["triage_model_version"] == "claude-sonnet-4-6"
    assert snapshot["problem_summary"] == "Robinet qui fuit sous l'évier"


# ── RLS and view privilege ─────────────────────────────────────────────────────

def test_rls_is_enabled(db_conn):
    row = db_conn.execute(
        "SELECT relrowsecurity FROM pg_class WHERE relname = 'triage_notes_feedback'",
    ).fetchone()
    assert row["relrowsecurity"] is True


def test_anon_has_no_select_on_view(db_conn):
    row = db_conn.execute(
        "SELECT has_table_privilege('anon', 'triage_feedback_review', 'SELECT') AS can",
    ).fetchone()
    assert row["can"] is False


def test_authenticated_has_no_select_on_view(db_conn):
    row = db_conn.execute(
        "SELECT has_table_privilege('authenticated', 'triage_feedback_review', 'SELECT') AS can",
    ).fetchone()
    assert row["can"] is False
