"""Map a request to MAIN vs ST Majordome the way the Claude skill/guide does.

Guide cardinal rule 35: « MAIN - Calls ST Majordome Québec » holds calls entrusted
to Majordome — grosso modo the south shore of Québec (Lévis / Charny / rive-sud).
« MAIN - Calls » is the principal Gravity landing calendar.

In our DB that is sector.territoire Lévis-Est / Lévis-Ouest (color_code 6 in
secteurs-et-equipe.md). Everything else stays on main.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(s: str | None) -> str:
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    bare = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", bare.lower())


# Normalized territoire names that belong on the Majordome calendar.
_MAJORDOME_TERRITOIRES = frozenset({
    "levisest",
    "levisouest",
    "levis",
    "rivesud",
    "charny",
})

# Google colorId 6 = Lévis (Est et Ouest) in secteurs-et-equipe.md
_MAJORDOME_COLOR_CODES = frozenset({"6"})


def source_calendar_for_sector(*, territoire: str | None, color_code: str | None) -> str:
    """Return 'st_maj' or 'main' from sector fields."""
    if _norm(territoire) in _MAJORDOME_TERRITOIRES:
        return "st_maj"
    if (color_code or "").strip() in _MAJORDOME_COLOR_CODES:
        return "st_maj"
    return "main"


def infer_source_calendar_from_cur(cur, request_id: int) -> str:
    """Resolve Main vs Majordome via the open DB cursor (psycopg2 or psycopg3)."""
    cur.execute(
        """
        SELECT
            COALESCE(s_mr.territoire, s_b.territoire) AS territoire,
            COALESCE(s_mr.color_code, s_b.color_code) AS color_code
        FROM maintenance_request mr
        LEFT JOIN sector s_mr ON s_mr.sector_id = mr.sector_id
        LEFT JOIN building b ON b.building_id = mr.building_id
        LEFT JOIN sector s_b ON s_b.sector_id = b.sector_id
        WHERE mr.request_id = %s
        """,
        (request_id,),
    )
    row = cur.fetchone()
    if row is None:
        return "main"
    if isinstance(row, dict):
        return source_calendar_for_sector(
            territoire=row.get("territoire"),
            color_code=row.get("color_code"),
        )
    return source_calendar_for_sector(territoire=row[0], color_code=row[1])
