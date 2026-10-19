"""Sector → project → building → unit → tenant. Read-only, coordinator / director."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.core.db import get_db_conn
from backend.core.permissions import require_role

from . import service
from .schemas import BuildingDetail, ProjectDetail, SectorDetail, SectorSummary, UnitDetail

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


@router.get("/units/{unit_id}", operation_id="portfolio_get_unit", response_model=UnitDetail)
def portfolio_get_unit(unit_id: int, user=_COORD_DIR, conn=Depends(get_db_conn)) -> UnitDetail:
    return service.get_unit(conn, unit_id, user)
