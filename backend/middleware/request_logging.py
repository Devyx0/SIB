"""Middleware: structured access log for every HTTP request."""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("backend.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status, and duration for every request."""

    async def dispatch(self, request: Request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "%s %s → %d  %dms  req=%s",
            request.method,
            request.url.path,
            response.status_code,
            ms,
            getattr(request.state, "request_id", "-"),
        )
        return response
