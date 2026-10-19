"""Portfolio browser: one detail payload per level, children included for the next drill."""
from __future__ import annotations

import re

from backend.core.exceptions import NotFoundError
from backend.core.security import CurrentUser
from backend.core.utils import today_local
from backend.modules.intake.service import allowed_sector_ids

from . import repository as repo
from .schemas import (
    BuildingDetail,
    BuildingSummary,
    LeaseOut,
    ProjectDetail,
    ProjectSummary,
    SectorDetail,
    SectorSummary,
    TenantOut,
    UnitDetail,
    UnitSummary,
)


def _in_scope(allowed: frozenset[int] | None, sector_id: int | None) -> bool:
    if allowed is None:
        return True
    return sector_id is not None and int(sector_id) in allowed


def list_sectors(conn, user: CurrentUser) -> list[SectorSummary]:
    return [SectorSummary(**r) for r in repo.list_sectors(conn, allowed_sector_ids(conn, user))]


def get_sector(conn, sector_id: int, user: CurrentUser) -> SectorDetail:
    allowed = allowed_sector_ids(conn, user)
    if not _in_scope(allowed, sector_id):
        raise NotFoundError("Secteur introuvable")
    row = repo.get_sector(conn, sector_id)
    if row is None:
        raise NotFoundError("Secteur introuvable")
    projects = [ProjectSummary(**p) for p in repo.list_projects(conn, sector_id)]
    return SectorDetail(**row, projects=projects)


def get_project(conn, project_id: int, user: CurrentUser, sector_id: int | None) -> ProjectDetail:
    allowed = allowed_sector_ids(conn, user)
    if sector_id is not None and not _in_scope(allowed, sector_id):
        raise NotFoundError("Projet introuvable")
    row = repo.get_project(conn, project_id)
    if row is None:
        raise NotFoundError("Projet introuvable")
    visible = repo.list_buildings(conn, project_id, allowed, sector_id=None)
    if not visible:
        raise NotFoundError("Projet introuvable")
    buildings = visible
    if sector_id is not None:
        buildings = [b for b in visible if int(b["sector_id"]) == int(sector_id)]
    summaries = [BuildingSummary(**b) for b in buildings]
    return ProjectDetail(**row, building_count=len(summaries), buildings=summaries)


def get_building(conn, building_id: int, user: CurrentUser) -> BuildingDetail:
    row = repo.get_building(conn, building_id)
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Bâtiment introuvable")
    units = [_unit_summary(u) for u in _sorted_units(repo.list_units(conn, building_id, today_local()))]
    return BuildingDetail(**row, units=units)


def get_unit(conn, unit_id: int, user: CurrentUser) -> UnitDetail:
    row = repo.get_unit(conn, unit_id, today_local())
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Unité introuvable")
    lease = None
    tenants: list[TenantOut] = []
    if row["lease_id"] is not None:
        lease = LeaseOut(
            lease_id=row["lease_id"],
            debut_bail=row["debut_bail"],
            fin_bail=row["fin_bail"],
            statut=row["statut"],
            langue_bail=row["langue_bail"],
        )
        tenants = [TenantOut(**t) for t in repo.list_tenants(conn, row["lease_id"])]
    payload = {k: row[k] for k in (
        "unit_id", "building_id", "project_id", "sector_id",
        "numero_appartement", "rue", "grandeur",
        "building_adresse", "web_building_name", "nom_unique_projet", "territoire",
    )}
    return UnitDetail(**payload, lease=lease, tenants=tenants)


def _unit_summary(row: dict) -> UnitSummary:
    return UnitSummary(
        unit_id=row["unit_id"],
        numero_appartement=row["numero_appartement"],
        rue=row["rue"],
        grandeur=row["grandeur"],
        tenant_name=row["tenant_name"],
        occupant_count=row["occupant_count"],
        lease_statut=row["lease_statut"],
    )


def _sorted_units(rows: list[dict]) -> list[dict]:
    def key(u: dict) -> tuple:
        try:
            civic = int(str(u["rue"]).split(",")[0].strip()) if u["rue"] else 10 ** 9
        except ValueError:
            civic = 10 ** 9
        digits = re.sub(r"\D", "", u["numero_appartement"] or "")
        apt = int(digits) if digits else 10 ** 9
        return (civic, apt, u["numero_appartement"] or "", u["unit_id"])

    return sorted(rows, key=key)
