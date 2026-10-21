"""FastAPI router for the requests module."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, Query

from backend.core.db import get_db_conn
from backend.core.exceptions import ValidationFailed
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

from . import repository as repo
from . import service
from .schemas import (
    AddLogBody,
    AssignBody,
    BuildingLookup,
    EmployeeLookup,
    CloseoutBody,
    ArrivedBody,
    EnRouteBody,
    ListResponse,
    PhotoUploadResponse,
    PhotoUrlResponse,
    RequestDetail,
    RescheduleBody,
    SaveDispatchBody,
    RouteBody,
    SectorLookup,
    SetCostBody,
    SetFollowUpDateBody,
    SetNextStepsBody,
    SetUrgencyBody,
    SortKey,
    StatusValue,
    TechnicianSuggestionsResponse,
    TriageTriggerBody,
    UnitByNumberLookup,
    UnitLookup,
    UnitNumberHit,
)

router = APIRouter(prefix="/requests", tags=["requests"])
lookup_router = APIRouter(prefix="/lookup", tags=["lookup"])

_ALL_ROLES = require_role("technician", "coordinator", "director", "contractor")
_COORD_DIR  = require_role("coordinator", "director")
_INTAKE = require_role("coordinator", "director", "receptionist")
# Lookups needed to fill the intake form (not request list/detail).
_INTAKE_LOOKUP = require_role(
    "technician", "coordinator", "director", "contractor", "receptionist",
)
_TECH_CONTRACTOR = require_role("technician", "contractor")


class RequestListParams:
    """Query-parameter bundle for GET /requests. Validated via Depends()."""

    def __init__(
        self,
        # Optional as a pair: omitting both lists any date (tech portal
        # "all my open calls"); providing only one is a validation error.
        start_date: Optional[date] = Query(default=None),
        end_date: Optional[date] = Query(default=None),
        status: list[StatusValue] = Query(default=[]),
        building_id: Optional[int] = Query(default=None),
        sector_id: Optional[int] = Query(default=None),
        assigned_employee_id: Optional[int] = Query(default=None),
        urgency: Optional[Literal["URGENT", "Intermédiaire", "Faible"]] = Query(default=None),
        source_calendar: Optional[Literal["main", "st_maj", "unrouted"]] = Query(default=None),
        q: Optional[str] = Query(default=None),
        has_subcontractor: Optional[bool] = Query(default=None),
        sort_by: SortKey = Query(default="start_date"),
        sort_dir: Literal["asc", "desc"] = Query(default="asc"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        redispatch: bool = Query(default=False),
    ) -> None:
        if (start_date is None) != (end_date is None):
            raise ValidationFailed("start_date and end_date must be provided together")
        if start_date is not None and end_date is not None:
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
        self.q = q
        self.has_subcontractor = has_subcontractor
        self.sort_by = sort_by
        self.sort_dir = sort_dir
        self.limit = limit
        self.offset = offset
        self.redispatch = redispatch


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
    user: CurrentUser = _INTAKE_LOOKUP,
    conn=Depends(get_db_conn),
) -> list[SectorLookup]:
    from backend.modules.intake.service import allowed_sector_ids
    allowed = allowed_sector_ids(conn, user)
    return [SectorLookup(**r) for r in repo.list_sectors(conn, allowed)]


@lookup_router.get(
    "/buildings",
    operation_id="lookup_buildings",
    response_model=list[BuildingLookup],
)
def lookup_buildings(
    sector_id: Optional[int] = Query(default=None),
    user: CurrentUser = _INTAKE_LOOKUP,
    conn=Depends(get_db_conn),
) -> list[BuildingLookup]:
    from backend.modules.intake.service import allowed_sector_ids
    from backend.core.exceptions import PermissionDenied
    allowed = allowed_sector_ids(conn, user)
    if allowed is not None:
        if sector_id is None:
            # Coordinators must pick a sector — avoid leaking all buildings.
            return []
        if int(sector_id) not in allowed:
            raise PermissionDenied("Secteur hors de votre portée")
    return [BuildingLookup(**r) for r in repo.list_buildings(conn, sector_id)]


def _run_triage_background(request_id: int, lang: str = "fr") -> None:
    import logging
    from backend.core.db import get_legacy_conn
    from backend.triage.service import triage
    log = logging.getLogger("backend.triage.bg")
    conn = get_legacy_conn()
    try:
        triage(conn, request_id, lang=lang)
    except Exception as exc:
        log.exception("Unhandled error in triage background for request %s", request_id)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE maintenance_request "
                    "SET status = 'triage_failed', triage_started_at = NULL, "
                    "    triage_summary = %s "
                    "WHERE request_id = %s AND status = 'triage_pending'",
                    (f"Erreur interne: {type(exc).__name__}: {exc}"[:500], request_id),
                )
            conn.commit()
        except Exception:
            log.exception("Failed to write triage_failed for request %s", request_id)
    finally:
        conn.close()


@router.post("/{request_id}/triage", operation_id="request_trigger_triage", status_code=202)
def request_trigger_triage(
    request_id: int,
    background_tasks: BackgroundTasks,
    body: TriageTriggerBody = TriageTriggerBody(),
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> dict:
    service.action_trigger_triage(conn, request_id)
    background_tasks.add_task(_run_triage_background, request_id, body.lang)
    return {"request_id": request_id, "status": "triage_pending"}


@router.get(
    "/{request_id}/technician-suggestions",
    operation_id="request_technician_suggestions",
    response_model=TechnicianSuggestionsResponse,
)
def request_technician_suggestions(
    request_id: int,
    lang: Literal["fr", "en"] = Query(default="fr"),
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> TechnicianSuggestionsResponse:
    return service.get_technician_suggestions(conn, request_id, lang=lang)


@router.post("/{request_id}/route", operation_id="request_route", response_model=RequestDetail)
def request_route(
    request_id: int,
    body: RouteBody,
    user: CurrentUser = _COORD_DIR,
    conn=Depends(get_db_conn),
) -> RequestDetail:
    return service.action_route(conn, request_id, body, user)


@router.post("/{request_id}/en-route", operation_id="request_en_route", response_model=RequestDetail)
def request_en_route(request_id: int, body: EnRouteBody, user: CurrentUser = _TECH_CONTRACTOR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_en_route(conn, request_id, body, user)


@router.post("/{request_id}/arrived", operation_id="request_arrived", response_model=RequestDetail)
def request_arrived(request_id: int, body: ArrivedBody, user: CurrentUser = _TECH_CONTRACTOR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_arrived(conn, request_id, body, user)


@router.post("/{request_id}/photos", operation_id="request_upload_photo",
             response_model=PhotoUploadResponse, status_code=201)
def request_upload_photo(
    request_id: int,
    photo: Annotated[bytes, Body(media_type="image/*")],
    content_type: Annotated[str, Header()] = "",
    user: CurrentUser = _TECH_CONTRACTOR,
    conn=Depends(get_db_conn),
) -> PhotoUploadResponse:
    # Raw image body (no multipart) — the mime travels in Content-Type.
    return service.action_upload_photo(conn, request_id, photo, content_type, user)


@router.post("/{request_id}/closeout", operation_id="request_closeout", response_model=RequestDetail)
def request_closeout(request_id: int, body: CloseoutBody, user: CurrentUser = _TECH_CONTRACTOR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_closeout(conn, request_id, body, user)


@router.get("/{request_id}/photos/{attachment_id}", operation_id="request_photo_url", response_model=PhotoUrlResponse)
def request_photo_url(request_id: int, attachment_id: int, user: CurrentUser = _ALL_ROLES, conn=Depends(get_db_conn)) -> PhotoUrlResponse:
    return service.get_photo_url(conn, request_id, attachment_id, user)


@router.post("/{request_id}/assign", operation_id="request_assign", response_model=RequestDetail)
def request_assign(request_id: int, body: AssignBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_assign(conn, request_id, body, user)


@router.post("/{request_id}/reschedule", operation_id="request_reschedule", response_model=RequestDetail)
def request_reschedule(request_id: int, body: RescheduleBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_reschedule(conn, request_id, body, user)


@router.post("/{request_id}/urgency", operation_id="request_set_urgency", response_model=RequestDetail)
def request_set_urgency(request_id: int, body: SetUrgencyBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_set_urgency(conn, request_id, body, user)


@router.post("/{request_id}/follow-up-date", operation_id="request_set_follow_up_date", response_model=RequestDetail)
def request_set_follow_up_date(request_id: int, body: SetFollowUpDateBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_set_follow_up_date(conn, request_id, body, user)


@router.post("/{request_id}/next-steps", operation_id="request_set_next_steps", response_model=RequestDetail)
def request_set_next_steps(request_id: int, body: SetNextStepsBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_set_next_steps(conn, request_id, body, user)


@router.post("/{request_id}/cost", operation_id="request_set_cost", response_model=RequestDetail)
def request_set_cost(request_id: int, body: SetCostBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_set_cost(conn, request_id, body, user)


@router.post("/{request_id}/dispatch", operation_id="request_save_dispatch", response_model=RequestDetail)
def request_save_dispatch(request_id: int, body: SaveDispatchBody, user: CurrentUser = _COORD_DIR, conn=Depends(get_db_conn)) -> RequestDetail:
    """One save for every dispatcher edit in the call details."""
    return service.action_save_dispatch(conn, request_id, body, user)


@router.post("/{request_id}/log", operation_id="request_add_log", response_model=RequestDetail)
def request_add_log(request_id: int, body: AddLogBody, user: CurrentUser = _ALL_ROLES, conn=Depends(get_db_conn)) -> RequestDetail:
    return service.action_add_log(conn, request_id, body, user)


@lookup_router.get(
    "/units",
    operation_id="lookup_units",
    response_model=list[UnitLookup],
)
def lookup_units(
    building_id: int = Query(...),
    user: CurrentUser = _INTAKE_LOOKUP,
    conn=Depends(get_db_conn),
) -> list[UnitLookup]:
    return [UnitLookup(**r) for r in repo.list_units(conn, building_id)]


@lookup_router.get(
    "/unit-numbers",
    operation_id="lookup_unit_numbers",
    response_model=list[UnitNumberHit],
)
def lookup_unit_numbers(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    user: CurrentUser = _INTAKE,
    conn=Depends(get_db_conn),
) -> list[UnitNumberHit]:
    return [UnitNumberHit(**r) for r in repo.search_unique_unit_numbers(conn, q, limit=limit)]


@lookup_router.get(
    "/unit-by-number",
    operation_id="lookup_unit_by_number",
    response_model=UnitByNumberLookup,
)
def lookup_unit_by_number(
    unique_unit_number: str = Query(..., min_length=1),
    user: CurrentUser = _INTAKE,
    conn=Depends(get_db_conn),
) -> UnitByNumberLookup:
    from backend.core.exceptions import NotFoundError
    from backend.core.utils import today_local

    row = repo.get_unit_context(conn, today_local(), unique_unit_number=unique_unit_number)
    if row is None:
        raise NotFoundError()
    return UnitByNumberLookup(**row)


@lookup_router.get(
    "/unit-context",
    operation_id="lookup_unit_context",
    response_model=UnitByNumberLookup,
)
def lookup_unit_context(
    unit_id: int = Query(...),
    user: CurrentUser = _INTAKE,
    conn=Depends(get_db_conn),
) -> UnitByNumberLookup:
    from backend.core.exceptions import NotFoundError
    from backend.core.utils import today_local

    row = repo.get_unit_context(conn, today_local(), unit_id=unit_id)
    if row is None:
        raise NotFoundError()
    return UnitByNumberLookup(**row)


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
