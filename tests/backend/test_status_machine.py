"""Tests for domain/status_machine.py."""
from __future__ import annotations

import pytest

from backend.core.exceptions import InvalidTransition
from backend.domain.status_machine import ALL_STATUSES, _TRANSITIONS, transition


# ── Build the full allowed and forbidden edge sets ─────────────────────────────

_ALLOWED: list[tuple[str, str]] = [
    (src, tgt)
    for src, targets in _TRANSITIONS.items()
    for tgt in targets
]

_FORBIDDEN: list[tuple[str, str]] = [
    (src, tgt)
    for src in ALL_STATUSES
    for tgt in ALL_STATUSES
    if tgt not in _TRANSITIONS.get(src, frozenset())
]


# ── Allowed transitions ────────────────────────────────────────────────────────

@pytest.mark.parametrize("current,target", _ALLOWED)
def test_allowed_transition(current: str, target: str):
    transition(current, target)  # must not raise


# ── Forbidden transitions ──────────────────────────────────────────────────────

@pytest.mark.parametrize("current,target", _FORBIDDEN)
def test_forbidden_transition(current: str, target: str):
    with pytest.raises(InvalidTransition):
        transition(current, target)


# ── Spot-checks matching service.py ───────────────────────────────────────────

def test_triage_happy_path():
    transition("intake_received", "triage_pending")  # service.py:289
    transition("triage_pending", "triaged")           # service.py:166


def test_triage_retry_path():
    transition("triage_failed", "triage_pending")     # service.py:289 retry


def test_triage_exhausted():
    transition("triage_pending", "triage_failed")     # service.py:375


def test_triage_proposal_is_unreachable():
    """triage_proposal is blocked by rule 37 — nothing can transition INTO it."""
    for src in ALL_STATUSES:
        assert "triage_proposal" not in _TRANSITIONS.get(src, frozenset()), (
            f"{src!r} → triage_proposal is present but rule 37 blocks it"
        )


def test_closed_is_terminal():
    with pytest.raises(InvalidTransition):
        transition("closed", "intake_received")


def test_invalid_transition_is_409():
    """InvalidTransition carries HTTP 409, not 422."""
    from backend.core.exceptions import InvalidTransition as IT
    assert IT.status_code == 409
