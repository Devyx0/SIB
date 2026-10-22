"""SKILL §4.2 mechanical exclusions — Python matcher + output gate."""
from __future__ import annotations

from datetime import date

from backend.triage.context_builder import is_mechanically_excluded
from backend.triage.output_contract import validate


def test_exclusion_matcher_admin_prefix():
    assert is_mechanically_excluded("! Liste immeuble")
    assert not is_mechanically_excluded("Fuite lavabo")


def test_exclusion_matcher_recurring_patterns():
    assert is_mechanically_excluded("Pose abri d'hiver")
    assert is_mechanically_excluded("Tapis hiver entrée")
    assert is_mechanically_excluded("Lavage vitre façade")
    assert is_mechanically_excluded("Inspection incendie annuelle")
    assert is_mechanically_excluded("Liste choses à faire — Châtelets")
    assert is_mechanically_excluded("Remplacement batterie panneau")
    assert is_mechanically_excluded("Entretien compresseur")
    assert not is_mechanically_excluded("Fuite sous lavabo")


def test_gate_rejects_synergy_citing_excluded(db_conn):
    loc = db_conn.execute(
        """
        SELECT u.unit_id, u.building_id, b.sector_id
        FROM unit u JOIN building b ON b.building_id = u.building_id
        WHERE b.sector_id IS NOT NULL LIMIT 1
        """
    ).fetchone()
    if loc is None:
        sector_id = db_conn.execute(
            "INSERT INTO sector (territoire, color_code) VALUES ('TEST-EXCL', '#111') "
            "RETURNING sector_id"
        ).fetchone()["sector_id"]
        project_id = db_conn.execute(
            "INSERT INTO project (nom_unique_projet) VALUES ('TestExcl') RETURNING project_id"
        ).fetchone()["project_id"]
        building_id = db_conn.execute(
            "INSERT INTO building (project_id, sector_id, adresse) "
            "VALUES (%(p)s, %(s)s, '2 rue Excl') RETURNING building_id",
            {"p": project_id, "s": sector_id},
        ).fetchone()["building_id"]
        unit_id = db_conn.execute(
            "INSERT INTO unit (building_id, rue, numero_appartement) "
            "VALUES (%(b)s, 'rue Excl', '1') RETURNING unit_id",
            {"b": building_id},
        ).fetchone()["unit_id"]
        loc = {"unit_id": unit_id, "building_id": building_id, "sector_id": sector_id}
    excluded = db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, unit_id, sector_id, raw_title, start_date)
        VALUES ('triaged', %(b)s, %(u)s, %(s)s, '! Admin building list', %(d)s)
        RETURNING request_id
        """,
        {
            "b": loc["building_id"], "u": loc["unit_id"],
            "s": loc["sector_id"], "d": date.today(),
        },
    ).fetchone()["request_id"]
    incoming = db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, unit_id, sector_id, raw_title, start_date)
        VALUES ('intake_received', %(b)s, %(u)s, %(s)s, 'Fuite', %(d)s)
        RETURNING request_id
        """,
        {
            "b": loc["building_id"], "u": loc["unit_id"],
            "s": loc["sector_id"], "d": date.today(),
        },
    ).fetchone()["request_id"]

    parsed = {
        "verdict": "single", "duplicate_of_request_id": None, "addition_to_request_id": None,
        "title": "Fuite", "problems": ["Fuite"],
        "entry_permission": None, "animals": None, "urgency_tier": None,
        "complexity_tier": "C1", "congestion_level": "N2",
        "time_estimate_bucket": "UNDER_30_MIN", "delegable_status": "YES",
        "report_status": "CAN_WAIT", "routing_rule": "A1", "subcontractor_name": None,
        "vendor_id": None, "synergy_request_ids": [excluded], "other_notes": None,
        "recommended_tasks": [{"description": "Réparer le robinet"}],
    }
    result, detail = validate(parsed, db_conn, incoming)
    assert result == "rejected_excluded_candidate"
    assert str(excluded) in (detail or "")
