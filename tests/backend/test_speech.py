"""GET /api/v1/speech/token — AssemblyAI temporary streaming token."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.security import CurrentUser, get_current_user
from backend.modules.speech import router as speech


def _user(*roles: str) -> CurrentUser:
    return CurrentUser(employee_id=4, roles=frozenset(roles))


@pytest.fixture
def client(app, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user("coordinator")
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "test-key")
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _mock(monkeypatch, handler):
    monkeypatch.setattr(speech, "_client", httpx.Client(transport=httpx.MockTransport(handler)))


def test_returns_a_short_lived_token(client, monkeypatch):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"token": "tmp-123"})

    _mock(monkeypatch, handler)
    r = client.get("/api/v1/speech/token")
    assert r.status_code == 200
    assert r.json() == {"token": "tmp-123", "expires_in_seconds": 60}
    assert seen["url"].startswith("https://streaming.assemblyai.com/v3/token")
    assert "expires_in_seconds=60" in seen["url"]
    assert seen["auth"] == "test-key"  # raw key, no Bearer prefix


def test_missing_key_is_503(client, monkeypatch):
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "")
    r = client.get("/api/v1/speech/token")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SPEECH_UNAVAILABLE"


def test_upstream_failure_is_503(client, monkeypatch):
    _mock(monkeypatch, lambda req: httpx.Response(401, json={"error": "bad key"}))
    r = client.get("/api/v1/speech/token")
    assert r.status_code == 503


def test_technician_can_dictate_too(app, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user("technician")
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "test-key")
    _mock(monkeypatch, lambda req: httpx.Response(200, json={"token": "t"}))
    r = TestClient(app, raise_server_exceptions=False).get("/api/v1/speech/token")
    app.dependency_overrides.clear()
    assert r.status_code == 200
