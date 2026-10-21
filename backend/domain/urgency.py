"""Plain urgency levels from sheet Générale!E (Niveau d'urgence).

Stored values stay French/sheet-canonical; UI maps to Urgent / Medium / Low.
"""
from __future__ import annotations

from typing import Literal

UrgencyTier = Literal["URGENT", "Intermédiaire", "Faible"]

URGENCY_VALUES: frozenset[str] = frozenset({"URGENT", "Intermédiaire", "Faible"})

# Rank for sort / weather escalation (higher = more urgent).
URGENCY_RANK: dict[str | None, int] = {
    None: 0,
    "none": 0,  # legacy
    "Faible": 1,
    "Intermédiaire": 2,
    "URGENT": 3,
    # legacy letter codes (pre-migration rows / stale weather evals)
    "ajd": 2,
    "AJD": 3,
}

# Migrate letter codes → plain levels when reading old payloads.
LEGACY_URGENCY_MAP: dict[str, str | None] = {
    "AJD": "URGENT",
    "ajd": "Intermédiaire",
    "none": None,
}


def normalize_urgency(value: str | None) -> str | None:
    if value is None:
        return None
    if value in URGENCY_VALUES:
        return value
    if value in LEGACY_URGENCY_MAP:
        return LEGACY_URGENCY_MAP[value]
    return None
