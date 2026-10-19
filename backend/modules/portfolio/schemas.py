"""Read models for the sector → project → building → unit → tenant browser."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class SectorSummary(BaseModel):
    sector_id: int
    territoire: Optional[str] = None
    color_code: Optional[str] = None
    project_count: int
    building_count: int


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
