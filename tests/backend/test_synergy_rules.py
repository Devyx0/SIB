"""Internal synergy drops exclusive vendors; Saturday is not a shared visit day."""
from __future__ import annotations

from datetime import date

from backend.triage.context_builder import synergy
from backend.triage.service import _format_context


def _building(db_conn):
    return db_conn.execute(
        """
        SELECT building_id, sector_id, project_id
        FROM building
        WHERE project_id IS NOT NULL AND sector_id IS NOT NULL
        LIMIT 1
        """
    ).fetchone()


def _ins(db_conn, *, building_id, sector_id, project_id, title, start, sub=None):
    return db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, sector_id, project_id, raw_title, start_date, subcontractor_name)
        VALUES ('triaged', %(b)s, %(s)s, %(p)s, %(t)s, %(d)s, %(sub)s)
        RETURNING request_id
        """,
        {
            "b": building_id, "s": sector_id, "p": project_id,
            "t": title, "d": start, "sub": sub,
        },
    ).fetchone()["request_id"]


def test_internal_synergy_excludes_named_vendors(db_conn):
    loc = _building(db_conn)
    day = date(2026, 10, 20)  # Tuesday
    kept = _ins(
        db_conn, building_id=loc["building_id"], sector_id=loc["sector_id"],
        project_id=loc["project_id"], title="Peinture cage", start=day,
    )
    dropped = _ins(
        db_conn, building_id=loc["building_id"], sector_id=loc["sector_id"],
        project_id=loc["project_id"], title="Porte Duclos", start=day, sub="Duclos",
    )
    incoming = _ins(
        db_conn, building_id=loc["building_id"], sector_id=loc["sector_id"],
        project_id=loc["project_id"], title="Appel interne", start=day,
    )
    req = {
        "request_id": incoming,
        "project_id": loc["project_id"],
        "building_id": loc["building_id"],
        "start_date": day,
        "subcontractor_name": None,
        "vendor_id": None,
        "problems": "peinture",
    }
    with db_conn.cursor() as cur:
        result = synergy(cur, req)
    ids = {r["request_id"] for r in result["items"]}
    assert kept in ids
    assert dropped not in ids


def test_saturday_landing_is_flagged(db_conn):
    loc = _building(db_conn)
    saturday = date(2026, 10, 24)
    peer = _ins(
        db_conn, building_id=loc["building_id"], sector_id=loc["sector_id"],
        project_id=loc["project_id"], title="Autre samedi", start=saturday,
    )
    incoming = _ins(
        db_conn, building_id=loc["building_id"], sector_id=loc["sector_id"],
        project_id=loc["project_id"], title="Appel samedi", start=saturday,
    )
    req = {
        "request_id": incoming,
        "project_id": loc["project_id"],
        "building_id": loc["building_id"],
        "start_date": saturday,
        "subcontractor_name": None,
        "vendor_id": None,
        "problems": "",
    }
    with db_conn.cursor() as cur:
        result = synergy(cur, req)
    row = next(r for r in result["items"] if r["request_id"] == peer)
    assert row["saturday_landing"] is True


def test_prompt_caps_linked_synergy_at_five():
    items = [
        {
            "request_id": i,
            "start_date": date(2026, 10, 20),
            "raw_title": f"Call {i}",
            "status": "triaged",
            "saturday_landing": i == 1,
        }
        for i in range(1, 8)
    ]
    text = _format_context({
        "request": {"request_id": 1, "raw_title": "x", "start_date": date(2026, 10, 20)},
        "unit": None,
        "building": None,
        "duplicates": [],
        "synergy": {
            "scope": "project",
            "items": items,
            "total": 7,
            "narrowed_from": None,
            "link_cap": 5,
        },
        "history": {"unit": [], "building": [], "scope": "unit"},
        "photos": [],
    })
    assert "Liens (maximum 5)" in text
    assert "Compact sans lien (2)" in text
    assert "samedi, pas un argument de date" in text
