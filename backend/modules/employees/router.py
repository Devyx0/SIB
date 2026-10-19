"""FastAPI router for the employees module."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

router = APIRouter(prefix="/employees", tags=["employees"])


class MeResponse(BaseModel):
    employee_id: int
    nom_employe: str
    roles: list[str]
    weather_escalation_enabled: bool = False


@router.get("/me", response_model=MeResponse, operation_id="get_me")
def get_me(
    user: CurrentUser = Depends(get_current_user),
    conn=Depends(get_db_conn),
) -> MeResponse:
    row = conn.execute(
        "SELECT nom_employe FROM employee WHERE employee_id = %s",
        [user.employee_id],
    ).fetchone()
    return MeResponse(
        employee_id=user.employee_id,
        nom_employe=row["nom_employe"],
        roles=sorted(user.roles),
        weather_escalation_enabled=settings.WEATHER_ESCALATION_ENABLED,
    )
