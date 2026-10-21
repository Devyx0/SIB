"""Tests for domain/task_status_machine.py."""
from __future__ import annotations

import pytest

from backend.core.exceptions import InvalidTransition
from backend.domain.task_status_machine import (
    ALL_TASK_STATUSES,
    _TRANSITIONS,
    transition_task,
)

_ALLOWED: list[tuple[str, str]] = [
    (src, tgt) for src, targets in _TRANSITIONS.items() for tgt in targets
]

_FORBIDDEN: list[tuple[str, str]] = [
    (src, tgt)
    for src in ALL_TASK_STATUSES
    for tgt in ALL_TASK_STATUSES
    if tgt not in _TRANSITIONS.get(src, frozenset())
]


def test_all_statuses_match_spec():
    assert ALL_TASK_STATUSES == frozenset({
        "queued", "scheduled", "en_route", "arrived", "working", "done",
        "needs_expertise", "return_visit", "cancelled",
    })


@pytest.mark.parametrize("current,target", _ALLOWED)
def test_allowed_transition(current: str, target: str):
    transition_task(current, target)  # must not raise


@pytest.mark.parametrize("current,target", _FORBIDDEN)
def test_forbidden_transition(current: str, target: str):
    with pytest.raises(InvalidTransition):
        transition_task(current, target)


def test_queued_to_scheduled_allowed():
    transition_task("queued", "scheduled")


def test_scheduled_can_unassign_back_to_queued():
    transition_task("scheduled", "queued")


def test_happy_path():
    for src, tgt in [
        ("queued", "scheduled"), ("scheduled", "en_route"),
        ("en_route", "arrived"), ("arrived", "working"), ("working", "done"),
    ]:
        transition_task(src, tgt)


def test_working_to_done_allowed():
    transition_task("working", "done")


@pytest.mark.parametrize("target", ["done", "needs_expertise", "return_visit"])
def test_working_outcomes(target: str):
    transition_task("working", target)


def test_queued_to_en_route_forbidden():
    with pytest.raises(InvalidTransition):
        transition_task("queued", "en_route")


@pytest.mark.parametrize("terminal", ["done", "cancelled"])
def test_terminal_statuses_have_no_exits(terminal: str):
    assert _TRANSITIONS[terminal] == frozenset()


@pytest.mark.parametrize("src", ["needs_expertise", "return_visit"])
def test_attempt_terminals_cannot_resume(src: str):
    with pytest.raises(InvalidTransition):
        transition_task(src, "queued")


@pytest.mark.parametrize("src", ["needs_expertise", "return_visit"])
def test_abandon_after_unresolved_attempt(src: str):
    """Spec auto-close: these block closure until a follow-up exists or the
    task is cancelled, so cancelled must be reachable."""
    transition_task(src, "cancelled")


@pytest.mark.parametrize("src", ["queued", "scheduled"])
def test_cancel_before_field_work(src: str):
    transition_task(src, "cancelled")


def test_unknown_status_forbidden():
    with pytest.raises(InvalidTransition):
        transition_task("bogus", "queued")
