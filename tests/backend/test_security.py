"""Unit tests for JWT verification — security.py."""
from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest

import backend.core.security as sec
from backend.core.exceptions import Unauthorized
from backend.core.security import verify_jwt

_SECRET = "test-hs256-secret-unit-only"
_ISSUER = "http://localhost:54321/auth/v1"


def _hs256_token(overrides: dict = {}) -> str:
    payload = {
        "sub": "user-unit-abc",
        "aud": "authenticated",
        "iss": _ISSUER,
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return pyjwt.encode(payload, _SECRET, algorithm="HS256")


# ── HS256 path ────────────────────────────────────────────────────────────────

def test_valid_hs256_returns_payload(monkeypatch):
    monkeypatch.setattr(sec.settings, "SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    payload = verify_jwt(_hs256_token())
    assert payload["sub"] == "user-unit-abc"


def test_expired_token_raises_unauthorized(monkeypatch):
    monkeypatch.setattr(sec.settings, "SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    with pytest.raises(Unauthorized):
        verify_jwt(_hs256_token({"exp": int(time.time()) - 10}))


def test_wrong_issuer_raises_unauthorized(monkeypatch):
    monkeypatch.setattr(sec.settings, "SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    with pytest.raises(Unauthorized):
        verify_jwt(_hs256_token({"iss": "http://attacker.example.com/auth/v1"}))


def test_tampered_signature_raises_unauthorized(monkeypatch):
    monkeypatch.setattr(sec.settings, "SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    header_b64, payload_b64, _ = _hs256_token().split(".")
    with pytest.raises(Unauthorized):
        verify_jwt(f"{header_b64}.{payload_b64}.invalidsig")


def test_unknown_algorithm_raises_unauthorized(monkeypatch):
    monkeypatch.setattr(sec.settings, "SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    # RS256 header with a fake signature — hits the else branch immediately
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "x", "aud": "authenticated", "iss": _ISSUER, "exp": int(time.time()) + 300}).encode()
    ).rstrip(b"=").decode()
    with pytest.raises(Unauthorized):
        verify_jwt(f"{header}.{body}.fakesig")


# ── ES256 path ────────────────────────────────────────────────────────────────

def test_valid_es256_returns_payload(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    token = pyjwt.encode(
        {"sub": "user-es256", "aud": "authenticated", "iss": _ISSUER, "exp": int(time.time()) + 300},
        private_key,
        algorithm="ES256",
    )

    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    mock_client = MagicMock()
    mock_key = MagicMock()
    mock_key.key = private_key.public_key()
    mock_client.get_signing_key_from_jwt.return_value = mock_key
    monkeypatch.setattr(sec, "_jwks_client", mock_client)

    payload = verify_jwt(token)
    assert payload["sub"] == "user-es256"


def test_forged_iss_cannot_redirect_jwks_fetch(monkeypatch):
    """Attacker token with forged iss must not cause a JWKS fetch to any URL but ours."""
    from cryptography.hazmat.primitives.asymmetric import ec

    our_key = ec.generate_private_key(ec.SECP256R1())
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    _JWKS_URL = "http://localhost:54321/auth/v1/.well-known/jwks.json"

    # Signed by attacker, iss points to attacker's server
    token = pyjwt.encode(
        {"sub": "att", "aud": "authenticated", "iss": "http://attacker.example.com/auth/v1",
         "exp": int(time.time()) + 300},
        attacker_key, algorithm="ES256",
    )

    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    monkeypatch.setattr(sec.settings, "SUPABASE_JWKS_URL", _JWKS_URL)
    monkeypatch.setattr(sec, "_jwks_client", None)  # force lazy init to run

    mock_instance = MagicMock()
    mock_k = MagicMock()
    mock_k.key = our_key.public_key()  # our key, not attacker's
    mock_instance.get_signing_key_from_jwt.return_value = mock_k

    with patch.object(sec, "PyJWKClient", return_value=mock_instance) as mock_cls:
        with pytest.raises(Unauthorized):
            verify_jwt(token)
        # PyJWKClient was only ever initialised with our configured URL
        mock_cls.assert_called_once_with(_JWKS_URL)


def test_alg_none_raises_unauthorized(monkeypatch):
    """JWT 'none' algorithm bypass must be rejected before any decode attempt."""
    monkeypatch.setattr(sec.settings, "SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.setattr(sec.settings, "SUPABASE_ISSUER", _ISSUER)
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "x", "aud": "authenticated", "iss": _ISSUER, "exp": int(time.time()) + 300}).encode()
    ).rstrip(b"=").decode()
    with pytest.raises(Unauthorized):
        verify_jwt(f"{header}.{body}.")  # "none" tokens have no signature


# ── Settings startup validation ───────────────────────────────────────────────

def test_settings_rejects_empty_issuer():
    from pydantic import ValidationError
    from backend.core.config import Settings
    with pytest.raises(ValidationError, match="SUPABASE_ISSUER"):
        Settings(SUPABASE_JWKS_URL="http://x/jwks.json", SUPABASE_ISSUER="")
