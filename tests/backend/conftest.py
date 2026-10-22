"""
Shared fixtures for backend tests.

Isolation model
───────────────
Each test gets a real psycopg3 connection (db_conn) that is never committed —
it is rolled back at teardown.  The `client` fixture overrides get_db_conn so
that every Depends(get_db_conn) inside a route returns the same connection.
DBTransactionMiddleware still runs but acquires its own pool connection; that
connection sees no writes and its commit is a no-op.

Writes made through the TestClient are therefore visible within the test
(same connection, uncommitted) and disappear after teardown (rollback).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn, get_pool
from backend.main import create_app
from backend.modules.portfolio.geocode import GeocodeResult


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(autouse=True)
def _stub_building_geocode(monkeypatch):
    """Portfolio create/patch must not call live Nominatim in tests."""
    def _fake(adresse=None, ville=None, code_postal=None, **_kwargs):
        from backend.modules.portfolio.geocode import build_query
        q = build_query(adresse, ville, code_postal) or ""
        if not q:
            return GeocodeResult("skipped", None, None, "", note="blank_address")
        return GeocodeResult("ok", 46.8139, -71.2080, q, display_name="stub", note="test_stub")

    monkeypatch.setattr("backend.modules.portfolio.edit_service.geocode_address", _fake)


@pytest.fixture
def db_conn():
    """Psycopg3 connection that rolls back unconditionally at test end."""
    with get_pool().connection() as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def client(app, db_conn):
    """
    TestClient with get_db_conn overridden to return the test connection.
    Writes never persist beyond the test.
    """
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
