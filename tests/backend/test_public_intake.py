"""Public tenant intake: Turnstile gate, rate limit, lookup/submit."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.rate_limit import public_intake_limiter
from backend.main import create_app
from backend.modules.intake import public_service


def test_format_address_shows_full_civic():
    assert public_service._format_address("123 Rue Principale", "4B") == (
        "123 Rue Principale, app. 4B"
    )
    assert public_service._format_address(None, None) == "Adresse enregistrée"


@pytest.fixture
def client(db_conn):
    app = create_app()
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_limiter_and_mock_turnstile(monkeypatch):
    public_intake_limiter.reset()

    def _ok(token, *, expected_action, remote_ip=None):
        assert token
        assert expected_action in ("tenant_lookup", "tenant_submit")

    # Patch the name bound in public_service (from-import).
    monkeypatch.setattr(public_service, "verify_turnstile", _ok)


def _seed_tenant(db_conn) -> dict:
    """Attach a synthetic phone/email to an existing active lease tenant."""
    row = db_conn.execute(
        """
        SELECT t.tenant_id, u.unit_id, u.building_id, t.nom_complet
        FROM tenant t
        JOIN tenancy_record tr ON tr.tenant_id = t.tenant_id
        JOIN lease l ON l.lease_id = tr.lease_id
        JOIN unit u ON u.unit_id = l.unit_id
        JOIN building b ON b.building_id = u.building_id
        WHERE b.sector_id IS NOT NULL
          AND (l.debut_bail IS NULL OR l.debut_bail <= CURRENT_DATE)
          AND (l.fin_bail IS NULL OR l.fin_bail >= CURRENT_DATE)
        LIMIT 1
        """
    ).fetchone()
    assert row is not None, "need an active lease tenant in seed DB"
    phone = "4185550199"
    email = "public.intake.test@example.com"
    db_conn.execute(
        """
        UPDATE tenant
        SET telephone = %(phone)s, courriel = %(email)s
        WHERE tenant_id = %(id)s
        """,
        {"phone": phone, "email": email, "id": row["tenant_id"]},
    )
    return {
        "tenant_id": row["tenant_id"],
        "unit_id": row["unit_id"],
        "building_id": row["building_id"],
        "phone": phone,
        "email": email,
    }


def test_lookup_by_phone_and_submit(client, db_conn):
    seed = _seed_tenant(db_conn)
    r = client.post(
        "/api/v1/public/intake/lookup",
        json={"phone": seed["phone"], "turnstile_token": "tok-lookup"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_token"]
    assert body["pets_allowed"] in (True, False)
    assert body["address_label"]
    assert "***" not in body["address_label"]

    r2 = client.post(
        "/api/v1/public/intake/submit",
        json={
            "session_token": body["session_token"],
            "turnstile_token": "tok-submit",
            "access": "yes",
            "problem": "Fuite sous l'évier de la cuisine.",
            "element": "Plomberie",
            "symptome": "Fuite",
            "composante": "Robinet",
            "emplacement": "Cuisine",
        },
    )
    assert r2.status_code == 201, r2.text
    body2 = r2.json()
    rid = body2["request_id"]
    assert body2["asnu"] and body2["asnu"].startswith("ASNUF")
    assert body2["asnu"][5:].isdigit()
    row = db_conn.execute(
        """
        SELECT external_source, caller_tenant_id, unit_id, building_id, asnu,
               status::text AS status
        FROM maintenance_request WHERE request_id = %s
        """,
        [rid],
    ).fetchone()
    assert row["external_source"] == "tenant_web"
    assert row["caller_tenant_id"] == seed["tenant_id"]
    assert row["unit_id"] == seed["unit_id"]
    assert row["building_id"] == seed["building_id"]
    assert row["asnu"] == body2["asnu"]
    assert row["status"] in ("intake_received", "triage_pending", "triaged", "triage_failed", "triage_clarify")


def test_lookup_by_email(client, db_conn):
    seed = _seed_tenant(db_conn)
    r = client.post(
        "/api/v1/public/intake/lookup",
        json={"email": seed["email"], "turnstile_token": "tok"},
    )
    assert r.status_code == 200, r.text


def test_lookup_not_found(client):
    r = client.post(
        "/api/v1/public/intake/lookup",
        json={"phone": "0000000000", "turnstile_token": "tok"},
    )
    assert r.status_code == 404


def test_submit_rejects_bad_session(client):
    r = client.post(
        "/api/v1/public/intake/submit",
        json={
            "session_token": "not.a.jwt",
            "turnstile_token": "tok",
            "access": "yes",
            "problem": "x" * 10,
            "element": "A",
            "symptome": "B",
            "composante": "C",
            "emplacement": "D",
        },
    )
    assert r.status_code == 422


def test_rate_limit_lookup(client, db_conn):
    seed = _seed_tenant(db_conn)
    # Per-contact window is 10 / 15 min (stricter than per-IP 20).
    for _ in range(10):
        r = client.post(
            "/api/v1/public/intake/lookup",
            json={"phone": seed["phone"], "turnstile_token": "tok"},
        )
        assert r.status_code == 200, r.text
    r = client.post(
        "/api/v1/public/intake/lookup",
        json={"phone": seed["phone"], "turnstile_token": "tok"},
    )
    assert r.status_code == 429


def test_verify_turnstile_is_noop():
    """Backend Turnstile check disabled — always accepts (FE widget optional)."""
    from backend.core import turnstile as ts

    ts.verify_turnstile(None, expected_action="tenant_lookup")
    ts.verify_turnstile("", expected_action="tenant_submit")
    ts.verify_turnstile("any-token", expected_action="tenant_lookup")
