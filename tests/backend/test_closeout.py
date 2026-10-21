"""Tests for stop 3: photos upload, task closeout validation and conflicts,
signed URLs, « À redispatcher » filter. Storage is mocked — no network traffic.

Outcome → task status mapping lives in test_task_closeout.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

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
    """Record uploads; sign URLs deterministically. No storage traffic."""
    uploads: list[tuple[str, int, str]] = []
    monkeypatch.setattr(
        "backend.modules.requests.storage.upload_photo",
        lambda path, content, mime: uploads.append((path, len(content), mime)),
    )
    monkeypatch.setattr(
        "backend.modules.requests.storage.create_signed_url",
        lambda path, expires_in_seconds=300: f"https://signed.local/{path}",
    )
    return uploads


@pytest.fixture
def building(db_conn):
    return db_conn.execute(
        "SELECT building_id, adresse FROM building WHERE adresse IS NOT NULL LIMIT 1"
    ).fetchone()


def _mk_request(db_conn, building_id, *, status="open"):
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, raw_title) "
        "VALUES (%(s)s, %(b)s, 'Appel closeout') RETURNING request_id",
        {"s": status, "b": building_id},
    ).fetchone()["request_id"]


def _mk_task(db_conn, rid, *, status="scheduled", emp=_TECH):
    now = datetime.now(timezone.utc)
    return insert_task(
        db_conn, request_id=rid, description="Plomberie", status=status,
        assigned_employee_id=emp, due_at=now, source="dispatcher", accepted_at=now,
    )["task_id"]


def _mk(db_conn, building_id, **kw):
    rid = _mk_request(db_conn, building_id)
    return rid, _mk_task(db_conn, rid, **kw)


def _en_route(client, tid):
    r = client.post(f"/api/v1/tasks/{tid}/en-route", json={"lat": None, "lng": None})
    assert r.status_code == 200, r.text
    return r


def _arrive(client, tid):
    r = client.post(f"/api/v1/tasks/{tid}/arrived", json={"lat": None, "lng": None})
    assert r.status_code == 200, r.text
    return r


def _upload(client, rid, *, mime="image/jpeg", content=b"x" * 128):
    return client.post(
        f"/api/v1/requests/{rid}/photos", content=content,
        headers={"Content-Type": mime},
    )


def _closeout(client, tid, attachment_ids, *, outcome="complete", comment=_COMMENT,
              next_date=None, urgent=False, current_status=None):
    body = {"outcome": outcome, "comment": comment, "input_method": "typed",
            "attachment_ids": attachment_ids,
            "next_date": str(next_date) if next_date else None,
            "urgent": urgent, "lat": None, "lng": None}
    if current_status is not None:
        body["current_status"] = current_status
    return client.post(f"/api/v1/tasks/{tid}/closeout", json=body)


@pytest.fixture
def open_call(ac, db_conn, building):
    """Task arrived on site by tech 24 with one uploaded photo."""
    c = ac(_user(_TECH, "technician"))
    rid, tid = _mk(db_conn, building["building_id"])
    _en_route(c, tid)
    _arrive(c, tid)
    pid = _upload(c, rid).json()["attachment_id"]
    return c, rid, tid, [pid]


# ── Photo upload ───────────────────────────────────────────────────────────────

def test_photo_upload_creates_row_and_uploads(ac, db_conn, building, mock_storage):
    c = ac(_user(_TECH, "technician"))
    rid, _ = _mk(db_conn, building["building_id"])
    r = _upload(c, rid, mime="image/png")
    assert r.status_code == 201
    aid = r.json()["attachment_id"]
    row = db_conn.execute(
        "SELECT * FROM maintenance_attachment WHERE attachment_id = %s", [aid]
    ).fetchone()
    assert row["photo_context"] == "closeout"
    assert row["uploaded_by_employee_id"] == _TECH
    assert row["file_type"] == "photo"
    assert row["visit_id"] is None
    assert row["storage_path"] == f"closeout/{rid}/{aid}.png"
    assert mock_storage == [(f"closeout/{rid}/{aid}.png", 128, "image/png")]


def test_photo_upload_bad_mime_422(ac, db_conn, building):
    c = ac(_user(_TECH, "technician"))
    rid, _ = _mk(db_conn, building["building_id"])
    r = _upload(c, rid, mime="image/gif")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_photo_upload_too_big_422(ac, db_conn, building):
    c = ac(_user(_TECH, "technician"))
    rid, _ = _mk(db_conn, building["building_id"])
    r = _upload(c, rid, content=b"x" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 422


def test_photo_upload_coordinator_403(ac, db_conn, building):
    rid, _ = _mk(db_conn, building["building_id"])
    r = _upload(ac(_user(_COORD, "coordinator")), rid)
    assert r.status_code == 403


def test_photo_upload_unassigned_403(ac, db_conn, building):
    rid, _ = _mk(db_conn, building["building_id"])
    r = _upload(ac(_user(_OTHER_TECH, "technician")), rid)
    assert r.status_code == 403


def test_photo_upload_any_task_assignee_on_call_ok(ac, db_conn, building):
    rid, _ = _mk(db_conn, building["building_id"])
    _mk_task(db_conn, rid, emp=_OTHER_TECH)
    assert _upload(ac(_user(_OTHER_TECH, "technician")), rid).status_code == 201


# ── Closeout side effects ──────────────────────────────────────────────────────

def test_closeout_closes_visit_and_consumes_photo(open_call, db_conn):
    c, rid, tid, pids = open_call
    r = _closeout(c, tid, pids, outcome="complete")
    assert r.status_code == 200, r.text
    v = db_conn.execute("SELECT * FROM request_visit WHERE task_id = %s", [tid]).fetchone()
    assert v["closeout_at"] is not None
    assert v["outcome"] == "complete"
    assert v["closeout_comment"] == _COMMENT
    assert v["duration_minutes"] is not None and v["duration_minutes"] >= 0
    assert v["arrived_at"] is not None
    assert v["travel_minutes"] is not None and v["travel_minutes"] >= 0
    assert v["on_site_minutes"] is not None and v["on_site_minutes"] >= 0
    used = db_conn.execute(
        "SELECT visit_id FROM maintenance_attachment WHERE attachment_id = %s", [pids[0]]
    ).fetchone()
    assert used["visit_id"] == v["visit_id"]
    # follow-up entry with the comment, on the call
    fu = db_conn.execute(
        "SELECT entry_text, entered_by_initials FROM maintenance_followup_entry "
        "WHERE request_id = %s ORDER BY followup_id DESC LIMIT 1", [rid]).fetchone()
    assert fu["entry_text"] == _COMMENT
    assert fu["entered_by_initials"]


# ── Validation ─────────────────────────────────────────────────────────────────

def test_closeout_zero_photos_422(open_call):
    c, _, tid, _ = open_call
    assert _closeout(c, tid, []).status_code == 422


def test_closeout_foreign_photo_422(open_call, db_conn):
    c, rid, tid, _ = open_call
    foreign = db_conn.execute(
        "INSERT INTO maintenance_attachment (request_id, file_type, photo_context, "
        "uploaded_by_employee_id, storage_path) "
        "VALUES (%s, 'photo', 'closeout', %s, 'closeout/x.jpg') RETURNING attachment_id",
        [rid, _OTHER_TECH]).fetchone()["attachment_id"]
    assert _closeout(c, tid, [foreign]).status_code == 422


def test_closeout_other_requests_photo_422(open_call, db_conn, building):
    c, _, tid, _ = open_call
    other_rid = _mk_request(db_conn, building["building_id"])
    other_pid = db_conn.execute(
        "INSERT INTO maintenance_attachment (request_id, file_type, photo_context, "
        "uploaded_by_employee_id, storage_path) "
        "VALUES (%s, 'photo', 'closeout', %s, 'closeout/y.jpg') RETURNING attachment_id",
        [other_rid, _TECH]).fetchone()["attachment_id"]
    assert _closeout(c, tid, [other_pid]).status_code == 422


def test_closeout_used_photo_422(open_call, db_conn):
    c, rid, tid, pids = open_call
    # Consume the photo with a previous (closed) visit of another employee.
    old_tid = _mk_task(db_conn, rid, status="done", emp=_OTHER_TECH)
    old_visit = db_conn.execute(
        "INSERT INTO request_visit (request_id, task_id, employee_id, closeout_at) "
        "VALUES (%s, %s, %s, NOW()) RETURNING visit_id",
        [rid, old_tid, _OTHER_TECH]).fetchone()["visit_id"]
    db_conn.execute("UPDATE maintenance_attachment SET visit_id = %s WHERE attachment_id = %s",
                    [old_visit, pids[0]])
    assert _closeout(c, tid, pids).status_code == 422


def test_closeout_outcome2_date_in_past_422(open_call):
    c, _, tid, pids = open_call
    r = _closeout(c, tid, pids, outcome="partial_reschedule",
                  next_date=today_local() - timedelta(days=1))
    assert r.status_code == 422


def test_closeout_date_rejected_on_other_outcomes(open_call):
    c, _, tid, pids = open_call
    r = _closeout(c, tid, pids, outcome="complete", next_date=today_local())
    assert r.status_code == 422


@pytest.mark.parametrize("outcome", ["complete", "partial_reschedule"])
def test_closeout_urgent_rejected_on_1_and_2(open_call, outcome):
    c, _, tid, pids = open_call
    kw = {"next_date": today_local()} if outcome == "partial_reschedule" else {}
    r = _closeout(c, tid, pids, outcome=outcome, urgent=True, **kw)
    assert r.status_code == 422


def test_closeout_short_comment_422(open_call):
    c, _, tid, pids = open_call
    assert _closeout(c, tid, pids, comment="court").status_code == 422


def test_rejected_closeout_writes_nothing(open_call, db_conn):
    c, _, tid, pids = open_call
    assert _closeout(c, tid, pids, outcome="complete", urgent=True).status_code == 422
    assert db_conn.execute(
        "SELECT status::text AS s FROM dispatch_task WHERE task_id = %s", [tid],
    ).fetchone()["s"] == "arrived"


# ── State conflicts ────────────────────────────────────────────────────────────

def test_closeout_before_arrival_409(ac, db_conn, building):
    c = ac(_user(_TECH, "technician"))
    rid, tid = _mk(db_conn, building["building_id"])
    _en_route(c, tid)
    pid = _upload(c, rid).json()["attachment_id"]
    r = _closeout(c, tid, [pid])
    assert r.status_code == 409
    assert "arrivée" in r.json()["error"]["message"]


def test_closeout_no_open_visit_409(ac, db_conn, building):
    # arrived status but no visit row (e.g. visit closed by an admin action).
    c = ac(_user(_TECH, "technician"))
    rid, tid = _mk(db_conn, building["building_id"], status="arrived")
    pid = _upload(c, rid).json()["attachment_id"]
    r = _closeout(c, tid, [pid])
    assert r.status_code == 409
    assert "Aucune visite en cours" in r.json()["error"]["message"]


def test_closeout_stale_status_409(open_call):
    c, _, tid, pids = open_call
    r = _closeout(c, tid, pids, current_status="scheduled")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_closeout_twice_409(open_call):
    c, _, tid, pids = open_call
    assert _closeout(c, tid, pids, outcome="partial_expertise").status_code == 200
    assert _closeout(c, tid, pids, outcome="partial_expertise").status_code == 409


def test_closeout_coordinator_403(open_call, ac):
    _, _, tid, pids = open_call
    assert _closeout(ac(_user(_COORD, "coordinator")), tid, pids).status_code == 403


def test_closeout_unassigned_403(open_call, ac):
    _, _, tid, pids = open_call
    assert _closeout(ac(_user(_OTHER_TECH, "technician")), tid, pids).status_code == 403


def test_next_en_route_allowed_after_closeout(open_call, db_conn, building):
    c, _, tid, pids = open_call
    assert _closeout(c, tid, pids, outcome="complete").status_code == 200
    _, tid2 = _mk(db_conn, building["building_id"])
    assert _en_route(c, tid2).status_code == 200


# ── Signed URL ─────────────────────────────────────────────────────────────────

def test_photo_url_assigned_and_coordinator_ok(open_call, ac):
    c, rid, _, pids = open_call
    r = c.get(f"/api/v1/requests/{rid}/photos/{pids[0]}")
    assert r.status_code == 200
    assert r.json()["url"].startswith(f"https://signed.local/closeout/{rid}/")
    r2 = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{rid}/photos/{pids[0]}")
    assert r2.status_code == 200


def test_photo_url_other_tech_403(open_call, ac):
    _, rid, _, pids = open_call
    r = ac(_user(_OTHER_TECH, "technician")).get(f"/api/v1/requests/{rid}/photos/{pids[0]}")
    assert r.status_code == 403


# ── À redispatcher ─────────────────────────────────────────────────────────────

def test_list_redispatch_membership(ac, db_conn, building):
    b = building["building_id"]
    returned = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, closeout_outcome, closeout_urgent) "
        "VALUES ('awaiting_redispatch', %s, 'partial_expertise', true) RETURNING request_id", [b]).fetchone()["request_id"]
    returned_failed = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, closeout_outcome) "
        "VALUES ('awaiting_redispatch', %s, 'failed') RETURNING request_id", [b]).fetchone()["request_id"]
    still_assigned = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, assigned_employee_id, closeout_outcome) "
        "VALUES ('triaged', %s, %s, 'partial_expertise') RETURNING request_id", [b, _TECH]).fetchone()["request_id"]
    plain_triaged = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id) "
        "VALUES ('triaged', %s) RETURNING request_id", [b]).fetchone()["request_id"]

    c = ac(_user(_COORD, "coordinator"))
    r = c.get("/api/v1/requests?redispatch=true&limit=200")
    assert r.status_code == 200
    ids = [i["request_id"] for i in r.json()["items"]]
    assert returned in ids
    assert returned_failed in ids
    assert still_assigned not in ids
    assert plain_triaged not in ids
    urgent_flags = {i["request_id"]: i["closeout_urgent"] for i in r.json()["items"]}
    assert urgent_flags[returned] is True
