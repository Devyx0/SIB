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


def _ensure_staff(cur) -> None:
    """Hard-coded employee ids used by this module's role fixtures."""
    for eid, name, role in (
        (_TECH, "Tech Portfolio", "technician"),
        (_COORD, "Coord Portfolio", "coordinator"),
        (_DIRECTOR, "Dir Portfolio", "director"),
    ):
        cur.execute(
            """
            INSERT INTO employee (employee_id, initials, nom_employe, is_active, employment_type)
            VALUES (%s, %s, %s, true, 'staff')
            ON CONFLICT (employee_id) DO NOTHING
            """,
            (eid, f"P{eid}", name),
        )
        cur.execute(
            """
            INSERT INTO employee_role (employee_id, role) VALUES (%s, %s)
            ON CONFLICT (employee_id, role) DO NOTHING
            """,
            (eid, role),
        )


def _ensure_host(cur) -> dict:
    """A building with a sector, creating the hierarchy when sib_test is empty."""
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
    if host is not None:
        return dict(host)

    sector_id = _nxt(cur, "sector", "sector_id")
    project_id = _nxt(cur, "project", "project_id")
    building_id = _nxt(cur, "building", "building_id")
    cur.execute(
        "INSERT INTO sector (sector_id, territoire, color_code) VALUES (%s, 'Portfolio-A', '#abc')",
        (sector_id,),
    )
    # Second sector so ACL / scope tests can reassign the coordinator.
    other_sector = sector_id + 1
    cur.execute(
        """
        INSERT INTO sector (sector_id, territoire, color_code)
        SELECT %s, 'Portfolio-B', '#def'
        WHERE NOT EXISTS (SELECT 1 FROM sector WHERE sector_id = %s)
        """,
        (other_sector, other_sector),
    )
    cur.execute(
        "INSERT INTO project (project_id, nom_unique_projet) VALUES (%s, 'Portfolio Project')",
        (project_id,),
    )
    cur.execute(
        """
        INSERT INTO building (building_id, project_id, sector_id, adresse)
        VALUES (%s, %s, %s, '100 rue Portfolio')
        """,
        (building_id, project_id, sector_id),
    )
    return {
        "building_id": building_id,
        "project_id": project_id,
        "sector_id": sector_id,
        "nom_unique_projet": "Portfolio Project",
    }


def _seed(db_conn):
    """One unit with a current lease and named tenant, on an existing building."""
    with db_conn.cursor() as cur:
        _ensure_staff(cur)
        host = _ensure_host(cur)
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
    return {
        **host,
        "unit_id": unit_id,
        "lease_id": lease_id,
        "tenant_id": tenant_id,
        "tenancy_id": tenancy_id,
    }


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
    assert unit["tenant_names"] == ["Ada Portfolio"]
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
        "tenancy_id": seed["tenancy_id"],
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
    assert unit["tenant_names"] == []
    assert unit["occupant_count"] == 0
    detail = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}")
    assert detail.json()["lease"] is None
    assert detail.json()["tenants"] == []


def _add_occupant(db_conn, lease_id: int, name: str, capacite: str = "named_on_lease") -> int:
    with db_conn.cursor() as cur:
        tenant_id = _nxt(cur, "tenant", "tenant_id")
        cur.execute("INSERT INTO tenant (tenant_id, nom_complet) VALUES (%s, %s)", (tenant_id, name))
        cur.execute(
            "INSERT INTO tenancy_record (tenancy_id, lease_id, tenant_id, capacite) VALUES (%s, %s, %s, %s)",
            (_nxt(cur, "tenancy_record", "tenancy_id"), lease_id, tenant_id, capacite),
        )
    return tenant_id


def test_unit_row_lists_every_occupant(ac, db_conn):
    seed = _seed(db_conn)
    _add_occupant(db_conn, seed["lease_id"], "Bob Roommate", "took_over")
    building = ac(_user(_DIRECTOR, "director")).get(f"/api/v1/portfolio/buildings/{seed['building_id']}")
    unit = next(u for u in building.json()["units"] if u["unit_id"] == seed["unit_id"])
    # Lease holder first, then whoever took over.
    assert unit["tenant_names"] == ["Ada Portfolio", "Bob Roommate"]
    assert unit["occupant_count"] == 2


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


# ── Search ────────────────────────────────────────────────────────────────────

def _set_fiche(db_conn, building_id: int, label: str, value: str) -> None:
    db_conn.execute(
        """
        UPDATE building
        SET raw_fiche_technique = COALESCE(
                CASE WHEN jsonb_typeof(raw_fiche_technique) = 'object' THEN raw_fiche_technique END,
                '{}'::jsonb) || jsonb_build_object(%s::text, %s::text)
        WHERE building_id = %s
        """,
        (label, value, building_id),
    )


def test_search_finds_paint_fact_by_address_and_label(ac, db_conn):
    seed = _seed(db_conn)
    db_conn.execute("UPDATE building SET adresse = '77 rue Zébulon' WHERE building_id = %s",
                    (seed["building_id"],))
    _set_fiche(db_conn, seed["building_id"], "Code de peinture", "SW 7005 Pure White")
    client = ac(_user(_DIRECTOR, "director"))

    # Accents and language don't matter: "paint" → peinture, "zebulon" → Zébulon.
    body = client.get("/api/v1/portfolio/search", params={"q": "paint zebulon"}).json()
    fact = next(f for f in body["facts"] if f["label"] == "Code de peinture")
    assert fact == {
        "building_id": seed["building_id"], "building_adresse": "77 rue Zébulon",
        "web_building_name": fact["web_building_name"], "label": "Code de peinture",
        "value": "SW 7005 Pure White", "source": "fiche",
    }
    # Every word must match: a word that matches nothing empties the facts.
    body = client.get("/api/v1/portfolio/search", params={"q": "peinture zebulon xyzzy"}).json()
    assert body["facts"] == []


def test_search_finds_unit_and_current_tenant(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    body = client.get("/api/v1/portfolio/search", params={"q": "ada portfolio"}).json()
    assert any(t["tenant_id"] == seed["tenant_id"] and t["unit_id"] == seed["unit_id"]
               for t in body["tenants"])
    assert any(u["unit_id"] == seed["unit_id"] for u in body["units"])
    # A tenant whose lease ended is no longer found.
    db_conn.execute("UPDATE lease SET fin_bail = '2020-12-31', debut_bail = '2020-01-01' WHERE lease_id = %s",
                    (seed["lease_id"],))
    body = client.get("/api/v1/portfolio/search", params={"q": "ada portfolio"}).json()
    assert all(t["tenant_id"] != seed["tenant_id"] for t in body["tenants"])


def test_search_short_query_returns_nothing(ac):
    body = ac(_user(_DIRECTOR, "director")).get("/api/v1/portfolio/search", params={"q": "a"}).json()
    assert body == {"q": "a", "units": [], "buildings": [], "projects": [], "tenants": [], "facts": []}


def test_search_scoped_to_coordinator_sectors(ac, db_conn):
    seed = _seed(db_conn)
    other = db_conn.execute(
        "SELECT sector_id FROM sector WHERE sector_id <> %s ORDER BY sector_id LIMIT 1",
        (seed["sector_id"],),
    ).fetchone()
    if other is None:
        pytest.skip("need two sectors")
    db_conn.execute("DELETE FROM employee_building_assignment WHERE employee_id = %s", (_COORD,))
    db_conn.execute("UPDATE employee SET sector_id = %s WHERE employee_id = %s", (other["sector_id"], _COORD))
    body = ac(_user(_COORD, "coordinator")).get(
        "/api/v1/portfolio/search", params={"q": "ada portfolio"}).json()
    assert all(u["unit_id"] != seed["unit_id"] for u in body["units"])
    assert all(t["tenant_id"] != seed["tenant_id"] for t in body["tenants"])


# ── Filtered unit list ────────────────────────────────────────────────────────

def test_units_list_vacancy_matches_sector_totals(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    sector = next(s for s in client.get("/api/v1/portfolio/sectors").json()
                  if s["sector_id"] == seed["sector_id"])
    vacant = client.get("/api/v1/portfolio/units",
                        params={"sector_id": seed["sector_id"], "occupancy": "vacant"}).json()
    assert vacant["total"] == sector["unit_count"] - sector["occupied_unit_count"]
    assert vacant["vacant_total"] == vacant["total"]
    assert all(u["occupant_count"] == 0 for u in vacant["items"])

    occupied = client.get("/api/v1/portfolio/units",
                          params={"building_id": seed["building_id"], "occupancy": "occupied"}).json()
    row = next(u for u in occupied["items"] if u["unit_id"] == seed["unit_id"])
    assert row["tenant_names"] == ["Ada Portfolio"]
    assert row["fin_bail"] == "2027-06-30"
    # The vacant count ignores the occupancy filter, so the chip keeps its number.
    assert occupied["vacant_total"] == client.get(
        "/api/v1/portfolio/units", params={"building_id": seed["building_id"]}).json()["vacant_total"]


def test_units_list_grandeur_and_lease_end_filters(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    page = client.get("/api/v1/portfolio/units",
                      params={"building_id": seed["building_id"], "grandeur": "3 1/2"}).json()
    assert "3 1/2" in page["grandeur_options"]
    assert all(u["grandeur"] == "3 1/2" for u in page["items"])
    assert any(u["unit_id"] == seed["unit_id"] for u in page["items"])

    db_conn.execute("UPDATE lease SET fin_bail = CURRENT_DATE + 20 WHERE lease_id = %s", (seed["lease_id"],))
    soon = client.get("/api/v1/portfolio/units",
                      params={"building_id": seed["building_id"], "lease_ending_within_days": 30}).json()
    assert seed["unit_id"] in [u["unit_id"] for u in soon["items"]]
    assert all(u["fin_bail"] is not None for u in soon["items"])


def test_units_list_pages(ac, db_conn):
    client = ac(_user(_DIRECTOR, "director"))
    first = client.get("/api/v1/portfolio/units", params={"page_size": 5}).json()
    if first["total"] <= 5:
        pytest.skip("need more than 5 units")
    second = client.get("/api/v1/portfolio/units", params={"page_size": 5, "page": 2}).json()
    assert len(first["items"]) == 5
    assert not {u["unit_id"] for u in first["items"]} & {u["unit_id"] for u in second["items"]}


# ── Filtered tenant list ──────────────────────────────────────────────────────

def test_tenants_list_returns_current_occupant(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    page = client.get("/api/v1/portfolio/tenants",
                      params={"building_id": seed["building_id"]}).json()
    row = next(t for t in page["items"] if t["tenant_id"] == seed["tenant_id"])
    assert row["nom_complet"] == "Ada Portfolio"
    assert row["telephone"] == "4185550199"
    assert row["courriel"] == "ada@example.test"
    assert row["capacite"] == "named_on_lease"
    assert row["unit_id"] == seed["unit_id"]
    assert row["building_id"] == seed["building_id"]
    assert row["project_id"] == seed["project_id"]
    assert row["sector_id"] == seed["sector_id"]
    assert row["lease_id"] == seed["lease_id"]
    assert row["lease_statut"] == "Actif"
    assert row["fin_bail"] == "2027-06-30"
    assert row["has_turnover"] is False
    assert page["total"] >= 1
    assert page["page"] == 1 and page["page_size"] == 50


def test_tenants_list_filters_and_search(ac, db_conn):
    seed = _seed(db_conn)
    roommate = _add_occupant(db_conn, seed["lease_id"], "Bob Roommate", "added_occupant")
    client = ac(_user(_DIRECTOR, "director"))

    named = client.get("/api/v1/portfolio/tenants", params={
        "unit_id": seed["unit_id"], "capacite": "named_on_lease",
    }).json()
    assert [t["tenant_id"] for t in named["items"]] == [seed["tenant_id"]]
    assert named["total"] == 1

    added = client.get("/api/v1/portfolio/tenants", params={
        "unit_id": seed["unit_id"], "capacite": "added_occupant",
    }).json()
    assert [t["tenant_id"] for t in added["items"]] == [roommate]

    by_q = client.get("/api/v1/portfolio/tenants", params={
        "building_id": seed["building_id"], "q": "ada portfolio",
    }).json()
    assert seed["tenant_id"] in [t["tenant_id"] for t in by_q["items"]]
    assert roommate not in [t["tenant_id"] for t in by_q["items"]]

    db_conn.execute("UPDATE lease SET fin_bail = CURRENT_DATE + 20 WHERE lease_id = %s", (seed["lease_id"],))
    soon = client.get("/api/v1/portfolio/tenants", params={
        "building_id": seed["building_id"], "lease_ending_within_days": 30,
    }).json()
    ids = {t["tenant_id"] for t in soon["items"]}
    assert seed["tenant_id"] in ids and roommate in ids
    assert all(t["fin_bail"] is not None for t in soon["items"])


def test_tenants_list_has_turnover_and_scope(ac, db_conn):
    seed = _seed(db_conn)
    _seed_turnover(db_conn, seed["unit_id"], incoming_tenant_id=seed["tenant_id"],
                   lease_start_date="2026-07-01")
    client = ac(_user(_DIRECTOR, "director"))
    page = client.get("/api/v1/portfolio/tenants",
                      params={"unit_id": seed["unit_id"]}).json()
    assert page["items"][0]["has_turnover"] is True

    other = db_conn.execute(
        "SELECT sector_id FROM sector WHERE sector_id <> %s LIMIT 1",
        (seed["sector_id"],),
    ).fetchone()
    if other is None:
        pytest.skip("need two sectors")
    db_conn.execute("DELETE FROM employee_building_assignment WHERE employee_id = %s", (_COORD,))
    db_conn.execute("UPDATE employee SET sector_id = %s WHERE employee_id = %s", (other["sector_id"], _COORD))
    scoped = ac(_user(_COORD, "coordinator")).get(
        "/api/v1/portfolio/tenants", params={"q": "ada portfolio"}).json()
    assert all(t["tenant_id"] != seed["tenant_id"] for t in scoped["items"])


def test_tenants_list_pages(ac, db_conn):
    client = ac(_user(_DIRECTOR, "director"))
    first = client.get("/api/v1/portfolio/tenants", params={"page_size": 5}).json()
    if first["total"] <= 5:
        pytest.skip("need more than 5 current tenants")
    second = client.get("/api/v1/portfolio/tenants", params={"page_size": 5, "page": 2}).json()
    assert len(first["items"]) == 5
    first_keys = {(t["tenant_id"], t["unit_id"]) for t in first["items"]}
    second_keys = {(t["tenant_id"], t["unit_id"]) for t in second["items"]}
    assert not first_keys & second_keys


def test_tenants_list_403_technician(ac):
    r = ac(_user(_TECH, "technician")).get("/api/v1/portfolio/tenants")
    assert r.status_code == 403


# ── Tenant / occupancy edits ──────────────────────────────────────────────────

def test_patch_tenant_contact(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    r = client.patch(f"/api/v1/portfolio/tenants/{seed['tenant_id']}", json={
        "changes": {"telephone": "4185550000", "courriel": "ada.new@example.test"},
        "current": {"telephone": "4185550199", "courriel": "ada@example.test"},
    })
    assert r.status_code == 204
    unit = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    t = unit["tenants"][0]
    assert t["telephone"] == "4185550000"
    assert t["courriel"] == "ada.new@example.test"


def test_patch_tenant_stale(ac, db_conn):
    seed = _seed(db_conn)
    r = ac(_user(_DIRECTOR, "director")).patch(f"/api/v1/portfolio/tenants/{seed['tenant_id']}", json={
        "changes": {"telephone": "4185550000"},
        "current": {"telephone": "wrong"},
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"


def test_patch_tenancy_capacite(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    r = client.patch(f"/api/v1/portfolio/tenancies/{seed['tenancy_id']}", json={
        "changes": {"capacite": "took_over", "reason_for_change": "correction"},
        "current": {"capacite": "named_on_lease"},
    })
    assert r.status_code == 204
    unit = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    assert unit["tenants"][0]["capacite"] == "took_over"
    assert unit["tenants"][0]["tenancy_id"] == seed["tenancy_id"]


def test_add_occupant(ac, db_conn):
    from backend.core.utils import today_local
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    r = client.post(f"/api/v1/portfolio/units/{seed['unit_id']}/occupants", json={
        "new_tenant": {"nom_complet": "Bob Roommate", "telephone": "4185551111"},
        "capacite": "added_occupant",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["tenant_id"] and body["tenancy_id"] and body["lease_id"] == seed["lease_id"]
    unit = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    names = {t["nom_complet"] for t in unit["tenants"]}
    assert names == {"Ada Portfolio", "Bob Roommate"}
    # Duplicate on same lease → conflict
    dup = client.post(f"/api/v1/portfolio/units/{seed['unit_id']}/occupants", json={
        "tenant_id": body["tenant_id"],
    })
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "ALREADY_ON_LEASE"
    assert today_local()  # sanity: helpers importable


def test_takeover_and_end_occupant(ac, db_conn):
    from backend.core.utils import today_local
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    today = today_local().isoformat()
    r = client.post(f"/api/v1/portfolio/units/{seed['unit_id']}/occupants/takeover", json={
        "outgoing_tenancy_id": seed["tenancy_id"],
        "new_tenant": {"nom_complet": "Cara Incoming"},
        "effective_date": today,
        "reason_for_change": "cession",
    })
    assert r.status_code == 201
    incoming = r.json()
    unit = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    assert len(unit["tenants"]) == 1
    assert unit["tenants"][0]["nom_complet"] == "Cara Incoming"
    assert unit["tenants"][0]["capacite"] == "took_over"
    assert unit["tenants"][0]["tenancy_id"] == incoming["tenancy_id"]

    end = client.post(
        f"/api/v1/portfolio/units/{seed['unit_id']}/occupants/{incoming['tenancy_id']}/end",
        json={"end_date": today, "current_end_date": None},
    )
    assert end.status_code == 204
    vacant = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    assert vacant["tenants"] == []


def test_end_and_start_lease(ac, db_conn):
    from backend.core.utils import today_local
    from datetime import timedelta
    seed = _seed(db_conn)
    client = ac(_user(_DIRECTOR, "director"))
    today = today_local()
    # Ending without matching current_fin_bail → stale
    stale = client.post(f"/api/v1/portfolio/units/{seed['unit_id']}/leases/end", json={
        "fin_bail": today.isoformat(),
        "statut": "Terminé",
        "current_fin_bail": "2099-01-01",
    })
    assert stale.status_code == 409

    end = client.post(f"/api/v1/portfolio/units/{seed['unit_id']}/leases/end", json={
        "fin_bail": today.isoformat(),
        "statut": "Terminé",
        "current_fin_bail": "2027-06-30",
        "close_tenancies": True,
    })
    assert end.status_code == 204
    unit = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    assert unit["lease"] is None
    assert unit["tenants"] == []

    # New lease without end_previous while somehow still current — already ended, so OK
    start = client.post(f"/api/v1/portfolio/units/{seed['unit_id']}/leases", json={
        "debut_bail": today.isoformat(),
        "fin_bail": (today + timedelta(days=365)).isoformat(),
        "statut": "Actif",
        "occupants": [{"new_tenant": {"nom_complet": "New Lease Holder"}, "capacite": "named_on_lease"}],
    })
    assert start.status_code == 201
    unit = client.get(f"/api/v1/portfolio/units/{seed['unit_id']}").json()
    assert unit["lease"]["lease_id"] == start.json()["lease_id"]
    assert unit["tenants"][0]["nom_complet"] == "New Lease Holder"


def test_start_lease_requires_end_previous(ac, db_conn):
    seed = _seed(db_conn)
    r = ac(_user(_DIRECTOR, "director")).post(
        f"/api/v1/portfolio/units/{seed['unit_id']}/leases",
        json={"debut_bail": "2026-08-01", "occupants": []},
    )
    assert r.status_code == 409


def test_occupancy_edits_403_technician(ac, db_conn):
    seed = _seed(db_conn)
    client = ac(_user(_TECH, "technician"))
    assert client.patch(f"/api/v1/portfolio/tenants/{seed['tenant_id']}", json={
        "changes": {"telephone": "1"}, "current": {"telephone": "4185550199"},
    }).status_code == 403
    assert client.post(f"/api/v1/portfolio/units/{seed['unit_id']}/occupants", json={
        "new_tenant": {"nom_complet": "X"},
    }).status_code == 403
