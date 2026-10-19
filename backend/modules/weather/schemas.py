"""Response schema for the weather-check endpoint and the detail-panel summary."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class WeatherEvaluation(BaseModel):
    evaluation_id: int
    status: Literal["ok", "location_unknown", "source_failed"]
    location: Optional[str] = None
    band_name: Optional[str] = None
    suggested_tier: Optional[str] = None
    direction: Optional[Literal["higher", "lower", "equal"]] = None
    is_critical: bool = False
    min_forecast_temp_24h_c: Optional[float] = None
    current_temp_c: Optional[float] = None
    wind_chill_c: Optional[float] = None
    current_urgency_tier: Optional[str] = None
    # Urgency tier at the moment this forecast was evaluated — used to detect a
    # stale suggestion (UI hides it; accept endpoint 409s) when urgency changes.
    current_tier_at_eval: Optional[str] = None
    forecast_time_local: Optional[str] = None  # snapshot fetched_at as HH:MM, app tz
    source: Optional[str] = None
    source_url: Optional[str] = None
    evaluated_at: Optional[datetime] = None  # set on the detail-panel summary
