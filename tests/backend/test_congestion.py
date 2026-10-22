"""Congestion N1–N5 is computed from open calls in the sector."""
from __future__ import annotations

from datetime import date

from backend.triage.context_builder import congestion, congestion_level_for_count
from backend.triage.output_contract import validate


def test_bands():
    assert congestion_level_for_count(0) == "N1"
    assert congestion_level_for_count(15) == "N1"
    assert congestion_level_for_count(16) == "N2"
    assert congestion_level_for_count(40) == "N2"
    assert congestion_level_for_count(41) == "N3"
    assert congestion_level_for_count(80) == "N3"
    assert congestion_level_for_count(81) == "N4"
    assert congestion_level_for_count(150) == "N4"
    assert congestion_level_for_count(151) == "N5"


def test_sector_open_count(db_conn):
    loc = db_conn.execute(
        "SELECT building_id, sector_id FROM building WHERE sector_id IS NOT NULL LIMIT 1"
    ).fetchone()
    for _ in range(3):
        db_conn.execute(
            """
            INSERT INTO maintenance_request (status, building_id, sector_id, raw_title, start_date)
            VALUES ('triaged', %(b)s, %(s)s, 'open backlog', %(d)s)
            """,
            {"b": loc["building_id"], "s": loc["sector_id"], "d": date.today()},
        )
    incoming = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, raw_title, start_date)
        VALUES ('intake_received', %(b)s, %(s)s, 'this call', %(d)s)
        RETURNING request_id
        """,
        {"b": loc["building_id"], "s": loc["sector_id"], "d": date.today()},
    ).fetchone()["request_id"]
    req = {"request_id": incoming, "sector_id": loc["sector_id"]}
    with db_conn.cursor() as cur:
        result = congestion(cur, req)
    assert result["open_count"] >= 3
    assert result["level"] == congestion_level_for_count(result["open_count"])


def test_gate_rejects_wrong_level():
    parsed = {
        "verdict": "single", "duplicate_of_request_id": None, "addition_to_request_id": None,
        "title": "Robinet qui fuit", "problems": ["Fuite sous le lavabo"],
        "entry_permission": None, "animals": None, "urgency_tier": None,
        "complexity_tier": "C1", "congestion_level": "N5",
        "time_estimate_bucket": "UNDER_30_MIN", "delegable_status": "YES",
        "report_status": "CAN_WAIT", "routing_rule": "A1", "subcontractor_name": None,
        "vendor_id": None, "synergy_request_ids": [], "other_notes": None,
        "recommended_tasks": [{"description": "Réparer le robinet"}],
    }
    result, _ = validate(parsed, None, 1, expected_congestion="N2")
    assert result == "rejected_congestion"
    ok, _ = validate(parsed, None, 1, expected_congestion="N5")
    assert ok == "accepted"
