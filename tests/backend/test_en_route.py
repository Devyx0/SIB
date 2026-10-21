"""Tests for POST /api/v1/tasks/{id}/en-route (technician portal stop 2)."""
from __future__ import annotations

from datetime import datetime, timezone

import psycopg.errors
import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.tasks.repository import insert_task

_TECH = 24          # technician
_CONTRACTOR = 20    # contractor (Mahmoud Chachia)
_OTHER_TECH = 14    # technician, never assigned here
_COORD = 4

_SENTINEL_PHONE = "(000) 000-0000"
_SENTINEL_EMAIL = "info@sibelanger.com"


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
def building(db_conn):
    """Any building with an address — used for the message template."""
    return db_conn.execute(
        "SELECT building_id, adresse FROM building WHERE adresse IS NOT NULL LIMIT 1"
    ).fetchone()


def _mk_call(db_conn, building_id, *, status="open", phone=None, email=None,
             unit_label=None, title="Test en route"):
    return db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, caller_phone, caller_email, unit_label, raw_title)
        VALUES (%(status)s, %(bldg)s, %(phone)s, %(email)s, %(unit_label)s, %(title)s)
        RETURNING request_id
        """,
        {"status": status, "bldg": building_id, "phone": phone,
         "email": email, "unit_label": unit_label, "title": title},
    ).fetchone()["request_id"]


def _mk_task(db_conn, rid, *, status="scheduled", emp=_TECH, accepted=True):
    now = datetime.now(timezone.utc)
    return insert_task(
        db_conn, request_id=rid, description="Plomberie", status=status,
        assigned_employee_id=emp, due_at=now, source="dispatcher",
        accepted_at=now if accepted else None,
    )["task_id"]


def _mk(db_conn, building_id, **call_kw):
    """Open call + one scheduled task for tech 24. Returns (request_id, task_id)."""
    emp = call_kw.pop("emp", _TECH)
    rid = _mk_call(db_conn, building_id, **call_kw)
    return rid, _mk_task(db_conn, rid, emp=emp)


def _post(client, task_id, *, current_status=None, lat=None, lng=None):
    body = {"lat": lat, "lng": lng}
    if current_status is not None:
        body["current_status"] = current_status
    return client.post(f"/api/v1/tasks/{task_id}/en-route", json=body)


# ── Status transitions ─────────────────────────────────────────────────────────

def test_en_route_from_scheduled(ac, db_conn, building):
    rid, tid = _mk(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), tid, current_status="scheduled")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "en_route"
    row = db_conn.execute(
        "SELECT status::text AS status FROM dispatch_task WHERE task_id = %s", [tid],
    ).fetchone()
    assert row["status"] == "en_route"
    # Hard cutover: no fieldwork writes on the call.
    call = db_conn.execute(
        "SELECT status::text AS status, en_route_at FROM maintenance_request "
        "WHERE request_id = %s", [rid],
    ).fetchone()
    assert call["status"] == "open"
    assert call["en_route_at"] is None


@pytest.mark.parametrize("status", ["queued", "en_route", "arrived", "working", "done",
                                    "needs_expertise", "return_visit", "cancelled"])
def test_en_route_from_non_scheduled_is_409(ac, db_conn, building, status):
    rid = _mk_call(db_conn, building["building_id"])
    tid = _mk_task(db_conn, rid, status=status)
    r = _post(ac(_user(_TECH, "technician")), tid)
    assert r.status_code == 409


def test_en_route_contractor_allowed(ac, db_conn, building):
    _, tid = _mk(db_conn, building["building_id"], emp=_CONTRACTOR)
    r = _post(ac(_user(_CONTRACTOR, "contractor")), tid)
    assert r.status_code == 200
    assert r.json()["status"] == "en_route"


# ── Visit row + geolocation ────────────────────────────────────────────────────

def test_en_route_creates_visit_with_location(ac, db_conn, building):
    rid, tid = _mk(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), tid, lat=46.81, lng=-71.21)
    assert r.status_code == 200
    v = db_conn.execute(
        "SELECT * FROM request_visit WHERE task_id = %s", [tid]
    ).fetchone()
    assert v["request_id"] == rid
    assert v["employee_id"] == _TECH
    assert float(v["en_route_lat"]) == 46.81
    assert float(v["en_route_lng"]) == -71.21
    assert v["closeout_at"] is None


def test_en_route_location_null_when_denied(ac, db_conn, building):
    _, tid = _mk(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), tid)  # no lat/lng
    assert r.status_code == 200
    v = db_conn.execute(
        "SELECT en_route_lat, en_route_lng FROM request_visit WHERE task_id = %s",
        [tid],
    ).fetchone()
    assert v["en_route_lat"] is None
    assert v["en_route_lng"] is None


def test_visit_appears_on_call_detail(ac, db_conn, building):
    rid, tid = _mk(db_conn, building["building_id"])
    assert _post(ac(_user(_TECH, "technician")), tid).status_code == 200
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/requests/{rid}")
    assert r.status_code == 200
    assert len(r.json()["visits"]) == 1


# ── Outbox ─────────────────────────────────────────────────────────────────────

def test_en_route_writes_two_outbox_rows_with_cleaned_contact(ac, db_conn, building):
    rid, tid = _mk(db_conn, building["building_id"],
                   phone="418-555-1234", email="tenant@example.com", unit_label="3")
    r = _post(ac(_user(_TECH, "technician")), tid)
    assert r.status_code == 200
    rows = db_conn.execute(
        "SELECT channel, recipient, status, body, visit_id, created_by_employee_id "
        "FROM message_outbox WHERE request_id = %s ORDER BY channel", [rid],
    ).fetchall()
    assert len(rows) == 2
    by_channel = {x["channel"]: x for x in rows}
    assert by_channel["sms"]["recipient"] == "418-555-1234"
    assert by_channel["email"]["recipient"] == "tenant@example.com"
    for x in rows:
        assert x["status"] == "not_sent"
        assert x["visit_id"] is not None
        assert x["created_by_employee_id"] == _TECH
        # Template start is the client's; address = unit (civic + apartment).
        assert "Ce message est destiné aux occupants, aux locataires du" in x["body"]
        assert building["adresse"] in x["body"]
        assert "app. 3" in x["body"]


def test_en_route_placeholder_contacts_write_null_recipient(ac, db_conn, building):
    rid, tid = _mk(db_conn, building["building_id"],
                   phone=_SENTINEL_PHONE, email=_SENTINEL_EMAIL)
    r = _post(ac(_user(_TECH, "technician")), tid)
    assert r.status_code == 200
    rows = db_conn.execute(
        "SELECT channel, recipient, status FROM message_outbox WHERE request_id = %s",
        [rid],
    ).fetchall()
    assert len(rows) == 2
    assert all(x["recipient"] is None for x in rows)
    assert all(x["status"] == "not_sent" for x in rows)


# ── Provenance ─────────────────────────────────────────────────────────────────

def test_en_route_writes_task_status_provenance(ac, db_conn, building):
    _, tid = _mk(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), tid)
    assert r.status_code == 200
    rows = db_conn.execute(
        "SELECT previous_value, ingested_value, employee_id FROM data_provenance "
        "WHERE target_table = 'dispatch_task' AND target_pk = %s "
        "AND target_column = 'status' AND source_type = 'app'", [str(tid)],
    ).fetchall()
    assert [(x["previous_value"], x["ingested_value"]) for x in rows] == [("scheduled", "en_route")]


# ── Conflicts ──────────────────────────────────────────────────────────────────

def test_en_route_409_when_caller_has_open_visit(ac, db_conn, building):
    """One open visit per employee (I-2): enforced in the service, not only the index."""
    c = ac(_user(_TECH, "technician"))
    first_rid, first_tid = _mk(db_conn, building["building_id"], title="Premier appel")
    _, second_tid = _mk(db_conn, building["building_id"])
    assert _post(c, first_tid).status_code == 200
    r = _post(c, second_tid)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "CONFLICT"
    assert str(first_tid) in err["message"]
    assert err["details"]["open_task_id"] == first_tid
    assert err["details"]["open_request_id"] == first_rid
    assert err["details"]["open_request_title"] == "Premier appel"
    # Second task untouched.
    assert db_conn.execute(
        "SELECT status::text AS s FROM dispatch_task WHERE task_id = %s", [second_tid],
    ).fetchone()["s"] == "scheduled"


def test_en_route_409_with_second_task_on_same_call(ac, db_conn, building):
    c = ac(_user(_TECH, "technician"))
    rid, first = _mk(db_conn, building["building_id"])
    second = _mk_task(db_conn, rid)
    assert _post(c, first).status_code == 200
    assert _post(c, second).status_code == 409


def test_en_route_stale_status_is_409(ac, db_conn, building):
    _, tid = _mk(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), tid, current_status="queued")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_en_route_closed_call_is_409(ac, db_conn, building):
    rid = _mk_call(db_conn, building["building_id"], status="closed")
    tid = _mk_task(db_conn, rid)
    r = _post(ac(_user(_TECH, "technician")), tid)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REQUEST_CLOSED"


def test_en_route_unknown_task_is_404(ac):
    assert _post(ac(_user(_TECH, "technician")), 999_999_999).status_code == 404


def test_en_route_proposal_is_404(ac, db_conn, building):
    rid = _mk_call(db_conn, building["building_id"])
    tid = _mk_task(db_conn, rid, accepted=False)
    assert _post(ac(_user(_TECH, "technician")), tid).status_code == 404


# ── Permissions ────────────────────────────────────────────────────────────────

def test_en_route_coordinator_is_403(ac, db_conn, building):
    _, tid = _mk(db_conn, building["building_id"])
    r = _post(ac(_user(_COORD, "coordinator")), tid)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_en_route_unassigned_technician_is_403(ac, db_conn, building):
    _, tid = _mk(db_conn, building["building_id"])
    r = _post(ac(_user(_OTHER_TECH, "technician")), tid)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


# ── DB constraints ─────────────────────────────────────────────────────────────

def test_unique_index_rejects_second_open_visit(db_conn, building):
    rid1, tid1 = _mk(db_conn, building["building_id"])
    rid2, tid2 = _mk(db_conn, building["building_id"])
    db_conn.execute(
        "INSERT INTO request_visit (request_id, task_id, employee_id) VALUES (%s, %s, %s)",
        [rid1, tid1, _TECH],
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db_conn.transaction():  # savepoint so the test conn survives
            db_conn.execute(
                "INSERT INTO request_visit (request_id, task_id, employee_id) VALUES (%s, %s, %s)",
                [rid2, tid2, _TECH],
            )
    # Closing the first visit frees the slot.
    db_conn.execute(
        "UPDATE request_visit SET closeout_at = now() WHERE task_id = %s", [tid1]
    )
    db_conn.execute(
        "INSERT INTO request_visit (request_id, task_id, employee_id) VALUES (%s, %s, %s)",
        [rid2, tid2, _TECH],
    )


def test_new_visit_requires_task_id(db_conn, building):
    rid = _mk_call(db_conn, building["building_id"])
    with pytest.raises(psycopg.errors.CheckViolation):
        with db_conn.transaction():
            db_conn.execute(
                "INSERT INTO request_visit (request_id, employee_id) VALUES (%s, %s)",
                [rid, _TECH],
            )
