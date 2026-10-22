"""RRIA cross-checks: lease language, recent move-in, caller, missing lease."""
from __future__ import annotations

from datetime import date

from backend.triage.context_builder import rentroll_checks, unit_context
from backend.triage.output_contract import validate
from backend.triage.service import _format_context


def _base(**kw):
    d = {
        "verdict": "single",
        "duplicate_of_request_id": None,
        "addition_to_request_id": None,
        "title": "Robinet qui fuit",
        "problems": ["Fuite sous le lavabo"],
        "entry_permission": None,
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


def _ids(cur):
    def nxt(table, col):
        cur.execute(f"SELECT COALESCE(MAX({col}), 0) + 1 AS n FROM {table}")
        return cur.fetchone()["n"]

    return nxt("unit", "unit_id"), nxt("lease", "lease_id"), nxt("tenant", "tenant_id"), nxt("tenancy_record", "tenancy_id")


def _building(cur):
    cur.execute(
        """
        SELECT b.building_id, b.sector_id
        FROM building b
        WHERE b.sector_id IS NOT NULL
        LIMIT 1
        """
    )
    return cur.fetchone()


def _unit(cur, building_id, unit_id):
    cur.execute(
        """
        INSERT INTO unit (unit_id, building_id, rue, numero_appartement, grandeur)
        VALUES (%s, %s, 'Rue Test', '12', '4 1/2')
        """,
        (unit_id, building_id),
    )


def _lease(cur, lease_id, unit_id, *, debut, langue="Français", pets=False):
    cur.execute(
        """
        INSERT INTO lease (lease_id, unit_id, debut_bail, fin_bail, langue_bail, droit_animaux)
        VALUES (%s, %s, %s, '2027-08-31', %s, %s)
        """,
        (lease_id, unit_id, debut, langue, pets),
    )


def _occupant(cur, tenancy_id, lease_id, tenant_id, name):
    cur.execute(
        "INSERT INTO tenant (tenant_id, nom_complet, telephone) VALUES (%s, %s, '4185550100')",
        (tenant_id, name),
    )
    cur.execute(
        """
        INSERT INTO tenancy_record (tenancy_id, lease_id, tenant_id, capacite)
        VALUES (%s, %s, %s, 'named_on_lease')
        """,
        (tenancy_id, lease_id, tenant_id),
    )


def _request(cur, **cols):
    cur.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, unit_id, sector_id, raw_title, start_date,
             animals, caller_name, caller_tenant_id)
        VALUES (
            'intake_received'::request_status, %(building_id)s, %(unit_id)s, %(sector_id)s,
            'Fuite', %(start_date)s, %(animals)s, %(caller_name)s, %(caller_tenant_id)s
        )
        RETURNING request_id
        """,
        {
            "animals": None,
            "caller_name": None,
            "caller_tenant_id": None,
            "start_date": date(2026, 10, 19),
            **cols,
        },
    )
    rid = cur.fetchone()["request_id"]
    cur.execute("SELECT * FROM maintenance_request WHERE request_id = %s", (rid,))
    return cur.fetchone()


def _ctx(cur, req):
    unit = unit_context(cur, req)
    return {"request": req, "unit": unit, "rentroll": rentroll_checks(req, unit)}


def test_flags_for_recent_english_and_stranger(db_conn):
    with db_conn.cursor() as cur:
        b = _building(cur)
        unit_id, lease_id, tenant_id, tenancy_id = _ids(cur)
        _unit(cur, b["building_id"], unit_id)
        _lease(cur, lease_id, unit_id, debut=date(2026, 9, 1), langue="Anglais", pets=False)
        _occupant(cur, tenancy_id, lease_id, tenant_id, "Marie Curie")
        req = _request(
            cur,
            building_id=b["building_id"],
            unit_id=unit_id,
            sector_id=b["sector_id"],
            animals="Un chien",
            caller_name="Paul Autre",
        )
        ctx = _ctx(cur, req)

    rr = ctx["rentroll"]
    assert rr["lease_missing"] is False
    assert rr["recent_move_in"] is True
    assert rr["langue_en"] is True
    assert rr["caller_mismatch"] is True
    assert rr["required_notes"] == [
        "RÉQUÉRANT ABSENT",
        "emménagement récent",
        "bail anglais",
    ]
    text = _format_context(ctx)
    for phrase in rr["required_notes"]:
        assert phrase in text
    assert "Animaux" not in text
    assert "ÉCART ANIMAUX" not in text


def test_holder_needs_no_extra_notes(db_conn):
    with db_conn.cursor() as cur:
        b = _building(cur)
        unit_id, lease_id, tenant_id, tenancy_id = _ids(cur)
        _unit(cur, b["building_id"], unit_id)
        _lease(cur, lease_id, unit_id, debut=date(2020, 1, 1), langue="Français", pets=True)
        _occupant(cur, tenancy_id, lease_id, tenant_id, "Marie Curie")
        req = _request(
            cur,
            building_id=b["building_id"],
            unit_id=unit_id,
            sector_id=b["sector_id"],
            animals="Non",
            caller_name="Curie",
        )
        rr = rentroll_checks(req, unit_context(cur, req))

    assert rr["required_notes"] == []
    assert rr["recent_move_in"] is False
    assert rr["langue_en"] is False


def test_caller_tenant_id_counts_as_on_lease(db_conn):
    with db_conn.cursor() as cur:
        b = _building(cur)
        unit_id, lease_id, tenant_id, tenancy_id = _ids(cur)
        _unit(cur, b["building_id"], unit_id)
        _lease(cur, lease_id, unit_id, debut=date(2020, 1, 1))
        _occupant(cur, tenancy_id, lease_id, tenant_id, "Marie Curie")
        req = _request(
            cur,
            building_id=b["building_id"],
            unit_id=unit_id,
            sector_id=b["sector_id"],
            caller_name="Nom mal saisi",
            caller_tenant_id=tenant_id,
        )
        rr = rentroll_checks(req, unit_context(cur, req))
    assert rr["caller_mismatch"] is False


def test_vacant_unit(db_conn):
    with db_conn.cursor() as cur:
        b = _building(cur)
        unit_id, lease_id, _, _ = _ids(cur)
        _unit(cur, b["building_id"], unit_id)
        _lease(cur, lease_id, unit_id, debut=date(2020, 1, 1))
        req = _request(
            cur,
            building_id=b["building_id"],
            unit_id=unit_id,
            sector_id=b["sector_id"],
            caller_name="Quelqu'un",
        )
        rr = rentroll_checks(req, unit_context(cur, req))
    assert rr["vacant"] is True
    assert rr["caller_mismatch"] is False
    assert rr["required_notes"] == ["LOGEMENT VACANT"]


def test_missing_lease_blocks(db_conn):
    with db_conn.cursor() as cur:
        b = _building(cur)
        unit_id, _, _, _ = _ids(cur)
        _unit(cur, b["building_id"], unit_id)
        req = _request(
            cur,
            building_id=b["building_id"],
            unit_id=unit_id,
            sector_id=b["sector_id"],
        )
        rr = rentroll_checks(req, unit_context(cur, req))
    assert rr["lease_missing"] is True
    assert rr["required_notes"] == []


def test_common_area_skips_rentroll():
    rr = rentroll_checks({"unit_id": None, "animals": "chien", "caller_name": "X"}, None)
    assert rr["applies"] is False
    assert rr["lease_missing"] is False


def test_gate_requires_the_phrases(db_conn):
    result, detail = validate(
        _base(), db_conn, 1, required_notes=["RÉQUÉRANT ABSENT", "bail anglais"],
    )
    assert result == "rejected_rentroll", detail
    result, detail = validate(
        _base(other_notes="RÉQUÉRANT ABSENT. bail anglais."),
        db_conn, 1, required_notes=["RÉQUÉRANT ABSENT", "bail anglais"],
    )
    assert result == "accepted", detail


def test_missing_lease_sets_triage_clarify(db_conn):
    """triage() commits on its own connection. Clean the row up afterwards."""
    import psycopg2

    from backend.core.config import settings
    from backend.triage.service import triage

    with db_conn.cursor() as cur:
        b = _building(cur)
        unit_id, _, _, _ = _ids(cur)
    db_conn.rollback()

    c2 = psycopg2.connect(
        host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
        user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
        dbname=settings.LOCAL_DB_NAME,
    )
    rid = None
    try:
        with c2.cursor() as cur:
            cur.execute(
                """
                INSERT INTO unit (unit_id, building_id, rue, numero_appartement)
                VALUES (%s, %s, 'Rue Sans Bail', '1')
                """,
                (unit_id, b["building_id"]),
            )
            cur.execute(
                """
                INSERT INTO maintenance_request
                    (status, building_id, unit_id, sector_id, raw_title, start_date)
                VALUES ('intake_received', %s, %s, %s, 'Fuite', CURRENT_DATE)
                RETURNING request_id
                """,
                (b["building_id"], unit_id, b["sector_id"]),
            )
            rid = cur.fetchone()[0]
        c2.commit()

        result = triage(c2, rid)
        assert result["result"] == "triage_clarify", result

        with c2.cursor() as cur:
            cur.execute(
                "SELECT status::text, triage_summary FROM maintenance_request WHERE request_id = %s",
                (rid,),
            )
            status, summary = cur.fetchone()
        assert status == "triage_clarify"
        assert "bail" in (summary or "").lower()
    finally:
        with c2.cursor() as cur:
            if rid is not None:
                cur.execute("DELETE FROM maintenance_request WHERE request_id = %s", (rid,))
            cur.execute("DELETE FROM unit WHERE unit_id = %s", (unit_id,))
        c2.commit()
        c2.close()
