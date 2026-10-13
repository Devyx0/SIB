"""Global exception handler that maps AppError subclasses to HTTP responses."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.core.exceptions import AppError


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Return a JSON error body for any AppError subclass."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
