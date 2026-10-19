"""Portfolio browser: sector → project → building → unit → current tenant."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user

_TECH = 24
_COORD = 4
_DIRECTOR = 5


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


def _nxt(cur, table, col):
    cur.execute(f"SELECT COALESCE(MAX({col}), 0) + 1 AS n FROM {table}")
    return cur.fetchone()["n"]


def _seed(db_conn):
    """One unit with a current lease and named tenant, on an existing building."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.building_id, b.project_id, b.sector_id, p.nom_unique_projet
            FROM building b
            JOIN project p ON p.project_id = b.project_id
            WHERE b.sector_id IS NOT NULL
            LIMIT 1
            """
        )
        host = cur.fetchone()
        unit_id = _nxt(cur, "unit", "unit_id")
        lease_id = _nxt(cur, "lease", "lease_id")
        tenant_id = _nxt(cur, "tenant", "tenant_id")
        tenancy_id = _nxt(cur, "tenancy_record", "tenancy_id")
        cur.execute(
            """
            INSERT INTO unit (unit_id, building_id, rue, numero_appartement, grandeur)
            VALUES (%s, %s, '9, rue Portfolio', '404', '3 1/2')
            """,
            (unit_id, host["building_id"]),
        )
        cur.execute(
            """
            INSERT INTO lease (lease_id, unit_id, debut_bail, fin_bail, statut, langue_bail)
            VALUES (%s, %s, '2026-07-01', '2027-06-30', 'Actif', 'Français')
            """,
            (lease_id, unit_id),
        )
        cur.execute(
            """
            INSERT INTO tenant (tenant_id, nom_complet, telephone, courriel)
            VALUES (%s, 'Ada Portfolio', '4185550199', 'ada@example.test')
            """,
            (tenant_id,),
        )
        cur.execute(
            """
            INSERT INTO tenancy_record (tenancy_id, lease_id, tenant_id, capacite)
            VALUES (%s, %s, %s, 'named_on_lease')
            """,
            (tenancy_id, lease_id, tenant_id),
        )
    return {**host, "unit_id": unit_id, "lease_id": lease_id, "tenant_id": tenant_id}


def test_portfolio_403_technician(ac):
    r = ac(_user(_TECH, "technician")).get("/api/v1/portfolio/sectors")
    assert r.status_code == 403


def test_drill_sector_to_tenant(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))

    sectors = client.get("/api/v1/portfolio/sectors")
    assert sectors.status_code == 200
    listed = next(s for s in sectors.json() if s["sector_id"] == seed["sector_id"])
    # The seeded unit has a current lease with a tenant, so it counts as occupied.
    assert listed["unit_count"] >= listed["occupied_unit_count"] >= 1
    assert seed["nom_unique_projet"] in listed["top_projects"] or len(listed["top_projects"]) == 3

    sector = client.get(f"/api/v1/portfolio/sectors/{seed['sector_id']}")
    assert sector.status_code == 200
    body = sector.json()
    assert any(p["project_id"] == seed["project_id"] for p in body["projects"])

    project = client.get(
        f"/api/v1/portfolio/projects/{seed['project_id']}",
        params={"sector_id": seed["sector_id"]},
    )
    assert project.status_code == 200
    buildings = project.json()["buildings"]
    assert any(b["building_id"] == seed["building_id"] for b in buildings)

    building = client.get(f"/api/v1/portfolio/buildings/{seed['building_id']}")
    assert building.status_code == 200
    unit = next(u for u in building.json()["units"] if u["unit_id"] == seed["unit_id"])
    assert unit["tenant_name"] == "Ada Portfolio"
    assert unit["occupant_count"] == 1
    assert unit["numero_appartement"] == "404"

    detail = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["project_id"] == seed["project_id"]
    assert payload["lease"]["statut"] == "Actif"
    assert payload["lease"]["debut_bail"] == "2026-07-01"
    assert payload["tenants"] == [{
        "tenant_id": seed["tenant_id"],
        "nom_complet": "Ada Portfolio",
        "telephone": "4185550199",
        "telephone_international": None,
        "courriel": "ada@example.test",
        "capacite": "named_on_lease",
        "has_turnover": False,
    }]


def test_ended_lease_is_not_current_tenant(ac, db_conn):
    seed = _seed(db_conn)
    db_conn.execute(
        "UPDATE lease SET debut_bail = '2020-01-01', fin_bail = '2020-12-31' WHERE lease_id = %s",
        (seed["lease_id"],),
    )
    client = ac(_user(_DIRECTOR, "director"))
    building = client.get(f"/api/v1/portfolio/buildings/{seed['building_id']}")
    unit = next(u for u in building.json()["units"] if u["unit_id"] == seed["unit_id"])
    assert unit["tenant_name"] is None
    assert unit["occupant_count"] == 0
    detail = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}")
    assert detail.json()["lease"] is None
    assert detail.json()["tenants"] == []


def test_missing_unit_404(ac):
    r = ac(_user(_DIRECTOR, "director")).get("/api/v1/portfolio/units/99999999")
    assert r.status_code == 404


def test_coordinator_cannot_see_other_sector(ac, db_conn):
    sectors = db_conn.execute("SELECT sector_id FROM sector ORDER BY sector_id").fetchall()
    if len(sectors) < 2:
        pytest.skip("need two sectors")
    keep, hide = sectors[0]["sector_id"], sectors[1]["sector_id"]
    db_conn.execute("DELETE FROM employee_building_assignment WHERE employee_id = %s", (_COORD,))
    db_conn.execute("UPDATE employee SET sector_id = %s WHERE employee_id = %s", (keep, _COORD))

    client = ac(_user(_COORD, "coordinator"))
    listed = client.get("/api/v1/portfolio/sectors")
    assert listed.status_code == 200
    ids = {s["sector_id"] for s in listed.json()}
    assert keep in ids
    assert hide not in ids
    assert client.get(f"/api/v1/portfolio/sectors/{hide}").status_code == 404


def _seed_turnover(db_conn, unit_id, **cols) -> int:
    with db_conn.cursor() as cur:
        turnover_id = _nxt(cur, "unit_turnover", "turnover_id")
        names = ", ".join(["turnover_id", "unit_id", *cols])
        marks = ", ".join(["%s"] * (2 + len(cols)))
        cur.execute(f"INSERT INTO unit_turnover ({names}) VALUES ({marks})",
                    (turnover_id, unit_id, *cols.values()))
    return turnover_id


def test_tenant_turnover_matches_by_id_and_name(ac, db_conn):
    seed = _seed(db_conn)
    by_id = _seed_turnover(db_conn, seed["unit_id"], incoming_tenant_id=seed["tenant_id"],
                           lease_start_date="2026-07-01", outgoing_tenant_name_raw="Old Tenant")
    by_name = _seed_turnover(db_conn, seed["unit_id"], lease_end_date="2027-06-30",
                             outgoing_tenant_name_raw="Ada Portfolio\nBob Roommate")
    other = _seed_turnover(db_conn, seed["unit_id"], lease_start_date="2020-07-01",
                           incoming_tenant_name_raw="Someone Else")

    r = ac(_user(_DIRECTOR, "director")).get(
        f"/api/v1/portfolio/units/{seed['unit_id']}/tenants/{seed['tenant_id']}/turnover")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant"]["nom_complet"] == "Ada Portfolio"
    roles = {t["turnover_id"]: t["tenant_role"] for t in body["turnovers"]}
    assert roles == {by_id: "incoming", by_name: "outgoing"}
    assert [t["turnover_id"] for t in body["other_turnovers"]] == [other]
    incoming = next(t for t in body["turnovers"] if t["turnover_id"] == by_id)
    assert incoming["incoming_tenant_name"] == "Ada Portfolio"
    assert incoming["settlement"] is None and incoming["furniture"] == []

    unit = ac(_user(_DIRECTOR, "director")).get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    assert [t["has_turnover"] for t in unit["tenants"]] == [True]


def test_tenant_turnover_404_for_tenant_not_on_unit(ac, db_conn):
    seed = _seed(db_conn)
    other = _seed(db_conn)
    r = ac(_user(_DIRECTOR, "director")).get(
        f"/api/v1/portfolio/units/{seed['unit_id']}/tenants/{other['tenant_id']}/turnover")
    assert r.status_code == 404


def test_tenant_turnover_403_technician(ac):
    r = ac(_user(_TECH, "technician")).get("/api/v1/portfolio/units/1/tenants/1/turnover")
    assert r.status_code == 403
