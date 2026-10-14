"""Tests for require_role dependency."""
from __future__ import annotations

import pytest

from backend.core.exceptions import PermissionDenied
from backend.core.permissions import require_role
from backend.core.security import CurrentUser


def _user(*roles: str) -> CurrentUser:
    return CurrentUser(employee_id=1, roles=frozenset(roles))


def test_require_role_allow_exact():
    dep = require_role("coordinator")
    # Simulate FastAPI calling the inner _dep directly
    inner = dep.dependency
    user = inner(user=_user("coordinator"))
    assert user.employee_id == 1


def test_require_role_allow_any():
    """User with one of several accepted roles is allowed."""
    inner = require_role("coordinator", "director").dependency
    user = inner(user=_user("director"))
    assert user.employee_id == 1


def test_require_role_deny():
    inner = require_role("coordinator").dependency
    with pytest.raises(PermissionDenied):
        inner(user=_user("technician"))


def test_require_role_deny_empty_roles():
    inner = require_role("coordinator").dependency
    with pytest.raises(PermissionDenied):
        inner(user=_user())


def test_require_role_multi_user_has_subset():
    """User with technician+contractor cannot access coordinator-only endpoint."""
    inner = require_role("coordinator", "director").dependency
    with pytest.raises(PermissionDenied):
        inner(user=_user("technician", "contractor"))
