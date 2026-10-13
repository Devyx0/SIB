"""
Allowed status transitions for maintenance_request.
Enforced in service layer before any UPDATE.
"""
from __future__ import annotations

_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending":     frozenset({"in_progress", "closed"}),
    "in_progress": frozenset({"closed", "pending"}),
    "closed":      frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Invalid transition: {current!r} → {target!r}")
