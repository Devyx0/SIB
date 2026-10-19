"""Supabase Storage client for closeout photos. Any httpx failure surfaces as
StorageError (502, French) — the portal never sees a raw 500 for storage.
All calls go through the module-level `_client`; tests swap it for an
httpx.Client with a MockTransport, so the real request shape is exercised
while no storage traffic ever leaves the local stack."""
from __future__ import annotations

import logging

import httpx

from backend.core.config import settings
from backend.core.exceptions import StorageError

BUCKET = "request-photos"

logger = logging.getLogger("backend.storage")

_client = httpx.Client(timeout=30)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.STORAGE_SERVICE_KEY}"}


def upload_photo(path: str, content: bytes, mime: str) -> None:
    """Upload to the private bucket with the service key."""
    try:
        r = _client.post(
            f"{settings.STORAGE_URL}/object/{BUCKET}/{path}",
            content=content,
            headers=_auth() | {"Content-Type": mime},
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Storage upload failed  path=%s  err=%s", path, exc)
        raise StorageError() from exc


def create_signed_url(path: str, expires_in_seconds: int = 300) -> str:
    """Short-lived signed URL for a private object."""
    try:
        r = _client.post(
            f"{settings.STORAGE_URL}/object/sign/{BUCKET}/{path}",
            json={"expiresIn": expires_in_seconds},
            headers=_auth(),
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Storage sign failed  path=%s  err=%s", path, exc)
        raise StorageError("Impossible de charger la photo — réessayez") from exc
    return f"{settings.STORAGE_URL}{r.json()['signedURL']}"


def delete_photo(path: str) -> None:
    """Remove an object — cleanup when the attachment row can't be written."""
    try:
        r = _client.delete(
            f"{settings.STORAGE_URL}/object/{BUCKET}/{path}",
            headers=_auth(),
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Storage delete failed  path=%s  err=%s", path, exc)
        raise StorageError() from exc
