"""
Allowed transitions over the request_status enum.

Current enum values (from DB):
    intake_received, triage_pending, triaged, triage_clarify,
    triage_proposal, triage_failed, en_route, closed

Source annotations
  service.py:N  — written by triage/service.py at that line
  proposed      — no writer exists yet; will need a coordinator endpoint
  unreachable   — in the enum but no code can reach it under current rules

F1 finding: triage/service.py never writes triage_clarify or triage_proposal.
  triage_clarify  is mentioned in the docstring as a future structural-blocker path.
  triage_proposal is blocked by rule 37 (dispatcher-suggestion feature deferred).

See docs/status-machine-proposal.md for the 0002 migration proposal
(adding 'scheduled' and 'cancelled').
"""
from __future__ import annotations

from backend.core.exceptions import InvalidTransition

# Each key is a "from" status; the frozenset is the set of legal "to" statuses.
# en_route is reachable from EVERY open status (anything except closed /
# en_route itself) — mirrors the assign action, which only rejects closed
# (service.py _check_not_closed). Written by requests/service.action_en_route.
_TRANSITIONS: dict[str, frozenset[str]] = {
    # ── Written by triage/service.py ──────────────────────────────────────────
    # service.py:289  acquire lock (accepts intake_received or triage_failed)
    "intake_received": frozenset({"triage_pending", "en_route"}),
    "triage_failed":   frozenset({"triage_pending", "en_route"}),  # service.py:289 retry path
    # service.py:166  success  /  service.py:375  retries exhausted
    "triage_pending":  frozenset({"triaged", "triage_failed",
                                  "triage_clarify", "en_route"}),  # triage_clarify: proposed path, no writer yet

    # ── Coordinator / technician actions ──────────────────────────────────────
    "triage_clarify":  frozenset({"intake_received", "en_route"}),  # proposed: coordinator resets blocked row
    "triaged":         frozenset({"en_route", "closed"}),
    # en_route → closed: closeout outcome 1 (stop 3)
    # en_route → triaged: closeout outcomes 2/3/4 — back to his schedule or
    #                     the coordinator queue (stop 3)
    "en_route":        frozenset({"closed", "triaged"}),

    # ── Terminal ──────────────────────────────────────────────────────────────
    "closed":          frozenset(),

    # ── Unreachable under current rules ───────────────────────────────────────
    # triage_proposal blocked by rule 37; nothing transitions INTO it, but as
    # an open status an assigned call could still be taken en route.
    "triage_proposal": frozenset({"en_route"}),
}

# All known status values — used for exhaustiveness checks.
ALL_STATUSES: frozenset[str] = frozenset(_TRANSITIONS)


def transition(current: str, target: str) -> None:
    """
    Assert that moving from *current* to *target* is permitted.
    Raises InvalidTransition (HTTP 409) if not.
    Does NOT write to the database — callers do that.
    """
    if target not in _TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(
            f"Cannot transition from {current!r} to {target!r}"
        )
