"""Portfolio browser: one detail payload per level, children included for the next drill."""
from __future__ import annotations

import re
import unicodedata

from backend.core.exceptions import NotFoundError
from backend.core.security import CurrentUser
from backend.core.utils import today_local
from backend.modules.intake.service import allowed_sector_ids

from . import edit_repository as edit_repo
from . import repository as repo
from .schemas import (
    BuildingDetail,
    BuildingReference,
    DocumentOut,
    FicheEntry,
    PaintSpecOut,
    BuildingSummary,
    LeaseOut,
    PortfolioSearchResult,
    ProjectDetail,
    ProjectSummary,
    SectorDetail,
    SearchBuildingHit,
    SearchFactHit,
    SearchProjectHit,
    SearchTenantHit,
    SearchUnitHit,
    SectorSummary,
    TenantListPage,
    TenantListRow,
    TenantOut,
    TenantTurnover,
    TurnoverFurnitureOut,
    TurnoverOut,
    TurnoverSettlementOut,
    UnitDetail,
    UnitListPage,
    UnitListRow,
    UnitSummary,
)


def _in_scope(allowed: frozenset[int] | None, sector_id: int | None) -> bool:
    if allowed is None:
        return True
    return sector_id is not None and int(sector_id) in allowed


def list_sectors(conn, user: CurrentUser) -> list[SectorSummary]:
    return [SectorSummary(**r) for r in repo.list_sectors(conn, allowed_sector_ids(conn, user), today_local())]


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
    ref = edit_repo.get_building_reference(conn, building_id) or {}
    return BuildingDetail(
        **row,
        units=units,
        reference=BuildingReference(**{k: v for k, v in ref.items() if k != "fiche"}),
        fiche=_fiche_entries(ref.get("fiche") or {}),
        paint_specs=[PaintSpecOut(**p) for p in edit_repo.list_paint_specs(conn, building_id)],
        documents=[DocumentOut(**d) for d in edit_repo.list_documents(conn, building_id)],
    )


def _fiche_entries(fiche: dict) -> list[FicheEntry]:
    """Fiche-technique lines in alphabetical order (accents ignored)."""
    entries = [FicheEntry(label=k, value=str(v)) for k, v in fiche.items() if v is not None]
    return sorted(entries, key=lambda e: _fold(e.label))


def _is_paint_label(label: str) -> bool:
    return "peinture" in _fold(label) or "paint" in _fold(label)


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
        today = today_local()
        rows = repo.list_tenants(conn, row["lease_id"], today)
        flagged = repo.tenants_with_turnover(conn, unit_id, [t["tenant_id"] for t in rows])
        tenants = [TenantOut(**t, has_turnover=t["tenant_id"] in flagged) for t in rows]
    payload = {k: row[k] for k in (
        "unit_id", "building_id", "project_id", "sector_id",
        "numero_appartement", "rue", "grandeur",
        "building_adresse", "web_building_name", "nom_unique_projet", "territoire",
        "unique_unit_number",
    )}
    ref = edit_repo.get_building_reference(conn, row["building_id"]) or {}
    return UnitDetail(
        **payload,
        lease=lease,
        tenants=tenants,
        paint_specs=[PaintSpecOut(**p) for p in edit_repo.list_paint_specs(conn, row["building_id"])],
        paint_notes=[e for e in _fiche_entries(ref.get("fiche") or {}) if _is_paint_label(e.label)],
    )


def get_tenant_turnover(conn, unit_id: int, tenant_id: int, user: CurrentUser) -> TenantTurnover:
    unit = repo.get_unit(conn, unit_id, today_local())
    if unit is None or not _in_scope(allowed_sector_ids(conn, user), unit["sector_id"]):
        raise NotFoundError("Unité introuvable")
    tenant = repo.get_unit_tenant(conn, unit_id, tenant_id)
    if tenant is None:
        raise NotFoundError("Locataire introuvable")

    rows = repo.list_unit_turnovers(conn, unit_id, tenant_id)
    ids = [r["turnover_id"] for r in rows]
    settlements = {s["turnover_id"]: s for s in repo.list_turnover_settlements(conn, ids)}
    furniture: dict[int, list[TurnoverFurnitureOut]] = {}
    for f in repo.list_turnover_furniture(conn, ids):
        furniture.setdefault(f["turnover_id"], []).append(TurnoverFurnitureOut(**f))

    def build(r: dict) -> TurnoverOut:
        s = settlements.get(r["turnover_id"])
        fields = {k: r[k] for k in TurnoverOut.model_fields if k in r and k not in ("settlement", "furniture")}
        for k in ("move_reason", "intercom_status"):
            fields[k] = None if r[k] is None else str(r[k])
        return TurnoverOut(
            **fields,
            settlement=TurnoverSettlementOut(**{k: v for k, v in s.items() if k != "turnover_id"}) if s else None,
            furniture=furniture.get(r["turnover_id"], []),
        )

    turnovers = [build(r) for r in rows]
    mine = [t for t in turnovers if t.tenant_role is not None]
    return TenantTurnover(
        unit_id=unit_id,
        tenant=TenantOut(**tenant, has_turnover=bool(mine)),
        turnovers=mine,
        other_turnovers=[t for t in turnovers if t.tenant_role is None],
    )


def _unit_summary(row: dict) -> UnitSummary:
    return UnitSummary(
        unit_id=row["unit_id"],
        numero_appartement=row["numero_appartement"],
        unique_unit_number=row["unique_unit_number"],
        rue=row["rue"],
        grandeur=row["grandeur"],
        tenant_names=row["tenant_names"],
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


# ── Search ────────────────────────────────────────────────────────────────────

# English words staff type for French fiche-technique labels (and a few French
# spellings that differ from the labels). Keys are unaccented and lower-case.
_SYNONYMS: dict[str, list[str]] = {
    "paint": ["peinture"],
    "painting": ["peinture"],
    "colour": ["peinture", "couleur"],
    "color": ["peinture", "couleur"],
    "heating": ["chauffage"],
    "heat": ["chauffage"],
    "heater": ["chauffe-eau", "chauffage"],
    "boiler": ["chaudiere", "chauffe-eau"],
    "key": ["cle"],
    "keys": ["cle"],
    "keybox": ["boite a cle"],
    "lockbox": ["boite a cle"],
    "fire": ["incendie"],
    "alarm": ["alarme"],
    "roof": ["toiture", "toit"],
    "window": ["fenetre"],
    "windows": ["fenetre"],
    "parking": ["stationnement"],
    "laundry": ["buanderie"],
    "elevator": ["ascenseur"],
    "plumbing": ["plomberie"],
    "water": ["eau"],
    "electrical": ["electricite"],
    "electricity": ["electricite"],
    "basement": ["sous-sol"],
    "snow": ["deneigement"],
    "storage": ["entrepot", "rangement"],
    "door": ["porte"],
    "garage": ["garage"],
    "generator": ["generatrice"],
    "siding": ["revetement"],
}

_MAX_TOKENS = 6


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def search_tokens(q: str | None) -> list[list[str]]:
    """Split a query into tokens, each with its synonyms (the word itself first)."""
    words = [w for w in re.split(r"[\s,;]+", (q or "").strip()) if w]
    tokens: list[list[str]] = []
    for w in words[:_MAX_TOKENS]:
        alts = [w.lower()]
        for syn in _SYNONYMS.get(_fold(w), []):
            if syn not in alts:
                alts.append(syn)
        tokens.append(alts)
    return tokens


def search(conn, q: str, user: CurrentUser, limit: int) -> PortfolioSearchResult:
    q = (q or "").strip()
    empty = PortfolioSearchResult(q=q, units=[], buildings=[], projects=[], tenants=[], facts=[])
    tokens = search_tokens(q)
    if len(q) < 2 or not tokens:
        return empty
    allowed = allowed_sector_ids(conn, user)
    if allowed is not None and not allowed:
        return empty
    today = today_local()
    return PortfolioSearchResult(
        q=q,
        units=[SearchUnitHit(**r) for r in repo.search_units(conn, tokens, allowed, today, limit)],
        buildings=[SearchBuildingHit(**r) for r in repo.search_buildings(conn, tokens, allowed, limit)],
        projects=[SearchProjectHit(**r) for r in repo.search_projects(conn, tokens, allowed, limit)],
        tenants=[SearchTenantHit(**r) for r in repo.search_tenants(conn, tokens, allowed, today, limit)],
        facts=[SearchFactHit(**r) for r in repo.search_facts(conn, tokens, allowed, limit)],
    )


def list_units_filtered(
    conn,
    user: CurrentUser,
    *,
    sector_id: int | None,
    project_id: int | None,
    building_id: int | None,
    occupancy: str | None,
    grandeur: str | None,
    lease_ending_within_days: int | None,
    q: str | None,
    page: int,
    page_size: int,
) -> UnitListPage:
    allowed = allowed_sector_ids(conn, user)
    if allowed is not None and (not allowed or (sector_id is not None and sector_id not in allowed)):
        return UnitListPage(items=[], total=0, vacant_total=0, grandeur_options=[], page=page, page_size=page_size)
    result = repo.list_units_filtered(
        conn,
        sector_ids=allowed,
        today=today_local(),
        sector_id=sector_id,
        project_id=project_id,
        building_id=building_id,
        occupancy=occupancy,
        grandeur=grandeur,
        lease_ending_within_days=lease_ending_within_days,
        tokens=search_tokens(q),
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return UnitListPage(
        items=[UnitListRow(**r) for r in result["items"]],
        total=result["total"],
        vacant_total=result["vacant_total"],
        grandeur_options=result["grandeur_options"],
        page=page,
        page_size=page_size,
    )


def list_tenants_filtered(
    conn,
    user: CurrentUser,
    *,
    sector_id: int | None,
    project_id: int | None,
    building_id: int | None,
    unit_id: int | None,
    capacite: str | None,
    lease_ending_within_days: int | None,
    q: str | None,
    page: int,
    page_size: int,
) -> TenantListPage:
    allowed = allowed_sector_ids(conn, user)
    if allowed is not None and (not allowed or (sector_id is not None and sector_id not in allowed)):
        return TenantListPage(items=[], total=0, page=page, page_size=page_size)
    result = repo.list_tenants_filtered(
        conn,
        sector_ids=allowed,
        today=today_local(),
        sector_id=sector_id,
        project_id=project_id,
        building_id=building_id,
        unit_id=unit_id,
        capacite=capacite,
        lease_ending_within_days=lease_ending_within_days,
        tokens=search_tokens(q),
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return TenantListPage(
        items=[TenantListRow(**r) for r in result["items"]],
        total=result["total"],
        page=page,
        page_size=page_size,
    )
