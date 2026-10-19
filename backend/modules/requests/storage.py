"""Supabase Storage client for closeout photos. Tests monkeypatch these two
functions — no storage traffic ever leaves the local stack in tests."""
from __future__ import annotations

import httpx

from backend.core.config import settings

BUCKET = "request-photos"


def upload_photo(path: str, content: bytes, mime: str) -> None:
    """Upload to the private bucket with the service key. Raises on failure."""
    r = httpx.post(
        f"{settings.STORAGE_URL}/object/{BUCKET}/{path}",
        content=content,
        headers={
            "Authorization": f"Bearer {settings.SERVICE_ROLE}",
            "Content-Type": mime,
        },
        timeout=30,
    )
    r.raise_for_status()


def create_signed_url(path: str, expires_in_seconds: int = 300) -> str:
    """Short-lived signed URL for a private object."""
    r = httpx.post(
        f"{settings.STORAGE_URL}/object/sign/{BUCKET}/{path}",
        json={"expiresIn": expires_in_seconds},
        headers={"Authorization": f"Bearer {settings.SERVICE_ROLE}"},
        timeout=30,
    )
    r.raise_for_status()
    return f"{settings.STORAGE_URL}{r.json()['signedURL']}"
