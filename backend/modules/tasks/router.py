"""FastAPI router for the tasks module."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from backend.core.db import get_db_conn
from backend.core.exceptions import ValidationFailed
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import service
from .schemas import (
    ArrivedBody, AssignTaskBody, CloseoutBody, CloseoutOut, CreateTaskBody, EnRouteBody,
    ScheduleTaskBody, TaskListResponse, TaskOut, TaskStatusValue,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

_ALL_ROLES = require_role("technician", "coordinator", "director", "contractor")
_COORD_DIR = require_role("coordinator", "director")
_TECH_CONTRACTOR = require_role("technician", "contractor")


class TaskListParams:
    """Query-parameter bundle for GET /tasks."""

    def __init__(
        self,
        start_date: Optional[date] = Query(default=None),
        end_date: Optional[date] = Query(default=None),
        status: list[TaskStatusValue] = Query(default=[]),
        assigned_employee_id: Optional[int] = Query(default=None),
    ) -> None:
        if (start_date is None) != (end_date is None):
            raise ValidationFailed("start_date and end_date must be provided together")
        if start_date is not None and end_date is not None:
            if end_date < start_date:
                raise ValidationFailed("end_date must not be before start_date")
            if (end_date - start_date).days > 31:
                raise ValidationFailed("Date range cannot exceed 31 days")
        self.start_date = start_date
        self.end_date = end_date
        self.status = status
        self.assigned_employee_id = assigned_employee_id


@router.get("", operation_id="task_list", response_model=TaskListResponse)
def task_list(
    params: Annotated[TaskListParams, Depends()],
    user: CurrentUser = _ALL_ROLES,
    conn=Depends(get_db_conn),
) -> TaskListResponse:
    return service.list_tasks(
        conn, user, start_date=params.start_date, end_date=params.end_date,
        statuses=params.status, assigned_employee_id=params.assigned_employee_id,
    )


@router.post("", operation_id="task_create", response_model=TaskOut)
def task_create(body: CreateTaskBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> TaskOut:
    return service.create_task(conn, body, user)


@router.post("/{task_id}/assign", operation_id="task_assign", response_model=TaskOut)
def task_assign(task_id: int, body: AssignTaskBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> TaskOut:
    return service.assign_task(conn, task_id, body, user)


@router.post("/{task_id}/schedule", operation_id="task_schedule", response_model=TaskOut)
def task_schedule(task_id: int, body: ScheduleTaskBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> TaskOut:
    return service.schedule_task(conn, task_id, body, user)


@router.post("/{task_id}/en-route", operation_id="task_en_route", response_model=TaskOut)
def task_en_route(task_id: int, body: EnRouteBody, user: CurrentUser = _TECH_CONTRACTOR, conn=Depends(get_db_conn)) -> TaskOut:
    return service.en_route(conn, task_id, body, user)


@router.post("/{task_id}/arrived", operation_id="task_arrived", response_model=TaskOut)
def task_arrived(task_id: int, body: ArrivedBody, user: CurrentUser = _TECH_CONTRACTOR, conn=Depends(get_db_conn)) -> TaskOut:
    return service.arrived(conn, task_id, body, user)


@router.post("/{task_id}/closeout", operation_id="task_closeout", response_model=CloseoutOut)
def task_closeout(task_id: int, body: CloseoutBody, user: CurrentUser = _TECH_CONTRACTOR, conn=Depends(get_db_conn)) -> CloseoutOut:
    return service.closeout(conn, task_id, body, user)
