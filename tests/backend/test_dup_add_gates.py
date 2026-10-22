"""Gate 7: duplicate / addition must cite an open same-unit peer (rule 12)."""
from __future__ import annotations

from datetime import date

from backend.triage.output_contract import validate


def _base(**kw):
    d = {
        "verdict": "single",
        "duplicate_of_request_id": None,
        "addition_to_request_id": None,
        "title": "Robinet qui fuit",
        "problems": ["Fuite sous le lavabo"],
        "entry_permission": None,
        "animals": None,
        "urgency_tier": None,
        "complexity_tier": "C1",
        "congestion_level": "N2",
        "time_estimate_bucket": "UNDER_30_MIN",
        "delegable_status": "YES",
        "report_status": "CAN_WAIT",
        "routing_rule": "A1",
        "subcontractor_name": None,
        "vendor_id": None,
        "synergy_request_ids": [],
        "other_notes": None,
        "recommended_tasks": [{"description": "Réparer le robinet"}],
    }
    d.update(kw)
    return d


def _loc(db_conn):
    return db_conn.execute(
        """
        SELECT u.unit_id, u.building_id, b.sector_id
        FROM unit u
        JOIN building b ON b.building_id = u.building_id
        WHERE b.sector_id IS NOT NULL
        LIMIT 1
        """
    ).fetchone()


def _mk(db_conn, *, unit_id, building_id, sector_id, title, status="triaged"):
    return db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, unit_id, sector_id, raw_title, start_date)
        VALUES (%(st)s::request_status, %(b)s, %(u)s, %(s)s, %(t)s, %(d)s)
        RETURNING request_id
        """,
        {
            "st": status, "b": building_id, "u": unit_id, "s": sector_id,
            "t": title, "d": date.today(),
        },
    ).fetchone()["request_id"]


def test_duplicate_same_problem_accepted(db_conn):
    loc = _loc(db_conn)
    peer = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite sous le lavabo app",
    )
    incoming = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite lavabo",
    )
    parsed = _base(
        verdict="duplicate",
        duplicate_of_request_id=peer,
        title="DOUBLON POTENTIEL — Fuite sous le lavabo",
        problems=["Fuite sous le lavabo"],
    )
    result, detail = validate(parsed, db_conn, incoming)
    assert result == "accepted", detail


def test_duplicate_different_problem_rejected(db_conn):
    loc = _loc(db_conn)
    peer = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fourmis partout dans l'appartement",
    )
    incoming = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite sous le lavabo",
    )
    parsed = _base(
        verdict="duplicate",
        duplicate_of_request_id=peer,
        title="DOUBLON POTENTIEL — Fuite sous le lavabo",
        problems=["Fuite sous le lavabo"],
    )
    result, _ = validate(parsed, db_conn, incoming)
    assert result == "rejected_invalid_duplicate_ref"


def test_addition_different_problem_accepted(db_conn):
    loc = _loc(db_conn)
    peer = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fourmis partout dans l'appartement",
    )
    incoming = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite sous le lavabo",
    )
    parsed = _base(
        verdict="addition",
        addition_to_request_id=peer,
        title="Fuite sous le lavabo",
        problems=["Fuite sous le lavabo"],
    )
    result, detail = validate(parsed, db_conn, incoming)
    assert result == "accepted", detail


def test_addition_same_problem_rejected(db_conn):
    loc = _loc(db_conn)
    peer = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite sous le lavabo",
    )
    incoming = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite lavabo cuisine",
    )
    parsed = _base(
        verdict="addition",
        addition_to_request_id=peer,
        title="Fuite sous le lavabo",
        problems=["Fuite sous le lavabo"],
    )
    result, _ = validate(parsed, db_conn, incoming)
    assert result == "rejected_invalid_addition_ref"


def test_closed_peer_rejected(db_conn):
    loc = _loc(db_conn)
    peer = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite sous le lavabo", status="closed",
    )
    incoming = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite lavabo",
    )
    parsed = _base(
        verdict="duplicate",
        duplicate_of_request_id=peer,
        title="DOUBLON POTENTIEL — Fuite sous le lavabo",
        problems=["Fuite sous le lavabo"],
    )
    result, _ = validate(parsed, db_conn, incoming)
    assert result == "rejected_invalid_duplicate_ref"


def test_duplicates_query_open_only_and_labels(db_conn):
    from backend.triage.context_builder import duplicates

    loc = _loc(db_conn)
    open_same = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite sous le lavabo",
    )
    closed_peer = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite lavabo ancienne", status="closed",
    )
    open_diff = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fourmis partout",
    )
    incoming = _mk(
        db_conn, unit_id=loc["unit_id"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite sous le lavabo cuisine",
    )
    req = {
        "request_id": incoming,
        "unit_id": loc["unit_id"],
        "start_date": date.today(),
        "raw_title": "Fuite sous le lavabo cuisine",
        "problems": "Fuite sous le lavabo",
    }
    with db_conn.cursor() as cur:
        rows = duplicates(cur, req)
    ids = {r["request_id"] for r in rows}
    assert open_same in ids
    assert open_diff in ids
    assert closed_peer not in ids
    by_id = {r["request_id"]: r for r in rows}
    assert by_id[open_same]["problem_relation"] == "same_problem"
    assert by_id[open_diff]["problem_relation"] == "different_problem"
