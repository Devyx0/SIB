"""MSC CityPage Weather fetcher (Environment and Climate Change Canada).

Free, no API key. Datamart layout (2026): the stable per-site path was removed;
files live under /today/citypage_weather/QC/<HH>/<ts>_MSC_CitypageWeather_<site>_en.xml
with timestamped names, so we list the current UTC hour's directory (falling back
to the previous hour near the top of the hour), take the newest file for the site,
and parse it.

This module is ALWAYS mocked in tests (service.fetch_forecast). parse_citypage_xml
is pure and unit-tested with a static XML string (no network).

Attribution (shown in the UI): "Source : Environnement et Changement climatique Canada".
"""
from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timezone

from .location import SITE_CODES

_BASE = "https://dd.weather.gc.ca/today/citypage_weather/QC"


def _num(text: str | None) -> float | None:
    if text is None or text.strip() == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_citypage_xml(xml: str | bytes) -> dict:
    """Extract current temp, min of the next-24h hourly temps, and wind chill."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml)
    cc = root.find("currentConditions")
    current = wind_now = None
    if cc is not None:
        t = cc.find("temperature")
        current = _num(t.text) if t is not None else None
        w = cc.find("windChill")
        wind_now = _num(w.text) if w is not None else None

    temps: list[float] = []
    hourly_wind: list[float] = []
    hg = root.find("hourlyForecastGroup")
    if hg is not None:
        for h in hg.findall("hourlyForecast"):
            tv = _num(h.findtext("temperature"))
            if tv is not None:
                temps.append(tv)
            wv = _num(h.findtext("windChill"))
            if wv is not None:
                hourly_wind.append(wv)

    wind = wind_now if wind_now is not None else (min(hourly_wind) if hourly_wind else None)
    return {
        "current_temp_c": current,
        "wind_chill_c": wind,
        "min_forecast_temp_24h_c": min(temps) if temps else None,
    }


def _get(url: str, timeout: int = 10) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 (fixed https host)
        return r.read()


def fetch_forecast(location: str) -> dict:
    """Real MSC fetch. Raises on failure; the service turns that into 'source_failed'."""
    site = SITE_CODES[location]
    now = datetime.now(timezone.utc)
    for back in (0, 1):
        hour = f"{(now.hour - back) % 24:02d}"
        try:
            listing = _get(f"{_BASE}/{hour}/").decode("utf-8", "replace")
        except Exception:
            continue
        files = re.findall(rf'href="([^"]*_MSC_CitypageWeather_{site}_en\.xml)"', listing)
        if not files:
            continue
        fname = sorted(files)[-1]
        url = f"{_BASE}/{hour}/{fname}"
        reading = parse_citypage_xml(_get(url))
        reading["source"] = "msc_citypage"
        reading["source_url"] = url
        return reading
    raise RuntimeError(f"MSC citypage weather unavailable for {location}")
