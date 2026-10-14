"""Application-level exception types. Services raise these; never import FastAPI here."""
from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None, *, details: object = None) -> None:
        super().__init__(detail or self.__class__.detail)
        if detail:
            self.detail = detail
        self.details = details  # optional structured payload


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    detail = "Not found"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    detail = "Conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"
    detail = "Validation failed"


class PermissionDenied(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"
    detail = "Permission denied"


class InvalidTransition(AppError):
    # 409: the request conflicts with the resource's current state
    status_code = 409
    code = "INVALID_TRANSITION"
    detail = "Invalid status transition"


# Legacy alias kept for any future references
ForbiddenError = PermissionDenied
