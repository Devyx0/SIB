"""Speech-to-text: hands the browser a short-lived AssemblyAI streaming token.

The browser streams microphone audio straight to AssemblyAI (Universal-3.6
Pro, French) over a WebSocket. Our API key never leaves the server: each
dictation asks for a single-use token valid for 60 s to open one session.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.exceptions import AppError
from backend.core.permissions import require_role
from backend.core.security import CurrentUser

logger = logging.getLogger("backend.speech")

router = APIRouter(prefix="/speech", tags=["speech"])

_ANY_STAFF = require_role("technician", "coordinator", "director", "contractor")

TOKEN_URL = "https://streaming.assemblyai.com/v3/token"
TOKEN_TTL_SECONDS = 60            # time to open the WebSocket (1–600)
MAX_SESSION_SECONDS = 30 * 60     # one dictation never runs longer (60–10800)

# Module-level client so tests can swap in an httpx.MockTransport.
_client = httpx.Client(timeout=10)


class SpeechUnavailable(AppError):
    status_code = 503
    code = "SPEECH_UNAVAILABLE"
    detail = "Dictée indisponible pour le moment — écrivez votre texte."


class SpeechTokenResponse(BaseModel):
    token: str
    expires_in_seconds: int


@router.get("/token", operation_id="speech_token", response_model=SpeechTokenResponse)
def speech_token(user: CurrentUser = _ANY_STAFF) -> SpeechTokenResponse:
    if not settings.ASSEMBLYAI_API_KEY:
        raise SpeechUnavailable()
    try:
        r = _client.get(
            TOKEN_URL,
            params={
                "expires_in_seconds": TOKEN_TTL_SECONDS,
                "max_session_duration_seconds": MAX_SESSION_SECONDS,
            },
            headers={"Authorization": settings.ASSEMBLYAI_API_KEY},
        )
        r.raise_for_status()
        token = r.json().get("token")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("assemblyai token request failed: %s", exc)
        raise SpeechUnavailable() from exc
    if not token:
        raise SpeechUnavailable()
    return SpeechTokenResponse(token=token, expires_in_seconds=TOKEN_TTL_SECONDS)
