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
          AND t.nom_complet !~* 'antenne|antenna'
          AND COALESCE(u.numero_appartement, '') !~* 'antenne|antenna'
          AND lower(trim(COALESCE(u.numero_appartement, ''))) <> 'toit'
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


def _nxt_id(db_conn, table: str, col: str) -> int:
    return db_conn.execute(
        f"SELECT COALESCE(MAX({col}), 0) + 1 AS n FROM {table}"
    ).fetchone()["n"]


def _seed_antenna_lease(db_conn, *, email: str, phone: str = "4185550188") -> dict:
    """Active roof/antenna lease on a real building — must not bind public lookup."""
    b = db_conn.execute(
        """
        SELECT building_id, sector_id FROM building
        WHERE sector_id IS NOT NULL LIMIT 1
        """
    ).fetchone()
    assert b is not None, "need a building with sector_id"
    # Explicit PKs: identity sequences often lag after ingest with fixed ids.
    unit_id = _nxt_id(db_conn, "unit", "unit_id")
    tenant_id = _nxt_id(db_conn, "tenant", "tenant_id")
    lease_id = _nxt_id(db_conn, "lease", "lease_id")
    tenancy_id = _nxt_id(db_conn, "tenancy_record", "tenancy_id")
    db_conn.execute(
        """
        INSERT INTO unit (unit_id, building_id, rue, numero_appartement)
        VALUES (%(uid)s, %(bid)s, 'toit test', 'TOIT')
        """,
        {"uid": unit_id, "bid": b["building_id"]},
    )
    db_conn.execute(
        """
        INSERT INTO tenant (tenant_id, nom_complet, courriel, telephone)
        VALUES (%(tid)s, 'Bell Mobility (antenne)', %(email)s, %(phone)s)
        """,
        {"tid": tenant_id, "email": email, "phone": phone},
    )
    db_conn.execute(
        """
        INSERT INTO lease (lease_id, unit_id, debut_bail, fin_bail, droit_animaux)
        VALUES (%(lid)s, %(uid)s, CURRENT_DATE - 30, CURRENT_DATE + 365, false)
        """,
        {"lid": lease_id, "uid": unit_id},
    )
    db_conn.execute(
        """
        INSERT INTO tenancy_record (tenancy_id, lease_id, tenant_id, capacite)
        VALUES (%(tr)s, %(lid)s, %(tid)s, 'named_on_lease')
        """,
        {"tr": tenancy_id, "lid": lease_id, "tid": tenant_id},
    )
    return {
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "building_id": b["building_id"],
        "email": email,
        "phone": phone,
    }


def test_lookup_excludes_antenna_lease(client, db_conn):
    """Antenna / TOIT leases must not bind the tenant form (Bell Mobility case)."""
    antenna = _seed_antenna_lease(
        db_conn, email="antenna.only@bgis.test", phone="4185550177",
    )
    r = client.post(
        "/api/v1/public/intake/lookup",
        json={"email": antenna["email"], "turnstile_token": "tok"},
    )
    assert r.status_code == 404, r.text


def test_lookup_prefers_housing_over_antenna(client, db_conn):
    """Same contact on antenna + residential → bind the housing unit only."""
    shared_email = "shared.antenna.housing@example.com"
    shared_phone = "4185550166"
    housing = _seed_tenant(db_conn)
    db_conn.execute(
        """
        UPDATE tenant
        SET courriel = %(email)s, telephone = %(phone)s
        WHERE tenant_id = %(id)s
        """,
        {
            "email": shared_email,
            "phone": shared_phone,
            "id": housing["tenant_id"],
        },
    )
    _seed_antenna_lease(db_conn, email=shared_email, phone=shared_phone)

    r = client.post(
        "/api/v1/public/intake/lookup",
        json={"email": shared_email, "turnstile_token": "tok"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["session_token"]
    sess = public_service._read_session(token)
    assert sess["tid"] == housing["tenant_id"]
    assert sess["uid"] == housing["unit_id"]
    assert sess["bid"] == housing["building_id"]


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
