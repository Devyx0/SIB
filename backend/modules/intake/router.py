"""FastAPI router for the intake module."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.db import get_db_conn
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import service
from .schemas import ManualCreateBody, ManualCreateResponse, MatchRequest, MatchResponse

router = APIRouter(prefix="/intake", tags=["intake"])

_COORD_DIR = require_role("coordinator", "director")


@router.post(
    "/match",
    operation_id="intake_match_address",
    response_model=MatchResponse,
)
def intake_match_address(
    body: MatchRequest,
    user: CurrentUser = _COORD_DIR,
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
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> ManualCreateResponse:
    return service.create_manual(conn, body, user)
