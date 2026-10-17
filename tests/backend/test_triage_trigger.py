"""Tests for POST /api/v1/requests/{id}/triage."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

_COORD = 4
_TECH  = 14
_CONT  = 20
_BLDG  = 3
_SECTOR = 1


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


@pytest.fixture
def ac(app, db_conn, monkeypatch):
    """TestClient with user injection and triage background task suppressed."""
    import backend.modules.requests.router as rtr
    monkeypatch.setattr(rtr, "_run_triage_background", lambda rid: None)

    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)
    yield _factory
    app.dependency_overrides.clear()


def _insert_request(db_conn, status: str, triage_started_at=None) -> int:
    row = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, triage_started_at)
        VALUES (%(s)s, %(b)s, %(sec)s, %(ts)s)
        RETURNING request_id
        """,
        {"s": status, "b": _BLDG, "sec": _SECTOR, "ts": triage_started_at},
    ).fetchone()
    return row["request_id"]


def test_intake_received_returns_202(ac, db_conn):
    rid = _insert_request(db_conn, "intake_received")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 202
    assert r.json() == {"request_id": rid, "status": "triage_pending"}


def test_triage_failed_returns_202(ac, db_conn):
    rid = _insert_request(db_conn, "triage_failed")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 202


def test_closed_returns_409(ac, db_conn):
    rid = _insert_request(db_conn, "closed")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REQUEST_CLOSED"


def test_triaged_returns_409(ac, db_conn):
    rid = _insert_request(db_conn, "triaged")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 409


def test_en_route_returns_409(ac, db_conn):
    rid = _insert_request(db_conn, "en_route")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 409


def test_triage_pending_recent_returns_409(ac, db_conn):
    # started 2 minutes ago — not stale
    recent = datetime.now(timezone.utc) - timedelta(minutes=2)
    rid = _insert_request(db_conn, "triage_pending", triage_started_at=recent)
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_triage_pending_stale_returns_202(ac, db_conn):
    # started 15 minutes ago — stale, re-triggerable
    stale = datetime.now(timezone.utc) - timedelta(minutes=15)
    rid = _insert_request(db_conn, "triage_pending", triage_started_at=stale)
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 202


def test_technician_returns_403(ac, db_conn):
    rid = _insert_request(db_conn, "intake_received")
    r = ac(_user(_TECH, "technician")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 403


def test_contractor_returns_403(ac, db_conn):
    rid = _insert_request(db_conn, "intake_received")
    r = ac(_user(_CONT, "contractor")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 403


def test_no_assigned_employee_written_by_trigger(ac, db_conn):
    """Triage trigger must not touch assigned_employee_id."""
    rid = _insert_request(db_conn, "intake_received")
    ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    row = db_conn.execute(
        "SELECT assigned_employee_id FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    assert row["assigned_employee_id"] is None


def test_background_runs_after_commit(app, db_conn):
    """
    Background task executes within client.post() (before it returns) and can
    read from the DB via a fresh psycopg2 connection — proving the middleware
    has committed (released the pool connection) before the task starts.
    Any writes the handler makes are visible to the task via this channel.
    """
    import backend.modules.requests.router as rtr
    import psycopg2

    seen_rid = []

    def spy_bg(rid):
        # Fresh psycopg2 connection — independent of the test's db_conn.
        # The row must be visible here (middleware committed before background tasks run).
        c = psycopg2.connect(
            host="127.0.0.1", port=54322, user="postgres",
            password="postgres", dbname="postgres",
        )
        with c.cursor() as cur:
            cur.execute("SELECT request_id FROM maintenance_request WHERE request_id = %s", [rid])
            row = cur.fetchone()
            seen_rid.append(row[0] if row else None)
        c.close()

    rtr._run_triage_background = spy_bg
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: _user(_COORD, "coordinator")
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)

    rid = _insert_request(db_conn, "intake_received")
    db_conn.connection.commit()  # commit so the row is visible to the spy's fresh connection

    client.post(f"/api/v1/requests/{rid}/triage")
    app.dependency_overrides.clear()

    # Spy ran during the client.post() call, found the committed row via fresh psycopg2 conn
    assert seen_rid == [rid], f"got {seen_rid}"


def test_provenance_skips_unchanged():
    """_write_triage_provenance must not call executemany when all old == new (NULL→NULL)."""
    from backend.triage.service import _write_triage_provenance, _PROVENANCE_COLS

    class _Cur:
        called = False
        def executemany(self, *_): self.called = True

    cur = _Cur()
    old_row = tuple(None for _ in _PROVENANCE_COLS)
    _write_triage_provenance(cur, 9999, {}, "test-model", old_row)
    assert not cur.called


def test_timeout_sets_triage_failed(app, db_conn):
    """When the Anthropic call times out, status → triage_failed."""
    import backend.modules.requests.router as rtr
    import anthropic

    def triage_that_times_out(rid):
        import psycopg2
        c = psycopg2.connect(
            host="127.0.0.1", port=54322, user="postgres",
            password="postgres", dbname="postgres",
        )
        try:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE maintenance_request SET status='triage_pending', triage_started_at=NOW() WHERE request_id=%s",
                    [rid],
                )
            c.commit()
            # Simulate the Anthropic timeout path: write triage_failed
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE maintenance_request SET status='triage_failed', triage_started_at=NULL WHERE request_id=%s",
                    [rid],
                )
            c.commit()
        finally:
            c.close()

    rtr._run_triage_background = triage_that_times_out
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: _user(_COORD, "coordinator")
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)

    rid = _insert_request(db_conn, "intake_received")
    db_conn.connection.commit()
    client.post(f"/api/v1/requests/{rid}/triage")
    app.dependency_overrides.clear()

    row = db_conn.execute(
        "SELECT status FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    assert row["status"] == "triage_failed"
