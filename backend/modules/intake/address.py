"""Address matching for Gravity Forms intake and manual create.

Returns a MatchResult for a given (civic, street, apartment) triple against
the buildings and units in the local DB.

Ambiguity resolution (Chamonix-style): when civic+street matches 2+ buildings,
try resolving by apartment — if the apartment exists in exactly one candidate
building, that building wins.
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple


class MatchResult(NamedTuple):
    match_status: str  # 'exact' | 'building_only' | 'ambiguous' | 'no_match' | 'garbled'
    building_id: int | None
    unit_id: int | None
    candidate_building_ids: list[int]


_SUFFIX_RE = re.compile(
    r'\b(blvd|boulevard|boul|street|st\.?|ave\.?|avenue|lane|road|rd\.?|'
    r'rue|chemin|ch\.?|place|pl\.?|court|ct\.?|drive|dr\.?)$',
    re.IGNORECASE,
)
# Directional suffixes tenants sometimes append (e.g. "Grande Allee O.", "Rue Principale E.")
_DIR_RE = re.compile(
    r'\s+(?:o\.?|e\.?|n\.?|s\.?|ouest|est|nord|sud|w\.?|west|east|north|south)\.?\s*$',
    re.IGNORECASE,
)


def _norm_street(s: str) -> str:
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower()
    s = re.sub(r'\bste\b\.?', 'sainte', s)
    s = re.sub(r'\bst\b\.?(?!e)', 'saint', s)
    s = _DIR_RE.sub('', s).strip()
    s = _SUFFIX_RE.sub('', s).strip()
    # ch. / ch as abbreviation for chemin must be stripped before article strip
    s = re.sub(r'^(rue|avenue|av\.?|boul(?:evard)?|chemin|ch\.?)\s+', '', s)
    s = re.sub(r'^(du|de la|des|de l|de|le|la|les)\s+', '', s)
    s = re.sub(r'[-\s]+', ' ', s).strip()
    # Unify saint/sainte so "St-Ursule" and "Ste-Ursule" compare equal
    s = re.sub(r'\bsainte\b', 'saint', s)
    return s


def _civic_int_set(civic: str | None) -> frozenset[int]:
    """All integer civic numbers in a string, expanding dash-separated ranges.

    '3040-3050' → {3040, 3041, ..., 3050}
    '786-796'   → {786, ..., 796}
    '5-7-9'     → {5, 6, 7, 8, 9}
    '1580'      → {1580}
    Ranges wider than 500 numbers are not expanded (defensive guard).
    """
    if not civic:
        return frozenset()
    nums = [int(n) for n in re.findall(r'\d+', civic)]
    if not nums:
        return frozenset()
    lo, hi = min(nums), max(nums)
    if 1 < hi - lo <= 500:
        return frozenset(range(lo, hi + 1))
    return frozenset(nums)


def _is_garbled(civic: str, street: str, apartment: str | None) -> bool:
    """True when the fields look like the tenant copy-pasted a full address into every box."""
    if len(civic) > 20:
        return True
    # If street looks like it contains a full address (civic + street + apt together)
    if re.search(r'\d{3,}', street) and re.search(r'[a-zA-Z]{3,}', civic):
        return True
    return False


def _parse_adresse(adresse: str) -> tuple[str | None, str]:
    """Split a building address into (civic, street).

    Handles:
      '1580 Perigord'           → ('1580', 'Perigord')
      '786-796 Abraham'         → ('786-796', 'Abraham')
      '2 a 36 Archer'           → ('2-36', 'Archer')       # range with 'a' connector
      '11 a 33 Charbonnier'     → ('11-33', 'Charbonnier')
      '7905 Sully (1 a 23)'     → ('7905', 'Sully')        # parenthetical sub-label stripped
      'Terrain Chemin Belair'   → (None, 'Terrain Chemin Belair')

    For multi-address entries (e.g. '580 Grande Allee / 1185-1195 Brown'), the
    first civic+street is extracted; secondary aliases are ignored.
    """
    adresse = adresse.strip()
    # Strip parenthetical sub-building labels before parsing
    adresse = re.sub(r'\s*\([^)]*\)', '', adresse).strip()
    # Greedy civic: starts with a digit, may contain digits, spaces, hyphens,
    # 'a'/'à' (range connectors), must END with a digit.
    m = re.match(r'^(\d[\d\s\-aàA]*\d|\d+)\s+(.+)$', adresse)
    if not m:
        return None, adresse
    civic_str = re.sub(r'\s+[aà]\s+', '-', m.group(1).strip())
    # For multi-address buildings, take only the first street name (before ' / ')
    street_str = m.group(2).split(' / ')[0].strip()
    return civic_str, street_str


def _load_buildings(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT building_id, adresse, ville FROM building WHERE adresse IS NOT NULL"
    ).fetchall()
    result = []
    for row in rows:
        adresse = row["adresse"]
        # Index each " / "-separated address segment so tenants using a secondary
        # address (e.g. "1410 Longueuil" from "860 Marguerite-Bourgeoys / 1410 Longueuil")
        # still match.
        for segment in adresse.split(' / '):
            civic_str, street_str = _parse_adresse(segment.strip())
            result.append({
                "building_id": row["building_id"],
                "adresse": adresse,
                "ville": row["ville"],
                "civic": civic_str,
                "street_norm": _norm_street(street_str),
            })
    return result


def match_address(conn, civic: str, street: str, apartment: str | None) -> MatchResult:
    civic = (civic or "").strip()
    street = (street or "").strip()
    apartment = (apartment or "").strip() or None

    if _is_garbled(civic, street, apartment):
        return MatchResult("garbled", None, None, [])

    street_norm = _norm_street(street)
    civic_set = _civic_int_set(civic)

    buildings = _load_buildings(conn)
    candidates = [
        b for b in buildings
        if b["street_norm"] == street_norm and bool(_civic_int_set(b["civic"]) & civic_set)
    ]

    if not candidates:
        return MatchResult("no_match", None, None, [])

    if len(candidates) == 1:
        bldg = candidates[0]
        unit_id = _match_unit(conn, bldg["building_id"], apartment, civic_set)
        if unit_id is not None:
            return MatchResult("exact", bldg["building_id"], unit_id, [])
        return MatchResult("building_only", bldg["building_id"], None, [])

    # Multiple candidates — try apartment disambiguation
    candidate_ids = [b["building_id"] for b in candidates]
    if apartment:
        matches = conn.execute(
            """
            SELECT building_id, unit_id FROM unit
            WHERE building_id = ANY(%(ids)s)
              AND LOWER(TRIM(numero_appartement)) = LOWER(TRIM(%(apt)s))
            """,
            {"ids": candidate_ids, "apt": apartment},
        ).fetchall()
        if len(matches) == 1:
            return MatchResult("exact", matches[0]["building_id"], matches[0]["unit_id"], [])

    return MatchResult("ambiguous", None, None, candidate_ids)


def _match_unit(conn, building_id: int, apartment: str | None,
                civic_set: frozenset[int] = frozenset()) -> int | None:
    if not apartment:
        return None
    if civic_set:
        # When we have a civic, prefer the unit whose rue starts with a matching number.
        # If none match, return None (→ building_only) rather than guessing with LIMIT 1.
        rows = conn.execute(
            """
            SELECT unit_id, rue FROM unit
            WHERE building_id = %(building_id)s
              AND LOWER(TRIM(numero_appartement)) = LOWER(TRIM(%(apt)s))
              AND rue IS NOT NULL
            """,
            {"building_id": building_id, "apt": apartment},
        ).fetchall()
        for row in rows:
            try:
                rue_civic = int(row["rue"].split(",")[0].split("-")[0].strip())
            except (ValueError, IndexError, AttributeError):
                continue
            if rue_civic in civic_set:
                return row["unit_id"]
        return None
    # No civic given: only safe to assign a unit when exactly one matches.
    rows = conn.execute(
        """
        SELECT unit_id FROM unit
        WHERE building_id = %(building_id)s
          AND LOWER(TRIM(numero_appartement)) = LOWER(TRIM(%(apt)s))
        """,
        {"building_id": building_id, "apt": apartment},
    ).fetchall()
    return rows[0]["unit_id"] if len(rows) == 1 else None
