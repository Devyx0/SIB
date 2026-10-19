"""Response schema for the weather-check endpoint."""
from __future__ import annotations

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
    source: Optional[str] = None
    source_url: Optional[str] = None
