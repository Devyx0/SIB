"""Raw-SQL repository for dispatch_task. Receives a psycopg3 connection.

Pure persistence: transition rules (backend.domain.task_status_machine) are
enforced by the service layer, not here. `maybe_close_request` is the one
exception that also touches the request container (via domain.status_machine).
"""
from __future__ import annotations

from typing import Any

from backend.core.exceptions import InvalidTransition
from backend.domain.status_machine import transition

# Whitelist: column names are interpolated into SQL, never taken from callers' strings.
_INSERTABLE_FIELDS: frozenset[str] = frozenset({
    "request_id", "description", "status", "assigned_employee_id", "vendor_id",
    "subcontractor_name", "due_at", "urgency_tier", "source", "accepted_at",
    "parent_task_id", "sort_order",
})

_TASK_SELECT = """
    SELECT task_id, request_id, description, status::text AS status,
           assigned_employee_id, vendor_id, subcontractor_name, due_at,
           urgency_tier, source, accepted_at, parent_task_id, sort_order,
           created_at, updated_at
    FROM dispatch_task
"""

_RESOLVED = ("done", "cancelled")


def insert_task(conn, **fields: Any) -> dict:
    """Insert a task; `request_id` and `description` are required. Returns the row."""
    unknown = set(fields) - _INSERTABLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown dispatch_task fields: {sorted(unknown)}")
    cols = list(fields)
    placeholders = [
        f"%({c})s::dispatch_task_status" if c == "status" else f"%({c})s" for c in cols
    ]
    row = conn.execute(
        f"""
        INSERT INTO dispatch_task ({", ".join(cols)})
        VALUES ({", ".join(placeholders)})
        RETURNING task_id
        """,
        fields,
    ).fetchone()
    return get_task(conn, row["task_id"])


def get_task(conn, task_id: int) -> dict | None:
    row = conn.execute(
        f"{_TASK_SELECT} WHERE task_id = %(task_id)s",
        {"task_id": task_id},
    ).fetchone()
    return dict(row) if row else None


def list_tasks_for_request(conn, request_id: int) -> list[dict]:
    rows = conn.execute(
        f"{_TASK_SELECT} WHERE request_id = %(request_id)s ORDER BY sort_order, task_id",
        {"request_id": request_id},
    ).fetchall()
    return [dict(r) for r in rows]


def update_task_status(conn, task_id: int, status: str) -> dict:
    """Set status (no transition check — see module docstring). Raises KeyError if absent."""
    row = conn.execute(
        """
        UPDATE dispatch_task
        SET status = %(status)s::dispatch_task_status, updated_at = now()
        WHERE task_id = %(task_id)s
        RETURNING task_id
        """,
        {"status": status, "task_id": task_id},
    ).fetchone()
    if row is None:
        raise KeyError(task_id)
    return get_task(conn, task_id)


def maybe_close_request(conn, request_id: int) -> bool:
    """Close the call when all its work is resolved; return True if it was closed.

    Closes when there is ≥1 accepted task (accepted_at IS NOT NULL), every
    accepted task is done/cancelled, and no proposal rows (accepted_at IS NULL)
    remain. needs_expertise / return_visit block until followed up or cancelled.
    Calls that cannot legally move to closed (triage states, already closed)
    are left untouched.
    """
    req = conn.execute(
        "SELECT status::text AS status FROM maintenance_request "
        "WHERE request_id = %(request_id)s FOR UPDATE",
        {"request_id": request_id},
    ).fetchone()
    if req is None:
        return False
    try:
        transition(req["status"], "closed")
    except InvalidTransition:
        return False

    agg = conn.execute(
        """
        SELECT
            count(*) FILTER (WHERE accepted_at IS NOT NULL)                       AS accepted,
            count(*) FILTER (WHERE accepted_at IS NOT NULL
                             AND status::text <> ALL(%(resolved)s))               AS unresolved,
            count(*) FILTER (WHERE accepted_at IS NULL)                           AS proposals
        FROM dispatch_task
        WHERE request_id = %(request_id)s
        """,
        {"request_id": request_id, "resolved": list(_RESOLVED)},
    ).fetchone()
    if agg["accepted"] == 0 or agg["unresolved"] or agg["proposals"]:
        return False

    conn.execute(
        """
        UPDATE maintenance_request
        SET status = 'closed'::request_status, closed_at = COALESCE(closed_at, now())
        WHERE request_id = %(request_id)s
        """,
        {"request_id": request_id},
    )
    return True


_UPDATABLE_FIELDS: frozenset[str] = frozenset({"assigned_employee_id", "due_at"})


def lock_accepted_task(conn, task_id: int) -> dict | None:
    """SELECT … FOR UPDATE an accepted task (proposals are not addressable)."""
    row = conn.execute(
        f"{_TASK_SELECT} WHERE task_id = %(task_id)s AND accepted_at IS NOT NULL FOR UPDATE",
        {"task_id": task_id},
    ).fetchone()
    return dict(row) if row else None


def is_assignee_on_request(conn, request_id: int, employee_id: int) -> bool:
    """True if the employee is assigned to any accepted task of the call."""
    row = conn.execute(
        """
        SELECT 1 FROM dispatch_task
        WHERE request_id = %(request_id)s AND assigned_employee_id = %(emp)s
          AND accepted_at IS NOT NULL
        LIMIT 1
        """,
        {"request_id": request_id, "emp": employee_id},
    ).fetchone()
    return row is not None


def update_task_fields(conn, task_id: int, **fields: Any) -> None:
    """Set assignee and/or due_at (explicit None clears). Status is set separately."""
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown or not fields:
        raise ValueError(f"Bad dispatch_task update fields: {sorted(unknown)}")
    sets = ", ".join(f"{c} = %({c})s" for c in fields)
    conn.execute(
        f"UPDATE dispatch_task SET {sets}, updated_at = now() WHERE task_id = %(task_id)s",
        {**fields, "task_id": task_id},
    )


def list_accepted_tasks(
    conn,
    *,
    start_date=None,
    end_date=None,
    statuses: list[str] | None = None,
    assigned_employee_id: int | None = None,
    timezone: str = "UTC",
) -> list[dict]:
    """Accepted tasks (accepted_at IS NOT NULL) only; date range applies to due_at's local day."""
    where = ["accepted_at IS NOT NULL"]
    params: dict[str, Any] = {}
    if start_date is not None and end_date is not None:
        where.append("(due_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s")
        params.update(tz=timezone, start=start_date, end=end_date)
    if statuses:
        where.append("status::text = ANY(%(statuses)s)")
        params["statuses"] = list(statuses)
    if assigned_employee_id is not None:
        where.append("assigned_employee_id = %(assignee)s")
        params["assignee"] = assigned_employee_id
    rows = conn.execute(
        f"{_TASK_SELECT} WHERE {' AND '.join(where)} ORDER BY due_at NULLS LAST, task_id",
        params,
    ).fetchall()
    return [dict(r) for r in rows]
