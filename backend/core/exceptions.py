"""Application-level exception types."""
from __future__ import annotations


class AppError(Exception):
    """Base class for all application errors."""
    status_code: int = 500
    detail: str = "Internal server error"


class NotFoundError(AppError):
    status_code = 404
    detail = "Not found"


class ForbiddenError(AppError):
    status_code = 403
    detail = "Forbidden"


class ConflictError(AppError):
    status_code = 409
    detail = "Conflict"
