"""Dispatcher accept / reject of AI task proposals (accepted_at IS NULL rows)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.tasks.repository import get_task, insert_task

_COORD = 4
_TECH = 14


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


@pytest.fixture
def ac(app, db_conn):
    def _factory(user: CurrentUser | None = None) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user or _user(_COORD, "coordinator")
        return TestClient(app, raise_server_exceptions=False)
    yield _factory
    app.dependency_overrides.clear()


def _call(db_conn, status="triage_proposal") -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request "
        "(status, raw_title, building_id, sector_id, triage_model_version) "
        "VALUES (%(s)s::request_status, 'Appel propositions', 3, 1, 'test-model') "
        "RETURNING request_id",
        {"s": status},
    ).fetchone()["request_id"]


def _feedback(db_conn, rid, employee_id=_COORD) -> None:
    from backend.modules.feedback.repository import upsert_feedback
    upsert_feedback(
        db_conn, rid, employee_id, "utile", None,
        {"problem_summary": "x"}, "test-model",
    )


def _proposal(db_conn, rid, description="Proposition IA") -> int:
    return insert_task(
        db_conn, request_id=rid, description=description,
        source="ai_recommended", accepted_at=None,
    )["task_id"]


def _status(db_conn, rid) -> str:
    return db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid],
    ).fetchone()["s"]


def _count(db_conn, rid) -> int:
    return db_conn.execute(
        "SELECT count(*) AS n FROM dispatch_task WHERE request_id = %s", [rid],
    ).fetchone()["n"]


# ── POST /tasks/{id}/accept ───────────────────────────────────────────────────

def test_accept_without_feedback_422(ac, db_conn):
    a = _proposal(db_conn, _call(db_conn))
    r = ac().post(f"/api/v1/tasks/{a}/accept")
    assert r.status_code == 422, r.text
    assert get_task(db_conn, a)["accepted_at"] is None


def test_accept_first_proposal_opens_call(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    a, b = _proposal(db_conn, rid, "A"), _proposal(db_conn, rid, "B")
    r = ac().post(f"/api/v1/tasks/{a}/accept")
    assert r.status_code == 200, r.text
    assert r.json()["accepted_at"] is not None
    assert r.json()["status"] == "queued"
    assert _status(db_conn, rid) == "open"
    assert get_task(db_conn, b)["accepted_at"] is None  # the other proposal is untouched


def test_accept_second_proposal_keeps_call_open(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    a, b = _proposal(db_conn, rid), _proposal(db_conn, rid)
    assert ac().post(f"/api/v1/tasks/{a}/accept").status_code == 200
    assert ac().post(f"/api/v1/tasks/{b}/accept").status_code == 200
    assert _status(db_conn, rid) == "open"


def test_accept_with_edited_description(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    a = _proposal(db_conn, rid, "Original")
    r = ac().post(f"/api/v1/tasks/{a}/accept", json={"description": "  Corrigé  "})
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Corrigé"
    assert db_conn.execute(
        "SELECT previous_value, ingested_value FROM data_provenance "
        "WHERE target_table = 'dispatch_task' AND target_pk = %s AND target_column = 'description'",
        [str(a)],
    ).fetchone() == {"previous_value": "Original", "ingested_value": "Corrigé"}


def test_accept_with_planning_fields_and_assignee(ac, db_conn):
    """Coordinator can edit AI prefill and schedule in the same Accept step."""
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    a = insert_task(
        db_conn, request_id=rid, description="Fuite",
        source="ai_recommended", accepted_at=None,
        subcontractor_name="Fortin", urgency_tier="URGENT",
    )["task_id"]
    r = ac().post(f"/api/v1/tasks/{a}/accept", json={
        "subcontractor_name": "Fortin Plomberie",
        "urgency_tier": "Intermédiaire",
        "assigned_employee_id": _TECH,
        "due_at": "2026-10-25T12:00:00",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subcontractor_name"] == "Fortin Plomberie"
    assert body["urgency_tier"] == "Intermédiaire"
    assert body["assigned_employee_id"] == _TECH
    assert body["due_at"] is not None
    assert body["status"] == "scheduled"
    assert body["accepted_at"] is not None


def test_accept_blank_description_422(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    a = _proposal(db_conn, rid)
    assert ac().post(f"/api/v1/tasks/{a}/accept", json={"description": "   "}).status_code == 422


def test_accept_on_open_call_leaves_status(ac, db_conn):
    rid = _call(db_conn, "open")
    _feedback(db_conn, rid)
    a = _proposal(db_conn, rid)
    assert ac().post(f"/api/v1/tasks/{a}/accept").status_code == 200
    assert _status(db_conn, rid) == "open"


def test_accept_twice_409(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    a = _proposal(db_conn, rid)
    assert ac().post(f"/api/v1/tasks/{a}/accept").status_code == 200
    assert ac().post(f"/api/v1/tasks/{a}/accept").status_code == 409


def test_accept_unknown_404(ac):
    assert ac().post("/api/v1/tasks/999999999/accept").status_code == 404


def test_accept_on_closed_call_409(ac, db_conn):
    rid = _call(db_conn, "closed")
    _feedback(db_conn, rid)
    a = _proposal(db_conn, rid)
    assert ac().post(f"/api/v1/tasks/{a}/accept").status_code == 409
    assert get_task(db_conn, a)["accepted_at"] is None


def test_accept_forbidden_for_technician(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    a = _proposal(db_conn, rid)
    assert ac(_user(_TECH, "technician")).post(f"/api/v1/tasks/{a}/accept").status_code == 403


# ── POST /requests/{id}/tasks/accept-all ──────────────────────────────────────

def test_accept_all_without_feedback_422(ac, db_conn):
    rid = _call(db_conn)
    _proposal(db_conn, rid)
    assert ac().post(f"/api/v1/requests/{rid}/tasks/accept-all").status_code == 422


def test_accept_all(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    ids = [_proposal(db_conn, rid, f"T{i}") for i in range(3)]
    r = ac().post(f"/api/v1/requests/{rid}/tasks/accept-all")
    assert r.status_code == 200, r.text
    assert sorted(t["task_id"] for t in r.json()) == sorted(ids)
    assert all(t["accepted_at"] is not None for t in r.json())
    assert _status(db_conn, rid) == "open"


def test_accept_all_without_proposals_409(ac, db_conn):
    rid = _call(db_conn, "open")
    _feedback(db_conn, rid)
    assert ac().post(f"/api/v1/requests/{rid}/tasks/accept-all").status_code == 409


def test_accept_all_unknown_request_404(ac):
    assert ac().post("/api/v1/requests/999999999/tasks/accept-all").status_code == 404


def test_accept_all_forbidden_for_technician(ac, db_conn):
    rid = _call(db_conn)
    _feedback(db_conn, rid)
    _proposal(db_conn, rid)
    assert ac(_user(_TECH, "technician")).post(
        f"/api/v1/requests/{rid}/tasks/accept-all").status_code == 403


# ── DELETE /tasks/{id} (reject) ───────────────────────────────────────────────

def test_reject_one_of_several_keeps_triage_proposal(ac, db_conn):
    rid = _call(db_conn)
    a, b = _proposal(db_conn, rid), _proposal(db_conn, rid)
    assert ac().delete(f"/api/v1/tasks/{a}").status_code == 204
    assert get_task(db_conn, a) is None
    assert get_task(db_conn, b) is not None
    assert _status(db_conn, rid) == "triage_proposal"


def test_reject_last_proposal_with_zero_accepted_goes_to_clarify(ac, db_conn):
    rid = _call(db_conn)
    a = _proposal(db_conn, rid)
    assert ac().delete(f"/api/v1/tasks/{a}").status_code == 204
    assert _status(db_conn, rid) == "triage_clarify"


def test_reject_last_proposal_on_open_call_stays_open(ac, db_conn):
    rid = _call(db_conn, "open")
    insert_task(db_conn, request_id=rid, description="Fait", source="dispatcher",
                accepted_at="2026-10-22T12:00:00Z")
    a = _proposal(db_conn, rid)
    assert ac().delete(f"/api/v1/tasks/{a}").status_code == 204
    assert _status(db_conn, rid) == "open"


def test_reject_accepted_task_409(ac, db_conn):
    rid = _call(db_conn, "open")
    t = insert_task(db_conn, request_id=rid, description="Fait", source="dispatcher",
                    accepted_at="2026-10-22T12:00:00Z")["task_id"]
    assert ac().delete(f"/api/v1/tasks/{t}").status_code == 409
    assert get_task(db_conn, t) is not None


def test_reject_unknown_404(ac):
    assert ac().delete("/api/v1/tasks/999999999").status_code == 404


def test_reject_forbidden_for_technician(ac, db_conn):
    a = _proposal(db_conn, _call(db_conn))
    assert ac(_user(_TECH, "technician")).delete(f"/api/v1/tasks/{a}").status_code == 403


# ── POST /requests/{id}/tasks/reject-all ──────────────────────────────────────

def test_reject_all_with_zero_accepted_goes_to_clarify(ac, db_conn):
    rid = _call(db_conn)
    for i in range(3):
        _proposal(db_conn, rid, f"T{i}")
    r = ac().post(f"/api/v1/requests/{rid}/tasks/reject-all")
    assert r.status_code == 200, r.text
    assert _count(db_conn, rid) == 0
    assert _status(db_conn, rid) == "triage_clarify"
    assert r.json()["status"] == "triage_clarify"


def test_reject_all_keeps_accepted_tasks_and_status(ac, db_conn):
    rid = _call(db_conn, "open")
    kept = insert_task(db_conn, request_id=rid, description="Fait", source="dispatcher",
                       accepted_at="2026-10-22T12:00:00Z")["task_id"]
    _proposal(db_conn, rid)
    _proposal(db_conn, rid)
    assert ac().post(f"/api/v1/requests/{rid}/tasks/reject-all").status_code == 200
    assert _count(db_conn, rid) == 1
    assert get_task(db_conn, kept) is not None
    assert _status(db_conn, rid) == "open"


def test_reject_all_without_proposals_409(ac, db_conn):
    rid = _call(db_conn, "open")
    assert ac().post(f"/api/v1/requests/{rid}/tasks/reject-all").status_code == 409
    assert _status(db_conn, rid) == "open"


def test_reject_all_forbidden_for_technician(ac, db_conn):
    rid = _call(db_conn)
    _proposal(db_conn, rid)
    assert ac(_user(_TECH, "technician")).post(
        f"/api/v1/requests/{rid}/tasks/reject-all").status_code == 403


# ── Visibility ────────────────────────────────────────────────────────────────

def test_request_detail_shows_proposals_to_coordinator_only(ac, db_conn):
    rid = _call(db_conn)
    a = _proposal(db_conn, rid)
    coord = ac().get(f"/api/v1/requests/{rid}")
    assert coord.status_code == 200
    assert a in [t["task_id"] for t in coord.json()["tasks"]]
    # A technician in the call's sector sees the call but never the proposals.
    tech = ac(_user(_TECH, "technician")).get(f"/api/v1/requests/{rid}")
    if tech.status_code == 200:
        assert a not in [t["task_id"] for t in tech.json()["tasks"]]
