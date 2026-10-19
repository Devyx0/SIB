"""Read models for the sector → project → building → unit → tenant browser."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel


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
    rue: Optional[str] = None
    grandeur: Optional[str] = None
    tenant_name: Optional[str] = None
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
    lease: Optional[LeaseOut] = None
    tenants: list[TenantOut]


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
