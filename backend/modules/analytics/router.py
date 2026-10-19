"""Read-only analytics endpoints — coordinator / director only."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.core.db import get_db_conn
from backend.core.exceptions import ValidationFailed
from backend.core.permissions import require_role

from . import service
from .schemas import DashboardResponse, UtilizationResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])
_COORD_DIR = require_role("coordinator", "director")


@router.get("/dashboard", operation_id="get_dashboard", response_model=DashboardResponse)
def get_dashboard(user=_COORD_DIR, conn=Depends(get_db_conn)) -> DashboardResponse:
    return service.get_dashboard(conn)


@router.get("/utilization", operation_id="get_utilization", response_model=UtilizationResponse)
def get_utilization(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    user=_COORD_DIR,
    conn=Depends(get_db_conn),
) -> UtilizationResponse:
    if (start_date is None) != (end_date is None):
        raise ValidationFailed("start_date and end_date must be provided together")
    if start_date is None or end_date is None:
        raise ValidationFailed("start_date and end_date are required")
    return service.get_utilization(conn, start_date, end_date)
