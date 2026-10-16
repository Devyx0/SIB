"""JWT verification for Supabase-issued tokens."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header

from .config import settings
from .db import get_db_conn
from .exceptions import PermissionDenied, Unauthorized


@dataclass(frozen=True)
class CurrentUser:
    employee_id: int
    roles: frozenset[str]  # values from employee_role.role


# Lazily initialised from settings.SUPABASE_JWKS_URL — never from the token's iss.
_jwks_client: PyJWKClient | None = None


def _init_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is None and settings.SUPABASE_JWKS_URL:
        _jwks_client = PyJWKClient(settings.SUPABASE_JWKS_URL)
    return _jwks_client


def verify_jwt(token: str) -> dict:
    """Decode and verify a Supabase JWT. Returns the payload.

    HS256: verified with SUPABASE_JWT_SECRET (remote Supabase).
    ES256: verified via JWKS at SUPABASE_JWKS_URL (config only — never from token iss).
    Both paths require iss == SUPABASE_ISSUER (enforced unconditionally).
    Any other algorithm or any verification failure raises Unauthorized.
    """
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
        if alg == "HS256":
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        elif alg == "ES256":
            client = _init_jwks_client()
            if client is None:
                raise Unauthorized()
            signing_key = client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        else:
            raise Unauthorized()
        if payload["iss"] != settings.SUPABASE_ISSUER:
            raise Unauthorized()
        return payload
    except Unauthorized:
        raise
    except jwt.PyJWTError:
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
