"""GET /api/v1/requests/{id}/technician-suggestions — DB guardrails."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.tasks.repository import insert_task

_COORD = 4


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


@pytest.fixture
def ac(app, db_conn):
    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def sector_building(db_conn):
    row = db_conn.execute(
        "SELECT building_id, sector_id FROM building WHERE sector_id IS NOT NULL LIMIT 1"
    ).fetchone()
    assert row is not None
    return dict(row)


def _mk_tech(db_conn, *, initials: str, name: str, sector_id: int | None) -> int:
    eid = db_conn.execute(
        """
        INSERT INTO employee (initials, nom_employe, sector_id, is_active, employment_type)
        VALUES (%(i)s, %(n)s, %(s)s, true, 'staff')
        RETURNING employee_id
        """,
        {"i": initials, "n": name, "s": sector_id},
    ).fetchone()["employee_id"]
    db_conn.execute(
        "INSERT INTO employee_role (employee_id, role) VALUES (%s, 'technician') "
        "ON CONFLICT DO NOTHING",
        [eid],
    )
    return eid


def test_suggestions_sector_only_and_max_three(ac, db_conn, sector_building):
    bid, sid = sector_building["building_id"], sector_building["sector_id"]
    other_sid = db_conn.execute(
        "SELECT sector_id FROM sector WHERE sector_id <> %s LIMIT 1", [sid]
    ).fetchone()["sector_id"]

    in1 = _mk_tech(db_conn, initials="TSA", name="Tech A", sector_id=sid)
    in2 = _mk_tech(db_conn, initials="TSB", name="Tech B", sector_id=sid)
    in3 = _mk_tech(db_conn, initials="TSC", name="Tech C", sector_id=sid)
    in4 = _mk_tech(db_conn, initials="TSD", name="Tech D", sector_id=sid)
    out = _mk_tech(db_conn, initials="TSO", name="Tech Out", sector_id=other_sid)

    # History: A has most closed at building
    for n, eid in ((5, in1), (2, in2), (1, in3)):
        for _ in range(n):
            db_conn.execute(
                """
                INSERT INTO maintenance_request
                  (status, building_id, sector_id, assigned_employee_id, start_date, raw_title)
                VALUES ('closed', %s, %s, %s, CURRENT_DATE - 30, 'hist')
                """,
                [bid, sid, eid],
            )

    rid = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, raw_title)
        VALUES ('triaged', %s, %s, 'Suggest me') RETURNING request_id
        """,
        [bid, sid],
    ).fetchone()["request_id"]

    r = ac(_user(_COORD, "coordinator")).get(
        f"/api/v1/requests/{rid}/technician-suggestions"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [s["employee_id"] for s in body["suggestions"]]
    assert len(ids) <= 3
    assert out not in ids
    assert ids[0] == in1  # most history
    assert in4 not in ids or ids.index(in1) < ids.index(in4)


def test_suggestions_includes_a5_out_of_home_sector(ac, db_conn, sector_building):
    bid, sid = sector_building["building_id"], sector_building["sector_id"]
    other_sid = db_conn.execute(
        "SELECT sector_id FROM sector WHERE sector_id <> %s LIMIT 1", [sid]
    ).fetchone()["sector_id"]
    a5 = _mk_tech(db_conn, initials="TA5", name="A5 Tech", sector_id=other_sid)
    db_conn.execute(
        """
        INSERT INTO employee_building_assignment
          (employee_id, building_id, assignment_type, notes)
        VALUES (%s, %s, 'a5_dedicated', 'test')
        ON CONFLICT (employee_id, building_id) DO NOTHING
        """,
        [a5, bid],
    )
    rid = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, raw_title)
        VALUES ('triaged', %s, %s, 'A5 call') RETURNING request_id
        """,
        [bid, sid],
    ).fetchone()["request_id"]

    r = ac(_user(_COORD, "coordinator")).get(
        f"/api/v1/requests/{rid}/technician-suggestions"
    )
    assert r.status_code == 200
    ids = {s["employee_id"] for s in r.json()["suggestions"]}
    assert a5 in ids
    why = next(s["why"] for s in r.json()["suggestions"] if s["employee_id"] == a5)
    assert "Dédié" in why or "Dedicated" in why


def test_suggestions_en_route_flagged_not_excluded(ac, db_conn, sector_building):
    bid, sid = sector_building["building_id"], sector_building["sector_id"]
    busy = _mk_tech(db_conn, initials="TEN", name="En Route Tech", sector_id=sid)
    free = _mk_tech(db_conn, initials="TFR", name="Free Tech", sector_id=sid)
    # Same history so en_route soft-ranks below
    for eid in (busy, free):
        db_conn.execute(
            """
            INSERT INTO maintenance_request
              (status, building_id, sector_id, assigned_employee_id, start_date, raw_title)
            VALUES ('closed', %s, %s, %s, CURRENT_DATE - 10, 'hist')
            """,
            [bid, sid, eid],
        )
    # En route = an open visit on one of his tasks.
    busy_rid = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, raw_title)
        VALUES ('open', %s, %s, 'Busy elsewhere') RETURNING request_id
        """,
        [bid, sid],
    ).fetchone()["request_id"]
    busy_tid = insert_task(db_conn, request_id=busy_rid, description="Busy", status="en_route",
                           assigned_employee_id=busy,
                           accepted_at=datetime.now(timezone.utc))["task_id"]
    db_conn.execute(
        "INSERT INTO request_visit (request_id, task_id, employee_id) VALUES (%s, %s, %s)",
        [busy_rid, busy_tid, busy],
    )
    rid = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, raw_title)
        VALUES ('triaged', %s, %s, 'Need someone') RETURNING request_id
        """,
        [bid, sid],
    ).fetchone()["request_id"]

    r = ac(_user(_COORD, "coordinator")).get(
        f"/api/v1/requests/{rid}/technician-suggestions"
    )
    assert r.status_code == 200
    sugg = r.json()["suggestions"]
    by_id = {s["employee_id"]: s for s in sugg}
    assert busy in by_id
    assert by_id[busy]["is_en_route"] is True
    assert "En route" in by_id[busy]["why"] or "en route" in by_id[busy]["why"].lower()
    # Free peer with same history ranks above en_route
    assert sugg[0]["employee_id"] == free


def test_suggestions_tech_forbidden(ac, db_conn, sector_building):
    bid, sid = sector_building["building_id"], sector_building["sector_id"]
    rid = db_conn.execute(
        """
        INSERT INTO maintenance_request (status, building_id, sector_id, raw_title)
        VALUES ('triaged', %s, %s, 'Nope') RETURNING request_id
        """,
        [bid, sid],
    ).fetchone()["request_id"]
    r = ac(_user(14, "technician")).get(
        f"/api/v1/requests/{rid}/technician-suggestions"
    )
    assert r.status_code == 403
