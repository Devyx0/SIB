"""Coordinator alert API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.db import get_db_conn
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import service
from .schemas import AlertListResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])

_COORD_DIR = require_role("coordinator", "director")


@router.get("", operation_id="alerts_list", response_model=AlertListResponse)
def alerts_list(
    unread_only: bool = Query(default=False),
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> AlertListResponse:
    return service.list_for_coordinator(conn, unread_only=unread_only)


@router.post("/{alert_id}/read", operation_id="alerts_mark_read", status_code=204)
def alerts_mark_read(
    alert_id: int,
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> None:
    service.mark_read(conn, alert_id, user.employee_id)


@router.post("/read-all", operation_id="alerts_mark_all_read", status_code=204)
def alerts_mark_all_read(
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> None:
    service.mark_all_read(conn, user.employee_id)
