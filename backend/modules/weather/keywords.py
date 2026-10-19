"""Focused French "no heat" keyword matcher.

Advisory only — it decides whether to show the "Appel de chauffage possible"
hint next to the weather button. It never changes urgency. Same focused list
validated in docs/weather-escalation.md §A3 (dev DB: 30 hits over ~5 years;
~20-30% false positives, hence advisory-only).
"""
from __future__ import annotations

import re

_FOCUSED = re.compile(
    r"(pas de chauffage|sans chauffage|aucun chauffage|plus de chauffage|manque de chauffage"
    r"|panne de chauffage"
    r"|chauffage[^.]{0,18}(fonctionne pas|ne fonctionne|defectueux|défectueux|bris|hors service|en panne)"
    r"|pas de chaleur|manque de chaleur|aucune chaleur|plus de chaleur|no heat)",
    re.IGNORECASE,
)


def matches_heating_keywords(text: str | None) -> bool:
    return bool(text) and bool(_FOCUSED.search(text))
