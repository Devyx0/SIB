"""HTTP API for dispatch tasks: GET/POST /api/v1/tasks, assign, schedule."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.tasks.repository import (
    get_task, insert_task, maybe_close_request, update_task_status,
)

_COORD = 4    # coordinator
_TECH = 14    # technician
_TECH2 = 15   # other technician
_CONT = 20    # contractor

_DUE = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
_DUE_ISO = _DUE.isoformat()
_JUST = {"text": "Justification de test valide", "input_method": "typed"}


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


def _coord() -> CurrentUser:
    return _user(_COORD, "coordinator")


@pytest.fixture
def ac(app, db_conn):
    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)
    yield _factory
    app.dependency_overrides.clear()


def _mk_request(db_conn, status="open") -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, raw_title, building_id, sector_id) "
        "VALUES (%(s)s::request_status, 'Appel tâches', 3, 1) RETURNING request_id",
        {"s": status},
    ).fetchone()["request_id"]


def _req_status(db_conn, rid) -> str:
    return db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid],
    ).fetchone()["s"]


@pytest.fixture
def open_request_id(db_conn):
    return _mk_request(db_conn)


def _accepted(db_conn, rid, description="Plomberie", **kw) -> dict:
    kw.setdefault("accepted_at", "2026-10-22T12:00:00Z")
    kw.setdefault("source", "dispatcher")
    return insert_task(db_conn, request_id=rid, description=description, **kw)


@pytest.fixture
def call_with_proposal_and_accepted(db_conn):
    rid = _mk_request(db_conn)
    accepted = _accepted(db_conn, rid, "Accepté")
    proposal = insert_task(
        db_conn, request_id=rid, description="Proposition IA",
        source="ai_recommended", accepted_at=None,
    )
    return rid, accepted["task_id"], proposal["task_id"]


# ── POST /tasks ───────────────────────────────────────────────────────────────

def test_create_task_on_open_call(ac, open_request_id):
    r = ac(_coord()).post("/api/v1/tasks", json={"request_id": open_request_id, "description": "Plomberie", "justification": _JUST})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["accepted_at"] is not None
    assert body["source"] == "dispatcher"
    assert body["request_id"] == open_request_id


@pytest.mark.parametrize("parent_status", ["needs_expertise", "return_visit"])
def test_create_task_with_parent_links_lineage(ac, db_conn, open_request_id, parent_status):
    parent = _accepted(db_conn, open_request_id, status=parent_status)
    r = ac(_coord()).post("/api/v1/tasks", json={
        "request_id": open_request_id, "description": "Redispatch", "justification": _JUST,
        "parent_task_id": parent["task_id"],
    })
    assert r.status_code == 200, r.text
    child_id = r.json()["task_id"]
    assert r.json()["parent_task_id"] == parent["task_id"]

    rows = {t["task_id"]: t for t in ac(_coord()).get(
        "/api/v1/tasks", params={"status": parent_status}).json()["items"]}
    assert rows[parent["task_id"]]["has_followup"] is True

    # The parent no longer blocks auto-close; the child's own outcome decides.
    update_task_status(db_conn, child_id, "done")
    assert maybe_close_request(db_conn, open_request_id) is True


def test_list_tasks_has_followup_false_without_child(ac, db_conn, open_request_id):
    parent = _accepted(db_conn, open_request_id, status="needs_expertise")
    rows = {t["task_id"]: t for t in ac(_coord()).get(
        "/api/v1/tasks", params={"status": "needs_expertise"}).json()["items"]}
    assert rows[parent["task_id"]]["has_followup"] is False


@pytest.mark.parametrize("case", ["other_call", "wrong_status", "proposal", "unknown"])
def test_create_task_invalid_parent_422(ac, db_conn, open_request_id, case):
    if case == "other_call":
        pid = _accepted(db_conn, _mk_request(db_conn), status="needs_expertise")["task_id"]
    elif case == "wrong_status":
        pid = _accepted(db_conn, open_request_id, status="done")["task_id"]
    elif case == "proposal":
        pid = insert_task(db_conn, request_id=open_request_id, description="IA",
                          status="needs_expertise", source="ai_recommended",
                          accepted_at=None)["task_id"]
    else:
        pid = 999_999_999
    r = ac(_coord()).post("/api/v1/tasks", json={
        "request_id": open_request_id, "description": "Redispatch", "justification": _JUST,
        "parent_task_id": pid,
    })
    assert r.status_code == 422, r.text
    assert db_conn.execute(
        "SELECT count(*) AS n FROM dispatch_task WHERE description = 'Redispatch'",
    ).fetchone()["n"] == 0


def test_create_task_with_assignee_and_due_is_scheduled(ac, open_request_id):
    r = ac(_coord()).post("/api/v1/tasks", json={
        "request_id": open_request_id, "description": "Plomberie", "justification": _JUST,
        "assigned_employee_id": _TECH, "due_at": _DUE_ISO,
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"
    assert r.json()["assigned_employee_id"] == _TECH


def test_create_task_with_assignee_only_stays_queued(ac, open_request_id):
    r = ac(_coord()).post("/api/v1/tasks", json={
        "request_id": open_request_id, "description": "Plomberie", "assigned_employee_id": _TECH,
        "justification": _JUST,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_create_task_invalid_assignee_422(ac, open_request_id):
    r = ac(_coord()).post("/api/v1/tasks", json={
        "request_id": open_request_id, "description": "x", "assigned_employee_id": _COORD,
        "justification": _JUST,
    })
    assert r.status_code == 422


def test_create_task_blank_description_422(ac, open_request_id):
    r = ac(_coord()).post("/api/v1/tasks", json={"request_id": open_request_id, "description": "   ", "justification": _JUST})
    assert r.status_code == 422


def test_create_task_unknown_request_404(ac):
    r = ac(_coord()).post("/api/v1/tasks", json={"request_id": 999999999, "description": "x", "justification": _JUST})
    assert r.status_code == 404


def test_create_task_closed_call_409(ac, db_conn):
    rid = _mk_request(db_conn, "closed")
    r = ac(_coord()).post("/api/v1/tasks", json={"request_id": rid, "description": "x", "justification": _JUST})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REQUEST_CLOSED"


def test_create_task_on_triaged_call_opens_it(ac, db_conn):
    rid = _mk_request(db_conn, "triaged")
    r = ac(_coord()).post("/api/v1/tasks", json={"request_id": rid, "description": "x", "justification": _JUST})
    assert r.status_code == 200
    assert _req_status(db_conn, rid) == "open"


@pytest.mark.parametrize("status", ["intake_received", "triage_pending", "triage_proposal"])
def test_create_task_before_triage_done_409(ac, db_conn, status):
    rid = _mk_request(db_conn, status)
    r = ac(_coord()).post("/api/v1/tasks", json={"request_id": rid, "description": "x", "justification": _JUST})
    assert r.status_code == 409
    assert _req_status(db_conn, rid) == status


def test_create_task_forbidden_for_technician(ac, open_request_id):
    r = ac(_user(_TECH, "technician")).post(
        "/api/v1/tasks", json={"request_id": open_request_id, "description": "x", "justification": _JUST})
    assert r.status_code == 403


# ── GET /tasks ────────────────────────────────────────────────────────────────

def test_list_tasks_hides_proposals(ac, call_with_proposal_and_accepted):
    _, accepted_id, proposal_id = call_with_proposal_and_accepted
    items = ac(_coord()).get("/api/v1/tasks").json()["items"]
    assert all(t["accepted_at"] is not None for t in items)
    ids = {t["task_id"] for t in items}
    assert accepted_id in ids
    assert proposal_id not in ids


def test_list_tasks_filter_status_and_assignee(ac, db_conn, open_request_id):
    a = _accepted(db_conn, open_request_id, "A", assigned_employee_id=_TECH)
    b = _accepted(db_conn, open_request_id, "B", assigned_employee_id=_TECH2)
    c = _accepted(db_conn, open_request_id, "C", assigned_employee_id=_TECH)
    update_task_status(db_conn, c["task_id"], "cancelled")
    cl = ac(_coord())

    items = cl.get("/api/v1/tasks", params={"assigned_employee_id": _TECH}).json()["items"]
    ids = {t["task_id"] for t in items}
    assert {a["task_id"], c["task_id"]} <= ids and b["task_id"] not in ids

    items = cl.get("/api/v1/tasks", params=[("status", "cancelled"), ("assigned_employee_id", _TECH)]).json()["items"]
    assert [t["task_id"] for t in items] == [c["task_id"]]


def test_list_tasks_date_range_filters_on_due_at(ac, db_conn, open_request_id):
    inside = _accepted(db_conn, open_request_id, "in", due_at=_DUE)
    outside = _accepted(db_conn, open_request_id, "out", due_at=_DUE + timedelta(days=20))
    unscheduled = _accepted(db_conn, open_request_id, "none")
    d = _DUE.date()
    r = ac(_coord()).get("/api/v1/tasks", params={
        "start_date": str(d - timedelta(days=1)), "end_date": str(d + timedelta(days=1)),
    })
    ids = {t["task_id"] for t in r.json()["items"]}
    assert inside["task_id"] in ids
    assert outside["task_id"] not in ids and unscheduled["task_id"] not in ids


def test_list_tasks_carry_call_context(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, "ctx", assigned_employee_id=_TECH)
    items = ac(_coord()).get("/api/v1/tasks", params={"assigned_employee_id": _TECH}).json()["items"]
    row = next(i for i in items if i["task_id"] == t["task_id"])
    assert row["request_title"] == "Appel tâches"
    assert row["request_status"] == "open"
    assert row["sector_id"] == 1
    assert row["building_address"] is not None
    assert row["assigned_employee_name"] is not None


def test_list_tasks_dates_must_come_together(ac):
    r = ac(_coord()).get("/api/v1/tasks", params={"start_date": "2026-10-01"})
    assert r.status_code == 422


def test_list_tasks_technician_sees_only_own(ac, db_conn, open_request_id):
    mine = _accepted(db_conn, open_request_id, "mine", assigned_employee_id=_TECH)
    other = _accepted(db_conn, open_request_id, "other", assigned_employee_id=_TECH2)
    r = ac(_user(_TECH, "technician")).get("/api/v1/tasks", params={"assigned_employee_id": _TECH2})
    ids = {t["task_id"] for t in r.json()["items"]}
    assert other["task_id"] not in ids
    r = ac(_user(_TECH, "technician")).get("/api/v1/tasks")
    ids = {t["task_id"] for t in r.json()["items"]}
    assert mine["task_id"] in ids and other["task_id"] not in ids


# ── POST /tasks/{id}/assign ───────────────────────────────────────────────────

def test_assign_with_due_at_schedules(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, due_at=_DUE)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign", json={"assigned_employee_id": _TECH, "justification": _JUST})
    assert r.status_code == 200, r.text
    assert r.json()["assigned_employee_id"] == _TECH
    assert r.json()["status"] == "scheduled"


def test_assign_without_due_at_stays_queued(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign", json={"assigned_employee_id": _TECH, "justification": _JUST})
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert get_task(db_conn, t["task_id"])["assigned_employee_id"] == _TECH


def test_unassign_scheduled_returns_to_queued(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, due_at=_DUE, assigned_employee_id=_TECH, status="scheduled")
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign", json={"assigned_employee_id": None, "justification": _JUST})
    assert r.status_code == 200
    assert r.json()["assigned_employee_id"] is None
    assert r.json()["status"] == "queued"


def test_reassign_scheduled_keeps_scheduled(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, due_at=_DUE, assigned_employee_id=_TECH, status="scheduled")
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign", json={"assigned_employee_id": _TECH2, "justification": _JUST})
    assert r.status_code == 200
    assert r.json()["status"] == "scheduled"
    assert r.json()["assigned_employee_id"] == _TECH2


def test_assign_invalid_assignee_422(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign", json={"assigned_employee_id": _COORD, "justification": _JUST})
    assert r.status_code == 422
    assert get_task(db_conn, t["task_id"])["assigned_employee_id"] is None


@pytest.mark.parametrize("status", ["en_route", "arrived", "working", "done", "cancelled"])
def test_assign_after_dispatch_or_terminal_409(ac, db_conn, open_request_id, status):
    t = _accepted(db_conn, open_request_id, assigned_employee_id=_TECH, due_at=_DUE, status=status)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign", json={"assigned_employee_id": _TECH2, "justification": _JUST})
    assert r.status_code == 409
    assert get_task(db_conn, t["task_id"])["assigned_employee_id"] == _TECH


def test_assign_proposal_404(ac, call_with_proposal_and_accepted):
    # Proposals are invisible until accepted — they are not assignable via /tasks.
    _, _, proposal_id = call_with_proposal_and_accepted
    r = ac(_coord()).post(f"/api/v1/tasks/{proposal_id}/assign", json={"assigned_employee_id": _TECH, "justification": _JUST})
    assert r.status_code == 404


def test_assign_unknown_task_404(ac):
    r = ac(_coord()).post("/api/v1/tasks/999999999/assign", json={"assigned_employee_id": _TECH, "justification": _JUST})
    assert r.status_code == 404


def test_assign_forbidden_for_contractor(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id)
    r = ac(_user(_CONT, "contractor")).post(
        f"/api/v1/tasks/{t['task_id']}/assign", json={"assigned_employee_id": _TECH, "justification": _JUST})
    assert r.status_code == 403


# ── POST /tasks/{id}/schedule ─────────────────────────────────────────────────

def test_schedule_sets_due_at(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/schedule", json={"due_at": _DUE_ISO, "justification": _JUST})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"  # no assignee yet
    assert get_task(db_conn, t["task_id"])["due_at"] == _DUE


def test_schedule_with_assignee_schedules(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, assigned_employee_id=_TECH)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/schedule", json={"due_at": _DUE_ISO, "justification": _JUST})
    assert r.status_code == 200
    assert r.json()["status"] == "scheduled"


def test_schedule_clear_due_at_returns_to_queued(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, assigned_employee_id=_TECH, due_at=_DUE, status="scheduled")
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/schedule", json={"due_at": None, "justification": _JUST})
    assert r.status_code == 200
    assert r.json()["due_at"] is None
    assert r.json()["status"] == "queued"


def test_schedule_naive_datetime_accepted(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/schedule", json={"due_at": "2026-12-01T09:00:00", "justification": _JUST})
    assert r.status_code == 200
    assert r.json()["due_at"] is not None


def test_schedule_missing_due_at_422(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id)
    assert ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/schedule", json={"justification": _JUST}).status_code == 422


@pytest.mark.parametrize("status", ["en_route", "done", "cancelled"])
def test_schedule_after_dispatch_or_terminal_409(ac, db_conn, open_request_id, status):
    t = _accepted(db_conn, open_request_id, assigned_employee_id=_TECH, due_at=_DUE, status=status)
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/schedule", json={"due_at": _DUE_ISO, "justification": _JUST})
    assert r.status_code == 409


def test_schedule_unknown_task_404(ac):
    r = ac(_coord()).post("/api/v1/tasks/999999999/schedule", json={"due_at": _DUE_ISO, "justification": _JUST})
    assert r.status_code == 404


# ── GET /requests/{id} carries tasks ──────────────────────────────────────────

def test_request_detail_includes_tasks(ac, call_with_proposal_and_accepted):
    rid, accepted_id, proposal_id = call_with_proposal_and_accepted
    d = ac(_coord()).get(f"/api/v1/requests/{rid}").json()
    ids = {t["task_id"] for t in d["tasks"]}
    assert ids == {accepted_id, proposal_id}  # dispatcher sees proposals too


def test_request_detail_hides_proposals_from_technician(ac, db_conn, call_with_proposal_and_accepted):
    rid, accepted_id, proposal_id = call_with_proposal_and_accepted
    db_conn.execute("UPDATE dispatch_task SET assigned_employee_id = %s WHERE task_id = %s", [_TECH, accepted_id])
    d = ac(_user(_TECH, "technician")).get(f"/api/v1/requests/{rid}").json()
    assert [t["task_id"] for t in d["tasks"]] == [accepted_id]


# ── request-level fieldwork writes are gone (410) ─────────────────────────────

def _snapshot():
    return {"assigned_employee_id": None, "start_date": None, "urgency_tier": None,
            "next_follow_up_date": None, "next_steps": None, "estimated_cost": None}


def test_request_assign_is_gone(ac, db_conn, open_request_id):
    r = ac(_coord()).post(f"/api/v1/requests/{open_request_id}/assign", json={
        "employee_id": _TECH, "current_assigned_employee_id": None,
        "current_start_date": None, "current_urgency_tier": None, "justification": _JUST,
    })
    assert r.status_code == 410
    assert "/tasks" in r.json()["error"]["message"]
    row = db_conn.execute(
        "SELECT assigned_employee_id FROM maintenance_request WHERE request_id = %s", [open_request_id],
    ).fetchone()
    assert row["assigned_employee_id"] is None


def test_request_reschedule_is_gone(ac, db_conn, open_request_id):
    r = ac(_coord()).post(f"/api/v1/requests/{open_request_id}/reschedule", json={
        "start_date": "2026-12-01", "current_start_date": None,
        "current_assigned_employee_id": None, "current_urgency_tier": None, "justification": _JUST,
    })
    assert r.status_code == 410
    row = db_conn.execute(
        "SELECT start_date FROM maintenance_request WHERE request_id = %s", [open_request_id],
    ).fetchone()
    assert row["start_date"] is None


@pytest.mark.parametrize("changes", [
    {"assigned_employee_id": _TECH},
    {"start_date": "2026-12-01"},
    {"urgency_tier": "URGENT", "assigned_employee_id": _TECH},
])
def test_request_save_dispatch_with_fieldwork_is_gone_and_writes_nothing(ac, db_conn, open_request_id, changes):
    r = ac(_coord()).post(f"/api/v1/requests/{open_request_id}/dispatch", json={
        "current": _snapshot(), "changes": changes, "justification": _JUST,
    })
    assert r.status_code == 410
    row = db_conn.execute(
        "SELECT urgency_tier::text AS u, assigned_employee_id, start_date "
        "FROM maintenance_request WHERE request_id = %s", [open_request_id],
    ).fetchone()
    assert row["assigned_employee_id"] is None and row["start_date"] is None
    assert row["u"] in (None, "none")


def test_request_save_dispatch_without_fieldwork_still_works(ac, open_request_id):
    r = ac(_coord()).post(f"/api/v1/requests/{open_request_id}/dispatch", json={
        "current": _snapshot(), "changes": {"next_steps": "Commander la pièce"}, "justification": _JUST,
    })
    assert r.status_code == 200, r.text
    assert r.json()["next_steps"] == "Commander la pièce"


# ── justification + provenance on task decisions ──────────────────────────────

def _just_rows(db_conn, rid):
    return db_conn.execute(
        "SELECT decision_type, employee_id, justification_text, input_method, before_value, after_value "
        "FROM decision_justification_log WHERE request_id = %s ORDER BY id", [rid],
    ).fetchall()


def _prov(db_conn, task_id, column):
    return db_conn.execute(
        "SELECT source_type, employee_id, previous_value, ingested_value FROM data_provenance "
        "WHERE target_table = 'dispatch_task' AND target_pk = %s AND target_column = %s ORDER BY provenance_id",
        [str(task_id), column],
    ).fetchall()


def test_create_writes_justification_and_provenance(ac, db_conn, open_request_id):
    r = ac(_coord()).post("/api/v1/tasks", json={
        "request_id": open_request_id, "description": "Plomberie",
        "assigned_employee_id": _TECH, "due_at": _DUE_ISO,
        "justification": {"text": "Fuite active au sous-sol", "input_method": "voice"},
    })
    tid = r.json()["task_id"]
    [row] = _just_rows(db_conn, open_request_id)
    assert row["decision_type"] == "task_create"
    assert row["employee_id"] == _COORD
    assert row["justification_text"] == "Fuite active au sous-sol"
    assert row["input_method"] == "voice"
    assert row["after_value"]["task_id"] == tid
    assert row["after_value"]["assigned_employee_id"] == _TECH
    [st] = _prov(db_conn, tid, "status")
    assert (st["source_type"], st["employee_id"], st["previous_value"], st["ingested_value"]) == (
        "app", _COORD, None, "scheduled")
    assert [p["ingested_value"] for p in _prov(db_conn, tid, "assigned_employee_id")] == [str(_TECH)]


def test_assign_writes_justification_and_provenance(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, due_at=_DUE)
    ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign", json={
        "assigned_employee_id": _TECH,
        "justification": {"text": "Technicien le plus proche", "input_method": "typed"},
    })
    [row] = _just_rows(db_conn, open_request_id)
    assert row["decision_type"] == "task_assign"
    assert row["before_value"] == {"task_id": t["task_id"], "assigned_employee_id": None}
    assert row["after_value"] == {"task_id": t["task_id"], "assigned_employee_id": _TECH}
    [a] = _prov(db_conn, t["task_id"], "assigned_employee_id")
    assert (a["employee_id"], a["previous_value"], a["ingested_value"]) == (_COORD, None, str(_TECH))
    [st] = _prov(db_conn, t["task_id"], "status")
    assert (st["previous_value"], st["ingested_value"]) == ("queued", "scheduled")


def test_schedule_writes_justification_and_provenance(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id)
    ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/schedule", json={
        "due_at": _DUE_ISO, "justification": {"text": "Locataire disponible ce jour", "input_method": "typed"},
    })
    [row] = _just_rows(db_conn, open_request_id)
    assert row["decision_type"] == "task_schedule"
    assert row["before_value"]["due_at"] is None
    assert row["after_value"]["due_at"] is not None
    [d] = _prov(db_conn, t["task_id"], "due_at")
    assert d["previous_value"] is None and d["ingested_value"] is not None


@pytest.mark.parametrize("path,body", [
    ("assign", {"assigned_employee_id": _TECH}),
    ("schedule", {"due_at": _DUE_ISO}),
])
def test_assign_schedule_require_justification_no_change(ac, db_conn, open_request_id, path, body):
    t = _accepted(db_conn, open_request_id)
    c = ac(_coord())
    assert c.post(f"/api/v1/tasks/{t['task_id']}/{path}", json=body).status_code == 422
    short = {**body, "justification": {"text": "court", "input_method": "typed"}}
    assert c.post(f"/api/v1/tasks/{t['task_id']}/{path}", json=short).status_code == 422
    after = get_task(db_conn, t["task_id"])
    assert after["assigned_employee_id"] is None and after["due_at"] is None
    assert _just_rows(db_conn, open_request_id) == []


def test_create_requires_justification(ac, db_conn, open_request_id):
    r = ac(_coord()).post("/api/v1/tasks", json={"request_id": open_request_id, "description": "x"})
    assert r.status_code == 422
    assert db_conn.execute(
        "SELECT count(*) AS n FROM dispatch_task WHERE request_id = %s", [open_request_id]).fetchone()["n"] == 0


def test_rejected_assign_writes_no_log(ac, db_conn, open_request_id):
    t = _accepted(db_conn, open_request_id, status="done")
    r = ac(_coord()).post(f"/api/v1/tasks/{t['task_id']}/assign",
                          json={"assigned_employee_id": _TECH, "justification": _JUST})
    assert r.status_code == 409
    assert _just_rows(db_conn, open_request_id) == []
