"""Storage HTTP contract tests for closeout photos.

Unlike test_closeout.py, which stubs the storage *functions*, these tests run
the real storage code over a fake transport (httpx.MockTransport) and assert
the actual request shape — URL, method, header names, body — for the upload
and the signed URL. The last test is opt-in (STORAGE_INTEGRATION=1) and does
a full round-trip against the real local storage stack.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.modules.requests import storage
from backend.modules.tasks.repository import insert_task

_TECH = 24

# 1×1 valid JPEG (632 bytes) — real file bytes without a Pillow dependency.
_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2P/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwClRRRXIfQn/9k="
)


@pytest.fixture
def tech_client(app, db_conn):
    app.dependency_overrides[get_db_conn] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        employee_id=_TECH, roles=frozenset({"technician"})
    )
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def building(db_conn):
    return db_conn.execute(
        "SELECT building_id FROM building WHERE adresse IS NOT NULL LIMIT 1"
    ).fetchone()


@pytest.fixture
def rid(db_conn, building):
    rid = db_conn.execute(
        "INSERT INTO maintenance_request (status, building_id, raw_title) "
        "VALUES ('open', %(b)s, '[TEST] storage http') RETURNING request_id",
        {"b": building["building_id"]},
    ).fetchone()["request_id"]
    # Closeout photos are for the call's task assignees.
    insert_task(db_conn, request_id=rid, description="Photos", status="queued",
                assigned_employee_id=_TECH, accepted_at=datetime.now(timezone.utc))
    return rid


@pytest.fixture
def fake_storage(monkeypatch):
    """Real storage functions over a recording MockTransport."""
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        if "/object/sign/" in request.url.path:
            signed = request.url.path.replace("/storage/v1/object/sign/", "/object/sign/")
            return httpx.Response(200, json={"signedURL": f"{signed}?token=fake"})
        return httpx.Response(200, json={"Key": request.url.path})

    monkeypatch.setattr(
        storage, "_client", httpx.Client(transport=httpx.MockTransport(handler))
    )
    return recorded


def test_upload_request_shape(tech_client, db_conn, rid, fake_storage):
    r = tech_client.post(
        f"/api/v1/requests/{rid}/photos", content=_JPEG,
        headers={"Content-Type": "image/jpeg"},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["attachment_id"]

    assert len(fake_storage) == 1
    req = fake_storage[0]
    assert req.method == "POST"
    assert str(req.url) == f"{settings.STORAGE_URL}/object/request-photos/closeout/{rid}/{aid}.jpg"
    assert "authorization" in req.headers  # name only — never assert the value
    assert req.headers["content-type"] == "image/jpeg"
    assert req.content == _JPEG

    row = db_conn.execute(
        "SELECT storage_path FROM maintenance_attachment WHERE attachment_id = %s", [aid]
    ).fetchone()
    assert row["storage_path"] == f"closeout/{rid}/{aid}.jpg"


def test_signed_url_request_shape(tech_client, db_conn, rid, fake_storage):
    aid = db_conn.execute(
        "INSERT INTO maintenance_attachment (request_id, file_type, photo_context, "
        "uploaded_by_employee_id, storage_path) "
        "VALUES (%(r)s, 'photo', 'closeout', %(e)s, 'closeout/x/1.jpg') RETURNING attachment_id",
        {"r": rid, "e": _TECH},
    ).fetchone()["attachment_id"]

    r = tech_client.get(f"/api/v1/requests/{rid}/photos/{aid}")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith(settings.STORAGE_URL)

    assert len(fake_storage) == 1
    req = fake_storage[0]
    assert req.method == "POST"
    assert str(req.url) == f"{settings.STORAGE_URL}/object/sign/request-photos/closeout/x/1.jpg"
    assert "authorization" in req.headers
    assert req.headers["content-type"] == "application/json"
    import json
    assert json.loads(req.content) == {"expiresIn": 300}


def test_upload_storage_failure_is_french_502_no_row(tech_client, db_conn, rid, monkeypatch):
    monkeypatch.setattr(
        storage, "_client",
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))),
    )
    r = tech_client.post(
        f"/api/v1/requests/{rid}/photos", content=_JPEG,
        headers={"Content-Type": "image/jpeg"},
    )
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["code"] == "STORAGE_ERROR"
    assert err["message"] == "Échec de l'envoi de la photo — réessayez"
    n = db_conn.execute(
        "SELECT count(*) AS n FROM maintenance_attachment WHERE request_id = %s", [rid]
    ).fetchone()["n"]
    assert n == 0  # no row without its stored file


def test_insert_failure_deletes_uploaded_file(tech_client, db_conn, rid, fake_storage, monkeypatch):
    from backend.modules.requests import repository as repo

    def boom(*a, **kw):
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(repo, "insert_photo", boom)
    r = tech_client.post(
        f"/api/v1/requests/{rid}/photos", content=_JPEG,
        headers={"Content-Type": "image/jpeg"},
    )
    assert r.status_code == 500
    assert [req.method for req in fake_storage] == ["POST", "DELETE"]
    assert fake_storage[1].url.path == fake_storage[0].url.path  # same object cleaned up


@pytest.mark.skipif(
    os.environ.get("STORAGE_INTEGRATION") != "1",
    reason="set STORAGE_INTEGRATION=1 to run against the real local storage stack",
)
def test_storage_roundtrip_real_stack():
    """Upload a tiny JPEG to the real local bucket, sign it, download it,
    delete it, and confirm it is gone."""
    from backend.core.exceptions import StorageError

    path = "integration/roundtrip.jpg"
    storage.upload_photo(path, _JPEG, "image/jpeg")
    try:
        url = storage.create_signed_url(path)
        got = httpx.get(url, timeout=30)
        assert got.status_code == 200
        assert got.content == _JPEG
    finally:
        storage.delete_photo(path)
    with pytest.raises(StorageError):  # signing a deleted object fails
        storage.create_signed_url(path)
