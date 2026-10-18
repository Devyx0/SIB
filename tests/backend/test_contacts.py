"""Tests for contact sentinel normalisation in get_request."""
from __future__ import annotations

from backend.modules.requests.repository import _normalise_contacts


def test_sentinel_email_set_to_null_with_flag():
    d = {"caller_email": "info@sibelanger.com", "caller_phone": "514-555-1234"}
    _normalise_contacts(d)
    assert d["caller_email"] is None
    assert d["caller_email_placeholder"] is True
    assert d["caller_phone"] == "514-555-1234"
    assert d["caller_phone_placeholder"] is False


def test_sentinel_phone_set_to_null_with_flag():
    d = {"caller_email": "real@example.com", "caller_phone": "(000) 000-0000"}
    _normalise_contacts(d)
    assert d["caller_phone"] is None
    assert d["caller_phone_placeholder"] is True
    assert d["caller_email"] == "real@example.com"
    assert d["caller_email_placeholder"] is False


def test_non_sentinel_contacts_unchanged():
    d = {"caller_email": "tenant@mail.com", "caller_phone": "418-555-9999"}
    _normalise_contacts(d)
    assert d["caller_email"] == "tenant@mail.com"
    assert d["caller_email_placeholder"] is False
    assert d["caller_phone"] == "418-555-9999"
    assert d["caller_phone_placeholder"] is False


def test_null_contacts_not_flagged():
    d = {"caller_email": None, "caller_phone": None}
    _normalise_contacts(d)
    assert d["caller_email"] is None
    assert d["caller_email_placeholder"] is False
    assert d["caller_phone"] is None
    assert d["caller_phone_placeholder"] is False
