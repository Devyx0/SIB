"""Issue-only triage title cleanup."""
from backend.triage.titles import apply_clean_title, clean_issue_title


def test_strips_unit_address_prefix():
    assert clean_issue_title("1035-308 Pie XII: Fuite sous le lavabo") == "Fuite sous le lavabo"


def test_strips_urgency_and_location():
    assert (
        clean_issue_title("AJD 3140-501 France-Prime: DOUBLON POTENTIEL — Ventilateur SDB")
        == "DOUBLON POTENTIEL — Ventilateur SDB"
    )


def test_strips_ajd_only():
    assert clean_issue_title("ajd Fuite active cuisine") == "Fuite active cuisine"


def test_keeps_plain_issue():
    assert clean_issue_title("Fuite sous le lavabo") == "Fuite sous le lavabo"


def test_keeps_doublon_without_location():
    assert (
        clean_issue_title("DOUBLON POTENTIEL — Suivi ventilateur SDB")
        == "DOUBLON POTENTIEL — Suivi ventilateur SDB"
    )


def test_does_not_strip_colon_without_unitish_head():
    # No digit in the head → leave alone (not a calendar location prefix).
    assert clean_issue_title("Note: vérifier le joint") == "Note: vérifier le joint"


def test_apply_clean_title_mutates():
    parsed = {"title": "7885-12 Sully: Robinet qui fuit"}
    apply_clean_title(parsed)
    assert parsed["title"] == "Robinet qui fuit"
