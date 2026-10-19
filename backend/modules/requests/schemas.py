"""Pydantic request/response schemas for the requests module."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

SOURCE_CALENDAR_LABELS: dict[str, str] = {
    "main":   "Calendrier principal",
    "st_maj": "Butler/Majordome",
}

TIME_ESTIMATE_LABELS: dict[str, str] = {
    "UNDER_30_MIN":  "< 30 min",
    "MIN30_TO_1H":   "30 min – 1h",
    "H1_TO_2H":      "1h – 2h",
    "H2_TO_4H":      "2h – 4h",
    "HALF_DAY_PLUS": "Demi-journée+",
    "TBD_ON_SITE":   "Soumission requise",
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
    "estimated_cost":         "mr.estimated_cost",
    "next_follow_up_date":    "mr.next_follow_up_date",
    "next_steps":             "mr.next_steps",
}

SortKey = Literal[
    "start_date", "asnu", "urgency_tier", "raw_title",
    "territoire", "building_address", "assigned_employee_name",
    "subcontractor_name", "time_estimate_bucket", "status", "source_calendar",
    "last_followup_date", "estimated_cost", "next_follow_up_date", "next_steps",
]

StatusValue = Literal[
    "intake_received", "triage_pending", "triaged",
    "triage_clarify", "triage_proposal", "triage_failed",
    "en_route", "closed",
]


class JustificationBody(BaseModel):
    text: str = Field(..., min_length=10)
    input_method: Literal["voice", "typed"]


class AssignBody(BaseModel):
    employee_id: Optional[int] = None
    current_assigned_employee_id: Optional[int] = None
    current_start_date: Optional[date] = None
    current_urgency_tier: Optional[str] = None
    justification: JustificationBody


class RescheduleBody(BaseModel):
    start_date: date
    current_start_date: Optional[date] = None
    current_assigned_employee_id: Optional[int] = None
    current_urgency_tier: Optional[str] = None
    justification: JustificationBody


class SetUrgencyBody(BaseModel):
    urgency_tier: Optional[Literal["AJD", "ajd"]] = None
    current_urgency_tier: Optional[str] = None
    current_assigned_employee_id: Optional[int] = None
    current_start_date: Optional[date] = None
    justification: JustificationBody
    # Set when accepting a weather suggestion — recorded in the justification's
    # after_value for provenance. Does not change how urgency is written.
    weather_evaluation_id: Optional[int] = None


class SetFollowUpDateBody(BaseModel):
    next_follow_up_date: Optional[date] = None
    current_next_follow_up_date: Optional[date] = None


class SetNextStepsBody(BaseModel):
    next_steps: Optional[str] = None
    current_next_steps: Optional[str] = None


class SetCostBody(BaseModel):
    estimated_cost: Optional[Decimal] = Field(None, ge=0)
    current_estimated_cost: Optional[Decimal] = None


class AddLogBody(BaseModel):
    entry_text: str = Field(..., min_length=1)


class RouteBody(BaseModel):
    source_calendar: Literal["main", "st_maj"]
    expected_source_calendar: Optional[Literal["main", "st_maj"]]  # required; null = caller expected unrouted state


class JustificationEntry(BaseModel):
    id: int
    decision_type: str
    before_value: Optional[dict] = None
    after_value: Optional[dict] = None
    justification_text: str
    input_method: Optional[str] = None
    created_at: str
    employee_id: int


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
    estimated_cost: Optional[Decimal] = None
    next_follow_up_date: Optional[date] = None
    next_steps: Optional[str] = None
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
    justification_log: list[JustificationEntry] = Field(default_factory=list)
    # PII — null for tech/contractor unless they are the case-assigned employee
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_phone_placeholder: bool = False
    caller_email: Optional[str] = None
    caller_email_placeholder: bool = False
    caller_tenant_id: Optional[int] = None
    raw_caller_body: Optional[dict] = None
    problems: Optional[str] = None
    triage_model_version: Optional[str] = None
    # True when the tenant's problem text matches the focused "no heat" keyword
    # list — advisory hint next to the "Vérifier la météo" button.
    heating_keyword_hint: bool = False


class ListResponse(BaseModel):
    total: int
    items: list[ListRow]
    unscheduled_items: list[ListRow] = Field(default_factory=list)


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


class UnitLookup(BaseModel):
    unit_id: int
    numero_appartement: str
    rue: Optional[str] = None
