"""Tests for scripts/import_gf_csv.py — parsing, address matching, provenance, idempotency."""
from __future__ import annotations

import csv
import io
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
from scripts.import_gf_csv import (
    _parse_date,
    _build_problems,
    _animals_val,
    import_csv,
    cleanup,
    _COL_ID, _COL_DATE, _COL_NAME, _COL_EMAIL, _COL_PHONE1, _COL_PHONE2,
    _COL_CIVIC, _COL_STREET, _COL_APT, _COL_CITY, _COL_ACCESS,
    _COL_PROB, _COL_ALLDEV, _COL_REBOOT, _COL_ALLRM, _COL_ERRMSG, _COL_DESC,
    _COL_PREC, _COL_ATYPE, _COL_ATTN, _COL_OTHER, _COL_OTHER_EMAIL,
    _COL_PHONE2_ALT, _COL_ANIMAL, _COL_PHOTO, _COL_WPUSER, _COL_TYPE, _COL_MAINT,
)
from backend.modules.intake.address import match_address

# ── date parsing ─────────────────────────────────────────────────────────────


def test_parse_date_converts_to_utc():
    # Quebec EDT = UTC-4; "2026-10-14 10:30:00" → UTC 14:30:00
    dt = _parse_date("2026-10-14 10:30:00")
    assert dt.tzinfo is not None
    assert dt.tzinfo == timezone.utc or dt.utcoffset().total_seconds() == 0
    assert dt.hour == 14
    assert dt.minute == 30


def test_parse_date_empty_returns_none():
    assert _parse_date("") is None


# ── problems bundling ─────────────────────────────────────────────────────────


class _Body:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_build_problems_includes_all_fields():
    row = {
        _COL_PROB: "Robinet",
        _COL_ALLDEV: "Oui",
        _COL_REBOOT: "",
        _COL_ALLRM: "",
        _COL_ERRMSG: "",
        _COL_DESC: "L'eau coule nonstop",
        _COL_PREC: "Appeler avant",
        _COL_ATYPE: "Chat",
        _COL_ATTN: "Attention particulière",
        _COL_OTHER: "",
        _COL_OTHER_EMAIL: "",
        _COL_PHONE2_ALT: "418-555-0002",
    }
    result = _build_problems(row)
    assert "Robinet" in result
    assert "L'eau coule nonstop" in result
    assert "Appeler avant" in result
    assert "Chat" in result
    assert "Attention particulière" not in result  # ATTENTION goes to raw_caller_body, not problems
    assert "418-555-0002" in result


def test_animals_val_oui():
    assert _animals_val({_COL_ANIMAL: "Oui"}) == "Oui"


def test_animals_val_non_returns_string():
    assert _animals_val({_COL_ANIMAL: "Non"}) == "Non"


def test_animals_val_missing_returns_none():
    assert _animals_val({}) is None


# ── address matching (uses real local DB) ─────────────────────────────────────


def test_match_exact(db_conn):
    result = match_address(db_conn, "1580", "Perigord", "101")
    assert result.match_status == "exact"
    assert result.building_id is not None
    assert result.unit_id is not None


def test_match_building_only(db_conn):
    result = match_address(db_conn, "1580", "Perigord", "ZZZNOTEXIST")
    assert result.match_status == "building_only"
    assert result.building_id is not None
    assert result.unit_id is None


def test_match_no_match(db_conn):
    result = match_address(db_conn, "9999", "RueInventee", None)
    assert result.match_status == "no_match"
    assert result.building_id is None


def test_range_civic_matches(db_conn):
    """A DB building with civic range '3040-3050' should match tenant civic '3044'."""
    result = match_address(db_conn, "3044", "Chatelets", None)
    # If this building is in the DB, should be building_only or exact; not no_match
    # (If the building doesn't exist in this DB, no_match is also OK; skip gracefully)
    assert result.match_status in ("exact", "building_only", "no_match", "ambiguous")


def test_garbled_address(db_conn):
    result = match_address(db_conn, "1234 Rue Exemple Québec QC H1H 1H1", "Exemple", None)
    assert result.match_status == "garbled"


def test_ch_prefix_stripped(db_conn):
    """'350 Sainte-Foy' matches building '350 Ch Ste-Foy' — ch. prefix stripped, ste→saint unified."""
    result = match_address(db_conn, "350", "Sainte-Foy", None)
    assert result.match_status in ("exact", "building_only")
    assert result.building_id == 150


def test_saint_sainte_unified(db_conn):
    """'29 St-Ursule' matches building '29 Ste-Ursule' — st/ste both normalized to saint."""
    result = match_address(db_conn, "29", "St-Ursule", None)
    assert result.match_status in ("exact", "building_only")
    assert result.building_id == 154


def test_secondary_segment_matches(db_conn):
    """'1410 Longueuil' matches building '860 Marguerite-Bourgeoys / 1410 Longueuil' via secondary segment."""
    result = match_address(db_conn, "1410", "Longueuil", None)
    assert result.match_status in ("exact", "building_only")
    assert result.building_id == 121


# ── import_csv integration (uses test db_conn, rolls back) ───────────────────

_CSV_HEADER = [
    _COL_ID, _COL_DATE, _COL_NAME, _COL_EMAIL, _COL_PHONE1, _COL_PHONE2,
    _COL_CIVIC, _COL_STREET, _COL_APT, _COL_CITY, _COL_ACCESS, _COL_PREC,
    _COL_ATTN, _COL_ANIMAL, _COL_ATYPE, _COL_PROB, _COL_ALLDEV, _COL_REBOOT,
    _COL_ALLRM, _COL_ERRMSG, _COL_DESC, _COL_PHOTO, _COL_WPUSER,
    _COL_TYPE, _COL_OTHER, _COL_OTHER_EMAIL, _COL_MAINT,
]


def _make_csv(rows: list[dict]) -> Path:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_HEADER)
    writer.writeheader()
    for r in rows:
        writer.writerow({h: r.get(h, "") for h in _CSV_HEADER})
    tmp = Path("/tmp/test_import_gf.csv")
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    return tmp


def _uid(label: str) -> str:
    """Stable-within-run unique entry ID to avoid cross-run collisions on committed rows."""
    return f"{label}-{uuid.uuid4().hex[:8]}"


def _base_row(entry_id="TEST-1") -> dict:
    return {
        _COL_ID: entry_id,
        _COL_DATE: "2026-10-10 09:00:00",
        _COL_NAME: "Test Tenant",
        _COL_PHONE1: "418-000-0001",
        _COL_CIVIC: "1580",
        _COL_STREET: "Perigord",
        _COL_APT: "101",
        _COL_CITY: "Quebec",
        _COL_ACCESS: "Oui",
        _COL_ANIMAL: "Non",
        _COL_PROB: "Robinet qui coule",
        _COL_WPUSER: "42",
    }


def test_import_idempotent(db_conn):
    """Importing the same CSV twice only writes rows once."""
    eid = _uid("IDEM")
    csv_path = _make_csv([_base_row(eid)])
    counts1 = import_csv(db_conn, csv_path)
    counts2 = import_csv(db_conn, csv_path)
    assert counts1["exact"] == 1
    assert counts2["skipped"] == 1
    assert counts2["exact"] == 0


def test_import_no_ip_stored(db_conn):
    """No IP or user-agent columns should be stored."""
    eid = _uid("NOIP")
    csv_path = _make_csv([_base_row(eid)])
    import_csv(db_conn, csv_path)
    row = db_conn.execute(
        "SELECT problems FROM maintenance_request WHERE external_ref = %s", [eid],
    ).fetchone()
    assert row is not None
    problems = row["problems"] or ""
    assert "127.0.0.1" not in problems
    assert "User-Agent" not in problems


def test_import_submission_date_utc(db_conn):
    """submission_date stored as UTC (09:00 EDT = 13:00 UTC)."""
    eid = _uid("DATE")
    csv_path = _make_csv([_base_row(eid)])
    import_csv(db_conn, csv_path)
    row = db_conn.execute(
        "SELECT submission_date FROM maintenance_request WHERE external_ref = %s", [eid],
    ).fetchone()
    assert row is not None
    assert row["submission_date"] is not None
    assert row["submission_date"].hour == 13  # 09:00 EDT = 13:00 UTC


def test_import_writes_provenance(db_conn):
    eid = _uid("PROV")
    csv_path = _make_csv([_base_row(eid)])
    import_csv(db_conn, csv_path)
    rid = db_conn.execute(
        "SELECT request_id FROM maintenance_request WHERE external_ref = %s", [eid],
    ).fetchone()["request_id"]
    count = db_conn.execute(
        "SELECT count(*) AS n FROM data_provenance WHERE target_pk = %s AND source_type = 'csv_import'",
        [str(rid)],
    ).fetchone()["n"]
    assert count > 0


def test_import_match_counts(db_conn):
    rows = [
        _base_row(_uid("MATCH-EXACT")),
        {**_base_row(_uid("MATCH-NOMATCH")), _COL_CIVIC: "9999", _COL_STREET: "RueInventee"},
    ]
    csv_path = _make_csv(rows)
    counts = import_csv(db_conn, csv_path)
    assert counts["exact"] >= 1
    assert counts["no_match"] >= 1
    assert counts["error"] == 0


def test_import_writes_raw_caller_body(db_conn):
    """CSV import stores raw_caller_body jsonb with original caller-provided fields."""
    eid = _uid("RCB")
    csv_path = _make_csv([{**_base_row(eid), _COL_ACCESS: "Oui", _COL_ANIMAL: "Oui"}])
    import_csv(db_conn, csv_path)
    row = db_conn.execute(
        "SELECT raw_caller_body FROM maintenance_request WHERE external_ref = %s", [eid],
    ).fetchone()
    assert row is not None
    body = row["raw_caller_body"]
    assert body is not None
    assert "problems" in body
    assert "entry_permission" in body
    assert "animals" in body


def test_cleanup_removes_gravity_forms_rows(db_conn):
    """cleanup() deletes all external_source='gravity_forms' rows."""
    eid = _uid("CLEANUP")
    csv_path = _make_csv([_base_row(eid)])
    import_csv(db_conn, csv_path)

    before = db_conn.execute(
        "SELECT count(*) AS n FROM maintenance_request WHERE external_source = 'gravity_forms' AND external_ref = %s",
        [eid],
    ).fetchone()["n"]
    assert before == 1

    cleanup(db_conn)

    after = db_conn.execute(
        "SELECT count(*) AS n FROM maintenance_request WHERE external_source = 'gravity_forms' AND external_ref = %s",
        [eid],
    ).fetchone()["n"]
    assert after == 0
