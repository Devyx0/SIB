"""Resolve a building to its MSC weather location.

Layered rule (docs/weather-escalation.md §A2): any of ville / municipality /
sib_territory naming Lévis -> 'levis'; any other non-empty signal -> 'quebec'
(the Québec City agglomeration uses the Québec point); all blank -> None (unknown,
no check). Verified zero conflicts between municipality and sib_territory on the
dev DB.
"""
from __future__ import annotations

# MSC CityPage site codes (verified in site_list_en.geojson, 2026-10-19).
SITE_CODES: dict[str, str] = {
    "quebec": "s0000620",
    "levis": "s0000416",
}


def _n(s: str | None) -> str:
    return (s or "").strip().lower()


def resolve_location(ville: str | None, municipality: str | None,
                     sib_territory: str | None) -> str | None:
    vals = [_n(ville), _n(municipality), _n(sib_territory)]
    if any(("levis" in v or "lévis" in v) for v in vals):
        return "levis"
    if any(vals):
        return "quebec"
    return None
