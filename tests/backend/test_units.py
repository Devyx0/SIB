"""Tests for units lookup and address matching."""
from __future__ import annotations

import pytest

from backend.modules.requests.repository import list_units
from backend.modules.intake.address import match_address, _match_unit


# ── list_units: NULL filter ───────────────────────────────────────────────────

def test_list_units_excludes_null_numero_appartement(db_conn):
    """Buildings with NULL numero_appartement must not raise a 500.

    Building 152 (117 Ste-Anne) has exactly 1 unit and its numero_appartement
    is NULL — this was the original cause of the 500. The endpoint must return
    an empty list, not blow up.
    """
    result = list_units(db_conn, 152)
    assert isinstance(result, list)
    assert all(u["numero_appartement"] is not None for u in result)


def test_list_units_returns_rue_field(db_conn):
    """list_units now includes the rue column for civic display in the unit picker."""
    # Building 107 (315-317 St-Jean) has units with rue set
    result = list_units(db_conn, 107)
    assert len(result) >= 100
    assert all("rue" in u for u in result)
    assert all(u["numero_appartement"] is not None for u in result)


def test_list_units_empty_for_all_null_building(db_conn):
    """Building with only NULL-numbered units returns empty list (not 500)."""
    # Building 152 has 1 unit, all NULL
    result = list_units(db_conn, 152)
    assert result == []


# ── Address matcher: civic narrowing ─────────────────────────────────────────

def test_match_unit_uses_civic_to_disambiguate(db_conn):
    """When a building has multiple units with the same apartment number (one per
    civic entrance), _match_unit prefers the unit whose rue matches the stated civic.

    Buildings 60 and 62 (Châtelets) each have 6 units per apartment number,
    one per civic address (3040, 3042, 3044, 3046, 3048, 3050 for building 60).
    """
    # Find one of the Châtelets buildings and a civic that has a duplicate apt
    rows = db_conn.execute(
        """
        SELECT building_id, rue, unit_id, numero_appartement
        FROM unit
        WHERE building_id IN (60, 62) AND numero_appartement IS NOT NULL
        ORDER BY building_id, numero_appartement, rue
        LIMIT 1
        """
    ).fetchone()

    if rows is None:
        pytest.skip("Châtelets buildings not found in this DB")

    building_id = rows["building_id"]
    apt = rows["numero_appartement"]
    expected_unit_id = rows["unit_id"]
    # Extract civic from rue, e.g. "3040, rue des Châtelets" → 3040
    rue_civic = int(rows["rue"].split(",")[0].strip())

    from backend.modules.intake.address import _civic_int_set
    civic_set = frozenset([rue_civic])

    matched_id = _match_unit(db_conn, building_id, apt, civic_set)
    assert matched_id == expected_unit_id, (
        f"Expected unit {expected_unit_id} at {rue_civic} apt {apt}, got {matched_id}"
    )


def test_match_unit_returns_none_when_civic_given_but_no_rue_match(db_conn):
    """When civic_set is non-empty but no unit's rue matches, return None (building_only).

    The old LIMIT 1 fallback is removed: if the caller supplied a civic and none
    of the units have a matching rue, we refuse to guess.
    """
    # Pass a civic set that won't match any unit.rue (impossible civic 999999)
    rows = db_conn.execute(
        "SELECT building_id, numero_appartement FROM unit WHERE numero_appartement IS NOT NULL LIMIT 1"
    ).fetchone()
    result = _match_unit(db_conn, rows["building_id"], rows["numero_appartement"], frozenset([999999]))
    assert result is None


def test_match_unit_no_civic_single_unit_returns_id(db_conn):
    """With no civic, if exactly one unit has that apartment number, return it."""
    # Find a building+apt combination that has exactly one unit
    row = db_conn.execute(
        """
        SELECT building_id, numero_appartement
        FROM unit
        WHERE numero_appartement IS NOT NULL
        GROUP BY building_id, LOWER(TRIM(numero_appartement)), numero_appartement
        HAVING COUNT(*) = 1
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        pytest.skip("No building with a unique apartment number found")
    result = _match_unit(db_conn, row["building_id"], row["numero_appartement"], frozenset())
    assert isinstance(result, int)


def test_match_unit_no_civic_dup_apt_returns_none(db_conn):
    """3034 Lechasseur apt '1' with no civic → building_only (None).

    Building 119 has 4 sub-civic entrances (3034, 3038, 3052, 3054) each
    with an apt '1'. Without a civic to disambiguate, we refuse to guess.
    """
    row = db_conn.execute(
        "SELECT building_id FROM building WHERE adresse ILIKE '%3034%lechasseur%' LIMIT 1"
    ).fetchone()
    if row is None:
        pytest.skip("Lechasseur building not found")
    result = _match_unit(db_conn, row["building_id"], "1", frozenset())
    assert result is None, f"Expected None for ambiguous apt, got unit_id {result}"


def test_match_unit_chatelets_no_match_returns_none(db_conn):
    """#14931 pattern: submitted civic 3070 (not in DB for bldg 62) → None, not 3066."""
    row = db_conn.execute(
        """SELECT building_id FROM building
           WHERE adresse ILIKE '%3066%chatelets%' OR adresse ILIKE '%3066%chat%'
           LIMIT 1"""
    ).fetchone()
    if row is None:
        pytest.skip("Châtelets building not found")

    building_id = row["building_id"]
    # 3070 is not a civic in unit table for this building
    result = _match_unit(db_conn, building_id, "5", frozenset([3070]))
    assert result is None, f"Expected None (building_only), got unit_id {result}"
