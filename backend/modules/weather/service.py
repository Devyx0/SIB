"""Weather-escalation business logic.

fetch_forecast is imported here so tests can monkeypatch service.fetch_forecast
(no network). Nothing writes urgency — accepting a suggestion runs through the
existing POST /requests/{id}/urgency action.
"""
from __future__ import annotations

from typing import Any, Optional
from zoneinfo import ZoneInfo

from backend.core.config import settings
from backend.core.exceptions import NotFoundError
from backend.core.security import CurrentUser

from . import repository as repo
from .location import SITE_CODES, resolve_location
from .schemas import WeatherEvaluation
from .source import fetch_forecast  # monkeypatched in tests

_RANK = {None: 0, "none": 0, "ajd": 1, "AJD": 2}


def list_bands(conn) -> list[dict]:
    return repo.list_bands(conn)


def pick_band(bands: list[dict], temp: Any) -> Optional[dict]:
    """Inclusive lower bound, exclusive upper bound. NULL = unbounded."""
    if temp is None:
        return None
    for b in bands:
        lo, hi = b["temp_min_c"], b["temp_max_c"]
        if (lo is None or temp >= lo) and (hi is None or temp < hi):
            return b
    return None


def suggestion_direction(current: Optional[str], suggested: Optional[str]) -> str:
    c, s = _RANK.get(current, 0), _RANK.get(suggested, 0)
    return "higher" if s > c else "lower" if s < c else "equal"


def _f(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def _local_hhmm(dt: Any) -> Optional[str]:
    """Format a tz-aware timestamp as HH:MM in the app timezone (same source as today_local)."""
    if dt is None:
        return None
    return dt.astimezone(ZoneInfo(settings.TIMEZONE)).strftime("%H:%M")


def check_weather(conn, request_id: int, user: CurrentUser) -> WeatherEvaluation:
    if not settings.WEATHER_ESCALATION_ENABLED:
        raise NotFoundError("Weather escalation is disabled")

    req = repo.get_request_location(conn, request_id)
    if req is None:
        raise NotFoundError(f"Request {request_id} not found")
    current = req["urgency_tier"]

    location = resolve_location(req["ville"], req["municipality"], req["sib_territory"])
    if location is None:
        ev = repo.insert_evaluation(conn, request_id=request_id, status="location_unknown",
                                    evaluated_by=user.employee_id, current_tier_at_eval=current)
        return WeatherEvaluation(evaluation_id=ev["evaluation_id"], status="location_unknown",
                                 current_urgency_tier=current, current_tier_at_eval=current)

    snap = repo.get_cached_snapshot(conn, location)
    if snap is None:
        try:
            reading = fetch_forecast(location)
        except Exception:
            ev = repo.insert_evaluation(conn, request_id=request_id, status="source_failed",
                                        location=location, evaluated_by=user.employee_id,
                                        current_tier_at_eval=current)
            return WeatherEvaluation(evaluation_id=ev["evaluation_id"], status="source_failed",
                                     location=location, current_urgency_tier=current,
                                     current_tier_at_eval=current)
        snap = repo.insert_snapshot(conn, location=location, site_code=SITE_CODES[location],
                                    reading=reading)

    band = pick_band(list_bands(conn), snap["min_forecast_temp_24h_c"])
    suggested = band["suggested_tier"] if band else None
    is_critical = bool(band["is_critical"]) if band else False

    ev = repo.insert_evaluation(
        conn, request_id=request_id, snapshot_id=snap["snapshot_id"], location=location,
        band_name=band["name"] if band else None, suggested_tier=suggested,
        min_forecast_temp_24h_c=snap["min_forecast_temp_24h_c"],
        is_critical=is_critical, status="ok", evaluated_by=user.employee_id,
        current_tier_at_eval=current,
    )
    return WeatherEvaluation(
        evaluation_id=ev["evaluation_id"], status="ok", location=location,
        band_name=band["name"] if band else None, suggested_tier=suggested,
        direction=suggestion_direction(current, suggested), is_critical=is_critical,
        min_forecast_temp_24h_c=_f(snap["min_forecast_temp_24h_c"]),
        current_temp_c=_f(snap["current_temp_c"]), wind_chill_c=_f(snap["wind_chill_c"]),
        current_urgency_tier=current, current_tier_at_eval=current,
        forecast_time_local=_local_hhmm(snap.get("fetched_at")),
        source=snap["source"], source_url=snap["source_url"],
    )
