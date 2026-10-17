"""FastAPI router for the intake module."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.db import get_db_conn
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import service
from .schemas import ManualCreateBody, ManualCreateResponse

router = APIRouter(prefix="/intake", tags=["intake"])

_COORD_DIR = require_role("coordinator", "director")


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
