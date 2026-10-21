from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class StatusCount(BaseModel):
    status: str
    count: int


class LoadTodayRow(BaseModel):
    employee_id: int
    nom_employe: str
    assigned_count: int
    en_route_count: int
    minutes_worked: int


class TerritoryRow(BaseModel):
    sector_id: int
    territoire: str
    active: int
    AJD: int  # noqa: N815 — matches urgency_tier enum / UI column
    ajd: int
    untriaged: int
    board_link: str


class QueueCounts(BaseModel):
    a_router: int
    a_redispatcher: int
    a_router_link: str
    a_redispatcher_link: str


class WeatherLine(BaseModel):
    location: str
    current_temp_c: Optional[float] = None
    min_forecast_temp_24h_c: Optional[float] = None
    source_credit: str = "Source : Environnement et Changement climatique Canada"


class DashboardResponse(BaseModel):
    as_of_date: date
    today_by_status: list[StatusCount]
    load_today: list[LoadTodayRow]
    by_territory: list[TerritoryRow]
    queue_counts: QueueCounts
    # null = source absent / flag off / fetch failed → UI hides or shows N/A
    after_hours: None = None
    weather: Optional[WeatherLine] = None
    satisfaction: None = None
    untriaged_statuses: list[str]  # for column tooltip


class OutcomeMix(BaseModel):
    complete: int = 0
    partial_reschedule: int = 0
    partial_expertise: int = 0
    failed: int = 0


class TechnicianReview(BaseModel):
    """One submitted tenant satisfaction survey."""
    survey_id: int
    request_id: int
    submitted_at: datetime
    rating: Optional[int] = None  # 1–5; null for surveys submitted before star rating
    polite: Optional[bool] = None
    problem_solved: Optional[bool] = None
    comments: Optional[str] = None
    building_address: Optional[str] = None


class UtilizationRow(BaseModel):
    employee_id: int
    nom_employe: str
    territoire: Optional[str] = None
    calls_assigned: int
    calls_closed: int
    planned_minutes: int
    planned_unknown_count: int
    visit_minutes: int
    visits_count: int
    outcome_mix: OutcomeMix
    capacity_minutes: None = None
    utilization_pct: None = None
    # Tenant reviews submitted in the range (newest first)
    avg_rating: Optional[float] = None
    rating_count: int = 0
    reviews: list[TechnicianReview] = []


class UtilizationResponse(BaseModel):
    start_date: date
    end_date: date
    capacity_enabled: bool = False
    capacity_hours_per_day: None = None
    planned_footnote: str = "estimation provisoire"
    rows: list[UtilizationRow]
