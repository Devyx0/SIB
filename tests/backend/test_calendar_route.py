"""Unit tests for Main vs Majordome calendar inference (guide rule 35)."""
from __future__ import annotations

from backend.triage.calendar_route import source_calendar_for_sector


def test_levis_est_is_majordome():
    assert source_calendar_for_sector(territoire="Levis-Est", color_code="6") == "st_maj"


def test_levis_ouest_accent_is_majordome():
    assert source_calendar_for_sector(territoire="Lévis-Ouest", color_code=None) == "st_maj"


def test_color_6_alone_is_majordome():
    assert source_calendar_for_sector(territoire="Something-Else", color_code="6") == "st_maj"


def test_sainte_foy_is_main():
    assert source_calendar_for_sector(territoire="Sainte-Foy", color_code="7") == "main"


def test_haute_ville_is_main():
    assert source_calendar_for_sector(territoire="Haute-Ville", color_code="5") == "main"


def test_unknown_defaults_main():
    assert source_calendar_for_sector(territoire=None, color_code=None) == "main"
