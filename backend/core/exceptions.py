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


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    detail = "Unauthorized"


class PermissionDenied(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"
    detail = "Permission denied"


class InvalidTransition(AppError):
    # 409: the request conflicts with the resource's current state
    status_code = 409
    code = "INVALID_TRANSITION"
    detail = "Invalid status transition"


class GoneError(AppError):
    # 410: the endpoint's behaviour was removed on purpose (hard cutover)
    status_code = 410
    code = "GONE"
    detail = "This endpoint is no longer available"


class StaleDataError(ConflictError):
    code = "STALE_DATA"
    detail = "Request was modified by another user"


class NoCurrentLeaseError(ConflictError):
    code = "NO_CURRENT_LEASE"
    detail = "No current lease on this unit"


class AlreadyOnLeaseError(ConflictError):
    code = "ALREADY_ON_LEASE"
    detail = "Tenant is already on this lease"


class TenancyNotActiveError(ConflictError):
    code = "TENANCY_NOT_ACTIVE"
    detail = "Tenancy is not active"


class RequestClosedError(ConflictError):
    code = "REQUEST_CLOSED"
    detail = "No changes allowed on a closed request"


class RequestEnRouteError(ConflictError):
    code = "REQUEST_EN_ROUTE"
    detail = "Call in progress — technician must close out first"


class AssigneeEnRouteError(ConflictError):
    code = "ASSIGNEE_EN_ROUTE"
    detail = "Technician already en route — close out first"


class StorageError(AppError):
    # 502: the storage backend failed, not us — the client can safely retry
    status_code = 502
    code = "STORAGE_ERROR"
    detail = "Photo upload failed — try again"


# Legacy alias kept for any future references
ForbiddenError = PermissionDenied
