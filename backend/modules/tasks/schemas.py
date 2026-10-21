"""Pydantic request/response schemas for the tasks module."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from backend.core.config import settings

TaskStatusValue = Literal[
    "queued", "scheduled", "en_route", "arrived", "working", "done",
    "needs_expertise", "return_visit", "cancelled",
]


def _localize(v: datetime | None) -> datetime | None:
    """Naive datetimes are read as the platform's local time (settings.TIMEZONE)."""
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=ZoneInfo(settings.TIMEZONE))
    return v


class JustificationBody(BaseModel):
    """Required on every dispatcher decision (same shape the call-level actions used)."""
    text: str = Field(..., min_length=10)
    input_method: Literal["voice", "typed"]


class TaskOut(BaseModel):
    task_id: int
    request_id: int
    description: str
    status: TaskStatusValue
    assigned_employee_id: Optional[int] = None
    vendor_id: Optional[int] = None
    subcontractor_name: Optional[str] = None
    due_at: Optional[datetime] = None
    urgency_tier: Optional[str] = None
    source: str
    accepted_at: Optional[datetime] = None
    parent_task_id: Optional[int] = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class TaskListItem(TaskOut):
    """GET /tasks row: the task plus list context from its call."""
    assigned_employee_name: Optional[str] = None
    request_title: Optional[str] = None
    request_status: Optional[str] = None
    request_asnu: Optional[str] = None
    request_urgency_tier: Optional[str] = None
    sector_id: Optional[int] = None
    territoire: Optional[str] = None
    building_address: Optional[str] = None
    unit_label: Optional[str] = None
    has_followup: bool = False


class TaskListResponse(BaseModel):
    total: int
    items: list[TaskListItem]


class CreateTaskBody(BaseModel):
    request_id: int
    description: str = Field(min_length=1, max_length=2000)
    due_at: Optional[datetime] = None
    assigned_employee_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    justification: JustificationBody

    @field_validator("description")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("description must not be blank")
        return v

    @field_validator("due_at")
    @classmethod
    def _local(cls, v: datetime | None) -> datetime | None:
        return _localize(v)


class AssignTaskBody(BaseModel):
    # None unassigns (scheduled → queued).
    assigned_employee_id: Optional[int] = None
    justification: JustificationBody


class ScheduleTaskBody(BaseModel):
    # Required key; explicit null clears the date.
    due_at: Optional[datetime]
    justification: JustificationBody

    @field_validator("due_at")
    @classmethod
    def _local(cls, v: datetime | None) -> datetime | None:
        return _localize(v)


class EnRouteBody(BaseModel):
    current_status: Optional[TaskStatusValue] = None  # stale check when sent
    # Location point only if the browser granted it — null otherwise.
    lat: Optional[float] = None
    lng: Optional[float] = None


class ArrivedBody(BaseModel):
    current_status: Optional[TaskStatusValue] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class CloseoutBody(BaseModel):
    outcome: Literal["complete", "partial_reschedule", "partial_expertise", "failed"]
    comment: str = Field(..., min_length=10)
    input_method: Literal["voice", "typed"] = "typed"
    attachment_ids: list[int] = Field(..., min_length=1)
    next_date: Optional[date] = None   # partial_reschedule only; default today + 14 days
    urgent: bool = False               # partial_expertise / failed only
    current_status: Optional[TaskStatusValue] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class CloseoutOut(TaskOut):
    follow_up_task: Optional[TaskOut] = None   # spawned by partial_reschedule
    request_status: str                        # the call, after the auto-close check
