"""Geocode building addresses via Nominatim (OpenStreetMap).

Used by the one-time backfill script and by portfolio create/patch when an
address field changes. Keep ≤1 request/second against the public Nominatim
endpoint; identify the app in the User-Agent.

Important: normalize_street() only shapes the *search query*. It never edits
building.adresse / ville / code_postal.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

GeocodeStatus = Literal["ok", "failed", "skipped", "needs_review"]

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "SIB-Francois/1.0 (building-geocode; local-dev)"

# Québec City + Lévis metro (WGS84). Hits outside → reject (don't store Montréal pins).
_METRO_LAT = (46.65, 46.98)
_METRO_LON = (-71.60, -71.05)
# Nominatim viewbox: left, top, right, bottom
_VIEWBOX = f"{_METRO_LON[0]},{_METRO_LAT[1]},{_METRO_LON[1]},{_METRO_LAT[0]}"

_last_request_at = 0.0


@dataclass(frozen=True)
class GeocodeResult:
    status: GeocodeStatus
    latitude: float | None
    longitude: float | None
    query: str
    display_name: str | None = None
    note: str | None = None


def normalize_street(adresse: str) -> str:
    """Collapse SIB portfolio labels into a single civic + street for search.

    Does not mutate stored addresses — return value is query-only.
    """
    s = adresse.strip()
    # Dual street: "580 Grande Allee / 1185-1195 Brown" → first side
    if " / " in s:
        s = s.split(" / ", 1)[0].strip()
    elif "/" in s:
        s = s.split("/", 1)[0].strip()
    # Drop block ranges: "1175 Chamonix (1 a 26)" → "1175 Chamonix"
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    # Vacant-lot labels: "Terrain Chemin Belair" → "Chemin Belair"
    s = re.sub(r"^Terrain\s+", "", s, flags=re.IGNORECASE).strip()
    # "2 a 36 Archer" / "2 à 36 Archer" → "2 Archer"
    m = re.match(r"^(\d+)\s*[aà]\s*\d+\s+(.+)$", s, re.IGNORECASE)
    if m:
        s = f"{m.group(1)} {m.group(2)}"
    # Civic ranges: "786-796 Abraham", "84-86-88 Carmichael", "405-415 41e Rue…"
    m = re.match(r"^(\d+)(?:-\d+)+\s+(.+)$", s)
    if m:
        s = f"{m.group(1)} {m.group(2)}"
    return re.sub(r"\s+", " ", s).strip()


def _accent_variants(street: str) -> list[str]:
    """Light FR spelling fallbacks when the first query misses."""
    variants = [street]
    swaps = (
        ("Allee", "Allée"),
        ("allee", "allée"),
        ("Cite", "Cité"),
        ("cite", "cité"),
        ("Hotel", "Hôtel"),
        ("Hopital", "Hôpital"),
        ("Eglise", "Église"),
    )
    for a, b in swaps:
        if a in street:
            variants.append(street.replace(a, b))
    # St-Jean → Saint-Jean (avoids Montréal Blvd Saint-Jean)
    expanded = re.sub(r"\bSt-", "Saint-", street, flags=re.IGNORECASE)
    expanded = re.sub(r"\bSt\b", "Saint", expanded, flags=re.IGNORECASE)
    if expanded != street:
        variants.append(expanded)
        # Prefer "rue Saint-…" for bare civic + abbreviated street
        if re.match(r"^\d+\s+Saint\b", expanded, re.IGNORECASE):
            variants.append(re.sub(r"^(\d+)\s+", r"\1 rue ", expanded, count=1))
    # Bare "254 Saint-Jean" without type → try with rue
    if re.match(r"^\d+\s+[A-Za-zÀ-ÿ]", street) and not re.search(
        r"\b(rue|avenue|av\.?|boul|boulevard|chemin|ch\.?|impasse|cote|côte)\b",
        street,
        re.IGNORECASE,
    ):
        variants.append(re.sub(r"^(\d+)\s+", r"\1 rue ", street, count=1))
        if expanded != street:
            variants.append(re.sub(r"^(\d+)\s+", r"\1 rue ", expanded, count=1))

    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v = re.sub(r"\s+", " ", v).strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def build_query(
    adresse: str | None,
    ville: str | None = None,
    code_postal: str | None = None,
    *,
    street_override: str | None = None,
) -> str | None:
    """Search query only — never write this back to adresse."""
    raw = (adresse or "").strip()
    if not raw and not street_override:
        return None
    street = street_override if street_override is not None else normalize_street(raw)
    if not street:
        return None
    parts = [street]
    if ville and str(ville).strip():
        parts.append(str(ville).strip())
    elif code_postal and str(code_postal).strip():
        parts.append(str(code_postal).strip())
    return ", ".join(parts) + ", Québec, Canada"


def _in_metro(lat: float, lon: float) -> bool:
    return _METRO_LAT[0] <= lat <= _METRO_LAT[1] and _METRO_LON[0] <= lon <= _METRO_LON[1]


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    _last_request_at = time.monotonic()


def _parse_hits(hits: list[dict[str, Any]], query: str) -> GeocodeResult:
    if not hits:
        return GeocodeResult("failed", None, None, query, note="no_results")

    # Prefer first hit that lands in the metro; else reject (no wrong-city pins).
    chosen: dict[str, Any] | None = None
    for h in hits:
        try:
            lat = float(h["lat"])
            lon = float(h["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if _in_metro(lat, lon):
            chosen = h
            break

    if chosen is None:
        try:
            display = hits[0].get("display_name")
        except Exception:  # noqa: BLE001
            display = None
        return GeocodeResult(
            "failed", None, None, query,
            display_name=display, note="outside_metro",
        )

    lat = float(chosen["lat"])
    lon = float(chosen["lon"])
    display = chosen.get("display_name")
    return GeocodeResult("ok", lat, lon, query, display_name=display)


def _search(client: httpx.Client, query: str, *, throttle: bool) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "format": "json",
        "limit": "5",
        "countrycodes": "ca",
        "addressdetails": "0",
        "viewbox": _VIEWBOX,
    }
    url = f"{NOMINATIM_URL}?{urlencode(params)}"
    if throttle:
        _throttle()
    r = client.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def geocode_address(
    adresse: str | None,
    ville: str | None = None,
    code_postal: str | None = None,
    *,
    client: httpx.Client | None = None,
    throttle: bool = True,
) -> GeocodeResult:
    """Resolve one address. Pass an httpx.Client in tests to mock Nominatim.

    Stored adresse / ville / code_postal are never modified — only used to
    build search queries (see normalize_street / build_query).
    """
    raw = (adresse or "").strip()
    if not raw:
        return GeocodeResult("skipped", None, None, "", note="blank_address")

    street = normalize_street(raw)
    if not street:
        return GeocodeResult("skipped", None, None, "", note="blank_address")

    queries: list[str] = []
    for variant in _accent_variants(street):
        q = build_query(adresse, ville, code_postal, street_override=variant)
        if q and q not in queries:
            queries.append(q)

    last = GeocodeResult("failed", None, None, queries[0] if queries else "", note="no_results")

    def _run(c: httpx.Client) -> GeocodeResult:
        nonlocal last
        for q in queries:
            try:
                hits = _search(c, q, throttle=throttle)
            except Exception as exc:  # noqa: BLE001
                last = GeocodeResult(
                    "failed", None, None, q, note=f"http_error:{type(exc).__name__}",
                )
                continue
            result = _parse_hits(hits, q)
            last = result
            if result.status == "ok":
                if street != raw and result.note is None:
                    return GeocodeResult(
                        result.status, result.latitude, result.longitude, result.query,
                        display_name=result.display_name, note="normalized_query",
                    )
                return result
        return last

    try:
        if client is not None:
            return _run(client)
        with httpx.Client(timeout=30.0) as owned:
            return _run(owned)
    except Exception as exc:  # noqa: BLE001
        return GeocodeResult(
            "failed", None, None, queries[0] if queries else "",
            note=f"http_error:{type(exc).__name__}",
        )
