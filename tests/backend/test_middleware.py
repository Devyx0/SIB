"""Tests for request_id, error envelope, commit-ordering, and DB isolation."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
import psycopg

from backend.core.db import get_db_conn, get_pool
from backend.main import create_app
from fastapi.testclient import TestClient


# ── Error envelope shape ───────────────────────────────────────────────────────

def test_404_uses_envelope(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    err = body["error"]
    assert set(err) == {"code", "message", "request_id", "details"}
    assert err["code"] == "NOT_FOUND"


def test_405_uses_envelope(client):
    r = client.post("/health")   # /health only accepts GET
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_422_uses_envelope(client):
    # /health/db expects no body; send one with a bad content-type to force
    # FastAPI's request validation to fire via a deliberately wrong path.
    # Simpler: hit a non-existent path that returns 404 (envelope confirmed above).
    # For 422 specifically, patch a route that has a required query param.
    pass  # covered by test_validation_error_envelope below


def test_validation_error_envelope(app, db_conn):
    """RequestValidationError (missing required field) → 422 envelope."""
    from fastapi import APIRouter, Depends, Query
    from backend.core.db import get_db_conn

    router = APIRouter()

    @router.get("/test-validate")
    def needs_param(q: int = Query(...)):
        return {"q": q}

    app.include_router(router)
    app.dependency_overrides[get_db_conn] = lambda: db_conn

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/test-validate")  # missing required ?q=

    app.dependency_overrides.clear()
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_FAILED"
    assert "details" in err


def test_unhandled_exception_returns_500_envelope(app, db_conn):
    """An unhandled exception in a route must produce 500 envelope, no internals."""
    from fastapi import APIRouter
    from backend.core.db import get_db_conn

    router = APIRouter()

    @router.get("/test-crash")
    def boom():
        raise RuntimeError("secret internal message")

    app.include_router(router)
    app.dependency_overrides[get_db_conn] = lambda: db_conn

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/test-crash")

    app.dependency_overrides.clear()
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert "secret internal message" not in err["message"]
    assert err["details"] is None


# ── X-Request-ID round-trip ────────────────────────────────────────────────────

def test_request_id_passthrough(client):
    custom = str(uuid.uuid4())
    r = client.get("/health", headers={"X-Request-ID": custom})
    assert r.headers["x-request-id"] == custom


def test_request_id_generated_when_absent(client):
    r = client.get("/health")
    rid = r.headers.get("x-request-id")
    assert rid is not None
    uuid.UUID(rid)  # must be a valid UUID


def test_request_id_in_error_envelope(client):
    custom = str(uuid.uuid4())
    r = client.get("/does-not-exist", headers={"X-Request-ID": custom})
    assert r.json()["error"]["request_id"] == custom


# ── Commit-before-response ─────────────────────────────────────────────────────

def test_commit_failure_is_500_not_2xx():
    """
    If conn.commit() raises after a successful handler, the client must receive
    500 — not the handler's 2xx.  Proves commit runs before response is sent.
    """
    # Build a fake connection whose commit() raises
    fake_conn = MagicMock()
    fake_conn.commit.side_effect = psycopg.OperationalError("simulated commit failure")
    fake_conn.execute.return_value = MagicMock(fetchone=MagicMock(return_value={"?column?": 1}))
    fake_conn.rollback = MagicMock()

    fake_ctx = MagicMock()
    fake_ctx.__enter__ = lambda s: fake_conn
    fake_ctx.__exit__ = MagicMock(return_value=False)

    import backend.core.db as db_module
    original_get_pool = db_module.get_pool
    original_pool = db_module._pool

    def patched_get_pool():
        pool = MagicMock()
        pool.connection.return_value = fake_ctx
        return pool

    db_module.get_pool = patched_get_pool
    db_module._pool = None
    try:
        fresh_app = create_app()
        with TestClient(fresh_app, raise_server_exceptions=False) as c:
            r = c.get("/health/db")
    finally:
        db_module.get_pool = original_get_pool
        db_module._pool = original_pool

    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert "simulated" not in err["message"]


# ── 4xx rolls back ────────────────────────────────────────────────────────────

def test_error_response_rolls_back():
    """
    A domain exception converted to a 4xx response by an exception handler must
    roll back the transaction — the middleware sees a 409 response, not an
    exception, and must still discard the write.

    Uses a real committed connection (no rollback fixture) and cleans up in
    finally so the test is safe even if the assertion fails.
    """
    from fastapi import APIRouter, Depends
    from backend.core.exceptions import ConflictError

    with get_pool().connection() as c:
        emp = c.execute("SELECT employee_id, notes FROM employee LIMIT 1").fetchone()
    emp_id, original_notes = emp["employee_id"], emp["notes"]

    fresh_app = create_app()
    router = APIRouter()

    @router.post("/test-rollback-on-409")
    def write_then_conflict(conn=Depends(get_db_conn)):
        conn.execute(
            "UPDATE employee SET notes = 'rollback_marker' WHERE employee_id = %s",
            [emp_id],
        )
        raise ConflictError("intentional conflict for rollback test")

    fresh_app.include_router(router)

    try:
        with TestClient(fresh_app, raise_server_exceptions=False) as c:
            r = c.post("/test-rollback-on-409")

        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CONFLICT"

        with get_pool().connection() as verify:
            row = verify.execute(
                "SELECT notes FROM employee WHERE employee_id = %s", [emp_id]
            ).fetchone()
        assert row["notes"] != "rollback_marker", \
            "4xx response must roll back — write must not be persisted"
    finally:
        with get_pool().connection() as cleanup:
            cleanup.execute(
                "UPDATE employee SET notes = %s WHERE employee_id = %s",
                [original_notes, emp_id],
            )
            cleanup.commit()


# ── TestClient write isolation ─────────────────────────────────────────────────

def test_client_writes_are_not_committed(db_conn):
    """
    Writes made via the test connection (db_conn) are uncommitted and therefore
    invisible to any other connection.  The fixture rolls back at teardown so no
    test-induced data survives into the next test.
    """
    emp = db_conn.execute("SELECT employee_id FROM employee LIMIT 1").fetchone()
    emp_id = emp["employee_id"]

    db_conn.execute("SAVEPOINT iso_test")
    db_conn.execute(
        "UPDATE employee SET notes = 'isolation_marker' WHERE employee_id = %s",
        [emp_id],
    )

    # Visible on this connection (uncommitted write, same transaction)
    local = db_conn.execute(
        "SELECT notes FROM employee WHERE employee_id = %s", [emp_id]
    ).fetchone()
    assert local["notes"] == "isolation_marker", "write must be visible on the same connection"

    # NOT visible on any other connection (not committed to disk)
    with get_pool().connection() as other:
        other_row = other.execute(
            "SELECT notes FROM employee WHERE employee_id = %s", [emp_id]
        ).fetchone()
    assert other_row["notes"] != "isolation_marker", \
        "uncommitted write must not be visible to other connections"

    db_conn.execute("ROLLBACK TO SAVEPOINT iso_test")
