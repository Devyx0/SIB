"""Task closeout: outcome → task status mapping, follow-up spawn, call auto-close,
auto-enter `working`, and the removed request-level fieldwork routes."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.core.utils import today_local
from backend.modules.tasks.repository import insert_task

_TECH = 24
_OTHER_TECH = 14
_COORD = 4

_COMMENT = "Travail effectué, remplacement du joint."


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


def _tech() -> CurrentUser:
    return _user(_TECH, "technician")


@pytest.fixture
def ac(app, db_conn):
    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_storage(monkeypatch):
    monkeypatch.setattr("backend.modules.requests.storage.upload_photo",
                        lambda path, content, mime: None)


@pytest.fixture
def building(db_conn):
    return db_conn.execute(
        "SELECT building_id FROM building WHERE adresse IS NOT NULL LIMIT 1"
    ).fetchone()


def _mk_call(db_conn, building_id) -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, raw_title) "
        "VALUES ('open', %s, 'Appel tâche') RETURNING request_id",
        [building_id],
    ).fetchone()["request_id"]


def _mk_task(db_conn, rid, *, status="scheduled", emp=_TECH, description="Plomberie") -> int:
    now = datetime.now(timezone.utc)
    return insert_task(
        db_conn, request_id=rid, description=description, status=status,
        assigned_employee_id=emp, due_at=now, source="dispatcher", accepted_at=now,
        urgency_tier="URGENT",
    )["task_id"]


def _req_status(db_conn, rid) -> str:
    return db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid],
    ).fetchone()["s"]


def _task(db_conn, tid) -> dict:
    return db_conn.execute(
        "SELECT *, status::text AS status FROM dispatch_task WHERE task_id = %s", [tid],
    ).fetchone()


def _alert_kinds(db_conn, rid) -> set[str]:
    return {r["kind"] for r in db_conn.execute(
        "SELECT kind FROM coordinator_alert WHERE request_id = %s", [rid]).fetchall()}


def _arrive(c, tid):
    assert c.post(f"/api/v1/tasks/{tid}/en-route", json={}).status_code == 200
    assert c.post(f"/api/v1/tasks/{tid}/arrived", json={}).status_code == 200


def _photo(c, rid) -> int:
    r = c.post(f"/api/v1/requests/{rid}/photos", content=b"x" * 64,
               headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 201, r.text
    return r.json()["attachment_id"]


def _closeout(c, tid, pids, *, outcome="complete", next_date=None, urgent=False, **extra):
    return c.post(f"/api/v1/tasks/{tid}/closeout", json={
        "outcome": outcome, "comment": _COMMENT, "input_method": "typed",
        "attachment_ids": pids, "next_date": str(next_date) if next_date else None,
        "urgent": urgent, "lat": None, "lng": None, **extra,
    })


@pytest.fixture
def sole_arrived_task(ac, db_conn, building):
    """Open call with one task, arrived on site by tech 24, one photo uploaded."""
    c = ac(_tech())
    rid = _mk_call(db_conn, building["building_id"])
    tid = _mk_task(db_conn, rid)
    _arrive(c, tid)
    return c, rid, tid, [_photo(c, rid)]


# ── en route on task ───────────────────────────────────────────────────────────

def test_en_route_on_task(ac, db_conn, building):
    rid = _mk_call(db_conn, building["building_id"])
    tid = _mk_task(db_conn, rid)
    r = ac(_tech()).post(f"/api/v1/tasks/{tid}/en-route", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "en_route"
    assert r.json()["task_id"] == tid
    v = db_conn.execute("SELECT task_id, request_id FROM request_visit WHERE task_id = %s",
                        [tid]).fetchone()
    assert v["request_id"] == rid
    # Hard cutover: the call container is not touched by fieldwork.
    assert _req_status(db_conn, rid) == "open"


# ── outcome mapping ────────────────────────────────────────────────────────────

def test_complete_closeout_may_close_call(sole_arrived_task, db_conn):
    c, rid, tid, pids = sole_arrived_task
    r = _closeout(c, tid, pids, outcome="complete")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["follow_up_task"] is None
    assert body["request_status"] == "closed"
    assert _req_status(db_conn, rid) == "closed"
    assert _alert_kinds(db_conn, rid) == {"call_completed"}
    assert db_conn.execute(
        "SELECT 1 FROM satisfaction_survey WHERE request_id = %s", [rid]).fetchone()


def test_complete_closeout_with_other_open_task_keeps_call_open(sole_arrived_task, db_conn):
    c, rid, tid, pids = sole_arrived_task
    _mk_task(db_conn, rid, status="queued", emp=None, description="Électricité")
    r = _closeout(c, tid, pids, outcome="complete")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert _req_status(db_conn, rid) == "open"
    # The call is not finished: no tenant survey, no « appel terminé » alert yet.
    assert _alert_kinds(db_conn, rid) == set()
    assert db_conn.execute(
        "SELECT 1 FROM satisfaction_survey WHERE request_id = %s", [rid]).fetchone() is None


def test_partial_reschedule_spawns_follow_up(sole_arrived_task, db_conn):
    c, rid, tid, pids = sole_arrived_task
    r = _closeout(c, tid, pids, outcome="partial_reschedule")
    assert r.status_code == 200, r.text
    parent = r.json()
    assert parent["status"] == "return_visit"
    follow_up = parent["follow_up_task"]
    assert follow_up["parent_task_id"] == parent["task_id"]
    assert follow_up["source"] == "follow_up"
    assert follow_up["request_id"] == rid
    assert follow_up["accepted_at"] is not None
    # Same tech keeps the work; default due date +14 days (local day).
    assert follow_up["assigned_employee_id"] == _TECH
    assert follow_up["status"] == "scheduled"
    assert follow_up["description"] == "Plomberie"
    assert follow_up["urgency_tier"] == "URGENT"
    due = datetime.fromisoformat(follow_up["due_at"]).astimezone(ZoneInfo(settings.TIMEZONE))
    assert due.date() == today_local() + timedelta(days=14)
    assert _req_status(db_conn, rid) == "open"
    assert _alert_kinds(db_conn, rid) == {"followup_added"}
    # follow-up is provenanced like any other task write
    cols = {x["target_column"] for x in db_conn.execute(
        "SELECT target_column FROM data_provenance WHERE target_table = 'dispatch_task' "
        "AND target_pk = %s", [str(follow_up["task_id"])]).fetchall()}
    assert {"status", "assigned_employee_id", "due_at"} <= cols


def test_partial_reschedule_uses_chosen_date(sole_arrived_task):
    c, rid, tid, pids = sole_arrived_task
    chosen = today_local() + timedelta(days=3)
    r = _closeout(c, tid, pids, outcome="partial_reschedule", next_date=chosen)
    assert r.status_code == 200, r.text
    due = datetime.fromisoformat(r.json()["follow_up_task"]["due_at"])
    assert due == datetime.combine(chosen, time.min, tzinfo=ZoneInfo(settings.TIMEZONE))


@pytest.mark.parametrize("outcome", ["partial_expertise", "failed"])
def test_expertise_outcomes_need_expertise(sole_arrived_task, db_conn, outcome):
    c, rid, tid, pids = sole_arrived_task
    r = _closeout(c, tid, pids, outcome=outcome, urgent=True)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "needs_expertise"
    assert r.json()["follow_up_task"] is None
    assert _req_status(db_conn, rid) == "open"
    assert _alert_kinds(db_conn, rid) == {"expertise_needed"}
    # The attempt stays on the task for history.
    assert _task(db_conn, tid)["assigned_employee_id"] == _TECH
    j = db_conn.execute(
        "SELECT decision_type, justification_text, after_value FROM decision_justification_log "
        "WHERE request_id = %s ORDER BY id DESC LIMIT 1", [rid]).fetchone()
    assert j["decision_type"] == "closeout"
    assert j["justification_text"] == _COMMENT
    assert j["after_value"]["task_id"] == tid
    assert j["after_value"]["status"] == "needs_expertise"
    assert j["after_value"]["urgent"] is True


def test_closeout_auto_enters_working(sole_arrived_task, db_conn):
    c, rid, tid, pids = sole_arrived_task
    assert _closeout(c, tid, pids, outcome="complete").status_code == 200
    rows = db_conn.execute(
        "SELECT previous_value, ingested_value FROM data_provenance "
        "WHERE target_table = 'dispatch_task' AND target_pk = %s AND target_column = 'status' "
        "ORDER BY provenance_id", [str(tid)]).fetchall()
    assert [(x["previous_value"], x["ingested_value"]) for x in rows][-2:] == [
        ("arrived", "working"), ("working", "done"),
    ]


def test_closeout_from_working(sole_arrived_task, db_conn):
    c, rid, tid, pids = sole_arrived_task
    db_conn.execute("UPDATE dispatch_task SET status = 'working' WHERE task_id = %s", [tid])
    r = _closeout(c, tid, pids, outcome="complete")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_closeout_visit_and_call_fields(sole_arrived_task, db_conn):
    c, rid, tid, pids = sole_arrived_task
    assert _closeout(c, tid, pids, outcome="complete").status_code == 200
    v = db_conn.execute("SELECT * FROM request_visit WHERE task_id = %s", [tid]).fetchone()
    assert v["outcome"] == "complete"
    assert v["closeout_at"] is not None
    # Outcome lives on the visit; the call's own closeout columns are not written.
    row = db_conn.execute(
        "SELECT closeout_outcome, work_performed FROM maintenance_request WHERE request_id = %s",
        [rid]).fetchone()
    assert row["closeout_outcome"] is None
    assert row["work_performed"] is None


# ── request-level fieldwork is gone ────────────────────────────────────────────

@pytest.fixture
def request_id(db_conn, building):
    return _mk_call(db_conn, building["building_id"])


@pytest.mark.parametrize("action", ["en-route", "arrived", "closeout"])
def test_request_fieldwork_routes_gone(ac, request_id, action):
    r = ac(_tech()).post(f"/api/v1/requests/{request_id}/{action}", json={})
    assert r.status_code in (404, 405, 410)
    assert r.status_code == 410
    assert "/api/v1/tasks/" in r.json()["error"]["message"]
