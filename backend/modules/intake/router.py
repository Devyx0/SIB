"""FastAPI router for the intake module."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from backend.core.db import get_db_conn
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import service
from .schemas import ManualCreateBody, ManualCreateResponse, MatchRequest, MatchResponse

router = APIRouter(prefix="/intake", tags=["intake"])

_INTAKE = require_role("coordinator", "director", "receptionist")


@router.post(
    "/match",
    operation_id="intake_match_address",
    response_model=MatchResponse,
)
def intake_match_address(
    body: MatchRequest,
    user: CurrentUser = _INTAKE,
    conn=Depends(get_db_conn),
) -> MatchResponse:
    """Match an address against buildings/units without writing anything."""
    return service.match_only(conn, body)


@router.post(
    "",
    operation_id="intake_manual_create",
    response_model=ManualCreateResponse,
    status_code=201,
)
def intake_manual_create(
    body: ManualCreateBody,
    background_tasks: BackgroundTasks,
    user: CurrentUser = _INTAKE,
    conn=Depends(get_db_conn),
) -> ManualCreateResponse:
    result = service.create_manual(conn, body, user)
    # Auto-triage: same path as POST /requests/{id}/triage
    from backend.modules.requests import service as req_service
    from backend.modules.requests.router import _run_triage_background
    req_service.action_trigger_triage(conn, result.request_id)
    background_tasks.add_task(_run_triage_background, result.request_id, body.ui_lang)
    return result
