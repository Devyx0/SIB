"""FastAPI router for the weather-escalation feature."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.db import get_db_conn
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import service
from .schemas import WeatherEvaluation

router = APIRouter(prefix="/requests", tags=["weather"])

_COORD_DIR = require_role("coordinator", "director")


@router.post(
    "/{request_id}/weather-check",
    operation_id="request_weather_check",
    response_model=WeatherEvaluation,
)
def request_weather_check(
    request_id: int,
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> WeatherEvaluation:
    return service.check_weather(conn, request_id, user)
