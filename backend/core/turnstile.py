"""Cloudflare Turnstile siteverify (server-side only)."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from backend.core.config import settings
from backend.core.exceptions import PermissionDenied

logger = logging.getLogger("backend.turnstile")

_SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT = 10.0


def verify_turnstile(
    token: str | None,
    *,
    expected_action: str,
    remote_ip: Optional[str] = None,
) -> None:
    """Raise PermissionDenied unless siteverify succeeds for action + hostname."""
    hostnames = settings.turnstile_hostnames
    secret = settings.TURNSTILE_SECRET
    if (
        not isinstance(token, str)
        or not token
        or len(token) > 2048
        or not secret
        or not hostnames
    ):
        raise PermissionDenied("Vérification anti-bot échouée")

    data = {
        "secret": secret,
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(_SITEVERIFY, data=data)
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("turnstile siteverify request failed")
        raise PermissionDenied("Vérification anti-bot échouée") from None

    if (
        not result.get("success")
        or result.get("action") != expected_action
        or result.get("hostname") not in hostnames
    ):
        raise PermissionDenied("Vérification anti-bot échouée")
