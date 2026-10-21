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


def test_triage_proposal_only_reachable_from_triage_pending():
    """Task-first-class revives triage_proposal (draft tasks, no assignee)."""
    sources = {s for s in ALL_STATUSES if "triage_proposal" in _TRANSITIONS[s]}
    assert sources == {"triage_pending"}


def test_triage_proposal_to_open():
    transition("triage_pending", "triage_proposal")
    transition("triage_proposal", "open")


def test_triage_proposal_reject_all_goes_to_clarify():
    transition("triage_proposal", "triage_clarify")


def test_open_to_closed():
    transition("open", "closed")


def test_open_cannot_bounce_back_to_proposal():
    with pytest.raises(InvalidTransition):
        transition("open", "triage_proposal")


@pytest.mark.parametrize("src", [
    "intake_received", "triage_pending", "triage_failed", "triage_clarify",
    "triage_proposal", "triaged", "open",
])
@pytest.mark.parametrize("fieldwork", [
    "scheduled", "en_route", "arrived", "awaiting_redispatch",
])
def test_no_fieldwork_targets_on_request(src: str, fieldwork: str):
    with pytest.raises(InvalidTransition):
        transition(src, fieldwork)


def test_intake_received_cannot_go_en_route():
    with pytest.raises(InvalidTransition):
        transition("intake_received", "en_route")


@pytest.mark.parametrize("src", ["triage_failed", "triage_clarify"])
def test_other_triage_states_cannot_go_en_route(src: str):
    with pytest.raises(InvalidTransition):
        transition(src, "en_route")


def test_fieldwork_statuses_are_never_targets():
    for targets in _TRANSITIONS.values():
        assert not targets & {"scheduled", "en_route", "arrived", "awaiting_redispatch"}


def test_closed_is_terminal():
    with pytest.raises(InvalidTransition):
        transition("closed", "intake_received")


def test_invalid_transition_is_409():
    """InvalidTransition carries HTTP 409, not 422."""
    from backend.core.exceptions import InvalidTransition as IT
    assert IT.status_code == 409
