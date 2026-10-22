"""Unit tests for triage AI note array normalization."""
from backend.triage.ai_notes import append_important, normalize_parsed, parse_other_notes


def test_normalize_from_arrays():
    parsed = {
        "ai_important_notes": ["RÉQUÉRANT ABSENT", "  "],
        "ai_next_steps": ["Couper l'eau", "Remplacer joint"],
        "reasoning": "  Urgence élevée : eau active.  ",
        "other_notes": None,
    }
    normalize_parsed(parsed)
    assert parsed["ai_important_notes"] == ["RÉQUÉRANT ABSENT"]
    assert parsed["ai_next_steps"] == ["Couper l'eau", "Remplacer joint"]
    assert parsed["next_steps"] == "Couper l'eau\nRemplacer joint"
    assert parsed["ai_reasoning"] == "Urgence élevée : eau active."
    assert "RÉQUÉRANT ABSENT" in parsed["other_notes"]
    assert "Couper l'eau" in parsed["other_notes"]


def test_normalize_from_legacy_headers():
    parsed = {
        "other_notes": "IMPORTANT:\n- bail anglais\nNEXT:\n- Appeler",
    }
    normalize_parsed(parsed)
    assert parsed["ai_important_notes"] == ["bail anglais"]
    assert parsed["ai_next_steps"] == ["Appeler"]


def test_normalize_freeform_other_notes():
    parsed = {"other_notes": "Plomberie d’abord."}
    normalize_parsed(parsed)
    assert parsed["ai_important_notes"] == ["Plomberie d’abord."]
    assert parsed["ai_next_steps"] is None


def test_append_important():
    parsed = {"ai_important_notes": ["déjà"], "ai_next_steps": None, "other_notes": "déjà"}
    append_important(parsed, "Escalade météo")
    assert parsed["ai_important_notes"] == ["déjà", "Escalade météo"]
    assert "Escalade météo" in parsed["other_notes"]


def test_parse_other_notes_empty():
    assert parse_other_notes(None) == (None, None)
    assert parse_other_notes("  ") == (None, None)
