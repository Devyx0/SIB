"""GET /api/v1/dossiers — calls with at least one visit, coordinator/director only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

_TECH = 24
_COORD = 4
_DIRECTOR = 5
_CONTRACTOR = 20


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
    return db_conn.execute(
        "SELECT building_id FROM building WHERE adresse IS NOT NULL LIMIT 1"
    ).fetchone()


def _mk_request(db_conn, building_id, *, title="Appel dossier", status="closed",
                emp=_TECH, urgent=None, unit_label=None):
    return db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, assigned_employee_id, "
        "raw_title, closeout_urgent, unit_label) "
        "VALUES (%(s)s, %(b)s, %(e)s, %(t)s, %(u)s, %(ul)s) RETURNING request_id",
        {"s": status, "b": building_id, "e": emp, "t": title, "u": urgent, "ul": unit_label},
    ).fetchone()["request_id"]


def _mk_visit(db_conn, rid, *, emp=_TECH, en_route_at=None, closeout_at=None, outcome=None):
    en_route_at = en_route_at or datetime.now(timezone.utc) - timedelta(hours=2)
    return db_conn.execute(
        "INSERT INTO request_visit (request_id, employee_id, en_route_at, closeout_at, outcome) "
        "VALUES (%(r)s, %(e)s, %(era)s, %(ca)s, %(o)s) RETURNING visit_id",
        {"r": rid, "e": emp, "era": en_route_at, "ca": closeout_at, "o": outcome},
    ).fetchone()["visit_id"]


def _mk_photo(db_conn, rid, *, emp=_TECH, context="closeout"):
    # Same columns/values action_upload_photo writes (file_type='photo',
    # photo_context='closeout', storage_path set) — see repo.insert_photo.
    db_conn.execute(
        "INSERT INTO maintenance_attachment (request_id, file_type, photo_context, "
        "uploaded_by_employee_id, storage_path) "
        "VALUES (%(r)s, 'photo', %(c)s, %(e)s, %(p)s)",
        {"r": rid, "c": context, "e": emp, "p": f"closeout/{rid}/t.jpg"},
    )


def test_only_requests_with_visits_listed(ac, db_conn, building):
    rid_with = _mk_request(db_conn, building["building_id"])
    _mk_visit(db_conn, rid_with, closeout_at=datetime.now(timezone.utc), outcome="complete")
    rid_without = _mk_request(db_conn, building["building_id"])
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers")
    assert r.status_code == 200, r.text
    ids = [x["request_id"] for x in r.json()["items"]]
    assert rid_with in ids
    assert rid_without not in ids


def test_row_shape_and_counts(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], urgent=True)
    _mk_visit(db_conn, rid,
              en_route_at=datetime.now(timezone.utc) - timedelta(hours=3),
              closeout_at=datetime.now(timezone.utc) - timedelta(hours=2),
              outcome="partial_expertise")
    _mk_photo(db_conn, rid)
    _mk_photo(db_conn, rid)
    r = ac(_user(_DIRECTOR, "director")).get("/api/v1/dossiers")
    row = next(x for x in r.json()["items"] if x["request_id"] == rid)
    assert row["last_outcome"] == "partial_expertise"
    assert row["photo_count"] == 2
    assert row["visit_count"] == 1
    assert row["closeout_urgent"] is True
    assert row["employee_name"]           # visit employee resolved
    assert row["last_en_route_at"] and row["last_closeout_at"]


def test_photo_count_counts_only_closeout_photos(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"])
    _mk_visit(db_conn, rid, closeout_at=datetime.now(timezone.utc), outcome="complete")
    _mk_photo(db_conn, rid)                      # what the upload writes
    _mk_photo(db_conn, rid, context="intake")    # Drive-ingested intake photo — not counted
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers")
    row = next(x for x in r.json()["items"] if x["request_id"] == rid)
    assert row["photo_count"] == 1


def test_open_visit_listed_with_null_outcome(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], status="en_route")
    _mk_visit(db_conn, rid)  # no closeout — open visit
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers")
    row = next(x for x in r.json()["items"] if x["request_id"] == rid)
    assert row["last_outcome"] is None
    assert row["last_closeout_at"] is None
    assert row["photo_count"] == 0


def test_last_visit_wins(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"])
    _mk_visit(db_conn, rid, en_route_at=datetime.now(timezone.utc) - timedelta(days=2),
              closeout_at=datetime.now(timezone.utc) - timedelta(days=2, hours=-1),
              outcome="partial_reschedule")
    _mk_visit(db_conn, rid, en_route_at=datetime.now(timezone.utc) - timedelta(hours=1),
              closeout_at=datetime.now(timezone.utc), outcome="complete")
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers")
    row = next(x for x in r.json()["items"] if x["request_id"] == rid)
    assert row["last_outcome"] == "complete"
    assert row["visit_count"] == 2


def test_last_visit_tiebreak_on_identical_en_route_at(ac, db_conn, building):
    # Same en_route_at: the later-created visit (higher visit_id) is "last".
    rid = _mk_request(db_conn, building["building_id"])
    at = datetime.now(timezone.utc) - timedelta(hours=1)
    _mk_visit(db_conn, rid, en_route_at=at, closeout_at=at + timedelta(minutes=30),
              outcome="partial_reschedule")
    _mk_visit(db_conn, rid, en_route_at=at, closeout_at=at + timedelta(minutes=45),
              outcome="complete")
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers")
    row = next(x for x in r.json()["items"] if x["request_id"] == rid)
    assert row["last_outcome"] == "complete"


def test_outcome_filter(ac, db_conn, building):
    rid_c = _mk_request(db_conn, building["building_id"])
    _mk_visit(db_conn, rid_c, closeout_at=datetime.now(timezone.utc), outcome="complete")
    rid_f = _mk_request(db_conn, building["building_id"])
    _mk_visit(db_conn, rid_f, closeout_at=datetime.now(timezone.utc), outcome="failed")
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers?outcome=failed")
    ids = [x["request_id"] for x in r.json()["items"]]
    assert rid_f in ids and rid_c not in ids


def test_employee_filter_matches_any_visit(ac, db_conn, building):
    # « A fait une visite »: an older visit by the employee matches even when
    # the LAST visit is someone else's.
    rid = _mk_request(db_conn, building["building_id"])
    _mk_visit(db_conn, rid, emp=_TECH,
              en_route_at=datetime.now(timezone.utc) - timedelta(days=1),
              closeout_at=datetime.now(timezone.utc) - timedelta(days=1, hours=-1),
              outcome="partial_reschedule")
    _mk_visit(db_conn, rid, emp=_CONTRACTOR, closeout_at=datetime.now(timezone.utc),
              outcome="complete")
    rid_other = _mk_request(db_conn, building["building_id"], emp=_CONTRACTOR)
    _mk_visit(db_conn, rid_other, emp=_CONTRACTOR, closeout_at=datetime.now(timezone.utc),
              outcome="complete")
    r = ac(_user(_COORD, "coordinator")).get(f"/api/v1/dossiers?employee_id={_TECH}")
    ids = [x["request_id"] for x in r.json()["items"]]
    assert rid in ids and rid_other not in ids
    # the column still shows the LAST visit's employee (the contractor)
    row = next(x for x in r.json()["items"] if x["request_id"] == rid)
    assert row["employee_name"] != "" and row["last_outcome"] == "complete"


def test_date_range_one_sided_422(ac):
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers?start_date=2026-10-01")
    assert r.status_code == 422


def test_q_search_unaccented(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], title="Électricité — panne")
    _mk_visit(db_conn, rid, closeout_at=datetime.now(timezone.utc), outcome="complete")
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers?q=electricite")
    assert rid in [x["request_id"] for x in r.json()["items"]]


def test_q_search_matches_unit(ac, db_conn, building):
    rid = _mk_request(db_conn, building["building_id"], title="Sans titre utile",
                      unit_label="7C-dossier")
    _mk_visit(db_conn, rid, closeout_at=datetime.now(timezone.utc), outcome="complete")
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers?q=7c-dossier")
    assert rid in [x["request_id"] for x in r.json()["items"]]


def test_pagination(ac, db_conn, building):
    for _ in range(3):
        rid = _mk_request(db_conn, building["building_id"])
        _mk_visit(db_conn, rid, closeout_at=datetime.now(timezone.utc), outcome="complete")
    r = ac(_user(_COORD, "coordinator")).get("/api/v1/dossiers?limit=2&offset=0")
    body = r.json()
    assert body["total"] >= 3
    assert len(body["items"]) == 2


@pytest.mark.parametrize("emp,role", [(_TECH, "technician"), (_CONTRACTOR, "contractor")])
def test_tech_and_contractor_403(ac, emp, role):
    r = ac(_user(emp, role)).get("/api/v1/dossiers")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"
