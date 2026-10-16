"""Tests for JWT authentication — 401 and 403 paths."""
from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.db import get_db_conn

_START = "2026-09-01"
_END   = "2026-09-25"
_URL   = f"/api/v1/requests?start_date={_START}&end_date={_END}"
# UUID not linked to any employee row — used for 403 tests.
_GHOST = "00000000-0000-0000-0000-000000000099"


def _token(
    sub: str = _GHOST,
    aud: str = "authenticated",
    exp_offset: int = 3600,
    secret: str | None = None,
) -> str:
    payload = {
        "sub": sub,
        "aud": aud,
        "iss": settings.SUPABASE_ISSUER,
        "exp": int(time.time()) + exp_offset,
    }
    return pyjwt.encode(payload, secret or settings.SUPABASE_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def raw_client(app, db_conn):
    """TestClient with real get_current_user (no dependency override)."""
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_missing_authorization_is_401(raw_client):
    r = raw_client.get(_URL)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_token_string_is_401(raw_client):
    r = raw_client.get(_URL, headers={"authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_wrong_secret_is_401(raw_client):
    tok = _token(secret="a-completely-different-secret-value-here!")
    r = raw_client.get(_URL, headers={"authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_expired_token_is_401(raw_client):
    tok = _token(exp_offset=-60)
    r = raw_client.get(_URL, headers={"authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_wrong_audience_is_401(raw_client):
    tok = _token(aud="anon")
    r = raw_client.get(_URL, headers={"authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_valid_token_no_linked_employee_is_403(raw_client):
    tok = _token()  # valid JWT; _GHOST UUID not linked to any employee
    r = raw_client.get(_URL, headers={"authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"
