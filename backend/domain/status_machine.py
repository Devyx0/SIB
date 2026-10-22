"""
Allowed transitions over the request_status enum (Service Call container).

Fieldwork (scheduled / en_route / arrived / working) lives on dispatch_task —
see task_status_machine.py. The request only carries intake, triage and a
container state:

    intake_received → triage_pending → triage_clarify | triage_failed
                                     → triage_proposal → open → closed
                                     → triaged (legacy single-step accept)

Always triage before fieldwork: no intake/triage_failed/triage_clarify →
en_route bypass.

Current enum values (from DB):
    intake_received, triage_pending, triaged, scheduled, awaiting_redispatch,
    triage_clarify, triage_proposal, triage_failed, en_route, arrived, open,
    closed

scheduled / awaiting_redispatch / en_route / arrived are legacy: they are
never valid *targets* for new work. They remain as sources only so rows not
yet migrated to tasks can still move to open / closed.
"""
from __future__ import annotations

from backend.core.exceptions import InvalidTransition

_TRANSITIONS: dict[str, frozenset[str]] = {
    "intake_received": frozenset({"triage_pending"}),
    "triage_failed":   frozenset({"triage_pending"}),
    "triage_pending":  frozenset({
        "triaged", "triage_proposal", "triage_failed", "triage_clarify",
    }),
    "triage_clarify":  frozenset({"intake_received"}),

    # AI wrote draft tasks; dispatcher accepts (→ open) or rejects all (→ clarify).
    "triage_proposal": frozenset({"open", "triage_clarify"}),
    "triaged":         frozenset({"open", "closed"}),
    "open":            frozenset({"closed"}),
    "closed":          frozenset(),

    # Legacy fieldwork states — source-only, drained by the task backfill.
    "scheduled":           frozenset({"open", "closed"}),
    "awaiting_redispatch": frozenset({"open", "closed"}),
    "en_route":            frozenset({"open", "closed"}),
    "arrived":             frozenset({"open", "closed"}),
}

ALL_STATUSES: frozenset[str] = frozenset(_TRANSITIONS)


def transition(current: str, target: str) -> None:
    if target not in _TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(
            f"Cannot transition from {current!r} to {target!r}"
        )
