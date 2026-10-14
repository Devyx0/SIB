"""
tests/test_gf_parser.py — Unit tests for the Gravity Forms parser fixes.

Three structural fixtures derived from cached events (rid=122, rid=173, rid=2301)
with all PII values replaced by synthetic placeholders.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from drive_pipeline.ingestion.parse_calendar_requests import (
    _gf_nrm_label,
    _parse_gravity_forms,
)


# ── _gf_nrm_label ─────────────────────────────────────────────────────────────

def test_apostrophe_labels_match():
    """All 8 labels that previously failed due to apostrophes now resolve."""
    cases = [
        ("Date et heure de l’appel", "submission_date"),
        ("Type de l’appelant",        "caller_type"),
        ("Num\xe9ro unique d’unit\xe9","unit_number"),
        ("Nom complet de l’appelant", "caller_name"),
        ("T\xe9l\xe9phone de l’appelant","caller_phone"),
        ("Courriel de l’appelant",    "caller_email"),
        ("Adresse de l’urgence",      "address_urgency"),
        ("J’ai avis\xe9 des frais, si applicable","fees_advised"),
    ]
    from drive_pipeline.ingestion.parse_calendar_requests import _GF_LABEL_MAP
    for label, expected_key in cases:
        assert _GF_LABEL_MAP.get(_gf_nrm_label(label)) == expected_key, (
            f"label {label!r} did not resolve to {expected_key!r}"
        )


def test_ascii_apostrophe_also_stripped():
    assert _gf_nrm_label("J'ai avis\xe9 des frais si applicable") == "j ai avise des frais si applicable"


def test_no_apostrophe_labels_unchanged():
    """Labels without apostrophes still work."""
    assert _gf_nrm_label("Urgent ou non-urgent") == "urgent ou non-urgent"
    assert _gf_nrm_label("D\xe9tails, commentaires ou autre") == "details, commentaires ou autre"
    assert _gf_nrm_label("Acc\xe8s au logement") == "acces au logement"


# ── _parse_gravity_forms — fixture 1 (rid=122 structure) ─────────────────────
# Blank-line format; all apostrophe labels present; multi-line Détails.

_FX1 = (
    "Date et heure de l’appel : 2026-08-01 11:17:55\n\n"
    "Type de l’appelant : Locataire actuel\n\n"
    "Num\xe9ro unique d’unit\xe9 : UNIT-404\n\n"
    "Nom complet de l’appelant :\n\n"  # empty value
    "T\xe9l\xe9phone de l’appelant : +15550001234\n\n"
    "Courriel de l’appelant :\xa0test@example.com\n\n"
    "Urgent ou non-urgent : Urgent\n\n"
    "Cat\xe9gorie :\n\n"  # empty
    "Adresse de l’urgence :\n\n"  # empty
    "D\xe9tails, commentaires ou autre : Probl\xe8me avec la porte\n"
    "Note technicien ligne 2\n"
    "2026-08-01 CFD\n\n"
    "Garde #1 nom : Coordo maintenance\n\n"
    "J’ai avis\xe9 des frais, si applicable : NA\n\n"
    "Acc\xe8s au logement : Oui\n\n"
    "Avez-vous des animaux? : Non\n\n"
)


def test_fx1_apostrophe_fields():
    r = _parse_gravity_forms(_FX1)
    assert r["submission_date"] == "2026-08-01 11:17:55"
    assert r["caller_type"] == "Locataire actuel"
    assert r["unit_number"] == "UNIT-404"
    assert r["caller_name"] is None          # empty value → not set
    assert r["caller_phone"] == "+15550001234"
    assert r["fees_advised"] == "NA"
    assert r["entry_permission"] == "Oui"
    assert r["animals"] == "Non"


def test_fx1_multiline_message():
    """Multi-line Détails value: continuation lines in same paragraph are captured."""
    r = _parse_gravity_forms(_FX1)
    assert r["message"] is not None
    assert "Probl\xe8me avec la porte" in r["message"]
    assert "Note technicien ligne 2" in r["message"]


def test_fx1_guard_fields_do_not_pollute():
    """Guard contact paragraphs (blank-line separated) do not corrupt GF fields."""
    r = _parse_gravity_forms(_FX1)
    # entry_permission should be "Oui", not "Oui\nGarde #1 nom : ..."
    assert r["entry_permission"] == "Oui"
    # fees_advised should be "NA"
    assert r["fees_advised"] == "NA"


# ── fixture 2 (rid=173 structure) — multi-line Détails with embedded colon ───

_FX2 = (
    "Date et heure de l’appel : 2026-08-13 10:54:37\n\n"
    "Type de l’appelant : Autre\n\n"
    "Num\xe9ro unique d’unit\xe9 : \n\n"  # empty
    "Nom complet de l’appelant : Carel info\n\n"
    "T\xe9l\xe9phone de l’appelant : +15550009999\n\n"
    "Courriel de l’appelant : \n\n"
    "Urgent ou non-urgent : Urgent\n\n"
    "Cat\xe9gorie : \n\n"
    "Adresse de l’urgence : 55 Testreet\n\n"
    "D\xe9tails, commentaires ou autre : Wifi non fonctionnel, appeler sur place : \n"
    "1-800-555-0000\n"
    "No compte : 99999\n\n"
    "2026-08-13 CFD\n\n"
    "J’ai avis\xe9 des frais, si applicable : Non applicable\n\n"
    "Acc\xe8s au logement : Accord\xe9\n\n"
    "Avez-vous des animaux? : Non\n\n"
)


def test_fx2_empty_unit_number():
    r = _parse_gravity_forms(_FX2)
    assert r["unit_number"] is None


def test_fx2_multiline_with_embedded_colon():
    """Détails value containing an embedded colon + continuation lines is fully captured."""
    r = _parse_gravity_forms(_FX2)
    assert r["message"] is not None
    assert "1-800-555-0000" in r["message"]


def test_fx2_address_urgency():
    r = _parse_gravity_forms(_FX2)
    assert r["address_urgency"] == "55 Testreet"


def test_fx2_fees_and_entry():
    r = _parse_gravity_forms(_FX2)
    assert r["fees_advised"] == "Non applicable"
    assert r["entry_permission"] == "Accord\xe9"


# ── fixture 3 (rid=2301 structure) — LINE SEPARATOR   format ─────────────
# After  →\n conversion this becomes a normal blank-line event.

_FX3 = (
    "Date et heure de l’appel : 2026-07-14 11:18:00  "
    "Type de l’appelant : Locataire actuel  "
    "Num\xe9ro unique d’unit\xe9 : UNIT-202  "
    "Nom complet de l’appelant : Camila Test  "
    "T\xe9l\xe9phone de l’appelant : +15550001111  "
    "Courriel de l’appelant : camila@example.com  "
    "Urgent ou non-urgent : Urgent  "
    "Cat\xe9gorie :   "
    "Adresse de l’urgence :   "
    "D\xe9tails, commentaires ou autre : Bris de tuyau  "
    "J’ai avis\xe9 des frais, si applicable : -  "
    "Acc\xe8s au logement : Oui  "
    "Avez-vous des animaux? : Non  "
)


def test_fx3_line_separator_handled():
    """  → \\n preprocessing produces correct blank-line paragraphs."""
    r = _parse_gravity_forms(_FX3)
    assert r["submission_date"] == "2026-07-14 11:18:00"
    assert r["unit_number"] == "UNIT-202"
    assert r["caller_name"] == "Camila Test"
    assert r["urgency_raw"] == "Urgent"
    assert r["fees_advised"] == "-"
    assert r["entry_permission"] == "Oui"
    assert r["animals"] == "Non"

# ── fixture 4 — single-\n format (no blank lines between fields) ──────────────
# Reproduces rid=5842: all fields separated by single \n only.
# The label-led splitter handles this because it checks each line independently.

_FX4 = (
    "Date et heure de l'appel : 2026-05-19 15:20:24\n"
    "Type de l'appelant : Locataire actuel\n"
    "Num\xe9ro unique d'unit\xe9 : UNIT-139\n"
    "Nom complet de l'appelant : Hugo Test\n"
    "T\xe9l\xe9phone de l'appelant : +15550004466\n"
    "Courriel de l'appelant : hugo@example.com\n"
    "Urgent ou non-urgent : Urgent\n"
    "Cat\xe9gorie :\n"
    "Adresse de l'urgence :\n"
    "D\xe9tails, commentaires ou autre : De l'eau sort du plafond\n"
    "Garde #1 nom : Simon Testeur\n"
    "Garde #1 t\xe9l\xe9phone : +15550003827\n"
)


def test_fx4_single_newline_format():
    """Label-led splitter extracts all fields even with no blank lines between them."""
    r = _parse_gravity_forms(_FX4)
    assert r["submission_date"] == "2026-05-19 15:20:24"
    assert r["caller_type"] == "Locataire actuel"
    assert r["unit_number"] == "UNIT-139"
    assert r["caller_name"] == "Hugo Test"
    assert r["caller_phone"] == "+15550004466"
    assert r["caller_email"] == "hugo@example.com"
    assert r["urgency_raw"] == "Urgent"


def test_fx4_guard_lines_appended_to_message():
    """Guard-contact lines (non-GF label) in a single-\n block append to current field."""
    r = _parse_gravity_forms(_FX4)
    assert r["message"] is not None
    assert "De l'eau sort du plafond" in r["message"]
    assert "Garde #1 nom" in r["message"]
