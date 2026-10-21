"""Read models for the sector → project → building → unit → tenant browser."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class SectorSummary(BaseModel):
    sector_id: int
    territoire: Optional[str] = None
    color_code: Optional[str] = None
    project_count: int
    building_count: int
    unit_count: int = 0
    # Units with a current lease that has at least one tenant.
    occupied_unit_count: int = 0
    # Up to three project names, largest (most buildings) first.
    top_projects: list[str] = []


class ProjectSummary(BaseModel):
    project_id: int
    nom_unique_projet: Optional[str] = None
    adresse_quickbooks: Optional[str] = None
    accounting_project_number: Optional[str] = None
    building_count: int


class BuildingSummary(BaseModel):
    building_id: int
    project_id: int
    sector_id: int
    adresse: Optional[str] = None
    ville: Optional[str] = None
    code_postal: Optional[str] = None
    web_building_name: Optional[str] = None
    actif_inactif: Optional[str] = None
    unit_count: int


class UnitSummary(BaseModel):
    unit_id: int
    numero_appartement: Optional[str] = None
    unique_unit_number: Optional[str] = None
    rue: Optional[str] = None
    grandeur: Optional[str] = None
    # Every occupant on the current lease, lease holder first.
    tenant_names: list[str] = []
    occupant_count: int
    lease_statut: Optional[str] = None


class SectorDetail(BaseModel):
    sector_id: int
    territoire: Optional[str] = None
    color_code: Optional[str] = None
    project_count: int
    building_count: int
    projects: list[ProjectSummary]


class ProjectDetail(BaseModel):
    project_id: int
    nom_unique_projet: Optional[str] = None
    adresse_quickbooks: Optional[str] = None
    accounting_project_number: Optional[str] = None
    building_count: int
    buildings: list[BuildingSummary]


class BuildingDetail(BaseModel):
    building_id: int
    project_id: int
    sector_id: int
    adresse: Optional[str] = None
    ville: Optional[str] = None
    code_postal: Optional[str] = None
    web_building_name: Optional[str] = None
    actif_inactif: Optional[str] = None
    nb_logements: Optional[str] = None
    nb_etages: Optional[str] = None
    annee_construction: Optional[str] = None
    territoire: Optional[str] = None
    nom_unique_projet: Optional[str] = None
    unit_count: int
    units: list[UnitSummary]
    # What staff used to open Drive for, now kept and edited here.
    reference: "BuildingReference"
    fiche: list["FicheEntry"] = []
    paint_specs: list["PaintSpecOut"] = []
    documents: list["DocumentOut"] = []


class LeaseOut(BaseModel):
    lease_id: int
    debut_bail: Optional[date] = None
    fin_bail: Optional[date] = None
    statut: Optional[str] = None
    langue_bail: Optional[str] = None


class TenantOut(BaseModel):
    tenant_id: int
    nom_complet: Optional[str] = None
    telephone: Optional[str] = None
    telephone_international: Optional[str] = None
    courriel: Optional[str] = None
    capacite: Optional[str] = None
    # True when at least one turnover on the unit names this tenant.
    has_turnover: bool = False


class UnitDetail(BaseModel):
    unit_id: int
    building_id: int
    project_id: int
    sector_id: int
    numero_appartement: Optional[str] = None
    rue: Optional[str] = None
    grandeur: Optional[str] = None
    building_adresse: Optional[str] = None
    web_building_name: Optional[str] = None
    nom_unique_projet: Optional[str] = None
    territoire: Optional[str] = None
    unique_unit_number: Optional[str] = None
    lease: Optional[LeaseOut] = None
    tenants: list[TenantOut]
    # The building's paint: spec sheet rows plus fiche-technique paint notes.
    paint_specs: list["PaintSpecOut"] = []
    paint_notes: list["FicheEntry"] = []


class TurnoverSettlementOut(BaseModel):
    deposit_amount_owed: Optional[Decimal] = None
    deposit_received: Optional[bool] = None
    deposit_refund_status: Optional[str] = None
    amount_owed_by_tenant: Optional[Decimal] = None
    tal_dossier_open: Optional[bool] = None
    edl_received: Optional[bool] = None
    edl_satisfactory: Optional[bool] = None
    notes: Optional[str] = None


class TurnoverFurnitureOut(BaseModel):
    appliance_type: Optional[str] = None
    included_current: Optional[bool] = None
    included_new: Optional[bool] = None


class TurnoverOut(BaseModel):
    turnover_id: int
    # This tenant's side of the turnover; null on the unit's other turnovers.
    tenant_role: Optional[Literal["incoming", "outgoing"]] = None
    move_reason: Optional[str] = None
    outgoing_tenant_name: Optional[str] = None
    lease_end_date: Optional[date] = None
    move_out_confirmed_date: Optional[date] = None
    move_out_time: Optional[time] = None
    key_return_method: Optional[str] = None
    assignment_desired_date: Optional[date] = None
    outgoing_loyer: Optional[Decimal] = None
    outgoing_fin_bail: Optional[date] = None
    incoming_tenant_name: Optional[str] = None
    lease_start_date: Optional[date] = None
    move_in_confirmed_date: Optional[date] = None
    move_in_time: Optional[time] = None
    key_pickup_method: Optional[str] = None
    intercom_status: Optional[str] = None
    cleaning_status: Optional[str] = None
    parking_remote_status: Optional[str] = None
    parking_stall_current: Optional[str] = None
    parking_stall_new: Optional[str] = None
    internet_transfer_current: Optional[bool] = None
    internet_transfer_new: Optional[bool] = None
    furnished_status_current: Optional[str] = None
    furnished_status_new: Optional[str] = None
    room_count: Optional[str] = None
    mattress_size: Optional[str] = None
    pre_departure_inspection_notes: Optional[str] = None
    general_notes: Optional[str] = None
    settlement: Optional[TurnoverSettlementOut] = None
    furniture: list[TurnoverFurnitureOut] = []


class TenantTurnover(BaseModel):
    unit_id: int
    tenant: TenantOut
    # Turnovers where this tenant moved in or out.
    turnovers: list[TurnoverOut]
    # The unit's remaining turnovers, for context when the tenant has none.
    other_turnovers: list[TurnoverOut]


# ── Search ────────────────────────────────────────────────────────────────────

class SearchUnitHit(BaseModel):
    unit_id: int
    building_id: int
    numero_appartement: Optional[str] = None
    unique_unit_number: Optional[str] = None
    rue: Optional[str] = None
    grandeur: Optional[str] = None
    building_adresse: Optional[str] = None
    tenant_names: list[str] = []
    occupant_count: int = 0


class SearchBuildingHit(BaseModel):
    building_id: int
    project_id: int
    sector_id: int
    adresse: Optional[str] = None
    ville: Optional[str] = None
    web_building_name: Optional[str] = None
    nom_unique_projet: Optional[str] = None
    territoire: Optional[str] = None


class SearchProjectHit(BaseModel):
    project_id: int
    # A sector the project has a visible building in, for the link.
    sector_id: int
    nom_unique_projet: Optional[str] = None
    adresse_quickbooks: Optional[str] = None
    accounting_project_number: Optional[str] = None
    building_count: int


class SearchTenantHit(BaseModel):
    tenant_id: int
    nom_complet: Optional[str] = None
    unit_id: int
    numero_appartement: Optional[str] = None
    building_adresse: Optional[str] = None


class SearchFactHit(BaseModel):
    """A building reference fact: a fiche-technique entry or a paint spec."""
    building_id: int
    building_adresse: Optional[str] = None
    web_building_name: Optional[str] = None
    label: str
    value: str
    source: Literal["fiche", "paint_spec"]


class PortfolioSearchResult(BaseModel):
    q: str
    units: list[SearchUnitHit]
    buildings: list[SearchBuildingHit]
    projects: list[SearchProjectHit]
    tenants: list[SearchTenantHit]
    facts: list[SearchFactHit]


# ── Filtered unit list ────────────────────────────────────────────────────────

class UnitListRow(BaseModel):
    unit_id: int
    building_id: int
    project_id: int
    sector_id: int
    numero_appartement: Optional[str] = None
    unique_unit_number: Optional[str] = None
    rue: Optional[str] = None
    grandeur: Optional[str] = None
    building_adresse: Optional[str] = None
    nom_unique_projet: Optional[str] = None
    territoire: Optional[str] = None
    lease_statut: Optional[str] = None
    fin_bail: Optional[date] = None
    tenant_names: list[str] = []
    occupant_count: int


class UnitListPage(BaseModel):
    items: list[UnitListRow]
    total: int
    # Vacant units under the same filters, ignoring the occupancy filter.
    vacant_total: int
    grandeur_options: list[str]
    page: int
    page_size: int


# ── Building reference info (formerly in Drive) ───────────────────────────────

class BuildingReference(BaseModel):
    """Typed building characteristics (table fondamentale)."""
    chauffage: Optional[str] = None
    chauffage_details: Optional[str] = None
    chauffe_eau: Optional[str] = None
    systeme_incendie: Optional[str] = None
    boite_a_cle_ext: Optional[str] = None
    boite_a_cle_int: Optional[str] = None
    internet: Optional[str] = None
    furnished: Optional[str] = None
    building_structure: Optional[str] = None
    property_type: Optional[str] = None
    ascenseur: Optional[bool] = None
    nb_elevateurs: Optional[int] = None
    piscine: Optional[bool] = None
    sauna: Optional[bool] = None
    gym: Optional[bool] = None
    dogs_allowed: Optional[bool] = None


class FicheEntry(BaseModel):
    """One line of the building's fiche technique."""
    label: str
    value: str


class PaintSpecOut(BaseModel):
    paint_spec_id: int
    zone: Optional[str] = None
    surface_label: Optional[str] = None
    product_interior: Optional[str] = None
    product_exterior: Optional[str] = None
    manufacturer: Optional[str] = None


class DocumentOut(BaseModel):
    document_id: int
    title: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None


BuildingDetail.model_rebuild()
UnitDetail.model_rebuild()


# ── Edits ─────────────────────────────────────────────────────────────────────
#
# Every edit body carries `changes` (only the fields being changed) and
# `current` (what the editor saw for those fields). If the stored value no
# longer matches `current`, the edit is refused with STALE_DATA.

def _blank_to_none(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class _Fields(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)


class ProjectFields(_Fields):
    nom_unique_projet: Optional[str] = Field(None, max_length=200)
    adresse_quickbooks: Optional[str] = Field(None, max_length=300)
    accounting_project_number: Optional[str] = Field(None, max_length=50)


class BuildingFields(_Fields):
    adresse: Optional[str] = Field(None, max_length=300)
    ville: Optional[str] = Field(None, max_length=100)
    code_postal: Optional[str] = Field(None, max_length=20)
    web_building_name: Optional[str] = Field(None, max_length=200)
    actif_inactif: Optional[Literal["Actif", "Inactif"]] = None
    nb_logements: Optional[str] = Field(None, max_length=20)
    nb_etages: Optional[str] = Field(None, max_length=20)
    annee_construction: Optional[str] = Field(None, max_length=50)
    chauffage: Optional[str] = Field(None, max_length=200)
    chauffage_details: Optional[str] = Field(None, max_length=2000)
    chauffe_eau: Optional[str] = Field(None, max_length=200)
    systeme_incendie: Optional[str] = Field(None, max_length=200)
    boite_a_cle_ext: Optional[str] = Field(None, max_length=200)
    boite_a_cle_int: Optional[str] = Field(None, max_length=200)
    internet: Optional[str] = Field(None, max_length=200)
    furnished: Optional[str] = Field(None, max_length=100)
    building_structure: Optional[str] = Field(None, max_length=100)
    property_type: Optional[str] = Field(None, max_length=200)
    ascenseur: Optional[bool] = None
    nb_elevateurs: Optional[int] = Field(None, ge=0, le=100)
    piscine: Optional[bool] = None
    sauna: Optional[bool] = None
    gym: Optional[bool] = None
    dogs_allowed: Optional[bool] = None


class UnitFields(_Fields):
    numero_appartement: Optional[str] = Field(None, max_length=50)
    rue: Optional[str] = Field(None, max_length=300)
    grandeur: Optional[str] = Field(None, max_length=50)
    unique_unit_number: Optional[str] = Field(None, max_length=100)


class PaintSpecFields(_Fields):
    zone: Optional[str] = Field(None, max_length=200)
    surface_label: Optional[str] = Field(None, max_length=300)
    product_interior: Optional[str] = Field(None, max_length=300)
    product_exterior: Optional[str] = Field(None, max_length=300)
    manufacturer: Optional[str] = Field(None, max_length=200)


class ProjectPatch(BaseModel):
    changes: ProjectFields
    current: ProjectFields = ProjectFields()


class BuildingPatch(BaseModel):
    changes: BuildingFields
    current: BuildingFields = BuildingFields()


class UnitPatch(BaseModel):
    changes: UnitFields
    current: UnitFields = UnitFields()


class PaintSpecPatch(BaseModel):
    changes: PaintSpecFields
    current: PaintSpecFields = PaintSpecFields()


class BuildingCreate(BuildingFields):
    sector_id: int
    adresse: str = Field(..., min_length=1, max_length=300)


class BuildingCreateBody(BuildingCreate):
    project_id: int


class ProjectCreateBody(ProjectFields):
    nom_unique_projet: str = Field(..., min_length=1, max_length=200)
    # A project is reached through its buildings, so it starts with one.
    first_building: BuildingCreate


class UnitCreateBody(UnitFields):
    building_id: int
    numero_appartement: str = Field(..., min_length=1, max_length=50)


class FicheEntryBody(BaseModel):
    """Set (or, with value null, remove) one fiche-technique line."""
    label: str = Field(..., min_length=1, max_length=200)
    value: Optional[str] = Field(None, max_length=5000)
    # What the editor saw; null for a new line.
    current_value: Optional[str] = None

    @field_validator("label", "value", "current_value", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)


class DocumentCreateBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    url: str = Field(..., min_length=1, max_length=2000, pattern=r"^https?://")
    category: Optional[Literal[
        "elevator_contract", "fire_protection", "paint_spec", "install_guide",
        "plumbing_reference", "other",
    ]] = None


class CreatedOut(BaseModel):
    """Ids of what was created, for the link to it."""
    project_id: Optional[int] = None
    building_id: Optional[int] = None
    unit_id: Optional[int] = None
    sector_id: Optional[int] = None
    paint_spec_id: Optional[int] = None
    document_id: Optional[int] = None
