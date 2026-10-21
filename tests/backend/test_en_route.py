"""Tests for POST /api/v1/requests/{id}/en-route (technician portal stop 2)."""
from __future__ import annotations

import psycopg.errors
import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

_TECH = 24          # technician
_CONTRACTOR = 20    # contractor (Mahmoud Chachia)
_OTHER_TECH = 14    # technician, never assigned here
_COORD = 4

# triage_pending excluded: background triage would overwrite the status → 409.
# triaged excluded: unassigned-only; assigned calls are scheduled.
_OPEN_STATUSES = [
    "intake_received", "scheduled",
    "triage_clarify", "triage_proposal", "triage_failed",
]

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


def _mk_request(db_conn, building_id, *, status="scheduled", emp=_TECH,
                phone=None, email=None, unit_label=None, title="Test en route"):
    return db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, assigned_employee_id, caller_phone,
             caller_email, unit_label, raw_title)
        VALUES (%(status)s, %(bldg)s, %(emp)s, %(phone)s, %(email)s,
                %(unit_label)s, %(title)s)
        RETURNING request_id
        """,
        {"status": status, "bldg": building_id, "emp": emp, "phone": phone,
         "email": email, "unit_label": unit_label, "title": title},
    ).fetchone()["request_id"]


def _post(client, request_id, *, current_status="scheduled", lat=None, lng=None):
    return client.post(
        f"/api/v1/requests/{request_id}/en-route",
        json={"current_status": current_status, "current_start_date": None,
              "lat": lat, "lng": lng},
    )


# ── Status transitions ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", _OPEN_STATUSES)
def test_en_route_from_each_open_status(ac, db_conn, building, status):
    rid = _mk_request(db_conn, building["building_id"], status=status)
    r = _post(ac(_user(_TECH, "technician")), rid, current_status=status)
    assert r.status_code == 200
    assert r.json()["status"] == "en_route"
    row = db_conn.execute(
        "SELECT status::text AS status, en_route_at FROM maintenance_request "
        "WHERE request_id = %s", [rid],
    ).fetchone()
    assert row["status"] == "en_route"
    assert row["en_route_at"] is not None


def test_en_route_contractor_allowed(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], emp=_CONTRACTOR)
    r = _post(ac(_user(_CONTRACTOR, "contractor")), rid)
    assert r.status_code == 200
    assert r.json()["status"] == "en_route"


# ── Visit row + geolocation ────────────────────────────────────────────────────

def test_en_route_creates_visit_with_location(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), rid, lat=46.81, lng=-71.21)
    assert r.status_code == 200
    v = db_conn.execute(
        "SELECT * FROM request_visit WHERE request_id = %s", [rid]
    ).fetchone()
    assert v["employee_id"] == _TECH
    assert float(v["en_route_lat"]) == 46.81
    assert float(v["en_route_lng"]) == -71.21
    assert v["closeout_at"] is None


def test_en_route_location_null_when_denied(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), rid)  # no lat/lng
    assert r.status_code == 200
    v = db_conn.execute(
        "SELECT en_route_lat, en_route_lng FROM request_visit WHERE request_id = %s",
        [rid],
    ).fetchone()
    assert v["en_route_lat"] is None
    assert v["en_route_lng"] is None


# ── Outbox ─────────────────────────────────────────────────────────────────────

def test_en_route_writes_two_outbox_rows_with_cleaned_contact(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"],
                      phone="418-555-1234", email="tenant@example.com",
                      unit_label="3")
    r = _post(ac(_user(_TECH, "technician")), rid)
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
    rid = _mk_request(db_conn, building["building_id"],
                      phone=_SENTINEL_PHONE, email=_SENTINEL_EMAIL)
    r = _post(ac(_user(_TECH, "technician")), rid)
    assert r.status_code == 200
    rows = db_conn.execute(
        "SELECT channel, recipient, status FROM message_outbox WHERE request_id = %s",
        [rid],
    ).fetchall()
    assert len(rows) == 2
    assert all(x["recipient"] is None for x in rows)
    assert all(x["status"] == "not_sent" for x in rows)
    # The response the UI uses to show « Aucun contact pour aviser le locataire »
    body = r.json()
    assert body["caller_phone"] is None
    assert body["caller_email"] is None


# ── Provenance ─────────────────────────────────────────────────────────────────

def test_en_route_writes_provenance_per_column(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"])
    r = _post(ac(_user(_TECH, "technician")), rid)
    assert r.status_code == 200
    rows = db_conn.execute(
        "SELECT target_column, previous_value, ingested_value FROM data_provenance "
        "WHERE target_table = 'maintenance_request' AND target_pk = %s "
        "AND source_type = 'app'", [str(rid)],
    ).fetchall()
    cols = {x["target_column"]: x for x in rows}
    assert cols["status"]["previous_value"] == "scheduled"
    assert cols["status"]["ingested_value"] == "en_route"
    assert cols["en_route_at"]["previous_value"] is None
    assert cols["en_route_at"]["ingested_value"] is not None


# ── Conflicts ──────────────────────────────────────────────────────────────────

def test_en_route_409_when_caller_has_open_call(ac, db_conn, building):
    c = ac(_user(_TECH, "technician"))
    first = _mk_request(db_conn, building["building_id"], title="Premier appel")
    second = _mk_request(db_conn, building["building_id"])
    assert _post(c, first).status_code == 200
    r = _post(c, second)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "CONFLICT"
    assert str(first) in err["message"]
    assert err["details"]["open_request_id"] == first
    assert err["details"]["open_request_title"] == "Premier appel"


def test_en_route_triage_pending_is_409(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], status="triage_pending")
    r = _post(ac(_user(_TECH, "technician")), rid, current_status="triage_pending")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "CONFLICT"
    assert err["message"] == "Triage en cours — réessayez dans un instant"


def test_en_route_stale_status_is_409(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], status="scheduled")
    r = _post(ac(_user(_TECH, "technician")), rid, current_status="intake_received")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_en_route_closed_request_is_409(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], status="closed")
    r = _post(ac(_user(_TECH, "technician")), rid, current_status="closed")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REQUEST_CLOSED"


# ── Permissions ────────────────────────────────────────────────────────────────

def test_en_route_coordinator_is_403(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"])
    r = _post(ac(_user(_COORD, "coordinator")), rid)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_en_route_unassigned_technician_is_403(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], emp=_TECH)
    r = _post(ac(_user(_OTHER_TECH, "technician")), rid)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


# ── DB constraint ──────────────────────────────────────────────────────────────

def test_unique_index_rejects_second_open_visit(db_conn, building):
    rid1 = _mk_request(db_conn, building["building_id"])
    rid2 = _mk_request(db_conn, building["building_id"])
    db_conn.execute(
        "INSERT INTO request_visit (request_id, employee_id) VALUES (%s, %s)",
        [rid1, _TECH],
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db_conn.transaction():  # savepoint so the test conn survives
            db_conn.execute(
                "INSERT INTO request_visit (request_id, employee_id) VALUES (%s, %s)",
                [rid2, _TECH],
            )
    # Closing the first visit frees the slot.
    db_conn.execute(
        "UPDATE request_visit SET closeout_at = now() WHERE request_id = %s", [rid1]
    )
    db_conn.execute(
        "INSERT INTO request_visit (request_id, employee_id) VALUES (%s, %s)",
        [rid2, _TECH],
    )
