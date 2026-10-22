"""Business logic for the requests module. Calls requests.repository, enforces domain rules."""
from __future__ import annotations

import contextlib
from datetime import date
from decimal import Decimal
from typing import Any

from datetime import datetime, timezone

from backend.core.exceptions import (
    ConflictError, GoneError, InvalidTransition, NotFoundError,
    PermissionDenied, RequestClosedError, StaleDataError,
    ValidationFailed,
)
from backend.core.security import CurrentUser
from backend.core.utils import today_local
from backend.modules.tasks import repository as task_repo
from backend.modules.tasks import service as task_service
from backend.modules.weather import repository as weather_repo

from . import repository as repo
from . import storage
from .schemas import (
    AddLogBody, AssignBody, ListResponse, ListRow,
    PhotoUploadResponse, PhotoUrlResponse, RequestDetail, RescheduleBody,
    RouteBody, SaveDispatchBody, SetCostBody, SetFollowUpDateBody, SetNextStepsBody,
    SetUrgencyBody, TechnicianSuggestion, TechnicianSuggestionsResponse,
)

_PHOTO_MIMES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_PHOTO_BYTES = 10 * 1024 * 1024

_TRIAGE_ABANDONED_MINUTES = 10

# Internal coordinator/admin fields — always null for technician and contractor.
_INTERNAL_TECH: frozenset[str] = frozenset({
    "triage_summary",
    "delegable_notes",
    "report_notes",
    "other_notes",
})

# Case-scoped personal data — null unless coordinator/director OR an assigned
# employee (see _ASSIGNED_SQL).  Covers both contact fields and tenant-identifying text.
#
# Technician/contractor ALWAYS receive (regardless of assignment):
#   request_id, start_date, asnu, urgency_tier, urgency_raw, raw_title,
#   building_id/address/name, sector_id, territoire, color_code,
#   assigned_employee_id/name, subcontractor_name, time_estimate_*, source_calendar*,
#   status, event_id, problem_summary, work_performed, ai_important_notes,
#   ai_next_steps, entry_permission, animals,
#   follow_up_expected, unit_id/label, project_id/label, html_link, caller_type,
#   bail_raw, historique_raw, ft_link, ft_name, problems, followup_log,
#   category_raw, element, symptome, composante, emplacement,
#   estimated_cost/next_follow_up_date/next_steps
_CASE_SCOPED_PII: frozenset[str] = frozenset({
    "caller_name",
    "caller_phone",
    "caller_email",
    "caller_tenant_id",
    "occupants_raw",
    "tenant_agreement_notes",
})


# Assigned = on an accepted task of the call, or the legacy call-level assignee
# (no longer written, kept so pre-task history stays visible).
_ASSIGNED_SQL = """(
    mr.assigned_employee_id = %(emp_id)s
    OR EXISTS (
        SELECT 1 FROM dispatch_task dt
        WHERE dt.request_id = mr.request_id
          AND dt.assigned_employee_id = %(emp_id)s
          AND dt.accepted_at IS NOT NULL
    )
)"""


def _scope(user: CurrentUser) -> tuple[str, dict[str, Any]]:
    """Return (scope_sql_fragment, params) to append to any WHERE clause."""
    if user.roles & {"director", "coordinator"}:
        return "", {}
    if "technician" in user.roles:
        # Assigned (see _ASSIGNED_SQL) OR sector buildings OR explicitly
        # assigned buildings via employee_building_assignment.
        return (
            f"""AND (
                {_ASSIGNED_SQL}
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
        return f"AND {_ASSIGNED_SQL}", {"emp_id": user.employee_id}
    return "AND FALSE", {}


def _is_assigned(conn, user: CurrentUser, row: dict) -> bool:
    """Same rule as _ASSIGNED_SQL, for one already-loaded request row."""
    return (
        row.get("assigned_employee_id") == user.employee_id
        or task_repo.is_assignee_on_request(conn, row["request_id"], user.employee_id)
    )


def _case_pii_visible(conn, user: CurrentUser, row: dict) -> bool:
    """True when the user may see case-scoped PII for this row."""
    if user.roles & {"director", "coordinator"}:
        return True
    return _is_assigned(conn, user, row)


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
        has_subcontractor=params.has_subcontractor,
        sort_by=params.sort_by,
        sort_dir=params.sort_dir,
        limit=params.limit,
        offset=params.offset,
        scope_sql=scope_sql,
        scope_params=scope_params,
        redispatch=params.redispatch,
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
            has_subcontractor=params.has_subcontractor,
        )
    return ListResponse(
        total=total,
        items=[ListRow(**r) for r in rows],
        unscheduled_items=[ListRow(**r) for r in unscheduled],
    )


def _hydrate_ai_notes(row: dict) -> None:
    """Fill ai_* arrays from other_notes when columns are empty (legacy rows).

    Tech/contractor never receive other_notes (stripped below); they do receive
    ai_important_notes / ai_next_steps — so hydrate before the strip.
    """
    has_arrays = bool(row.get("ai_important_notes")) or bool(row.get("ai_next_steps"))
    if has_arrays or not row.get("other_notes"):
        return
    from backend.triage.ai_notes import parse_other_notes
    important, next_steps = parse_other_notes(row["other_notes"])
    row["ai_important_notes"] = important
    row["ai_next_steps"] = next_steps


def get_request(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    scope_sql, scope_params = _scope(user)
    row = repo.get_request(conn, request_id, scope_sql=scope_sql, scope_params=scope_params)
    if row is None:
        raise NotFoundError(f"Request {request_id} not found")
    row["followup_log"] = repo.list_followup_entries(conn, request_id)
    row["visits"] = repo.list_visits(conn, request_id)
    row["tasks"] = task_service.list_for_request(conn, request_id, user)
    row["intake_photo_ids"] = repo.list_intake_photo_ids(conn, request_id)

    _hydrate_ai_notes(row)

    is_restricted = not bool(user.roles & {"director", "coordinator"})
    if is_restricted:
        row["justification_log"] = []
        for field in _INTERNAL_TECH:
            row[field] = None
        if not _case_pii_visible(conn, user, row):
            for field in _CASE_SCOPED_PII:
                row[field] = None
    else:
        row["justification_log"] = _with_assignee_names(conn, repo.list_justification_entries(conn, request_id))
        row["status_history"] = repo.list_status_changes(conn, request_id)

    # Weather summary is coordinator/director-only, like the manual check endpoint.
    row["weather_evaluation"] = None if is_restricted else weather_repo.get_latest_evaluation(conn, request_id)
    return RequestDetail(**row)


def _with_assignee_names(conn, entries: list[dict]) -> list[dict]:
    """Put assigned_employee_name next to each assigned_employee_id in before/after."""
    ids = {
        v["assigned_employee_id"] for e in entries for v in (e["before_value"], e["after_value"])
        if isinstance(v, dict) and isinstance(v.get("assigned_employee_id"), int)
    }
    names = repo.employee_names(conn, sorted(ids))
    for e in entries:
        for side in ("before_value", "after_value"):
            v = e[side]
            if isinstance(v, dict) and isinstance(v.get("assigned_employee_id"), int):
                e[side] = {**v, "assigned_employee_name": names.get(v["assigned_employee_id"])}
    return entries


def _after_action(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    """Return updated RequestDetail after a dispatch action (user is always coord/dir)."""
    row = repo.get_request(conn, request_id, scope_sql="", scope_params={})
    if row is None:  # should never happen — we just updated it
        raise NotFoundError(f"Request {request_id} not found")
    row["followup_log"] = repo.list_followup_entries(conn, request_id)
    row["justification_log"] = repo.list_justification_entries(conn, request_id)
    row["visits"] = repo.list_visits(conn, request_id)
    row["tasks"] = task_service.list_for_request(conn, request_id, user)
    row["intake_photo_ids"] = repo.list_intake_photo_ids(conn, request_id)
    row["weather_evaluation"] = weather_repo.get_latest_evaluation(conn, request_id)
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


# ── Dispatch actions ───────────────────────────────────────────────────────────

def _write_justification(conn, request_id: int, user: CurrentUser, body, *,
                         decision_type: str, before_value: dict, after_value: dict) -> None:
    """Log the decision's justification — required on every dispatcher decision."""
    repo.write_justification(conn,
        request_id=request_id, employee_id=user.employee_id, decision_type=decision_type,
        before_value=before_value, after_value=after_value,
        text=body.justification.text, input_method=body.justification.input_method,
    )


_USE_TASKS = "Assignee and due date now live on tasks — use POST /api/v1/tasks/{task_id}/%s"
_USE_TASK_FIELDWORK = "Visits now live on tasks — use POST /api/v1/tasks/{task_id}/%s"


def action_assign(conn, request_id: int, body: AssignBody, user: CurrentUser) -> RequestDetail:
    # Hard cutover: fieldwork (assignee) belongs to dispatch_task, not the call.
    raise GoneError(_USE_TASKS % "assign")


def action_reschedule(conn, request_id: int, body: RescheduleBody, user: CurrentUser) -> RequestDetail:
    # Hard cutover: the due date belongs to dispatch_task, not the call.
    raise GoneError(_USE_TASKS % "schedule")


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
    _write_justification(conn, request_id, user, body, decision_type="urgency",
        before_value={"urgency_tier": row["urgency_tier"]},
        after_value=after_value,
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
    _write_justification(conn, request_id, user, body, decision_type="follow_up_date",
        before_value={"next_follow_up_date": _to_str(row["next_follow_up_date"])},
        after_value={"next_follow_up_date": _to_str(body.next_follow_up_date)},
    )
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="next_follow_up_date", employee_id=user.employee_id,
        previous_value=_to_str(row["next_follow_up_date"]),
        new_value=_to_str(body.next_follow_up_date),
    )
    if body.next_follow_up_date is not None:
        title = (row.get("raw_title") or f"#{request_id}").strip()
        from backend.modules.alerts import service as alerts
        alerts.notify(
            conn, request_id=request_id, kind="followup_added",
            summary=f"Suivi planifié ({body.next_follow_up_date}) — {title}",
        )
    return _after_action(conn, request_id, user)


def action_set_next_steps(conn, request_id: int, body: SetNextStepsBody, user: CurrentUser) -> RequestDetail:
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    if row["next_steps"] != body.current_next_steps:
        raise StaleDataError()

    repo.update_field(conn, request_id, "next_steps", body.next_steps)
    _write_justification(conn, request_id, user, body, decision_type="next_steps",
        before_value={"next_steps": row["next_steps"]},
        after_value={"next_steps": body.next_steps},
    )
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="next_steps", employee_id=user.employee_id,
        previous_value=row["next_steps"], new_value=body.next_steps,
    )
    return _after_action(conn, request_id, user)


def action_save_dispatch(conn, request_id: int, body: SaveDispatchBody, user: CurrentUser) -> RequestDetail:
    """Apply several dispatcher edits as one save. Each field goes through its
    own action (same rules, stale checks, provenance and justification row);
    they all run in the request's transaction, so a failure saves nothing."""
    changed = body.changes.model_fields_set
    if not changed:
        raise ValidationFailed("Aucune modification à enregistrer")
    if changed & {"assigned_employee_id", "start_date"}:
        # Checked before any write so the call is left untouched.
        raise GoneError(_USE_TASKS % "assign or /schedule")
    ch = body.changes
    cur = body.current.model_dump()
    j = body.justification
    detail: RequestDetail | None = None

    def sync(d: RequestDetail, *keys: str) -> None:
        # Only refresh fields this step changed — keep the screen snapshot for
        # later stale checks (otherwise a mid-save refresh hides conflicts).
        nonlocal detail
        detail = d
        for k in keys:
            cur[k] = getattr(d, k)

    if "assigned_employee_id" in changed:
        sync(action_assign(conn, request_id, AssignBody(
            employee_id=ch.assigned_employee_id,
            current_assigned_employee_id=cur["assigned_employee_id"],
            current_start_date=cur["start_date"], current_urgency_tier=cur["urgency_tier"],
            justification=j), user), "assigned_employee_id")
    if "start_date" in changed:
        if ch.start_date is None:
            raise ValidationFailed("Date de répartition requise")
        sync(action_reschedule(conn, request_id, RescheduleBody(
            start_date=ch.start_date, current_start_date=cur["start_date"],
            current_assigned_employee_id=cur["assigned_employee_id"],
            current_urgency_tier=cur["urgency_tier"], justification=j), user), "start_date")
    if "urgency_tier" in changed:
        sync(action_set_urgency(conn, request_id, SetUrgencyBody(
            urgency_tier=ch.urgency_tier, current_urgency_tier=cur["urgency_tier"],
            current_assigned_employee_id=cur["assigned_employee_id"],
            current_start_date=cur["start_date"], justification=j), user), "urgency_tier")
    if "next_follow_up_date" in changed:
        sync(action_set_follow_up_date(conn, request_id, SetFollowUpDateBody(
            next_follow_up_date=ch.next_follow_up_date,
            current_next_follow_up_date=cur["next_follow_up_date"], justification=j), user),
            "next_follow_up_date")
    if "next_steps" in changed:
        sync(action_set_next_steps(conn, request_id, SetNextStepsBody(
            next_steps=ch.next_steps, current_next_steps=cur["next_steps"], justification=j), user),
            "next_steps")
    if "estimated_cost" in changed:
        sync(action_set_cost(conn, request_id, SetCostBody(
            estimated_cost=ch.estimated_cost, current_estimated_cost=cur["estimated_cost"],
            justification=j), user), "estimated_cost")
    details = [f for f in repo.DETAIL_FIELDS if f in changed]
    if details:
        detail = _set_detail_fields(conn, request_id,
            {f: getattr(ch, f) for f in details}, {f: cur.get(f) for f in details}, body, user)
    assert detail is not None
    return detail


def _blank(v: Any) -> str | None:
    """Empty text and null mean the same thing for call details."""
    s = (str(v).strip() if v is not None else "")
    return s or None


def _set_detail_fields(conn, request_id: int, changes: dict, current: dict,
                       body: SaveDispatchBody, user: CurrentUser) -> RequestDetail:
    """Correct call details (title, issue, access, caller, classification):
    stale check against what the dispatcher saw, one justification row, one
    provenance row per column."""
    row = _lock_or_404(conn, request_id)
    _check_not_closed(row)
    db = repo.get_detail_fields(conn, request_id)
    for f in changes:
        if _blank(db.get(f)) != _blank(current.get(f)):
            raise StaleDataError()
    if changes.get("raw_title") is not None and not _blank(changes["raw_title"]):
        raise ValidationFailed("Le titre ne peut pas être vide")
    before, after = {}, {}
    for f, v in changes.items():
        new = _blank(v)
        if new == _blank(db.get(f)):
            continue
        repo.update_field(conn, request_id, f, new)
        repo.write_provenance(conn,
            target_table="maintenance_request", target_pk=str(request_id),
            target_column=f, employee_id=user.employee_id,
            previous_value=_blank(db.get(f)), new_value=new,
        )
        before[f], after[f] = _blank(db.get(f)), new
    if after:
        _write_justification(conn, request_id, user, body, decision_type="details",
            before_value=before, after_value=after)
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
    _write_justification(conn, request_id, user, body, decision_type="cost",
        before_value={"estimated_cost": _to_str(current_db)},
        after_value={"estimated_cost": _to_str(body.estimated_cost)},
    )
    repo.write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="estimated_cost", employee_id=user.employee_id,
        previous_value=_to_str(current_db), new_value=_to_str(body.estimated_cost),
    )
    return _after_action(conn, request_id, user)


def action_en_route(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    # Hard cutover: fieldwork (visits) belongs to dispatch_task, not the call.
    raise GoneError(_USE_TASK_FIELDWORK % "en-route")


def action_arrived(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    raise GoneError(_USE_TASK_FIELDWORK % "arrived")


def action_upload_photo(conn, request_id: int, content: bytes, mime: str, user: CurrentUser) -> PhotoUploadResponse:
    """Closeout photo: raw image body, mime in Content-Type. File first, then
    row — an attachment row must never exist without its stored object; if the
    insert fails the uploaded file is deleted (best effort)."""
    row = _lock_or_404(conn, request_id)
    if not task_repo.is_assignee_on_request(conn, request_id, user.employee_id):
        raise PermissionDenied("Seul l'employé assigné peut ajouter des photos")
    _check_not_closed(row)
    ext = _PHOTO_MIMES.get(mime.split(";")[0].strip().lower())
    if ext is None:
        raise ValidationFailed("Format accepté : JPEG, PNG ou WebP")
    if len(content) == 0:
        raise ValidationFailed("Photo vide")
    if len(content) > _MAX_PHOTO_BYTES:
        raise ValidationFailed("Photo trop lourde (max 10 Mo)")

    attachment_id = repo.next_attachment_id(conn)
    path = f"closeout/{request_id}/{attachment_id}.{ext}"
    storage.upload_photo(path, content, mime)
    try:
        repo.insert_photo(
            conn, attachment_id=attachment_id, request_id=request_id,
            employee_id=user.employee_id, storage_path=path,
        )
    except Exception:
        with contextlib.suppress(Exception):
            storage.delete_photo(path)
        raise
    return PhotoUploadResponse(attachment_id=attachment_id)


def get_photo_url(conn, request_id: int, attachment_id: int, user: CurrentUser) -> PhotoUrlResponse:
    photo = repo.get_photo(conn, request_id, attachment_id)
    if photo is None or not photo["storage_path"]:
        raise NotFoundError("Photo introuvable")
    if not (user.roles & {"coordinator", "director"}) \
            and photo["uploaded_by_employee_id"] != user.employee_id \
            and not task_repo.is_assignee_on_request(conn, request_id, user.employee_id):
        raise PermissionDenied()
    return PhotoUrlResponse(url=storage.create_signed_url(photo["storage_path"]))


def action_closeout(conn, request_id: int, user: CurrentUser) -> RequestDetail:
    raise GoneError(_USE_TASK_FIELDWORK % "closeout")


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
    # Post-proposal fieldwork lives on tasks. `open` replaced scheduled /
    # en_route / arrived; re-triage would pull the call out from under them.
    # intake_received, triage_failed, and a stale triage_pending stay allowed.
    # triage_clarify stays blocked until a human resolves the address/lease.
    # triage_proposal stays blocked: accept/reject, don't run the model again.
    if status in ("open", "triaged", "scheduled", "awaiting_redispatch",
                  "triage_proposal", "en_route", "arrived"):
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


def _suggestion_why(c: dict, lang: str) -> str:
    fr = lang != "en"
    parts: list[str] = []
    hist = int(c.get("history_count") or 0)
    load = int(c.get("today_load") or 0)
    if c.get("is_a5"):
        parts.append("Dédié à cet immeuble" if fr else "Dedicated to this building")
    if hist > 0:
        parts.append(
            f"Déjà intervenu {hist}× ici (12 mois)" if fr
            else f"Worked here {hist}× (12 months)"
        )
    if not parts:
        parts.append("Secteur correspondant" if fr else "Matches sector")
    if load > 0:
        parts.append(
            f"{load} appel{'s' if load > 1 else ''} aujourd'hui" if fr
            else f"{load} call{'s' if load != 1 else ''} today"
        )
    else:
        parts.append("Charge légère aujourd'hui" if fr else "Light load today")
    if c.get("is_en_route"):
        parts.append("En route actuellement" if fr else "Currently en route")
    return " · ".join(parts)


def get_technician_suggestions(
    conn, request_id: int, lang: str = "fr",
) -> TechnicianSuggestionsResponse:
    """DB-ranked top-3 suggestions; never invents out-of-sector people.

    Rank: A5 dedicated → lighter today_load → more building history →
    prefer not en_route → name. Workload is a first-class signal, not a
    tie-break after history alone.
    """
    loc = repo.get_request_location(conn, request_id)
    if loc is None:
        raise NotFoundError(f"Request {request_id} not found")
    candidates = repo.list_technician_suggestion_candidates(
        conn, building_id=loc.get("building_id"), sector_id=loc.get("sector_id"),
    )
    candidates.sort(
        key=lambda c: (
            -int(bool(c.get("is_a5"))),
            int(c.get("today_load") or 0),
            -int(c.get("history_count") or 0),
            bool(c.get("is_en_route")),
            (c.get("name") or "").lower(),
        )
    )
    top = candidates[:3]
    return TechnicianSuggestionsResponse(
        request_id=request_id,
        suggestions=[
            TechnicianSuggestion(
                employee_id=int(c["employee_id"]),
                initials=c.get("initials"),
                name=c.get("name") or "",
                why=_suggestion_why(c, lang),
                is_en_route=bool(c.get("is_en_route")),
                today_load=int(c.get("today_load") or 0),
            )
            for c in top
        ],
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
    _write_justification(conn, request_id, user, body, decision_type="route",
        before_value={"source_calendar": row["source_calendar"]},
        after_value={"source_calendar": body.source_calendar},
    )
    return _after_action(conn, request_id, user)


def action_add_log(conn, request_id: int, body: AddLogBody, user: CurrentUser) -> RequestDetail:
    # Allowed even on closed requests — no status check.
    # Lock the request row to confirm it exists.
    row = _lock_or_404(conn, request_id)
    is_coord = bool(user.roles & {"coordinator", "director"})
    if not is_coord and not _is_assigned(conn, user, row):
        raise PermissionDenied("Seul l'employé assigné peut ajouter une note")

    # Resolve initials from the employee's name
    emp_row = conn.execute(
        "SELECT nom_employe FROM employee WHERE employee_id = %(emp_id)s",
        {"emp_id": user.employee_id},
    ).fetchone()
    name = emp_row["nom_employe"] if emp_row else "?"
    initials = "".join(w[0].upper() for w in name.split() if w)[:4]
    today = today_local()

    followup_id = repo.add_log_entry(conn, request_id, body.entry_text, initials, today)
    repo.write_provenance(conn,
        target_table="maintenance_followup_entry", target_pk=str(followup_id),
        target_column="entry_text", employee_id=user.employee_id,
        previous_value=None, new_value=body.entry_text,
    )

    title = (row.get("raw_title") or f"#{request_id}").strip()
    from backend.modules.alerts import service as alerts
    if is_coord:
        alerts.notify(
            conn, request_id=request_id, kind="followup_added",
            summary=f"Suivi ajouté — {title}",
        )
    else:
        alerts.notify(
            conn, request_id=request_id, kind="tech_log",
            summary=f"Note terrain — {name}: {title}",
        )
    return _after_action(conn, request_id, user)
