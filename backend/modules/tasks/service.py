"""Business logic for dispatch tasks. Enforces the task status machine.

The repository does not check transitions; every status change here goes
through `transition_task` first.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from backend.core.config import settings
from backend.core.exceptions import (
    ConflictError, InvalidTransition, NotFoundError, RequestClosedError, ValidationFailed,
)
from backend.core.security import CurrentUser
from backend.domain.status_machine import transition
from backend.domain.task_status_machine import transition_task
from backend.modules.requests import repository as request_repo

from . import repository as repo
from .schemas import (
    AssignTaskBody, CreateTaskBody, ScheduleTaskBody, TaskListResponse, TaskOut,
)

_COORD_DIR = frozenset({"coordinator", "director"})
# Only before dispatch may the coordinator move a task around; once the
# technician is en route the assignee/due date are his, and done/cancelled are final.
_EDITABLE = frozenset({"queued", "scheduled"})


def _derived_status(current: str, assignee: Any, due_at: Any) -> str:
    """queued ⇄ scheduled follows assignee + due_at; any other status is kept."""
    if current == "queued" and assignee is not None and due_at is not None:
        return "scheduled"
    if current == "scheduled" and (assignee is None or due_at is None):
        return "queued"
    return current


def _check_assignee(conn, employee_id: int | None) -> None:
    if employee_id is not None and not request_repo.is_valid_assignee(conn, employee_id):
        raise ValidationFailed("Employee must be an active technician or contractor")


def _get_editable(conn, task_id: int) -> dict:
    task = repo.lock_accepted_task(conn, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task["status"] not in _EDITABLE:
        raise ConflictError(
            f"Task is {task['status']} — assignee and due date can no longer be changed"
        )
    return task


def _apply(conn, task: dict, **fields: Any) -> TaskOut:
    """Write assignee/due_at, then move status (validated) if they imply a change."""
    merged = {
        "assigned_employee_id": task["assigned_employee_id"], "due_at": task["due_at"],
        **fields,
    }
    repo.update_task_fields(conn, task["task_id"], **fields)
    target = _derived_status(task["status"], merged["assigned_employee_id"], merged["due_at"])
    if target != task["status"]:
        transition_task(task["status"], target)
        repo.update_task_status(conn, task["task_id"], target)
    return TaskOut(**repo.get_task(conn, task["task_id"]))


def list_tasks(
    conn, user: CurrentUser, *, start_date: date | None, end_date: date | None,
    statuses: list[str], assigned_employee_id: int | None,
) -> TaskListResponse:
    if not user.roles & _COORD_DIR:
        assigned_employee_id = user.employee_id  # technicians/contractors: own tasks only
    rows = repo.list_accepted_tasks(
        conn, start_date=start_date, end_date=end_date, statuses=statuses,
        assigned_employee_id=assigned_employee_id, timezone=settings.TIMEZONE,
    )
    return TaskListResponse(total=len(rows), items=[TaskOut(**r) for r in rows])


def create_task(conn, body: CreateTaskBody, user: CurrentUser) -> TaskOut:
    req = request_repo.lock_request(conn, body.request_id)
    if req is None:
        raise NotFoundError(f"Request {body.request_id} not found")
    if req["status"] == "closed":
        raise RequestClosedError()
    if req["status"] == "triage_proposal":
        # Draft tasks are accepted explicitly; a dispatcher task must not skip that.
        raise InvalidTransition("Accept or reject the AI proposal before adding tasks")
    _check_assignee(conn, body.assigned_employee_id)

    if req["status"] != "open":  # triaged / legacy fieldwork states → container is now open
        transition(req["status"], "open")  # raises InvalidTransition before triage is done
        request_repo.update_field(conn, body.request_id, "status", "open")
        request_repo.write_provenance(
            conn, target_table="maintenance_request", target_pk=str(body.request_id),
            target_column="status", employee_id=user.employee_id,
            previous_value=req["status"], new_value="open",
        )

    status = _derived_status("queued", body.assigned_employee_id, body.due_at)
    if status != "queued":
        transition_task("queued", status)
    task = repo.insert_task(
        conn, request_id=body.request_id, description=body.description, status=status,
        assigned_employee_id=body.assigned_employee_id, due_at=body.due_at,
        source="dispatcher", accepted_at=datetime.now(timezone.utc),
    )
    return TaskOut(**task)


def assign_task(conn, task_id: int, body: AssignTaskBody, user: CurrentUser) -> TaskOut:
    task = _get_editable(conn, task_id)
    _check_assignee(conn, body.assigned_employee_id)
    return _apply(conn, task, assigned_employee_id=body.assigned_employee_id)


def schedule_task(conn, task_id: int, body: ScheduleTaskBody, user: CurrentUser) -> TaskOut:
    task = _get_editable(conn, task_id)
    return _apply(conn, task, due_at=body.due_at)


def list_for_request(conn, request_id: int, user: CurrentUser) -> list[TaskOut]:
    """Tasks shown on the call detail. Proposals (accepted_at IS NULL) are dispatcher-only."""
    rows = repo.list_tasks_for_request(conn, request_id)
    if not user.roles & _COORD_DIR:
        rows = [r for r in rows if r["accepted_at"] is not None]
    return [TaskOut(**r) for r in rows]
