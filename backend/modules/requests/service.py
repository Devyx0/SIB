"""Business logic for the requests module. Calls requests.repository, enforces domain rules."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from datetime import datetime, timezone

from backend.core.exceptions import (
    ConflictError, InvalidTransition, NotFoundError, RequestClosedError,
    StaleDataError, ValidationFailed,
)
from backend.core.security import CurrentUser
from backend.core.utils import today_local
from backend.modules.weather.keywords import matches_heating_keywords
from backend.modules.weather import repository as weather_repo

from . import repository as repo
from .schemas import (
    AddLogBody, AssignBody, ListResponse, ListRow, RequestDetail,
    RescheduleBody, RouteBody, SetCostBody, SetFollowUpDateBody, SetNextStepsBody,
    SetUrgencyBody,
)

_TRIAGE_ABANDONED_MINUTES = 10

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
    unscheduled: list[dict] = []
    # Without a date window the main query has no date filter, so undated rows
    # are already in `items` — the extra query would only duplicate them.
    if params.source_calendar != "unrouted" and params.start_date is not None:
        unscheduled = repo.list_routed_unscheduled(
            conn,
            scope_sql=scope_sql,
            scope_params=scope_params,
            building_id=params.building_id,
            sector_id=params.sector_id,
            assigned_employee_id=params.assigned_employee_id,
            urgency=params.urgency,
            source_calendar=params.source_calendar,
            status=params.status,
            q=params.q,
        )
    return ListResponse(
        total=total,
        items=[ListRow(**r) for r in rows],
        unscheduled_items=[ListRow(**r) for r in unscheduled],
    )


def get_request(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    scope_sql, scope_params = _scope(user)
    row = repo.get_request(conn, request_id, scope_sql=scope_sql, scope_params=scope_params)
    if row is None:
        raise NotFoundError(f"Request {request_id} not found")
    row["followup_log"] = repo.list_followup_entries(conn, request_id)

    is_restricted = not bool(user.roles & {"director", "coordinator"})
    if is_restricted:
        row["justification_log"] = []
        for field in _INTERNAL_TECH:
            row[field] = None
        if not _case_pii_visible(user, row):
            for field in _CASE_SCOPED_PII:
                row[field] = None
    else:
        row["justification_log"] = repo.list_justification_entries(conn, request_id)

    _set_heating_hint(row)
    return RequestDetail(**row)


def _after_action(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    """Return updated RequestDetail after a dispatch action (user is always coord/dir)."""
    row = repo.get_request(conn, request_id, scope_sql="", scope_params={})
    if row is None:  # should never happen — we just updated it
        raise NotFoundError(f"Request {request_id} not found")
    row["followup_log"] = repo.list_followup_entries(conn, request_id)
    row["justification_log"] = repo.list_justification_entries(conn, request_id)
    _set_heating_hint(row)
    return RequestDetail(**row)


def _lock_or_404(conn, request_id: int) -> dict:
    row = repo.lock_request(conn, request_id)
    if row is None:
        raise NotFoundError(f"Request {request_id} not found")
    return row


def _check_not_closed(row: dict) -> None:
    if row["status"] == "closed":
        raise RequestClosedError()


def _to_str(v: Any) -> str | None:
    return str(v) if v is not None else None


def _norm_urgency(v: Any) -> str | None:
    """Treat 'none' enum value and Python None both as absent urgency."""
    return None if (v is None or v == "none") else str(v)


def _set_heating_hint(row: dict) -> None:
    """Advisory 'no heat' keyword hint over the request's problem text."""
    text = " ".join(filter(None, (
        row.get("problem_summary"), row.get("problems"), row.get("raw_title"),
    )))
    row["heating_keyword_hint"] = matches_heating_keywords(text)


# ── Dispatch actions ───────────────────────────────────────────────────────────

def action_assign(conn, request_id: int, body: AssignBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    if (row["assigned_employee_id"] != body.current_assigned_employee_id
            or row["start_date"] != body.current_start_date
            or _norm_urgency(row["urgency_tier"]) != _norm_urgency(body.current_urgency_tier)):
        raise StaleDataError()
    if body.employee_id is not None and not repo.is_valid_assignee(conn, body.employee_id):
        raise ValidationFailed("Employee must be an active technician or contractor")

    repo.update_field(conn, request_id, "assigned_employee_id", body.employee_id)
    repo.write_justification(conn,
        request_id=request_id, employee_id=user.employee_id, decision_type="assign",
        before_value={"assigned_employee_id": row["assigned_employee_id"]},
        after_value={"assigned_employee_id": body.employee_id},
        text=body.justification.text, input_method=body.justification.input_method,
    )
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="assigned_employee_id", employee_id=user.employee_id,
        previous_value=_to_str(row["assigned_employee_id"]),
        new_value=_to_str(body.employee_id),
    )
    return _after_action(conn, request_id, user)


def action_reschedule(conn, request_id: int, body: RescheduleBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    if (row["start_date"] != body.current_start_date
            or row["assigned_employee_id"] != body.current_assigned_employee_id
            or _norm_urgency(row["urgency_tier"]) != _norm_urgency(body.current_urgency_tier)):
        raise StaleDataError()

    repo.update_field(conn, request_id, "start_date", body.start_date)
    repo.write_justification(conn,
        request_id=request_id, employee_id=user.employee_id, decision_type="reschedule",
        before_value={"start_date": _to_str(row["start_date"])},
        after_value={"start_date": str(body.start_date)},
        text=body.justification.text, input_method=body.justification.input_method,
    )
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="start_date", employee_id=user.employee_id,
        previous_value=_to_str(row["start_date"]), new_value=str(body.start_date),
    )
    return _after_action(conn, request_id, user)


def action_set_urgency(conn, request_id: int, body: SetUrgencyBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    if (_norm_urgency(row["urgency_tier"]) != _norm_urgency(body.current_urgency_tier)
            or row["assigned_employee_id"] != body.current_assigned_employee_id
            or row["start_date"] != body.current_start_date):
        raise StaleDataError()

    after_value: dict[str, Any] = {"urgency_tier": body.urgency_tier}
    if body.weather_evaluation_id is not None:
        ev = weather_repo.get_evaluation_provenance(conn, body.weather_evaluation_id)
        if ev is not None:
            # The suggestion is stale if urgency changed since it was computed.
            if _norm_urgency(ev["current_tier_at_eval"]) != _norm_urgency(row["urgency_tier"]):
                raise ConflictError("Suggestion périmée — revérifiez la météo")
            after_value["weather"] = {
                "evaluation_id": ev["evaluation_id"],
                "band": ev["band_name"],
                "min_forecast_temp_24h_c": _to_str(ev["min_forecast_temp_24h_c"]),
                "source_url": ev["source_url"],
            }

    repo.update_field(conn, request_id, "urgency_tier", body.urgency_tier)
    repo.write_justification(conn,
        request_id=request_id, employee_id=user.employee_id, decision_type="urgency",
        before_value={"urgency_tier": row["urgency_tier"]},
        after_value=after_value,
        text=body.justification.text, input_method=body.justification.input_method,
    )
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="urgency_tier", employee_id=user.employee_id,
        previous_value=row["urgency_tier"], new_value=body.urgency_tier,
    )
    return _after_action(conn, request_id, user)


def action_set_follow_up_date(conn, request_id: int, body: SetFollowUpDateBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    if row["next_follow_up_date"] != body.current_next_follow_up_date:
        raise StaleDataError()

    repo.update_field(conn, request_id, "next_follow_up_date", body.next_follow_up_date)
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="next_follow_up_date", employee_id=user.employee_id,
        previous_value=_to_str(row["next_follow_up_date"]),
        new_value=_to_str(body.next_follow_up_date),
    )
    return _after_action(conn, request_id, user)


def action_set_next_steps(conn, request_id: int, body: SetNextStepsBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    if row["next_steps"] != body.current_next_steps:
        raise StaleDataError()

    repo.update_field(conn, request_id, "next_steps", body.next_steps)
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="next_steps", employee_id=user.employee_id,
        previous_value=row["next_steps"], new_value=body.next_steps,
    )
    return _after_action(conn, request_id, user)


def action_set_cost(conn, request_id: int, body: SetCostBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    # Decimal comparison: normalise both to str for a reliable check
    current_db = row["estimated_cost"]
    if (current_db is None) != (body.current_estimated_cost is None) or \
       (current_db is not None and Decimal(str(current_db)) != Decimal(str(body.current_estimated_cost))):
        raise StaleDataError()

    repo.update_field(conn, request_id, "estimated_cost", body.estimated_cost)
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="estimated_cost", employee_id=user.employee_id,
        previous_value=_to_str(current_db), new_value=_to_str(body.estimated_cost),
    )
    return _after_action(conn, request_id, user)


def action_trigger_triage(conn, request_id: int) -> None:
    """Validate that triage can be triggered. Raises on bad state.

    The actual triage runs in a BackgroundTask (caller's responsibility).
    Returns without writing — the lock is set inside triage() after the request is committed.
    """
    row = repo.get_triage_status(conn, request_id)
    if row is None:
        raise NotFoundError()
    status = row["status"]
    if status == "closed":
        raise RequestClosedError()
    if status in ("triaged", "triage_proposal", "en_route"):
        raise InvalidTransition(f"Cannot trigger triage: current status is '{status}'")
    if status == "triage_clarify":
        raise ConflictError("Triage bloqué — résoudre l'ambiguïté d'adresse d'abord")
    if status == "triage_pending":
        started_at = row["triage_started_at"]
        if started_at is not None:
            age_min = (datetime.now(timezone.utc) - started_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if age_min < _TRIAGE_ABANDONED_MINUTES:
                raise ConflictError(
                    f"Triage déjà en cours (démarré il y a {age_min:.0f} min) — réessayez dans quelques minutes"
                )


def action_route(conn, request_id: int, body: RouteBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    if row["source_calendar"] != body.expected_source_calendar:
        raise StaleDataError()
    repo.route_request(conn,
        request_id=request_id,
        source_calendar=body.source_calendar,
        old_source_calendar=row["source_calendar"],
        employee_id=user.employee_id,
    )
    return _after_action(conn, request_id, user)


def action_add_log(conn, request_id: int, body: AddLogBody, user: CurrentUser) -> RequestDetail:
    # Allowed even on closed requests — no status check.
    # Lock the request row to confirm it exists.
    row = _lock_or_404(conn, request_id)

    # Resolve initials from the employee's name
    emp_row = conn.execute(
        "SELECT nom_employe FROM employee WHERE employee_id = %(emp_id)s",
        {"emp_id": user.employee_id},
    ).fetchone()
    initials = "".join(w[0].upper() for w in (emp_row["nom_employe"] if emp_row else "?").split() if w)[:4]
    today = today_local()

    followup_id = repo.add_log_entry(conn, request_id, body.entry_text, initials, today)
    repo.write_provenance(conn,
        target_table="maintenance_followup_entry", target_pk=str(followup_id),
        target_column="entry_text", employee_id=user.employee_id,
        previous_value=None, new_value=body.entry_text,
    )
    return _after_action(conn, request_id, user)
