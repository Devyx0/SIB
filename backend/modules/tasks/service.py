"""Business logic for dispatch tasks. Enforces the task status machine.

The repository does not check transitions; every status change here goes
through `transition_task` first.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.core.config import settings
from backend.core.exceptions import (
    AssigneeEnRouteError, ConflictError, InvalidTransition, NotFoundError,
    PermissionDenied, RequestClosedError, StaleDataError, ValidationFailed,
)
from backend.core.security import CurrentUser
from backend.core.utils import today_local
from backend.domain.status_machine import transition
from backend.domain.task_status_machine import transition_task
from backend.modules.requests import repository as request_repo

from . import repository as repo
from .schemas import (
    ArrivedBody, AssignTaskBody, CloseoutBody, CloseoutOut, CreateTaskBody, EnRouteBody,
    ScheduleTaskBody, TaskListResponse, TaskOut,
)

_FOLLOW_UP_DAYS = 14

_COORD_DIR = frozenset({"coordinator", "director"})
# Only before dispatch may the coordinator move a task around; once the
# technician is en route the assignee/due date are his, and done/cancelled are final.
_EDITABLE = frozenset({"queued", "scheduled"})


def _derived_status(current: str, assignee: Any, due_at: Any) -> str:
    """queued ⇄ scheduled follows assignee + due_at; any other status is kept."""
    if current == "queued" and assignee is not None and due_at is not None:
        return "scheduled"
    if current == "scheduled" and (assignee is None or due_at is None):
        return "queued"
    return current


def _check_assignee(conn, employee_id: int | None) -> None:
    if employee_id is None:
        return
    if not request_repo.is_valid_assignee(conn, employee_id):
        raise ValidationFailed("Employee must be an active technician or contractor")
    if request_repo.employee_has_open_en_route(conn, employee_id):
        raise AssigneeEnRouteError()


def _get_editable(conn, task_id: int) -> dict:
    task = repo.lock_accepted_task(conn, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task["status"] not in _EDITABLE:
        raise ConflictError(
            f"Task is {task['status']} — assignee and due date can no longer be changed"
        )
    return task


def _str(v: Any) -> str | None:
    return v.isoformat() if isinstance(v, datetime) else (str(v) if v is not None else None)


def _provenance(conn, task_id: int, column: str, user: CurrentUser, before: Any, after: Any) -> None:
    request_repo.write_provenance(
        conn, target_table="dispatch_task", target_pk=str(task_id), target_column=column,
        employee_id=user.employee_id, previous_value=_str(before), new_value=_str(after),
    )


def _justify(conn, request_id: int, user: CurrentUser, justification, *,
             decision_type: str, before: dict | None, after: dict) -> None:
    request_repo.write_justification(
        conn, request_id=request_id, employee_id=user.employee_id, decision_type=decision_type,
        before_value=before, after_value=after,
        text=justification.text, input_method=justification.input_method,
    )


def _apply(conn, task: dict, user: CurrentUser, justification, decision_type: str, **fields: Any) -> TaskOut:
    """Write assignee/due_at, then move status (validated) if they imply a change.

    Logs the justification and field provenance in the same transaction.
    """
    tid = task["task_id"]
    merged = {
        "assigned_employee_id": task["assigned_employee_id"], "due_at": task["due_at"],
        **fields,
    }
    repo.update_task_fields(conn, tid, **fields)
    for col, new in fields.items():
        _provenance(conn, tid, col, user, task[col], new)
    target = _derived_status(task["status"], merged["assigned_employee_id"], merged["due_at"])
    if target != task["status"]:
        transition_task(task["status"], target)
        repo.update_task_status(conn, tid, target)
        _provenance(conn, tid, "status", user, task["status"], target)
    _justify(
        conn, task["request_id"], user, justification, decision_type=decision_type,
        before={"task_id": tid, **{c: _str(task[c]) if c == "due_at" else task[c] for c in fields}},
        after={"task_id": tid, **{c: _str(v) if c == "due_at" else v for c, v in fields.items()}},
    )
    return TaskOut(**repo.get_task(conn, tid))


def list_tasks(
    conn, user: CurrentUser, *, start_date: date | None, end_date: date | None,
    statuses: list[str], assigned_employee_id: int | None,
) -> TaskListResponse:
    if not user.roles & _COORD_DIR:
        assigned_employee_id = user.employee_id  # technicians/contractors: own tasks only
    rows = repo.list_accepted_tasks(
        conn, start_date=start_date, end_date=end_date, statuses=statuses,
        assigned_employee_id=assigned_employee_id, timezone=settings.TIMEZONE,
    )
    return TaskListResponse(total=len(rows), items=[TaskOut(**r) for r in rows])


def create_task(conn, body: CreateTaskBody, user: CurrentUser) -> TaskOut:
    req = request_repo.lock_request(conn, body.request_id)
    if req is None:
        raise NotFoundError(f"Request {body.request_id} not found")
    if req["status"] == "closed":
        raise RequestClosedError()
    if req["status"] == "triage_proposal":
        # Draft tasks are accepted explicitly; a dispatcher task must not skip that.
        raise InvalidTransition("Accept or reject the AI proposal before adding tasks")
    _check_assignee(conn, body.assigned_employee_id)

    if req["status"] != "open":  # triaged / legacy fieldwork states → container is now open
        transition(req["status"], "open")  # raises InvalidTransition before triage is done
        request_repo.update_field(conn, body.request_id, "status", "open")
        request_repo.write_provenance(
            conn, target_table="maintenance_request", target_pk=str(body.request_id),
            target_column="status", employee_id=user.employee_id,
            previous_value=req["status"], new_value="open",
        )

    status = _derived_status("queued", body.assigned_employee_id, body.due_at)
    if status != "queued":
        transition_task("queued", status)
    task = repo.insert_task(
        conn, request_id=body.request_id, description=body.description, status=status,
        assigned_employee_id=body.assigned_employee_id, due_at=body.due_at,
        source="dispatcher", accepted_at=datetime.now(timezone.utc),
    )
    tid = task["task_id"]
    for col in ("assigned_employee_id", "due_at"):
        if getattr(body, col) is not None:
            _provenance(conn, tid, col, user, None, getattr(body, col))
    _provenance(conn, tid, "status", user, None, status)
    _justify(
        conn, body.request_id, user, body.justification, decision_type="task_create",
        before=None,
        after={"task_id": tid, "description": body.description,
               "assigned_employee_id": body.assigned_employee_id, "due_at": _str(body.due_at)},
    )
    return TaskOut(**task)


def assign_task(conn, task_id: int, body: AssignTaskBody, user: CurrentUser) -> TaskOut:
    task = _get_editable(conn, task_id)
    _check_assignee(conn, body.assigned_employee_id)
    return _apply(conn, task, user, body.justification, "task_assign",
                  assigned_employee_id=body.assigned_employee_id)


def schedule_task(conn, task_id: int, body: ScheduleTaskBody, user: CurrentUser) -> TaskOut:
    task = _get_editable(conn, task_id)
    return _apply(conn, task, user, body.justification, "task_schedule", due_at=body.due_at)


# ── Fieldwork: en route → arrived → closeout ───────────────────────────────────

def _lock_own(conn, task_id: int, user: CurrentUser, denied: str, current_status: str | None) -> dict:
    """Lock an accepted task the caller is assigned to, on a call that is not closed."""
    task = repo.lock_accepted_task(conn, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task["assigned_employee_id"] != user.employee_id:
        raise PermissionDenied(denied)
    req = request_repo.lock_request(conn, task["request_id"])
    if req["status"] == "closed":
        raise RequestClosedError()
    if current_status is not None and current_status != task["status"]:
        raise StaleDataError()
    task["_request"] = req
    return task


def _set_status(conn, task: dict, target: str, user: CurrentUser) -> None:
    transition_task(task["status"], target)
    repo.update_task_status(conn, task["task_id"], target)
    _provenance(conn, task["task_id"], "status", user, task["status"], target)
    task["status"] = target


def _own_open_visit(conn, task: dict, user: CurrentUser) -> dict:
    visit = request_repo.get_open_visit(conn, user.employee_id)
    if visit is None or visit["task_id"] != task["task_id"]:
        raise ConflictError("Aucune visite en cours pour cette tâche")
    return visit


def en_route(conn, task_id: int, body: EnRouteBody, user: CurrentUser) -> TaskOut:
    """Technician/contractor departs for the task. Status → en_route, visit row,
    two outbox rows (sms + email, never sent in V1), status provenance."""
    task = _lock_own(conn, task_id, user, "Seul l'employé assigné peut se mettre en route",
                     body.current_status)
    open_visit = request_repo.get_open_visit(conn, user.employee_id)
    if open_visit is not None:
        raise ConflictError(
            f"Tâche {open_visit['task_id']} (appel {open_visit['request_id']}) déjà en route "
            "— clôturez-la d'abord",
            details={
                "open_task_id": open_visit["task_id"],
                "open_request_id": open_visit["request_id"],
                "open_request_title": open_visit["raw_title"],
            },
        )
    transition_task(task["status"], "en_route")  # 409 before any write

    request_id = task["request_id"]
    # Insert the visit first: the partial unique index is the authoritative
    # one-open-visit guard if two devices race past the SELECT above.
    visit_id = request_repo.insert_visit(
        conn, request_id=request_id, task_id=task_id, employee_id=user.employee_id,
        lat=body.lat, lng=body.lng,
    )
    _set_status(conn, task, "en_route", user)

    # Tenant notification — template start is the client's (reference §5);
    # outbox only, status 'not_sent': no sender code exists in V1.
    ctx = request_repo.get_message_context(conn, request_id)
    address = ctx["adresse"] or ""
    if ctx["unit_label"]:
        address = f"{address}, app. {ctx['unit_label']}" if address else f"app. {ctx['unit_label']}"
    msg = (
        f"Bonjour, Ce message est destiné aux occupants, aux locataires du {address or 'logement'}. "
        "Votre technicien S.I. Bélanger est en route."
    )
    for channel, recipient, subject in (
        ("sms", ctx["caller_phone"], None),
        ("email", ctx["caller_email"], "Technicien en route — S.I. Bélanger"),
    ):
        request_repo.insert_outbox(conn,
            request_id=request_id, visit_id=visit_id, channel=channel,
            recipient=recipient, subject=subject, body=msg,
            employee_id=user.employee_id,
        )
    return TaskOut(**repo.get_task(conn, task_id))


def arrived(conn, task_id: int, body: ArrivedBody, user: CurrentUser) -> TaskOut:
    """Technician arrived on site. Status → arrived; stamps visit.arrived_at for travel KPI."""
    task = _lock_own(conn, task_id, user, "Seul l'employé assigné peut marquer l'arrivée",
                     body.current_status)
    if task["status"] != "en_route":
        raise ConflictError("La tâche n'est pas en route")
    visit = _own_open_visit(conn, task, user)
    _set_status(conn, task, "arrived", user)
    request_repo.mark_visit_arrived(conn, visit_id=visit["visit_id"], lat=body.lat, lng=body.lng)
    return TaskOut(**repo.get_task(conn, task_id))


_CLOSEOUT_TARGET = {
    "complete": "done",
    "partial_reschedule": "return_visit",
    "partial_expertise": "needs_expertise",
    "failed": "needs_expertise",
}


def closeout(conn, task_id: int, body: CloseoutBody, user: CurrentUser) -> CloseoutOut:
    """The four outcomes from François's notes (reference §6.1), mapped onto the
    task: complete → done, partial_reschedule → return_visit + follow-up task,
    partial_expertise / failed → needs_expertise. Closes the visit, logs the
    comment on the call, then runs the call auto-close check."""
    task = _lock_own(conn, task_id, user, "Seul l'employé assigné peut clôturer",
                     body.current_status)
    if task["status"] not in ("arrived", "working"):
        raise ConflictError("Marquez l'arrivée avant de clôturer")
    visit = _own_open_visit(conn, task, user)
    request_id = task["request_id"]

    today = today_local()
    if body.outcome == "partial_reschedule":
        if body.next_date is not None and body.next_date < today:
            raise ValidationFailed("La date de retour ne peut pas être dans le passé")
    elif body.next_date is not None:
        raise ValidationFailed("Une date de retour n'est permise que pour « je dois revenir »")
    if body.urgent and body.outcome not in ("partial_expertise", "failed"):
        raise ValidationFailed("« Urgent » n'est permis que pour les expertises")

    ids = list(dict.fromkeys(body.attachment_ids))
    if request_repo.count_usable_photos(conn, request_id, user.employee_id, ids) != len(ids):
        raise ValidationFailed("Photo invalide, d'un autre appel ou déjà utilisée")

    # No separate « au travail » tap yet: closing out implies work started.
    if task["status"] == "arrived":
        _set_status(conn, task, "working", user)
    target = _CLOSEOUT_TARGET[body.outcome]
    _set_status(conn, task, target, user)

    request_repo.close_visit(conn, visit_id=visit["visit_id"], outcome=body.outcome,
                             comment=body.comment, lat=body.lat, lng=body.lng)
    request_repo.mark_photos_used(conn, visit["visit_id"], ids)

    if target == "needs_expertise":
        request_repo.write_justification(conn,
            request_id=request_id, employee_id=user.employee_id, decision_type="closeout",
            before_value={"task_id": task_id, "status": "working"},
            after_value={"task_id": task_id, "status": target,
                         "closeout_outcome": body.outcome, "urgent": body.urgent},
            text=body.comment, input_method=body.input_method,
        )

    follow_up = None
    if body.outcome == "partial_reschedule":
        follow_up = _spawn_follow_up(conn, task, body.next_date or today + timedelta(days=_FOLLOW_UP_DAYS), user)

    # Follow-up entry with the comment, technician initials (add-log pattern).
    emp_row = conn.execute(
        "SELECT nom_employe FROM employee WHERE employee_id = %(emp_id)s",
        {"emp_id": user.employee_id},
    ).fetchone()
    tech_name = emp_row["nom_employe"] if emp_row else "?"
    initials = "".join(w[0].upper() for w in tech_name.split() if w)[:4]
    followup_id = request_repo.add_log_entry(conn, request_id, body.comment, initials, today)
    request_repo.write_provenance(conn,
        target_table="maintenance_followup_entry", target_pk=str(followup_id),
        target_column="entry_text", employee_id=user.employee_id,
        previous_value=None, new_value=body.comment,
    )

    call_closed = repo.maybe_close_request(conn, request_id)

    title = (task["_request"].get("raw_title") or f"#{request_id}").strip()
    from backend.modules.alerts import service as alerts
    from backend.modules.survey import repository as survey_repo

    if call_closed:
        survey_repo.create_survey(
            conn, request_id=request_id, visit_id=visit["visit_id"],
            employee_id=user.employee_id,
        )
        alerts.notify(
            conn, request_id=request_id, kind="call_completed",
            summary=f"Appel terminé — {tech_name}: {title}",
        )
    elif target == "needs_expertise":
        alerts.notify(
            conn, request_id=request_id, kind="expertise_needed",
            summary=f"Expertise requise — {tech_name}: {title}",
        )
    elif follow_up is not None:
        alerts.notify(
            conn, request_id=request_id, kind="followup_added",
            summary=f"Retour prévu — {tech_name}: {title}",
        )

    return CloseoutOut(
        **repo.get_task(conn, task_id),
        follow_up_task=follow_up,
        request_status="closed" if call_closed else task["_request"]["status"],
    )


def _spawn_follow_up(conn, parent: dict, due: date, user: CurrentUser) -> TaskOut:
    """Return visit: same work, same technician, new date (local midnight)."""
    due_at = datetime.combine(due, time.min, tzinfo=ZoneInfo(settings.TIMEZONE))
    status = _derived_status("queued", user.employee_id, due_at)
    transition_task("queued", status)
    row = repo.insert_task(
        conn, request_id=parent["request_id"], description=parent["description"],
        status=status, assigned_employee_id=user.employee_id, due_at=due_at,
        vendor_id=parent["vendor_id"], subcontractor_name=parent["subcontractor_name"],
        urgency_tier=parent["urgency_tier"], source="follow_up",
        accepted_at=datetime.now(timezone.utc), parent_task_id=parent["task_id"],
        sort_order=parent["sort_order"],
    )
    tid = row["task_id"]
    _provenance(conn, tid, "assigned_employee_id", user, None, user.employee_id)
    _provenance(conn, tid, "due_at", user, None, due_at)
    _provenance(conn, tid, "status", user, None, status)
    return TaskOut(**row)


def list_for_request(conn, request_id: int, user: CurrentUser) -> list[TaskOut]:
    """Tasks shown on the call detail. Proposals (accepted_at IS NULL) are dispatcher-only."""
    rows = repo.list_tasks_for_request(conn, request_id)
    if not user.roles & _COORD_DIR:
        rows = [r for r in rows if r["accepted_at"] is not None]
    return [TaskOut(**r) for r in rows]
