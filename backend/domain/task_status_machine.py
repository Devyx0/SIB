"""
Allowed transitions over the dispatch_task_status enum.

Values (from DB):
    queued, scheduled, en_route, arrived, working, done,
    needs_expertise, return_visit, cancelled

Spec: docs/superpowers/specs/2026-10-22-task-first-class-design.md
    queued → scheduled → en_route → arrived → working → done
                                                ↘ needs_expertise
                                                ↘ return_visit
done / cancelled are terminal. needs_expertise / return_visit end this
attempt (history is kept) but may still be abandoned via cancelled so the
call can auto-close.
"""
from __future__ import annotations

from backend.core.exceptions import InvalidTransition

_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued":          frozenset({"scheduled", "cancelled"}),
    "scheduled":       frozenset({"queued", "en_route", "cancelled"}),
    "en_route":        frozenset({"arrived"}),
    "arrived":         frozenset({"working"}),
    "working":         frozenset({"done", "needs_expertise", "return_visit"}),

    "done":            frozenset(),
    "needs_expertise": frozenset({"cancelled"}),
    "return_visit":    frozenset({"cancelled"}),
    "cancelled":       frozenset(),
}

ALL_TASK_STATUSES: frozenset[str] = frozenset(_TRANSITIONS)


def transition_task(current: str, target: str) -> None:
    if target not in _TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(
            f"Cannot transition task from {current!r} to {target!r}"
        )
