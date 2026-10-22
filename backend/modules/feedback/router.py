"""FastAPI router for triage notes feedback."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.db import get_db_conn
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import service
from .schemas import FeedbackBody, FeedbackResponse

router = APIRouter(prefix="/requests", tags=["feedback"])

_COORD_DIR = require_role("coordinator", "director")


@router.post(
    "/{request_id}/feedback",
    operation_id="feedback_upsert",
    response_model=FeedbackResponse,
    status_code=200,
)
def feedback_upsert(
    request_id: int,
    body: FeedbackBody,
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> FeedbackResponse:
    return service.upsert_feedback(conn, request_id, user, body)


@router.get(
    "/{request_id}/feedback",
    operation_id="feedback_get",
    response_model=FeedbackResponse,
)
def feedback_get(
    request_id: int,
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> FeedbackResponse:
    return service.get_feedback(conn, request_id, user.employee_id)
