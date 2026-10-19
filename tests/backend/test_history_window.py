"""6-month history: unit scope, building scope for common areas, stated cap."""
from __future__ import annotations

from datetime import date

from backend.triage import context_builder as cb


def _pair(db_conn):
    return db_conn.execute(
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


def test_history_is_unit_scoped_by_default(db_conn):
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
    assert same in unit_ids
    assert other not in unit_ids
    assert hist["building"] == []
    assert hist["scope"] == "unit"
    assert hist["unit"][0]["source_calendar"] == "main"


def test_common_area_adds_building_history(db_conn):
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
