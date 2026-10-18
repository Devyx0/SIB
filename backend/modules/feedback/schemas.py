"""Pydantic schemas for the triage feedback module."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, model_validator

FeedbackLevel = Literal['utile', 'partiellement utile', 'pas utile']


class FeedbackBody(BaseModel):
    level: FeedbackLevel
    reason: Optional[str] = None

    @model_validator(mode='after')
    def _reason_required(self) -> 'FeedbackBody':
        if self.level in ('partiellement utile', 'pas utile'):
            if not self.reason or len(self.reason.strip()) < 10:
                raise ValueError(
                    "reason must be at least 10 characters for this feedback level"
                )
        return self


class EditHistoryEntry(BaseModel):
    edited_at: str
    edited_by: int
    old_level: str
    new_level: str
    old_reason: Optional[str] = None
    new_reason: Optional[str] = None
    old_triage_output: dict
    old_triage_model_version: str


class FeedbackResponse(BaseModel):
    feedback_id: int
    request_id: int
    employee_id: int
    level: str
    reason: Optional[str] = None
    triage_output: dict
    triage_model_version: str
    edit_history: list[EditHistoryEntry]
    created_at: str
    updated_at: str
