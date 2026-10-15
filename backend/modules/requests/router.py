"""FastAPI router for the requests module."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query

from backend.core.db import get_db_conn
from backend.core.exceptions import ValidationFailed
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import repository as repo
from . import service
from .schemas import (
    BuildingLookup,
    EmployeeLookup,
    ListResponse,
    RequestDetail,
    SectorLookup,
    SortKey,
)

router = APIRouter(prefix="/requests", tags=["requests"])
lookup_router = APIRouter(prefix="/lookup", tags=["lookup"])

_ALL_ROLES = require_role("technician", "coordinator", "director", "contractor")
_COORD_DIR  = require_role("coordinator", "director")


class RequestListParams:
    """Query-parameter bundle for GET /requests. Validated via Depends()."""

    def __init__(
        self,
        start_date: date = Query(...),
        end_date: date = Query(...),
        status: list[str] = Query(default=[]),
        building_id: Optional[int] = Query(default=None),
        sector_id: Optional[int] = Query(default=None),
        assigned_employee_id: Optional[int] = Query(default=None),
        urgency: Optional[Literal["AJD", "ajd", "none"]] = Query(default=None),
        source_calendar: Optional[Literal["main", "st_maj"]] = Query(default=None),
        sort_by: SortKey = Query(default="start_date"),
        sort_dir: Literal["asc", "desc"] = Query(default="asc"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> None:
        if end_date < start_date:
            raise ValidationFailed("end_date must not be before start_date")
        if (end_date - start_date).days > 31:
            raise ValidationFailed("Date range cannot exceed 31 days")
        self.start_date = start_date
        self.end_date = end_date
        self.status = status
        self.building_id = building_id
        self.sector_id = sector_id
        self.assigned_employee_id = assigned_employee_id
        self.urgency = urgency
        self.source_calendar = source_calendar
        self.sort_by = sort_by
        self.sort_dir = sort_dir
        self.limit = limit
        self.offset = offset


@router.get(
    "",
    operation_id="request_list",
    response_model=ListResponse,
)
def request_list(
    params: Annotated[RequestListParams, Depends()],
    user: CurrentUser = _ALL_ROLES,
    conn=Depends(get_db_conn),
) -> ListResponse:
    return service.list_requests(conn, params, user)


@router.get(
    "/{request_id}",
    operation_id="request_get",
    response_model=RequestDetail,
)
def request_get(
    request_id: int,
    user: CurrentUser = _ALL_ROLES,
    conn=Depends(get_db_conn),
) -> RequestDetail:
    return service.get_request(conn, request_id, user)


@lookup_router.get(
    "/sectors",
    operation_id="lookup_sectors",
    response_model=list[SectorLookup],
)
def lookup_sectors(
    user: CurrentUser = _ALL_ROLES,
    conn=Depends(get_db_conn),
) -> list[SectorLookup]:
    return [SectorLookup(**r) for r in repo.list_sectors(conn)]


@lookup_router.get(
    "/buildings",
    operation_id="lookup_buildings",
    response_model=list[BuildingLookup],
)
def lookup_buildings(
    sector_id: Optional[int] = Query(default=None),
    user: CurrentUser = _ALL_ROLES,
    conn=Depends(get_db_conn),
) -> list[BuildingLookup]:
    return [BuildingLookup(**r) for r in repo.list_buildings(conn, sector_id)]


@lookup_router.get(
    "/employees",
    operation_id="lookup_employees",
    response_model=list[EmployeeLookup],
)
def lookup_employees(
    role: Optional[str] = Query(default=None),
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> list[EmployeeLookup]:
    return [EmployeeLookup(**r) for r in repo.list_employees(conn, role)]
