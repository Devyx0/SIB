"""Public satisfaction survey schemas (reference §8)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SurveyPublic(BaseModel):
    token: str
    request_id: int
    building_address: Optional[str] = None
    technician_name: Optional[str] = None
    already_submitted: bool = False


class SurveySubmitBody(BaseModel):
    polite: bool
    satisfaction_rating: int = Field(ge=1, le=5)
    problem_solved: bool
    comments: Optional[str] = Field(default=None, max_length=2000)


class SurveySubmitResponse(BaseModel):
    ok: bool = True
