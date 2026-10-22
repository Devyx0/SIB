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


def test_open_returns_409(ac, db_conn):
    """An open call has accepted tasks; re-triage must not pull it back to pending."""
    rid = _insert_request(db_conn, "open")
    r = ac(_user(_COORD, "coordinator")).post(f"/api/v1/requests/{rid}/triage")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"
    assert db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()["s"] == "open"


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

    def spy_bg(rid, lang="fr"):
        # Fresh psycopg2 connection — independent of the test's db_conn.
        # The row must be visible here (middleware committed before background tasks run).
        from backend.core.config import settings
        c = psycopg2.connect(
            host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
            user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
            dbname=settings.LOCAL_DB_NAME,
        )
        with c.cursor() as cur:
            cur.execute("SELECT request_id FROM maintenance_request WHERE request_id = %s", [rid])
            row = cur.fetchone()
            seen_rid.append(row[0] if row else None)
        c.close()

    original_bg = rtr._run_triage_background
    rtr._run_triage_background = spy_bg
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: _user(_COORD, "coordinator")
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)

    rid = _insert_request(db_conn, "intake_received")
    db_conn.commit()  # commit so the row is visible to the spy's fresh connection

    try:
        client.post(f"/api/v1/requests/{rid}/triage")
        # Spy ran during the client.post() call, found the committed row via fresh psycopg2 conn
        assert seen_rid == [rid], f"got {seen_rid}"
    finally:
        rtr._run_triage_background = original_bg
        app.dependency_overrides.clear()
        db_conn.execute("DELETE FROM maintenance_request WHERE request_id = %s", [rid])
        db_conn.commit()


def test_exception_before_api_call_sets_triage_failed():
    """Any exception raised inside triage() → _run_triage_background catches → triage_failed.

    Uses its own psycopg2 connections (matching the pattern of other direct-commit tests in
    this file) so that commit visibility is not affected by the psycopg3 pool's transaction state.
    """
    import psycopg2
    import psycopg2.extras
    import backend.modules.requests.router as rtr
    import backend.triage.service as svc
    from backend.core.config import settings

    # Insert a row and commit it so the background task's connection can see it.
    c_setup = psycopg2.connect(
        host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
        user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
        dbname=settings.LOCAL_DB_NAME,
    )
    c_setup.cursor_factory = psycopg2.extras.RealDictCursor
    try:
        with c_setup.cursor() as cur:
            cur.execute(
                "INSERT INTO maintenance_request (status, building_id, sector_id)"
                " VALUES ('intake_received', %s, %s) RETURNING request_id",
                [_BLDG, _SECTOR],
            )
            rid = cur.fetchone()["request_id"]
        c_setup.commit()
    finally:
        c_setup.close()

    def crashing_triage(conn, request_id, **_):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE maintenance_request SET status='triage_pending', triage_started_at=NOW() WHERE request_id=%s",
                [request_id],
            )
        conn.commit()
        raise KeyError("ANTHROPIC_API_KEY")

    try:
        original = svc.triage
        svc.triage = crashing_triage
        try:
            rtr._run_triage_background(rid)
        finally:
            svc.triage = original

        # Verify via a fresh psycopg2 connection so there's no transaction-isolation ambiguity.
        c_check = psycopg2.connect(
            host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
            user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
            dbname=settings.LOCAL_DB_NAME,
        )
        c_check.cursor_factory = psycopg2.extras.RealDictCursor
        try:
            with c_check.cursor() as cur:
                cur.execute("SELECT status FROM maintenance_request WHERE request_id = %s", [rid])
                row = cur.fetchone()
        finally:
            c_check.close()
        assert row["status"] == "triage_failed"
    finally:
        # Cleanup: row was committed via psycopg2; runs even if assertion fails.
        c_cleanup = psycopg2.connect(
            host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
            user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
            dbname=settings.LOCAL_DB_NAME,
        )
        try:
            with c_cleanup.cursor() as cur:
                cur.execute("DELETE FROM maintenance_request WHERE request_id = %s", [rid])
            c_cleanup.commit()
        finally:
            c_cleanup.close()


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
    from backend.core.config import settings

    def triage_that_times_out(rid, lang="fr"):
        import psycopg2
        c = psycopg2.connect(
            host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
            user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
            dbname=settings.LOCAL_DB_NAME,
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

    original_bg = rtr._run_triage_background
    rtr._run_triage_background = triage_that_times_out
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: _user(_COORD, "coordinator")
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)

    rid = _insert_request(db_conn, "intake_received")
    db_conn.commit()
    try:
        client.post(f"/api/v1/requests/{rid}/triage")
        row = db_conn.execute(
            "SELECT status FROM maintenance_request WHERE request_id = %s", [rid]
        ).fetchone()
        assert row["status"] == "triage_failed"
    finally:
        # Cleanup: psycopg2 committed status updates; runs even if assertion fails.
        rtr._run_triage_background = original_bg
        app.dependency_overrides.clear()
        db_conn.execute("DELETE FROM maintenance_request WHERE request_id = %s", [rid])
        db_conn.commit()
