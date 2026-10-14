"""
Global error handlers.  Every failure returns the same envelope:

    {"error": {"code": str, "message": str, "request_id": str|null, "details": any}}

Handler registry (wire all four in main.py):
  AppError              → status_code from exc, code from exc.code
  RequestValidationError → 422 VALIDATION_FAILED
  HTTPException         → exc.status_code, code from status (unknown route, 405, …)
  Exception             → 500 INTERNAL_ERROR, stack trace logged, no internals leaked
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.core.exceptions import AppError

logger = logging.getLogger("backend.errors")


def _envelope(*, code: str, message: str, request_id: str | None, details=None) -> dict:
    return {"error": {"code": code, "message": message,
                      "request_id": request_id, "details": details}}


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(
            code=exc.code,
            message=exc.detail,
            request_id=_rid(request),
            details=getattr(exc, "details", None),
        ),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_envelope(
            code="VALIDATION_FAILED",
            message="Request validation failed",
            request_id=_rid(request),
            details=exc.errors(),
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # Map Starlette status codes to terse codes
    _CODE = {
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        403: "PERMISSION_DENIED",
        401: "UNAUTHORIZED",
    }
    code = _CODE.get(exc.status_code, f"HTTP_{exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(
            code=code,
            message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            request_id=_rid(request),
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception  req=%s  path=%s",
        _rid(request), request.url.path,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content=_envelope(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            request_id=_rid(request),
        ),
    )
