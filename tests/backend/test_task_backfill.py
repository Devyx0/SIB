"""Backfill of open Service Calls into accepted dispatch_task rows (Task 5)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.core.config import settings
from backend.modules.tasks.backfill import backfill_open_requests
from backend.modules.tasks.repository import insert_task, list_tasks_for_request

_TECH = 24


def _mk_request(db_conn, status, *, assignee=None, start=None, summary="Fuite sous l'évier",
                title="Fuite") -> int:
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, raw_title, problem_summary, "
        "assigned_employee_id, start_date) "
        "VALUES (%s::request_status, %s, %s, %s, %s) RETURNING request_id",
        [status, title, summary, assignee, start],
    ).fetchone()["request_id"]


def _req_status(db_conn, rid) -> str:
    return db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid],
    ).fetchone()["s"]


def _mk_visit(db_conn, rid, emp=_TECH, *, closed=False) -> int:
    return db_conn.execute(
        "INSERT INTO request_visit (request_id, employee_id, task_id, closeout_at) "
        "VALUES (%s, %s, NULL, CASE WHEN %s THEN now() END) RETURNING visit_id",
        [rid, emp, closed],
    ).fetchone()["visit_id"]


@pytest.fixture(autouse=True)
def _allow_legacy_visits(db_conn):
    # Pre-cutover visits have task_id NULL; reproduce them inside this rolled-back txn.
    db_conn.execute(
        "ALTER TABLE request_visit DROP CONSTRAINT IF EXISTS request_visit_task_id_required"
    )


@pytest.fixture
def scheduled_request(db_conn):
    return _mk_request(db_conn, "scheduled", assignee=_TECH, start=date(2026, 11, 3))


def test_backfill_creates_one_task_and_opens_call(db_conn, scheduled_request):
    n = backfill_open_requests(db_conn)
    assert n >= 1
    tasks = list_tasks_for_request(db_conn, scheduled_request)
    assert len(tasks) == 1
    t = tasks[0]
    assert t["status"] == "scheduled"
    assert t["assigned_employee_id"] == _TECH
    assert t["accepted_at"] is not None
    assert t["description"] == "Fuite sous l'évier"
    assert t["due_at"].astimezone(ZoneInfo(settings.TIMEZONE)).date() == date(2026, 11, 3)
    assert _req_status(db_conn, scheduled_request) == "open"


@pytest.mark.parametrize("legacy,expected", [
    ("triaged", "queued"),
    ("scheduled", "scheduled"),
    ("en_route", "en_route"),
    ("arrived", "arrived"),
    ("awaiting_redispatch", "needs_expertise"),
])
def test_status_map(db_conn, legacy, expected):
    rid = _mk_request(db_conn, legacy, assignee=_TECH, start=date(2026, 11, 3))
    backfill_open_requests(db_conn)
    (t,) = list_tasks_for_request(db_conn, rid)
    assert t["status"] == expected
    assert _req_status(db_conn, rid) == "open"


def test_description_falls_back_to_raw_title(db_conn):
    rid = _mk_request(db_conn, "triaged", summary="  ", title="Titre brut")
    backfill_open_requests(db_conn)
    (t,) = list_tasks_for_request(db_conn, rid)
    assert t["description"] == "Titre brut"
    assert t["assigned_employee_id"] is None and t["due_at"] is None


def test_open_visits_attached_closed_left_alone(db_conn):
    rid = _mk_request(db_conn, "en_route", assignee=_TECH, start=date(2026, 11, 3))
    open_v = _mk_visit(db_conn, rid)
    closed_v = _mk_visit(db_conn, rid, 14, closed=True)
    backfill_open_requests(db_conn)
    (t,) = list_tasks_for_request(db_conn, rid)
    rows = {r["visit_id"]: r["task_id"] for r in db_conn.execute(
        "SELECT visit_id, task_id FROM request_visit WHERE request_id = %s", [rid]).fetchall()}
    assert rows[open_v] == t["task_id"]
    assert rows[closed_v] is None


def test_second_run_is_noop_and_closed_requests_skipped(db_conn):
    rid = _mk_request(db_conn, "triaged")
    closed = _mk_request(db_conn, "closed")
    assert backfill_open_requests(db_conn) >= 1
    assert backfill_open_requests(db_conn) == 0  # calls are 'open' now
    assert len(list_tasks_for_request(db_conn, rid)) == 1
    assert list_tasks_for_request(db_conn, closed) == []
    assert _req_status(db_conn, closed) == "closed"


def _visit_task(db_conn, vid):
    return db_conn.execute(
        "SELECT task_id FROM request_visit WHERE visit_id = %s", [vid]
    ).fetchone()["task_id"]


def test_existing_proposal_still_gets_cutover_task_open_and_visits(db_conn):
    rid = _mk_request(db_conn, "en_route", assignee=_TECH, start=date(2026, 11, 3))
    proposal = insert_task(db_conn, request_id=rid, description="Proposition IA",
                           source="ai_recommended")  # accepted_at IS NULL
    vid = _mk_visit(db_conn, rid)
    backfill_open_requests(db_conn)
    tasks = list_tasks_for_request(db_conn, rid)
    accepted = [t for t in tasks if t["accepted_at"] is not None]
    assert len(tasks) == 2 and len(accepted) == 1
    assert accepted[0]["task_id"] != proposal["task_id"]
    assert accepted[0]["status"] == "en_route"
    assert _req_status(db_conn, rid) == "open"
    assert _visit_task(db_conn, vid) == accepted[0]["task_id"]


def test_existing_accepted_task_reused_no_second_cutover_task(db_conn):
    rid = _mk_request(db_conn, "scheduled", assignee=_TECH, start=date(2026, 11, 3))
    first = insert_task(db_conn, request_id=rid, description="Manuel", status="scheduled",
                        assigned_employee_id=_TECH, source="dispatcher",
                        accepted_at=datetime.now(timezone.utc))
    later = insert_task(db_conn, request_id=rid, description="Autre", status="queued",
                        source="dispatcher", accepted_at=datetime.now(timezone.utc))
    vid = _mk_visit(db_conn, rid)
    assert backfill_open_requests(db_conn) >= 1
    tasks = list_tasks_for_request(db_conn, rid)
    assert {t["task_id"] for t in tasks} == {first["task_id"], later["task_id"]}
    assert _req_status(db_conn, rid) == "open"
    assert _visit_task(db_conn, vid) == first["task_id"]  # earliest accepted
