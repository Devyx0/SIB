"""Cloudflare Turnstile siteverify — currently a no-op.

Widget can still run on the FE; server acceptance was rejecting valid tokens
(hostname/action mismatch under tunnel). Re-enable when hostnames/actions are
aligned for every public origin.
"""
from __future__ import annotations

from typing import Optional


def verify_turnstile(
    token: str | None,
    *,
    expected_action: str,
    remote_ip: Optional[str] = None,
) -> None:
    return
