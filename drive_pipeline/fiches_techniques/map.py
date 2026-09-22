# map.py — one row per address (street + civic_number) found in Fiches Techniques filenames.
# Multi-address files (e.g., ANCIENNE entries spanning two streets) produce one row per address group.
# civic_number is kept verbatim (ranges like "405-415" are not split).
# Join to Building entity via: street + civic_number → building_id.
# Entries without a parseable city+civic pattern are excluded.

import re
from .links import FICHES

_ADDR_RE = re.compile(r'([^,(]+),\s+(Qu[ée]bec|L[ée]vis)\s+\((\d[\d-]*)\)')


def _parse_addresses(english_name: str) -> list[dict]:
    rows = []
    for m in _ADDR_RE.finditer(english_name):
        rows.append({
            "street": m.group(1).strip(),
            "city": m.group(2),
            "civic_number": m.group(3),
            "english_name": english_name,
        })
    return rows


ADDRESSES = [
    {**row, "subfolder": fiche["subfolder"]}
    for fiche in FICHES
    for row in _parse_addresses(fiche["english_name"])
]

# Index for O(1) lookup by (street, civic_number) — returns the first match (root preferred).
BY_CIVIC = {(r["street"], r["civic_number"]): r for r in reversed(ADDRESSES)}
