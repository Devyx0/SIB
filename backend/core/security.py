"""
Dev auth stub.

At import time the module asserts APP_ENV == "dev", crashing startup if the stub
is loaded in staging or prod.  Replace get_current_user with a real JWT verifier
when auth is wired — routers depend only on CurrentUser and get_current_user, both
of which stay stable across that swap.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from typing import Annotated

from .config import settings
from .db import get_db_conn
from .exceptions import PermissionDenied

# ── Startup guard ──────────────────────────────────────────────────────────────
if settings.APP_ENV != "dev":
    raise RuntimeError(
        f"Dev auth stub is the only auth mechanism configured, "
        f"but APP_ENV={settings.APP_ENV!r}. "
        "Set APP_ENV=dev or wire real Supabase JWT verification first."
    )


@dataclass(frozen=True)
class CurrentUser:
    employee_id: int
    roles: frozenset[str]  # values from employee_role.role


def get_current_user(
    x_dev_employee_id: Annotated[str | None, Header()] = None,
    conn=Depends(get_db_conn),
) -> CurrentUser:
    """
    Dev-only dependency.  Reads X-Dev-Employee-Id header, loads the employee
    and their roles from the DB, returns a CurrentUser.

    Also guards at request time so tests can monkeypatch settings.APP_ENV
    and see a 403 rather than a crash.
    """
    if settings.APP_ENV != "dev":
        raise PermissionDenied("Dev auth stub requires APP_ENV=dev")

    if not x_dev_employee_id:
        raise PermissionDenied("X-Dev-Employee-Id header is required in dev mode")

    try:
        emp_id = int(x_dev_employee_id)
    except ValueError:
        raise PermissionDenied("X-Dev-Employee-Id must be an integer employee_id")

    row = conn.execute(
        "SELECT employee_id FROM employee WHERE employee_id = %s AND is_active = true",
        [emp_id],
    ).fetchone()
    if row is None:
        raise PermissionDenied("Employee not found or inactive")

    roles = frozenset(
        r["role"]
        for r in conn.execute(
            "SELECT role FROM employee_role WHERE employee_id = %s",
            [emp_id],
        ).fetchall()
    )
    return CurrentUser(employee_id=emp_id, roles=roles)
