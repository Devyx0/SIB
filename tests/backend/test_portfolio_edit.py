"""Portfolio editing: create / edit projects, buildings, units and building reference info."""
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


@pytest.fixture(autouse=True)
def _sync_sequences(db_conn):
    # Ingestion inserts explicit ids; mirror the migration's setval so app
    # inserts don't collide on a database where it hasn't run yet.
    for table, col in (("project", "project_id"), ("building", "building_id"), ("unit", "unit_id"),
                       ("building_paint_spec", "paint_spec_id"), ("building_document", "document_id"),
                       ("data_provenance", "provenance_id")):
        db_conn.execute(
            f"SELECT setval(pg_get_serial_sequence('public.{table}', '{col}'), "
            f"COALESCE((SELECT MAX({col}) FROM public.{table}), 0) + 1, false)"
        )


@pytest.fixture
def director(ac):
    return ac(_user(_DIRECTOR, "director"))


@pytest.fixture
def sector_id(db_conn):
    return db_conn.execute("SELECT sector_id FROM sector ORDER BY sector_id LIMIT 1").fetchone()["sector_id"]


def _provenance(db_conn, table: str, pk: int) -> dict[str, tuple]:
    rows = db_conn.execute(
        """
        SELECT target_column, previous_value, ingested_value, employee_id
        FROM data_provenance
        WHERE target_table = %s AND target_pk = %s AND source_type = 'app'
        ORDER BY provenance_id
        """,
        (table, str(pk)),
    ).fetchall()
    return {r["target_column"]: (r["previous_value"], r["ingested_value"], r["employee_id"]) for r in rows}


def _new_project(director, sector_id: int) -> dict:
    r = director.post("/api/v1/portfolio/projects", json={
        "nom_unique_projet": "Projet Test Édition",
        "accounting_project_number": "T-1",
        "first_building": {"sector_id": sector_id, "adresse": "1 rue de l'Essai", "ville": "Québec"},
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_create_project_building_and_unit(director, db_conn, sector_id):
    created = _new_project(director, sector_id)
    assert created["sector_id"] == sector_id

    sector = director.get(f"/api/v1/portfolio/sectors/{sector_id}").json()
    assert any(p["project_id"] == created["project_id"] for p in sector["projects"])
    building = director.get(f"/api/v1/portfolio/buildings/{created['building_id']}").json()
    assert building["adresse"] == "1 rue de l'Essai"
    assert building["actif_inactif"] == "Actif"
    assert building["units"] == []

    r = director.post("/api/v1/portfolio/units", json={
        "building_id": created["building_id"], "numero_appartement": "101",
        "grandeur": "4 1/2", "unique_unit_number": "ESSAI-101",
    })
    assert r.status_code == 201, r.text
    unit_id = r.json()["unit_id"]
    unit = director.get(f"/api/v1/portfolio/units/{unit_id}").json()
    assert unit["numero_appartement"] == "101"
    assert unit["unique_unit_number"] == "ESSAI-101"

    prov = _provenance(db_conn, "project", created["project_id"])
    assert prov["nom_unique_projet"] == (None, "Projet Test Édition", _DIRECTOR)
    assert _provenance(db_conn, "unit", unit_id)["grandeur"] == (None, "4 1/2", _DIRECTOR)


def test_duplicate_unique_unit_number_conflicts(director, sector_id):
    created = _new_project(director, sector_id)
    body = {"building_id": created["building_id"], "numero_appartement": "1", "unique_unit_number": "DUP-1"}
    assert director.post("/api/v1/portfolio/units", json=body).status_code == 201
    r = director.post("/api/v1/portfolio/units", json={**body, "numero_appartement": "2"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_patch_building_with_stale_check(director, db_conn, sector_id):
    bid = _new_project(director, sector_id)["building_id"]
    url = f"/api/v1/portfolio/buildings/{bid}"
    r = director.patch(url, json={
        "changes": {"chauffage": "Plinthes électriques", "ascenseur": True},
        "current": {"chauffage": None, "ascenseur": None},
    })
    assert r.status_code == 204, r.text
    ref = director.get(url).json()["reference"]
    assert ref["chauffage"] == "Plinthes électriques"
    assert ref["ascenseur"] is True
    assert _provenance(db_conn, "building", bid)["chauffage"] == (None, "Plinthes électriques", _DIRECTOR)

    # Someone saw the old value: refused, nothing written.
    r = director.patch(url, json={"changes": {"chauffage": "Gaz"}, "current": {"chauffage": None}})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "STALE_DATA"
    assert director.get(url).json()["reference"]["chauffage"] == "Plinthes électriques"

    # The address can't be blanked.
    r = director.patch(url, json={"changes": {"adresse": " "}, "current": {"adresse": "1 rue de l'Essai"}})
    assert r.status_code == 422


def test_fiche_entry_set_edit_remove(director, db_conn, sector_id):
    bid = _new_project(director, sector_id)["building_id"]
    url = f"/api/v1/portfolio/buildings/{bid}/fiche"
    assert director.put(url, json={"label": "Code de peinture", "value": "SW 7005"}).status_code == 204
    fiche = director.get(f"/api/v1/portfolio/buildings/{bid}").json()["fiche"]
    assert {"label": "Code de peinture", "value": "SW 7005"} in fiche

    # Adding the same label again without knowing its value is stale.
    r = director.put(url, json={"label": "Code de peinture", "value": "SW 7006"})
    assert r.status_code == 409
    r = director.put(url, json={"label": "Code de peinture", "value": "SW 7006", "current_value": "SW 7005"})
    assert r.status_code == 204
    assert _provenance(db_conn, "building", bid)["raw_fiche_technique.Code de peinture"] == \
        ("SW 7005", "SW 7006", _DIRECTOR)

    # The unit page shows the building's paint notes.
    unit = director.post("/api/v1/portfolio/units", json={"building_id": bid, "numero_appartement": "3"}).json()
    detail = director.get(f"/api/v1/portfolio/units/{unit['unit_id']}").json()
    assert detail["paint_notes"] == [{"label": "Code de peinture", "value": "SW 7006"}]

    r = director.put(url, json={"label": "Code de peinture", "value": None, "current_value": "SW 7006"})
    assert r.status_code == 204
    fiche = director.get(f"/api/v1/portfolio/buildings/{bid}").json()["fiche"]
    assert all(e["label"] != "Code de peinture" for e in fiche)


def test_paint_spec_crud(director, db_conn, sector_id):
    bid = _new_project(director, sector_id)["building_id"]
    r = director.post(f"/api/v1/portfolio/buildings/{bid}/paint-specs", json={
        "zone": "LOGEMENTS", "surface_label": "Murs", "product_interior": "SW 7005", "manufacturer": "Sherwin",
    })
    assert r.status_code == 201, r.text
    spec_id = r.json()["paint_spec_id"]
    specs = director.get(f"/api/v1/portfolio/buildings/{bid}").json()["paint_specs"]
    assert [s["paint_spec_id"] for s in specs] == [spec_id]

    r = director.patch(f"/api/v1/portfolio/paint-specs/{spec_id}", json={
        "changes": {"product_interior": "SW 7006"}, "current": {"product_interior": "SW 7005"},
    })
    assert r.status_code == 204
    specs = director.get(f"/api/v1/portfolio/buildings/{bid}").json()["paint_specs"]
    assert specs[0]["product_interior"] == "SW 7006"

    assert director.delete(f"/api/v1/portfolio/paint-specs/{spec_id}").status_code == 204
    assert director.get(f"/api/v1/portfolio/buildings/{bid}").json()["paint_specs"] == []
    assert "*deleted*" in _provenance(db_conn, "building_paint_spec", spec_id)


def test_documents_link_and_unlink(director, sector_id):
    bid = _new_project(director, sector_id)["building_id"]
    url = f"/api/v1/portfolio/buildings/{bid}/documents"
    assert director.post(url, json={"title": "Plans", "url": "ftp://nope"}).status_code == 422
    r = director.post(url, json={"title": "Plans", "url": "https://drive.google.com/x", "category": "other"})
    assert r.status_code == 201
    docs = director.get(f"/api/v1/portfolio/buildings/{bid}").json()["documents"]
    assert docs == [{"document_id": r.json()["document_id"], "title": "Plans", "category": "other",
                     "url": "https://drive.google.com/x"}]
    assert director.delete(f"/api/v1/portfolio/documents/{docs[0]['document_id']}").status_code == 204


def test_edit_project_and_unit(director, sector_id):
    created = _new_project(director, sector_id)
    r = director.patch(f"/api/v1/portfolio/projects/{created['project_id']}", json={
        "changes": {"nom_unique_projet": "Projet Renommé"},
        "current": {"nom_unique_projet": "Projet Test Édition"},
    })
    assert r.status_code == 204
    project = director.get(f"/api/v1/portfolio/projects/{created['project_id']}").json()
    assert project["nom_unique_projet"] == "Projet Renommé"

    unit_id = director.post("/api/v1/portfolio/units", json={
        "building_id": created["building_id"], "numero_appartement": "5"}).json()["unit_id"]
    r = director.patch(f"/api/v1/portfolio/units/{unit_id}", json={
        "changes": {"grandeur": "3 1/2"}, "current": {"grandeur": None}})
    assert r.status_code == 204
    assert director.get(f"/api/v1/portfolio/units/{unit_id}").json()["grandeur"] == "3 1/2"


def test_technician_cannot_edit(ac, sector_id):
    tech = ac(_user(_TECH, "technician"))
    r = tech.post("/api/v1/portfolio/projects", json={
        "nom_unique_projet": "X", "first_building": {"sector_id": sector_id, "adresse": "1"}})
    assert r.status_code == 403


def test_coordinator_cannot_edit_other_sector(ac, db_conn, director):
    sectors = db_conn.execute("SELECT sector_id FROM sector ORDER BY sector_id LIMIT 2").fetchall()
    if len(sectors) < 2:
        pytest.skip("need two sectors")
    mine, other = sectors[0]["sector_id"], sectors[1]["sector_id"]
    created = _new_project(director, other)
    db_conn.execute("DELETE FROM employee_building_assignment WHERE employee_id = %s", (_COORD,))
    db_conn.execute("UPDATE employee SET sector_id = %s WHERE employee_id = %s", (mine, _COORD))
    coord = ac(_user(_COORD, "coordinator"))

    r = coord.patch(f"/api/v1/portfolio/buildings/{created['building_id']}",
                    json={"changes": {"ville": "Lévis"}, "current": {"ville": "Québec"}})
    assert r.status_code == 404
    r = coord.post("/api/v1/portfolio/projects", json={
        "nom_unique_projet": "Ailleurs", "first_building": {"sector_id": other, "adresse": "2 rue X"}})
    assert r.status_code == 404
    r = coord.post("/api/v1/portfolio/units", json={
        "building_id": created["building_id"], "numero_appartement": "9"})
    assert r.status_code == 404
