"""Dashboard / utilization orchestration."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from backend.core.config import settings
from backend.core.exceptions import ValidationFailed
from backend.core.utils import today_local
from backend.modules.weather import repository as weather_repo
from backend.modules.weather.location import SITE_CODES
from backend.modules.weather.source import fetch_forecast

from . import repository as repo
from .constants import UNTRIAGED_STATUSES
from .schemas import (
    DashboardResponse,
    LoadTodayRow,
    OutcomeMix,
    QueueCounts,
    StatusCount,
    TechnicianReview,
    TerritoryRow,
    UtilizationResponse,
    UtilizationRow,
    WeatherLine,
)


def get_dashboard(conn) -> DashboardResponse:
    today = today_local()
    return DashboardResponse(
        as_of_date=today,
        today_by_status=[StatusCount(**r) for r in repo.today_by_status(conn, today)],
        load_today=[LoadTodayRow(**r) for r in repo.load_today(conn, today)],
        by_territory=[TerritoryRow(**r) for r in repo.by_territory(conn, today)],
        queue_counts=QueueCounts(**repo.queue_counts(conn)),
        after_hours=None,
        weather=_weather_line(conn),
        satisfaction=None,
        untriaged_statuses=sorted(UNTRIAGED_STATUSES),
    )


def _weather_line(conn) -> WeatherLine | None:
    """Cached Québec snapshot when feature on; null on flag-off or source failure — never 500."""
    if not settings.WEATHER_ESCALATION_ENABLED:
        return None
    location = "quebec"
    try:
        snap = weather_repo.get_cached_snapshot(conn, location)
        if snap is None:
            reading = fetch_forecast(location)
            snap = weather_repo.insert_snapshot(
                conn, location=location, site_code=SITE_CODES[location], reading=reading,
            )
        return WeatherLine(
            location=location,
            current_temp_c=float(snap["current_temp_c"]) if snap.get("current_temp_c") is not None else None,
            min_forecast_temp_24h_c=(
                float(snap["min_forecast_temp_24h_c"])
                if snap.get("min_forecast_temp_24h_c") is not None else None
            ),
        )
    except Exception:
        return None


def get_utilization(conn, start: date, end: date) -> UtilizationResponse:
    if end < start:
        raise ValidationFailed("end_date must not be before start_date")
    if (end - start).days > 31:
        raise ValidationFailed("Date range must not exceed 31 days")
    reviews_by_emp: dict[int, list[TechnicianReview]] = defaultdict(list)
    for rv in repo.reviews_in_range(conn, start, end):
        reviews_by_emp[rv.pop("employee_id")].append(TechnicianReview(**rv))

    rows = []
    for r in repo.utilization_rows(conn, start, end):
        mix = r.pop("outcome_mix")
        reviews = reviews_by_emp.get(r["employee_id"], [])
        ratings = [rv.rating for rv in reviews if rv.rating is not None]
        rows.append(UtilizationRow(
            **r,
            outcome_mix=OutcomeMix(**mix),
            avg_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
            rating_count=len(ratings),
            reviews=reviews,
        ))
    return UtilizationResponse(
        start_date=start,
        end_date=end,
        capacity_enabled=False,
        capacity_hours_per_day=None,
        planned_footnote="estimation provisoire",
        rows=rows,
    )
