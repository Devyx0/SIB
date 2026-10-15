"""Pydantic request/response schemas for the requests module."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

SOURCE_CALENDAR_LABELS: dict[str, str] = {
    "main":   "Main calendar",
    "st_maj": "Butler/Majordome",
}

# Whitelisted sort-key → SQL expression (injected structurally, never as a value).
# urgency_tier ranks: AJD (most urgent) > ajd > none.
SORT_SQL: dict[str, str] = {
    "start_date":             "mr.start_date",
    "asnu":                   "mr.asnu",
    "urgency_tier":           (
        "CASE mr.urgency_tier::text"
        " WHEN 'AJD' THEN 1 WHEN 'ajd' THEN 2 WHEN 'none' THEN 3 ELSE 4 END"
    ),
    "raw_title":              "mr.raw_title",
    "territoire":             "s.territoire",
    "building_address":       "b.adresse",
    "assigned_employee_name": "e.nom_employe",
    "subcontractor_name":     "mr.subcontractor_name",
    "time_estimate_bucket":   "mr.time_estimate_bucket",
    "status":                 "mr.status",
    "source_calendar":        "mr.source_calendar",
    "last_followup_date":     "lf.entry_date",
}

SortKey = Literal[
    "start_date", "asnu", "urgency_tier", "raw_title",
    "territoire", "building_address", "assigned_employee_name",
    "subcontractor_name", "time_estimate_bucket", "status", "source_calendar",
    "last_followup_date",
]

StatusValue = Literal[
    "intake_received", "triage_pending", "triaged",
    "triage_clarify", "triage_proposal", "triage_failed",
    "en_route", "closed",
]


class FollowupEntry(BaseModel):
    followup_id: int
    entry_date: Optional[date] = None
    entered_by_initials: Optional[str] = None
    entry_text: Optional[str] = None


class ListRow(BaseModel):
    request_id: int
    start_date: Optional[date] = None
    asnu: Optional[str] = None
    urgency_tier: Optional[str] = None
    urgency_raw: Optional[str] = None
    raw_title: Optional[str] = None
    building_id: Optional[int] = None
    building_address: Optional[str] = None
    building_name: Optional[str] = None
    sector_id: Optional[int] = None
    territoire: Optional[str] = None
    color_code: Optional[str] = None
    assigned_employee_id: Optional[int] = None
    assigned_employee_name: Optional[str] = None
    subcontractor_name: Optional[str] = None
    time_estimate_bucket: Optional[str] = None
    time_estimate_raw: Optional[str] = None
    source_calendar: Optional[str] = None
    source_calendar_label: Optional[str] = None
    status: str
    event_id: Optional[str] = None
    estimated_cost: None = None  # pending migration 0002
    last_followup_date: Optional[date] = None
    last_followup_text: Optional[str] = None


class RequestDetail(ListRow):
    problem_summary: Optional[str] = None
    triage_summary: Optional[str] = None
    work_performed: Optional[str] = None
    other_notes: Optional[str] = None
    delegable_notes: Optional[str] = None
    report_notes: Optional[str] = None
    tenant_agreement_notes: Optional[str] = None
    entry_permission: Optional[str] = None
    animals: Optional[str] = None
    occupants_raw: Optional[str] = None
    follow_up_expected: Optional[bool] = None
    unit_id: Optional[int] = None
    unit_label: Optional[str] = None
    project_id: Optional[int] = None
    project_label: Optional[str] = None
    html_link: Optional[str] = None
    caller_type: Optional[str] = None
    followup_log: list[FollowupEntry] = Field(default_factory=list)
    # PII — null for tech/contractor unless they are the case-assigned employee
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_email: Optional[str] = None
    caller_tenant_id: Optional[int] = None
    # Pending migration 0002
    next_follow_up_date: None = None
    next_steps: None = None


class ListResponse(BaseModel):
    total: int
    items: list[ListRow]


class SectorLookup(BaseModel):
    sector_id: int
    territoire: str
    color_code: Optional[str] = None


class BuildingLookup(BaseModel):
    building_id: int
    adresse: Optional[str] = None
    web_building_name: Optional[str] = None
    sector_id: Optional[int] = None


class EmployeeLookup(BaseModel):
    employee_id: int
    nom_employe: str
    role: str
