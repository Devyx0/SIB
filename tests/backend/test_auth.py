"""Tests for the dev auth stub (get_current_user)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import backend.core.security as sec_module
from backend.core.config import settings

_REPO_ROOT = Path(__file__).parent.parent.parent


# ── Helpers ────────────────────────────────────────────────────────────────────

def _authed(client, emp_id: int):
    return client.get("/health/db", headers={"X-Dev-Employee-Id": str(emp_id)})


# ── Dev auth refusing wrong environments ───────────────────────────────────────

def test_dev_auth_refuses_when_not_dev(client, monkeypatch):
    """get_current_user raises PermissionDenied if APP_ENV != 'dev'."""
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    # /health/db doesn't use auth, so hit the stub directly via a protected route.
    # Since no protected routes exist yet, call the dependency directly.
    from backend.core.security import get_current_user
    from backend.core.exceptions import PermissionDenied
    import pytest

    with pytest.raises(PermissionDenied, match="APP_ENV=dev"):
        # Simulate calling the dependency with APP_ENV=prod
        # We pass a fake conn and the header
        class FakeConn:
            def execute(self, *a, **k):
                raise AssertionError("should not reach DB")
        get_current_user(x_dev_employee_id="1", conn=FakeConn())


def test_dev_auth_missing_header(client, monkeypatch):
    """Missing X-Dev-Employee-Id from the dependency → PermissionDenied."""
    from backend.core.security import get_current_user
    from backend.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied, match="required"):
        get_current_user(x_dev_employee_id=None, conn=None)


def test_dev_auth_non_integer_header(client):
    from backend.core.security import get_current_user
    from backend.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied, match="integer"):
        get_current_user(x_dev_employee_id="not-an-int", conn=None)


# ── Valid employee loads correctly ─────────────────────────────────────────────

def test_dev_auth_valid_employee(db_conn):
    """A known active employee resolves to a CurrentUser with correct roles."""
    from backend.core.security import get_current_user

    # Find any active employee with at least one role
    row = db_conn.execute(
        """
        SELECT e.employee_id
        FROM employee e
        JOIN employee_role er ON er.employee_id = e.employee_id
        WHERE e.is_active = true
        LIMIT 1
        """
    ).fetchone()
    assert row is not None, "No active employee with a role in DB"

    emp_id = row["employee_id"]
    user = get_current_user(x_dev_employee_id=str(emp_id), conn=db_conn)

    assert user.employee_id == emp_id
    assert len(user.roles) >= 1
    assert user.roles <= {"technician", "coordinator", "director", "contractor"}


def test_dev_auth_unknown_employee(db_conn):
    from backend.core.security import get_current_user
    from backend.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied, match="not found"):
        get_current_user(x_dev_employee_id="999999999", conn=db_conn)


# ── Startup guard (subprocess) ─────────────────────────────────────────────────

def test_app_startup_refuses_non_dev_env():
    """
    Importing security.py with APP_ENV=prod must raise RuntimeError before
    the process can serve any request.  Run in a subprocess so the module is
    fresh and the env var is read by pydantic-settings at instantiation time.
    """
    result = subprocess.run(
        [sys.executable, "-c", "from backend.core.security import get_current_user"],
        capture_output=True,
        text=True,
        env={**os.environ, "APP_ENV": "prod"},
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert "APP_ENV" in result.stderr
