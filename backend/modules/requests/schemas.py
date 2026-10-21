"""Pydantic request/response schemas for the requests module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.modules.tasks.schemas import JustificationBody, TaskOut
from backend.modules.weather.schemas import WeatherEvaluation

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
# urgency_tier ranks: URGENT > Intermédiaire > Faible > null.
SORT_SQL: dict[str, str] = {
    "start_date":             "mr.start_date",
    "asnu":                   "mr.asnu",
    "urgency_tier":           (
        "CASE mr.urgency_tier"
        " WHEN 'URGENT' THEN 1 WHEN 'Intermédiaire' THEN 2"
        " WHEN 'Faible' THEN 3 ELSE 4 END"
    ),
    "raw_title":              "mr.raw_title",
    "territoire":             "s.territoire",
    "building_address":       "b.adresse",
    "unique_unit_number":     "u.unique_unit_number",
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
    "territoire", "building_address", "unique_unit_number", "assigned_employee_name",
    "subcontractor_name", "time_estimate_bucket", "status", "source_calendar",
    "last_followup_date", "estimated_cost", "next_follow_up_date", "next_steps",
]

StatusValue = Literal[
    "intake_received", "triage_pending", "triaged", "scheduled",
    "awaiting_redispatch", "triage_clarify", "triage_proposal", "triage_failed",
    "en_route", "arrived", "open", "closed",
]


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


class VisitEntry(BaseModel):
    visit_id: int
    task_id: Optional[int] = None
    employee_id: int
    employee_name: Optional[str] = None
    en_route_at: datetime
    arrived_at: Optional[datetime] = None
    closeout_at: Optional[datetime] = None
    travel_minutes: Optional[int] = None
    on_site_minutes: Optional[int] = None
    duration_minutes: Optional[int] = None
    outcome: Optional[str] = None
    closeout_comment: Optional[str] = None
    photo_ids: list[int] = Field(default_factory=list)


class PhotoUploadResponse(BaseModel):
    attachment_id: int


class PhotoUrlResponse(BaseModel):
    url: str


class SetUrgencyBody(BaseModel):
    urgency_tier: Optional[Literal["URGENT", "Intermédiaire", "Faible"]] = None
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
    justification: JustificationBody


class SetNextStepsBody(BaseModel):
    next_steps: Optional[str] = None
    current_next_steps: Optional[str] = None
    justification: JustificationBody


class SetCostBody(BaseModel):
    estimated_cost: Optional[Decimal] = Field(None, ge=0)
    current_estimated_cost: Optional[Decimal] = None
    justification: JustificationBody


class DispatchSnapshot(BaseModel):
    """What the dispatcher saw before editing — the stale-data check."""
    assigned_employee_id: Optional[int] = None
    start_date: Optional[date] = None
    urgency_tier: Optional[str] = None
    next_follow_up_date: Optional[date] = None
    next_steps: Optional[str] = None
    estimated_cost: Optional[Decimal] = None


class DispatchChanges(BaseModel):
    """Only the fields present are changed (an explicit null clears it)."""
    assigned_employee_id: Optional[int] = None
    start_date: Optional[date] = None
    urgency_tier: Optional[Literal["URGENT", "Intermédiaire", "Faible"]] = None
    next_follow_up_date: Optional[date] = None
    next_steps: Optional[str] = None
    estimated_cost: Optional[Decimal] = Field(None, ge=0)


class SaveDispatchBody(BaseModel):
    """One « Enregistrer » in the call details: every changed field, one
    justification, applied together or not at all."""
    current: DispatchSnapshot
    changes: DispatchChanges
    justification: JustificationBody


class AddLogBody(BaseModel):
    entry_text: str = Field(..., min_length=1)


class TriageTriggerBody(BaseModel):
    """Optional UI language for AI-written text fields (title, problems, notes)."""
    lang: Literal["fr", "en"] = "fr"


class RouteBody(BaseModel):
    source_calendar: Literal["main", "st_maj"]
    expected_source_calendar: Optional[Literal["main", "st_maj"]]  # required; null = caller expected unrouted state
    justification: JustificationBody


class JustificationEntry(BaseModel):
    id: int
    decision_type: str
    # assigned_employee_id values come with an assigned_employee_name next to them.
    before_value: Optional[dict] = None
    after_value: Optional[dict] = None
    justification_text: str
    input_method: Optional[str] = None
    created_at: str
    employee_id: int
    # Who made the decision.
    employee_name: Optional[str] = None


class StatusChange(BaseModel):
    """A status transition made in the app (assignment, en route, arrival, closeout…)."""
    id: int
    status_from: Optional[str] = None
    status_to: Optional[str] = None
    changed_at: datetime
    employee_id: Optional[int] = None
    employee_name: Optional[str] = None


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
    building_full_address: Optional[str] = None
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
    unit_label: Optional[str] = None
    unique_unit_number: Optional[str] = None
    en_route_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    closeout_outcome: Optional[str] = None
    closeout_urgent: Optional[bool] = None
    duplicate_of_request_id: Optional[int] = None
    addition_to_request_id: Optional[int] = None


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
    # unit_label inherited from ListRow
    project_id: Optional[int] = None
    project_label: Optional[str] = None
    html_link: Optional[str] = None
    caller_type: Optional[str] = None
    followup_log: list[FollowupEntry] = Field(default_factory=list)
    justification_log: list[JustificationEntry] = Field(default_factory=list)
    # Coordinator / director only, like justification_log.
    status_history: list[StatusChange] = Field(default_factory=list)
    visits: list[VisitEntry] = Field(default_factory=list)
    tasks: list[TaskOut] = Field(default_factory=list)
    # Photos attached at intake (new call form).
    intake_photo_ids: list[int] = Field(default_factory=list)
    # PII — null for tech/contractor unless they are the case-assigned employee
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_phone_placeholder: bool = False
    caller_email: Optional[str] = None
    caller_email_placeholder: bool = False
    caller_tenant_id: Optional[int] = None
    raw_caller_body: Optional[dict] = None
    problems: Optional[str] = None
    category_raw: Optional[str] = None
    # 4-axis intake taxonomy — always visible to assigned tech/contractor.
    element: Optional[str] = None
    symptome: Optional[str] = None
    composante: Optional[str] = None
    emplacement: Optional[str] = None
    triage_model_version: Optional[str] = None
    # Fiche technique link — in the always-visible set for tech/contractor
    ft_link: Optional[str] = None
    ft_name: Optional[str] = None
    # Latest weather evaluation (triage-time or manual re-check) — read-only
    # display on the detail panel; null for tech/contractor.
    weather_evaluation: Optional[WeatherEvaluation] = None


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
    is_en_route: bool = False


class UnitLookup(BaseModel):
    unit_id: int
    numero_appartement: str
    rue: Optional[str] = None


class UnitNumberHit(BaseModel):
    unit_id: int
    unique_unit_number: str
    building_adresse: Optional[str] = None
    numero_appartement: Optional[str] = None


class LeaseTenantOut(BaseModel):
    tenant_id: int
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class UnitByNumberLookup(BaseModel):
    """Unit + current-lease tenants / pet flag (by unique number or unit_id)."""
    unit_id: int
    building_id: int
    sector_id: Optional[int] = None
    unique_unit_number: Optional[str] = None
    numero_appartement: Optional[str] = None
    rue: Optional[str] = None
    building_adresse: Optional[str] = None
    pets_allowed: bool = False
    tenants: list[LeaseTenantOut] = Field(default_factory=list)


class TechnicianSuggestion(BaseModel):
    employee_id: int
    initials: Optional[str] = None
    name: str
    why: str
    is_en_route: bool = False


class TechnicianSuggestionsResponse(BaseModel):
    request_id: int
    suggestions: list[TechnicianSuggestion]
