"""Satisfaction survey (public) + coordinator alerts on closeout / log / follow-up."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.core.utils import today_local

_COMMENT = "Travail effectué, remplacement du joint."
_JUSTIF = {"text": "Justification de test valide", "input_method": "typed"}


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
def mock_storage(monkeypatch):
    monkeypatch.setattr("backend.modules.requests.storage.upload_photo",
                        lambda path, content, mime: None)
    monkeypatch.setattr("backend.modules.requests.storage.create_signed_url",
                        lambda path, expires_in_seconds=300: f"https://signed.local/{path}")


def _seed(db_conn):
    sector_id = db_conn.execute(
        "INSERT INTO sector (territoire, color_code) VALUES ('TEST-SURVEY', '#333') "
        "RETURNING sector_id"
    ).fetchone()["sector_id"]
    project_id = db_conn.execute(
        "INSERT INTO project (nom_unique_projet) VALUES ('TestSurvey') RETURNING project_id"
    ).fetchone()["project_id"]
    building_id = db_conn.execute(
        "INSERT INTO building (project_id, sector_id, adresse) "
        "VALUES (%(p)s, %(s)s, '12 rue Survey') RETURNING building_id",
        {"p": project_id, "s": sector_id},
    ).fetchone()["building_id"]
    tech_id = db_conn.execute(
        "INSERT INTO employee (nom_employe, is_active) VALUES ('Tech Survey', true) "
        "RETURNING employee_id"
    ).fetchone()["employee_id"]
    db_conn.execute(
        "INSERT INTO employee_role (employee_id, role) VALUES (%s, 'technician')",
        [tech_id],
    )
    coord_id = db_conn.execute(
        "INSERT INTO employee (nom_employe, is_active) VALUES ('Coord Survey', true) "
        "RETURNING employee_id"
    ).fetchone()["employee_id"]
    db_conn.execute(
        "INSERT INTO employee_role (employee_id, role) VALUES (%s, 'coordinator')",
        [coord_id],
    )
    return building_id, tech_id, coord_id


def _en_route_call(ac, db_conn, building_id, tech_id):
    rid = db_conn.execute(
        "INSERT INTO maintenance_request "
        "(status, building_id, assigned_employee_id, raw_title) "
        "VALUES ('scheduled', %s, %s, 'Fuite survey') RETURNING request_id",
        [building_id, tech_id],
    ).fetchone()["request_id"]
    tech = ac(_user(tech_id, "technician"))
    assert tech.post(f"/api/v1/requests/{rid}/en-route", json={
        "current_status": "scheduled", "current_start_date": None,
        "lat": None, "lng": None,
    }).status_code == 200
    assert tech.post(f"/api/v1/requests/{rid}/arrived", json={
        "current_status": "en_route", "lat": None, "lng": None,
    }).status_code == 200
    return tech, rid


def test_complete_creates_survey_and_alert(ac, app, db_conn):
    building_id, tech_id, coord_id = _seed(db_conn)
    tech, rid = _en_route_call(ac, db_conn, building_id, tech_id)
    pid = tech.post(f"/api/v1/requests/{rid}/photos", content=b"x" * 64,
                    headers={"Content-Type": "image/jpeg"}).json()["attachment_id"]
    r = tech.post(f"/api/v1/requests/{rid}/closeout", json={
        "outcome": "complete", "comment": _COMMENT, "input_method": "typed",
        "attachment_ids": [pid], "next_date": None, "urgent": False,
        "current_status": "arrived", "lat": None, "lng": None,
    })
    assert r.status_code == 200, r.text

    survey = db_conn.execute(
        "SELECT token, submitted_at, employee_id FROM satisfaction_survey "
        "WHERE request_id = %s", [rid],
    ).fetchone()
    assert survey is not None
    assert survey["submitted_at"] is None
    assert survey["employee_id"] == tech_id

    # Public get + submit (no auth — clear user override)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    client = TestClient(app, raise_server_exceptions=False)

    g = client.get(f"/api/v1/survey/{survey['token']}")
    assert g.status_code == 200, g.text
    assert g.json()["already_submitted"] is False
    assert g.json()["technician_name"] == "Tech Survey"

    s = client.post(f"/api/v1/survey/{survey['token']}", json={
        "polite": True, "satisfied": True, "problem_solved": False,
        "comments": "Fuite réduite mais goutte encore.",
    })
    assert s.status_code == 200, s.text

    again = client.post(f"/api/v1/survey/{survey['token']}", json={
        "polite": True, "satisfied": True, "problem_solved": True, "comments": None,
    })
    assert again.status_code == 409

    coord = ac(_user(coord_id, "coordinator"))
    alerts = coord.get("/api/v1/alerts").json()
    kinds = {a["kind"] for a in alerts["items"] if a["request_id"] == rid}
    assert "call_completed" in kinds
    assert alerts["unread_count"] >= 1


def test_expertise_and_followup_alerts(ac, db_conn):
    building_id, tech_id, coord_id = _seed(db_conn)
    tech, rid = _en_route_call(ac, db_conn, building_id, tech_id)
    pid = tech.post(f"/api/v1/requests/{rid}/photos", content=b"x" * 64,
                    headers={"Content-Type": "image/jpeg"}).json()["attachment_id"]
    assert tech.post(f"/api/v1/requests/{rid}/closeout", json={
        "outcome": "partial_expertise", "comment": _COMMENT, "input_method": "typed",
        "attachment_ids": [pid], "next_date": None, "urgent": True,
        "current_status": "arrived", "lat": None, "lng": None,
    }).status_code == 200

    # No survey on expertise
    assert db_conn.execute(
        "SELECT 1 FROM satisfaction_survey WHERE request_id = %s", [rid],
    ).fetchone() is None

    coord = ac(_user(coord_id, "coordinator"))
    kinds = {a["kind"] for a in coord.get("/api/v1/alerts").json()["items"]
             if a["request_id"] == rid}
    assert "expertise_needed" in kinds

    # Follow-up date on a fresh open call
    rid2 = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, raw_title) "
        "VALUES ('triaged', %s, 'Suivi test') RETURNING request_id",
        [building_id],
    ).fetchone()["request_id"]
    r = coord.post(f"/api/v1/requests/{rid2}/follow-up-date", json={
        "next_follow_up_date": str(today_local()),
        "current_next_follow_up_date": None,
        "justification": _JUSTIF,
    })
    assert r.status_code == 200, r.text
    kinds2 = {a["kind"] for a in coord.get("/api/v1/alerts").json()["items"]
              if a["request_id"] == rid2}
    assert "followup_added" in kinds2


def test_tech_log_alert(ac, db_conn):
    building_id, tech_id, coord_id = _seed(db_conn)
    rid = db_conn.execute(
        "INSERT INTO maintenance_request "
        "(status, building_id, assigned_employee_id, raw_title) "
        "VALUES ('triaged', %s, %s, 'Note test') RETURNING request_id",
        [building_id, tech_id],
    ).fetchone()["request_id"]
    tech = ac(_user(tech_id, "technician"))
    r = tech.post(f"/api/v1/requests/{rid}/log", json={
        "entry_text": "Locataire absente, reviendra demain matin.",
    })
    assert r.status_code == 200, r.text

    coord = ac(_user(coord_id, "coordinator"))
    kinds = {a["kind"] for a in coord.get("/api/v1/alerts").json()["items"]
             if a["request_id"] == rid}
    assert "tech_log" in kinds
