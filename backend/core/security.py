"""JWT verification for Supabase-issued tokens."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header

from .config import settings
from .db import get_db_conn
from .exceptions import PermissionDenied, Unauthorized


@dataclass(frozen=True)
class CurrentUser:
    employee_id: int
    roles: frozenset[str]  # values from employee_role.role


def verify_jwt(token: str) -> dict:
    """Decode and verify a Supabase JWT. Returns the payload.

    Raises Unauthorized on any failure (bad signature, expired, wrong audience,
    missing required claims).

    # ponytail: HS256 only — swap to JWKS by replacing this function with
    # python-jose + a JWKS URL fetch; no other code changes required.
    """
    try:
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub", "aud"]},
        )
    except jwt.InvalidTokenError:
        raise Unauthorized()


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    conn=Depends(get_db_conn),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized()
    payload = verify_jwt(authorization.removeprefix("Bearer "))
    sub = payload["sub"]
    row = conn.execute(
        "SELECT employee_id FROM employee WHERE auth_user_id = %s AND is_active = true",
        [sub],
    ).fetchone()
    if row is None:
        raise PermissionDenied("No active employee linked to this account")
    roles = frozenset(
        r["role"] for r in conn.execute(
            "SELECT role FROM employee_role WHERE employee_id = %s",
            [row["employee_id"]],
        ).fetchall()
    )
    return CurrentUser(employee_id=row["employee_id"], roles=roles)
