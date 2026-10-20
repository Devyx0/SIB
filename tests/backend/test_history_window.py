"""6-month history: unit + building scope, stated cap."""
from __future__ import annotations

from datetime import date

from backend.triage import context_builder as cb


def _pair(db_conn):
    row = db_conn.execute(
        """
        SELECT u1.unit_id AS unit_a, u2.unit_id AS unit_b,
               u1.building_id, b.sector_id
        FROM unit u1
        JOIN unit u2 ON u2.building_id = u1.building_id AND u2.unit_id <> u1.unit_id
        JOIN building b ON b.building_id = u1.building_id
        WHERE b.sector_id IS NOT NULL
        LIMIT 1
        """
    ).fetchone()
    if row:
        return row
    # Empty sib_test — seed a minimal project / sector / building / two units.
    sector_id = db_conn.execute(
        "INSERT INTO sector (territoire, color_code) VALUES ('TEST-HIST', '#000') "
        "RETURNING sector_id"
    ).fetchone()["sector_id"]
    project_id = db_conn.execute(
        "INSERT INTO project (nom_unique_projet) VALUES ('TestHist') RETURNING project_id"
    ).fetchone()["project_id"]
    building_id = db_conn.execute(
        "INSERT INTO building (project_id, sector_id, adresse) "
        "VALUES (%(p)s, %(s)s, '1 rue Test') RETURNING building_id",
        {"p": project_id, "s": sector_id},
    ).fetchone()["building_id"]
    u1 = db_conn.execute(
        "INSERT INTO unit (building_id, rue, numero_appartement) "
        "VALUES (%(b)s, 'rue Test', '101') RETURNING unit_id",
        {"b": building_id},
    ).fetchone()["unit_id"]
    u2 = db_conn.execute(
        "INSERT INTO unit (building_id, rue, numero_appartement) "
        "VALUES (%(b)s, 'rue Test', '102') RETURNING unit_id",
        {"b": building_id},
    ).fetchone()["unit_id"]
    return {
        "unit_a": u1, "unit_b": u2,
        "building_id": building_id, "sector_id": sector_id,
    }


def _ins(db_conn, *, unit_id, building_id, sector_id, title, cal="main"):
    return db_conn.execute(
        """
        INSERT INTO maintenance_request
            (status, building_id, unit_id, sector_id, raw_title, start_date, source_calendar)
        VALUES ('triaged', %(b)s, %(u)s, %(s)s, %(t)s, %(d)s, %(c)s)
        RETURNING request_id
        """,
        {
            "b": building_id, "u": unit_id, "s": sector_id,
            "t": title, "d": date.today(), "c": cal,
        },
    ).fetchone()["request_id"]


def test_history_includes_unit_and_building(db_conn):
    loc = _pair(db_conn)
    same = _ins(
        db_conn, unit_id=loc["unit_a"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite unite A",
    )
    other = _ins(
        db_conn, unit_id=loc["unit_b"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Fuite unite B",
    )
    incoming = _ins(
        db_conn, unit_id=loc["unit_a"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Nouveau appel A",
    )
    req = {
        "request_id": incoming, "unit_id": loc["unit_a"],
        "building_id": loc["building_id"], "start_date": date.today(),
        "raw_title": "Nouveau appel A", "problems": "lavabo",
    }
    with db_conn.cursor() as cur:
        hist = cb.history(cur, req)
    unit_ids = {r["request_id"] for r in hist["unit"]}
    bld_ids = {r["request_id"] for r in hist["building"]}
    assert same in unit_ids
    assert other not in unit_ids
    assert other in bld_ids
    assert same not in bld_ids  # already under unit
    assert hist["scope"] == "unit+building"
    assert hist["unit"][0]["source_calendar"] == "main"


def test_common_area_still_gets_building_history(db_conn):
    loc = _pair(db_conn)
    other = _ins(
        db_conn, unit_id=loc["unit_b"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Hall principal", cal="st_maj",
    )
    incoming = _ins(
        db_conn, unit_id=loc["unit_a"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Espace commun",
    )
    req = {
        "request_id": incoming, "unit_id": loc["unit_a"],
        "building_id": loc["building_id"], "start_date": date.today(),
        "raw_title": "Espace commun — fuite",
        "problems": "Fuite dans l'espace commun",
    }
    with db_conn.cursor() as cur:
        hist = cb.history(cur, req)
    bld_ids = {r["request_id"] for r in hist["building"]}
    assert other in bld_ids
    assert hist["scope"] == "unit+building"


def test_history_cap_is_reported(db_conn, monkeypatch):
    monkeypatch.setattr(cb, "_HISTORY_CAP", 1)
    loc = _pair(db_conn)
    _ins(
        db_conn, unit_id=loc["unit_a"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Ancien 1",
    )
    _ins(
        db_conn, unit_id=loc["unit_a"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Ancien 2",
    )
    incoming = _ins(
        db_conn, unit_id=loc["unit_a"], building_id=loc["building_id"],
        sector_id=loc["sector_id"], title="Nouveau",
    )
    req = {
        "request_id": incoming, "unit_id": loc["unit_a"],
        "building_id": loc["building_id"], "start_date": date.today(),
        "raw_title": "Nouveau", "problems": "",
    }
    with db_conn.cursor() as cur:
        hist = cb.history(cur, req)
    assert len(hist["unit"]) == 1
    assert hist["unit_omitted"] >= 1
