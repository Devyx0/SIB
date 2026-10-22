"""Sector → project → building → unit → tenant, plus create / edit. Coordinator / director."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response

from backend.core.db import get_db_conn
from backend.core.permissions import require_role

from . import edit_service, service
from .schemas import (
    AddOccupantBody,
    BuildingCreateBody,
    BuildingDetail,
    BuildingPatch,
    CreatedOut,
    DocumentCreateBody,
    EndLeaseBody,
    EndOccupantBody,
    FicheEntryBody,
    PaintSpecFields,
    PaintSpecPatch,
    ProjectCreateBody,
    ProjectPatch,
    StartLeaseBody,
    TakeoverBody,
    TenantPatch,
    TenancyPatch,
    UnitCreateBody,
    UnitPatch,
    PortfolioSearchResult,
    ProjectDetail,
    SectorDetail,
    SectorSummary,
    TenantListPage,
    TenantTurnover,
    UnitDetail,
    UnitListPage,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
_COORD_DIR = require_role("coordinator", "director")


@router.get("/sectors", operation_id="portfolio_list_sectors", response_model=list[SectorSummary])
def portfolio_list_sectors(user=_COORD_DIR, conn=Depends(get_db_conn)) -> list[SectorSummary]:
    return service.list_sectors(conn, user)


@router.get("/sectors/{sector_id}", operation_id="portfolio_get_sector", response_model=SectorDetail)
def portfolio_get_sector(sector_id: int, user=_COORD_DIR, conn=Depends(get_db_conn)) -> SectorDetail:
    return service.get_sector(conn, sector_id, user)


@router.get("/projects/{project_id}", operation_id="portfolio_get_project", response_model=ProjectDetail)
def portfolio_get_project(
    project_id: int,
    sector_id: Optional[int] = Query(default=None),
    user=_COORD_DIR,
    conn=Depends(get_db_conn),
) -> ProjectDetail:
    return service.get_project(conn, project_id, user, sector_id)


@router.get("/buildings/{building_id}", operation_id="portfolio_get_building", response_model=BuildingDetail)
def portfolio_get_building(building_id: int, user=_COORD_DIR, conn=Depends(get_db_conn)) -> BuildingDetail:
    return service.get_building(conn, building_id, user)


@router.get("/search", operation_id="portfolio_search", response_model=PortfolioSearchResult)
def portfolio_search(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=8, ge=1, le=25),
    user=_COORD_DIR,
    conn=Depends(get_db_conn),
) -> PortfolioSearchResult:
    return service.search(conn, q, user, limit)


# Declared before /units/{unit_id} so "units" with no id is the list.
@router.get("/units", operation_id="portfolio_list_units", response_model=UnitListPage)
def portfolio_list_units(
    sector_id: Optional[int] = Query(default=None),
    project_id: Optional[int] = Query(default=None),
    building_id: Optional[int] = Query(default=None),
    occupancy: Optional[Literal["vacant", "occupied"]] = Query(default=None),
    grandeur: Optional[str] = Query(default=None, max_length=50),
    lease_ending_within_days: Optional[int] = Query(default=None, ge=1, le=730),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user=_COORD_DIR,
    conn=Depends(get_db_conn),
) -> UnitListPage:
    return service.list_units_filtered(
        conn, user,
        sector_id=sector_id, project_id=project_id, building_id=building_id,
        occupancy=occupancy, grandeur=grandeur, lease_ending_within_days=lease_ending_within_days,
        q=q, page=page, page_size=page_size,
    )


@router.get("/tenants", operation_id="portfolio_list_tenants", response_model=TenantListPage)
def portfolio_list_tenants(
    sector_id: Optional[int] = Query(default=None),
    project_id: Optional[int] = Query(default=None),
    building_id: Optional[int] = Query(default=None),
    unit_id: Optional[int] = Query(default=None),
    capacite: Optional[Literal["named_on_lease", "added_occupant", "took_over"]] = Query(default=None),
    lease_ending_within_days: Optional[int] = Query(default=None, ge=1, le=730),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user=_COORD_DIR,
    conn=Depends(get_db_conn),
) -> TenantListPage:
    return service.list_tenants_filtered(
        conn, user,
        sector_id=sector_id, project_id=project_id, building_id=building_id,
        unit_id=unit_id, capacite=capacite,
        lease_ending_within_days=lease_ending_within_days,
        q=q, page=page, page_size=page_size,
    )


@router.get("/units/{unit_id}", operation_id="portfolio_get_unit", response_model=UnitDetail)
def portfolio_get_unit(unit_id: int, user=_COORD_DIR, conn=Depends(get_db_conn)) -> UnitDetail:
    return service.get_unit(conn, unit_id, user)


@router.get(
    "/units/{unit_id}/tenants/{tenant_id}/turnover",
    operation_id="portfolio_get_tenant_turnover",
    response_model=TenantTurnover,
)
def portfolio_get_tenant_turnover(
    unit_id: int, tenant_id: int, user=_COORD_DIR, conn=Depends(get_db_conn),
) -> TenantTurnover:
    return service.get_tenant_turnover(conn, unit_id, tenant_id, user)


# ── Create / edit ─────────────────────────────────────────────────────────────

_NO_CONTENT = {"status_code": 204, "response_class": Response}


@router.post("/projects", operation_id="portfolio_create_project", response_model=CreatedOut, status_code=201)
def portfolio_create_project(body: ProjectCreateBody, user=_COORD_DIR, conn=Depends(get_db_conn)) -> CreatedOut:
    return edit_service.create_project(conn, body, user)


@router.patch("/projects/{project_id}", operation_id="portfolio_update_project", **_NO_CONTENT)
def portfolio_update_project(project_id: int, body: ProjectPatch, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.patch_project(conn, project_id, body, user)


@router.post("/buildings", operation_id="portfolio_create_building", response_model=CreatedOut, status_code=201)
def portfolio_create_building(body: BuildingCreateBody, user=_COORD_DIR, conn=Depends(get_db_conn)) -> CreatedOut:
    return edit_service.create_building(conn, body, user)


@router.patch("/buildings/{building_id}", operation_id="portfolio_update_building", **_NO_CONTENT)
def portfolio_update_building(building_id: int, body: BuildingPatch, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.patch_building(conn, building_id, body, user)


@router.put("/buildings/{building_id}/fiche", operation_id="portfolio_set_fiche_entry", **_NO_CONTENT)
def portfolio_set_fiche_entry(building_id: int, body: FicheEntryBody, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.set_fiche_entry(conn, building_id, body, user)


@router.post("/buildings/{building_id}/paint-specs", operation_id="portfolio_create_paint_spec",
             response_model=CreatedOut, status_code=201)
def portfolio_create_paint_spec(
    building_id: int, body: PaintSpecFields, user=_COORD_DIR, conn=Depends(get_db_conn),
) -> CreatedOut:
    return edit_service.create_paint_spec(conn, building_id, body, user)


@router.patch("/paint-specs/{paint_spec_id}", operation_id="portfolio_update_paint_spec", **_NO_CONTENT)
def portfolio_update_paint_spec(paint_spec_id: int, body: PaintSpecPatch, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.patch_paint_spec(conn, paint_spec_id, body, user)


@router.delete("/paint-specs/{paint_spec_id}", operation_id="portfolio_delete_paint_spec", **_NO_CONTENT)
def portfolio_delete_paint_spec(paint_spec_id: int, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.delete_paint_spec(conn, paint_spec_id, user)


@router.post("/buildings/{building_id}/documents", operation_id="portfolio_create_document",
             response_model=CreatedOut, status_code=201)
def portfolio_create_document(
    building_id: int, body: DocumentCreateBody, user=_COORD_DIR, conn=Depends(get_db_conn),
) -> CreatedOut:
    return edit_service.create_document(conn, building_id, body, user)


@router.delete("/documents/{document_id}", operation_id="portfolio_delete_document", **_NO_CONTENT)
def portfolio_delete_document(document_id: int, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.delete_document(conn, document_id, user)


@router.post("/units", operation_id="portfolio_create_unit", response_model=CreatedOut, status_code=201)
def portfolio_create_unit(body: UnitCreateBody, user=_COORD_DIR, conn=Depends(get_db_conn)) -> CreatedOut:
    return edit_service.create_unit(conn, body, user)


@router.patch("/units/{unit_id}", operation_id="portfolio_update_unit", **_NO_CONTENT)
def portfolio_update_unit(unit_id: int, body: UnitPatch, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.patch_unit(conn, unit_id, body, user)


@router.patch("/tenants/{tenant_id}", operation_id="portfolio_update_tenant", **_NO_CONTENT)
def portfolio_update_tenant(tenant_id: int, body: TenantPatch, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.patch_tenant(conn, tenant_id, body, user)


@router.patch("/tenancies/{tenancy_id}", operation_id="portfolio_update_tenancy", **_NO_CONTENT)
def portfolio_update_tenancy(tenancy_id: int, body: TenancyPatch, user=_COORD_DIR, conn=Depends(get_db_conn)):
    edit_service.patch_tenancy(conn, tenancy_id, body, user)


@router.post(
    "/units/{unit_id}/occupants",
    operation_id="portfolio_add_occupant",
    response_model=CreatedOut,
    status_code=201,
)
def portfolio_add_occupant(
    unit_id: int, body: AddOccupantBody, user=_COORD_DIR, conn=Depends(get_db_conn),
) -> CreatedOut:
    return edit_service.add_occupant(conn, unit_id, body, user)


@router.post(
    "/units/{unit_id}/occupants/takeover",
    operation_id="portfolio_takeover_occupant",
    response_model=CreatedOut,
    status_code=201,
)
def portfolio_takeover_occupant(
    unit_id: int, body: TakeoverBody, user=_COORD_DIR, conn=Depends(get_db_conn),
) -> CreatedOut:
    return edit_service.takeover_occupant(conn, unit_id, body, user)


@router.post(
    "/units/{unit_id}/occupants/{tenancy_id}/end",
    operation_id="portfolio_end_occupant",
    **_NO_CONTENT,
)
def portfolio_end_occupant(
    unit_id: int, tenancy_id: int, body: EndOccupantBody, user=_COORD_DIR, conn=Depends(get_db_conn),
):
    edit_service.end_occupant(conn, unit_id, tenancy_id, body, user)


@router.post(
    "/units/{unit_id}/leases/end",
    operation_id="portfolio_end_lease",
    **_NO_CONTENT,
)
def portfolio_end_lease(
    unit_id: int, body: EndLeaseBody, user=_COORD_DIR, conn=Depends(get_db_conn),
):
    edit_service.end_lease(conn, unit_id, body, user)


@router.post(
    "/units/{unit_id}/leases",
    operation_id="portfolio_start_lease",
    response_model=CreatedOut,
    status_code=201,
)
def portfolio_start_lease(
    unit_id: int, body: StartLeaseBody, user=_COORD_DIR, conn=Depends(get_db_conn),
) -> CreatedOut:
    return edit_service.start_lease(conn, unit_id, body, user)
