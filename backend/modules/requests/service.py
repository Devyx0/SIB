"""Business logic for the requests module. Calls requests.repository, enforces domain rules."""
from __future__ import annotations

from typing import Any

from backend.core.exceptions import NotFoundError
from backend.core.security import CurrentUser

from . import repository as repo
from .schemas import ListResponse, ListRow, RequestDetail

# Internal coordinator/admin fields — always null for technician and contractor.
_INTERNAL_TECH: frozenset[str] = frozenset({
    "triage_summary",
    "delegable_notes",
    "report_notes",
    "other_notes",
})

# Case-scoped personal data — null unless coordinator/director OR the directly-
# assigned employee.  Covers both contact fields and tenant-identifying text.
#
# Technician/contractor ALWAYS receive (regardless of assignment):
#   request_id, start_date, asnu, urgency_tier, urgency_raw, raw_title,
#   building_id/address/name, sector_id, territoire, color_code,
#   assigned_employee_id/name, subcontractor_name, time_estimate_*, source_calendar*,
#   status, event_id, problem_summary, work_performed, entry_permission, animals,
#   follow_up_expected, unit_id/label, project_id/label, html_link, caller_type,
#   bail_raw, historique_raw, ft_link, ft_name, problems, followup_log,
#   estimated_cost/next_follow_up_date/next_steps (all null – migration 0002)
_CASE_SCOPED_PII: frozenset[str] = frozenset({
    "caller_name",
    "caller_phone",
    "caller_email",
    "caller_tenant_id",
    "occupants_raw",
    "tenant_agreement_notes",
})


def _scope(user: CurrentUser) -> tuple[str, dict[str, Any]]:
    """Return (scope_sql_fragment, params) to append to any WHERE clause."""
    if user.roles & {"director", "coordinator"}:
        return "", {}
    if "technician" in user.roles:
        # Exact match of tech_scoped RLS: directly assigned OR sector buildings
        # OR explicitly assigned buildings via employee_building_assignment.
        return (
            """AND (
                mr.assigned_employee_id = %(emp_id)s
                OR mr.building_id IN (
                    SELECT b2.building_id FROM building b2
                    JOIN employee e2 ON b2.sector_id = e2.sector_id
                    WHERE e2.employee_id = %(emp_id)s
                    UNION
                    SELECT eba.building_id FROM employee_building_assignment eba
                    WHERE eba.employee_id = %(emp_id)s
                )
            )""",
            {"emp_id": user.employee_id},
        )
    if "contractor" in user.roles:
        return "AND mr.assigned_employee_id = %(emp_id)s", {"emp_id": user.employee_id}
    return "AND FALSE", {}


def _case_pii_visible(user: CurrentUser, row: dict) -> bool:
    """True when the user may see case-scoped PII for this row."""
    if user.roles & {"director", "coordinator"}:
        return True
    return row.get("assigned_employee_id") == user.employee_id


def list_requests(conn, params, user: CurrentUser) -> ListResponse:
    scope_sql, scope_params = _scope(user)
    total, rows = repo.list_requests(
        conn,
        start_date=params.start_date,
        end_date=params.end_date,
        status=params.status,
        building_id=params.building_id,
        sector_id=params.sector_id,
        assigned_employee_id=params.assigned_employee_id,
        urgency=params.urgency,
        source_calendar=params.source_calendar,
        q=params.q,
        sort_by=params.sort_by,
        sort_dir=params.sort_dir,
        limit=params.limit,
        offset=params.offset,
        scope_sql=scope_sql,
        scope_params=scope_params,
    )
    return ListResponse(total=total, items=[ListRow(**r) for r in rows])


def get_request(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    scope_sql, scope_params = _scope(user)
    row = repo.get_request(conn, request_id, scope_sql=scope_sql, scope_params=scope_params)
    if row is None:
        raise NotFoundError(f"Request {request_id} not found")
    row["followup_log"] = repo.list_followup_entries(conn, request_id)

    is_restricted = not bool(user.roles & {"director", "coordinator"})
    if is_restricted:
        for field in _INTERNAL_TECH:
            row[field] = None
        if not _case_pii_visible(user, row):
            for field in _CASE_SCOPED_PII:
                row[field] = None

    return RequestDetail(**row)
