"""
Allowed transitions over the request_status enum.

Current enum values (from DB):
    intake_received, triage_pending, triaged, scheduled, awaiting_redispatch,
    triage_clarify, triage_proposal, triage_failed, en_route, arrived, closed
"""
from __future__ import annotations

from backend.core.exceptions import InvalidTransition

_TRANSITIONS: dict[str, frozenset[str]] = {
    "intake_received": frozenset({"triage_pending", "en_route"}),
    "triage_failed":   frozenset({"triage_pending", "en_route"}),
    "triage_pending":  frozenset({"triaged", "triage_failed", "triage_clarify"}),

    "triage_clarify":  frozenset({"intake_received", "en_route"}),
    "triaged":         frozenset({"scheduled", "closed"}),
    "scheduled":       frozenset({"en_route", "triaged", "closed"}),
    "awaiting_redispatch": frozenset({"scheduled", "en_route"}),
    # en_route → arrived (on site); closeout only from arrived.
    "en_route":        frozenset({"arrived"}),
    "arrived":         frozenset({"closed", "scheduled", "awaiting_redispatch"}),

    "closed":          frozenset(),
    "triage_proposal": frozenset({"en_route"}),
}

ALL_STATUSES: frozenset[str] = frozenset(_TRANSITIONS)


def transition(current: str, target: str) -> None:
    if target not in _TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(
            f"Cannot transition from {current!r} to {target!r}"
        )
