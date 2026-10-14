"""Role-based access control."""
from __future__ import annotations

from fastapi import Depends

from .exceptions import PermissionDenied
from .security import CurrentUser, get_current_user

# Canonical role names — values from employee_role.role in the DB.
# employee.role carries French ingest values; the mapping to these canonical
# names lives in the ingestion layer, not here.
# Open decision: DB-vs-SoW role naming not yet finalised.
ROLES: frozenset[str] = frozenset({"technician", "coordinator", "director", "contractor"})


def require_role(*roles: str):
    """
    FastAPI dependency factory.  Usage:

        user: CurrentUser = require_role("coordinator", "director")

    Returns the CurrentUser so routes can inspect it further if needed.
    """
    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.roles.intersection(roles):
            raise PermissionDenied(
                f"One of these roles is required: {sorted(roles)}"
            )
        return user

    return Depends(_dep)
