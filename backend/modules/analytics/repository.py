"""SQL aggregations for dashboard / utilization. No tenant PII columns."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.core.config import settings

from .constants import (
    A_ROUTER_SQL,
    BUCKET_MIDPOINT_MINUTES,
    REDISPATCH_TASK_SQL,
    UNTRIAGED_STATUSES,
)


def _board_window(today: date) -> tuple[str, str]:
    """31-day window ending today — board requires a date pair for sector filters."""
    start = today - timedelta(days=30)
    return start.isoformat(), today.isoformat()


def today_by_status(conn, today: date) -> list[dict]:
    """Accepted tasks whose due day (platform timezone) is today, by task status."""
    rows = conn.execute(
        """
        SELECT t.status::text AS status, count(*)::int AS count
        FROM dispatch_task t
        WHERE t.accepted_at IS NOT NULL
          AND (t.due_at AT TIME ZONE %(tz)s)::date = %(today)s
        GROUP BY t.status::text
        ORDER BY t.status::text
        """,
        {"today": today, "tz": settings.TIMEZONE},
    ).fetchall()
    return [dict(r) for r in rows]


def load_today(conn, today: date) -> list[dict]:
    """Accepted tasks due today, plus minutes from today's visits.

    Assignment and en-route live on the task. A call with only
    assigned_employee_id / start_date / status en_route does not count.
    """
    rows = conn.execute(
        """
        WITH assigned AS (
            SELECT e.employee_id,
                   e.nom_employe,
                   count(*)::int AS assigned_count,
                   count(*) FILTER (WHERE t.status::text = 'en_route')::int AS en_route_count
            FROM employee e
            JOIN dispatch_task t ON t.assigned_employee_id = e.employee_id
            WHERE t.accepted_at IS NOT NULL
              AND (t.due_at AT TIME ZONE %(tz)s)::date = %(today)s
            GROUP BY e.employee_id, e.nom_employe
        ),
        mins AS (
            -- Closed visits that started today + any still-open visit (elapsed clipped to today).
            SELECT rv.employee_id,
                   coalesce(sum(
                       CASE
                           WHEN rv.closeout_at IS NOT NULL THEN
                               coalesce(
                                   rv.duration_minutes,
                                   GREATEST(
                                       0,
                                       ROUND(
                                           EXTRACT(EPOCH FROM (rv.closeout_at - rv.en_route_at))
                                           / 60.0
                                       )::integer
                                   )
                               )
                           ELSE
                               GREATEST(
                                   0,
                                   ROUND(
                                       EXTRACT(EPOCH FROM (
                                           NOW() - GREATEST(
                                               rv.en_route_at,
                                               (%(today)s::timestamp AT TIME ZONE 'America/Toronto')
                                           )
                                       )) / 60.0
                                   )::integer
                               )
                       END
                   ), 0)::int AS minutes_worked
            FROM request_visit rv
            WHERE (rv.en_route_at AT TIME ZONE 'America/Toronto')::date = %(today)s
               OR rv.closeout_at IS NULL
            GROUP BY rv.employee_id
        )
        SELECT a.employee_id,
               a.nom_employe,
               a.assigned_count,
               a.en_route_count,
               coalesce(m.minutes_worked, 0)::int AS minutes_worked
        FROM assigned a
        LEFT JOIN mins m ON m.employee_id = a.employee_id
        ORDER BY a.nom_employe
        """,
        {"today": today, "tz": settings.TIMEZONE},
    ).fetchall()
    return [dict(r) for r in rows]


def by_territory(conn, today: date) -> list[dict]:
    untriaged = list(UNTRIAGED_STATUSES)
    start_s, end_s = _board_window(today)
    rows = conn.execute(
        """
        SELECT s.sector_id,
               s.territoire,
               count(*) FILTER (WHERE mr.status::text <> 'closed')::int AS active,
               count(*) FILTER (
                   WHERE mr.status::text <> 'closed' AND mr.urgency_tier = 'URGENT'
               )::int AS urgent,
               count(*) FILTER (
                   WHERE mr.status::text <> 'closed' AND mr.urgency_tier = 'Intermédiaire'
               )::int AS medium,
               count(*) FILTER (
                   WHERE mr.status::text = ANY(%(untriaged)s)
               )::int AS untriaged
        FROM sector s
        LEFT JOIN maintenance_request mr ON mr.sector_id = s.sector_id
        GROUP BY s.sector_id, s.territoire
        HAVING count(*) FILTER (WHERE mr.status::text <> 'closed') > 0
            OR count(*) FILTER (WHERE mr.status::text = ANY(%(untriaged)s)) > 0
        ORDER BY s.territoire
        """,
        {"untriaged": untriaged},
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["board_link"] = (
            f"/board?sector_id={d['sector_id']}&start_date={start_s}&end_date={end_s}"
        )
        out.append(d)
    return out


def queue_counts(conn) -> dict[str, Any]:
    a_router = conn.execute(
        f"SELECT count(*)::int AS n FROM maintenance_request mr WHERE {A_ROUTER_SQL}"
    ).fetchone()["n"]
    a_redispatcher = conn.execute(
        f"SELECT count(*)::int AS n FROM dispatch_task t WHERE {REDISPATCH_TASK_SQL}"
    ).fetchone()["n"]
    return {
        "a_router": a_router,
        "a_redispatcher": a_redispatcher,
        "a_router_link": "/board?source_calendar=unrouted",
        "a_redispatcher_link": "/tasks?redispatch=1",
    }


def utilization_rows(conn, start: date, end: date) -> list[dict]:
    """Active technicians/contractors plus anyone with assignments in the range.

    Live work is an accepted task (assignee + due day). Pre-task rows — a call
    with assignee/start_date and no accepted task in the window — still count,
    so historical imports stay on the page.
    """
    case_sql = "CASE mr.time_estimate_bucket::text " + " ".join(
        f"WHEN '{k}' THEN {v}" for k, v in BUCKET_MIDPOINT_MINUTES.items()
    ) + " ELSE NULL END"
    unknown_sql = (
        "CASE WHEN mr.time_estimate_bucket IS NULL"
        " OR mr.time_estimate_bucket::text = 'TBD_ON_SITE' THEN 1 ELSE 0 END"
    )

    rows = conn.execute(
        f"""
        WITH workforce AS (
            SELECT DISTINCT e.employee_id, e.nom_employe, s.territoire
            FROM employee e
            JOIN employee_role er ON er.employee_id = e.employee_id
            LEFT JOIN sector s ON s.sector_id = e.sector_id
            WHERE e.is_active = true
              AND er.role IN ('technician', 'contractor')
            UNION
            SELECT DISTINCT e.employee_id, e.nom_employe, s.territoire
            FROM employee e
            JOIN dispatch_task t ON t.assigned_employee_id = e.employee_id
                                AND t.accepted_at IS NOT NULL
            LEFT JOIN maintenance_request mr ON mr.request_id = t.request_id
            LEFT JOIN sector s ON s.sector_id = COALESCE(mr.sector_id, e.sector_id)
            WHERE (t.due_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
            UNION
            SELECT DISTINCT e.employee_id, e.nom_employe, s.territoire
            FROM employee e
            JOIN maintenance_request mr ON mr.assigned_employee_id = e.employee_id
            LEFT JOIN sector s ON s.sector_id = COALESCE(mr.sector_id, e.sector_id)
            WHERE mr.start_date BETWEEN %(start)s AND %(end)s
              AND NOT EXISTS (
                  SELECT 1 FROM dispatch_task t
                  WHERE t.request_id = mr.request_id
                    AND t.accepted_at IS NOT NULL
                    AND t.assigned_employee_id = mr.assigned_employee_id
                    AND (t.due_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
              )
        ),
        assigned AS (
            SELECT employee_id,
                   count(*)::int AS calls_assigned,
                   coalesce(sum(planned), 0)::int AS planned_minutes,
                   coalesce(sum(unknown_flag), 0)::int AS planned_unknown_count
            FROM (
                SELECT t.assigned_employee_id AS employee_id,
                       {case_sql} AS planned,
                       {unknown_sql} AS unknown_flag
                FROM dispatch_task t
                JOIN maintenance_request mr ON mr.request_id = t.request_id
                WHERE t.accepted_at IS NOT NULL
                  AND t.assigned_employee_id IS NOT NULL
                  AND (t.due_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
                UNION ALL
                SELECT mr.assigned_employee_id,
                       {case_sql},
                       {unknown_sql}
                FROM maintenance_request mr
                WHERE mr.assigned_employee_id IS NOT NULL
                  AND mr.start_date BETWEEN %(start)s AND %(end)s
                  AND NOT EXISTS (
                      SELECT 1 FROM dispatch_task t
                      WHERE t.request_id = mr.request_id
                        AND t.accepted_at IS NOT NULL
                        AND t.assigned_employee_id IS NOT NULL
                        AND (t.due_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
                  )
            ) assigned_rows
            GROUP BY employee_id
        ),
        closed AS (
            -- Done tasks in the window (call closed_at, else the task's due day).
            -- Gravity/import rows have no task: status=closed, closed_at NULL,
            -- counted on start_date so historical utilization isn't empty.
            SELECT employee_id, count(*)::int AS calls_closed
            FROM (
                SELECT t.assigned_employee_id AS employee_id
                FROM dispatch_task t
                JOIN maintenance_request mr ON mr.request_id = t.request_id
                WHERE t.accepted_at IS NOT NULL
                  AND t.assigned_employee_id IS NOT NULL
                  AND t.status::text = 'done'
                  AND COALESCE(
                        (mr.closed_at AT TIME ZONE %(tz)s)::date,
                        (t.due_at AT TIME ZONE %(tz)s)::date
                      ) BETWEEN %(start)s AND %(end)s
                UNION ALL
                SELECT mr.assigned_employee_id
                FROM maintenance_request mr
                WHERE mr.assigned_employee_id IS NOT NULL
                  AND mr.status::text = 'closed'
                  AND COALESCE(
                        (mr.closed_at AT TIME ZONE %(tz)s)::date,
                        mr.start_date
                      ) BETWEEN %(start)s AND %(end)s
                  AND NOT EXISTS (
                      SELECT 1 FROM dispatch_task t
                      WHERE t.request_id = mr.request_id
                        AND t.accepted_at IS NOT NULL
                        AND t.status::text = 'done'
                        AND t.assigned_employee_id = mr.assigned_employee_id
                  )
            ) closed_rows
            GROUP BY employee_id
        ),
        visits AS (
            SELECT rv.employee_id,
                   count(*)::int AS visits_count,
                   coalesce(sum(
                       coalesce(
                           rv.duration_minutes::numeric,
                           EXTRACT(EPOCH FROM (rv.closeout_at - rv.en_route_at)) / 60.0
                       )
                   ), 0)::int AS visit_minutes,
                   count(*) FILTER (WHERE rv.outcome::text = 'complete')::int AS complete,
                   count(*) FILTER (WHERE rv.outcome::text = 'partial_reschedule')::int AS partial_reschedule,
                   count(*) FILTER (WHERE rv.outcome::text = 'partial_expertise')::int AS partial_expertise,
                   count(*) FILTER (WHERE rv.outcome::text = 'failed')::int AS failed
            FROM request_visit rv
            WHERE rv.closeout_at IS NOT NULL
              AND (rv.en_route_at AT TIME ZONE 'America/Toronto')::date
                    BETWEEN %(start)s AND %(end)s
            GROUP BY rv.employee_id
        ),
        -- Outcome mix: prefer request_visit; fall back to MR.closeout_outcome for
        -- app closeouts that never wrote a visit row (or legacy rows that have it).
        mr_outcomes AS (
            SELECT mr.assigned_employee_id AS employee_id,
                   count(*) FILTER (WHERE mr.closeout_outcome::text = 'complete')::int AS complete,
                   count(*) FILTER (WHERE mr.closeout_outcome::text = 'partial_reschedule')::int AS partial_reschedule,
                   count(*) FILTER (WHERE mr.closeout_outcome::text = 'partial_expertise')::int AS partial_expertise,
                   count(*) FILTER (WHERE mr.closeout_outcome::text = 'failed')::int AS failed
            FROM maintenance_request mr
            WHERE mr.assigned_employee_id IS NOT NULL
              AND mr.closeout_outcome IS NOT NULL
              AND COALESCE(
                    (mr.closed_at AT TIME ZONE 'America/Toronto')::date,
                    mr.start_date
                  ) BETWEEN %(start)s AND %(end)s
            GROUP BY mr.assigned_employee_id
        )
        SELECT w.employee_id,
               w.nom_employe,
               max(w.territoire) AS territoire,
               coalesce(max(a.calls_assigned), 0) AS calls_assigned,
               coalesce(max(c.calls_closed), 0) AS calls_closed,
               coalesce(max(a.planned_minutes), 0) AS planned_minutes,
               coalesce(max(a.planned_unknown_count), 0) AS planned_unknown_count,
               coalesce(max(v.visit_minutes), 0) AS visit_minutes,
               coalesce(max(v.visits_count), 0) AS visits_count,
               CASE WHEN coalesce(max(v.visits_count), 0) > 0
                    THEN coalesce(max(v.complete), 0)
                    ELSE coalesce(max(o.complete), 0) END AS complete,
               CASE WHEN coalesce(max(v.visits_count), 0) > 0
                    THEN coalesce(max(v.partial_reschedule), 0)
                    ELSE coalesce(max(o.partial_reschedule), 0) END AS partial_reschedule,
               CASE WHEN coalesce(max(v.visits_count), 0) > 0
                    THEN coalesce(max(v.partial_expertise), 0)
                    ELSE coalesce(max(o.partial_expertise), 0) END AS partial_expertise,
               CASE WHEN coalesce(max(v.visits_count), 0) > 0
                    THEN coalesce(max(v.failed), 0)
                    ELSE coalesce(max(o.failed), 0) END AS failed
        FROM workforce w
        LEFT JOIN assigned a ON a.employee_id = w.employee_id
        LEFT JOIN closed c ON c.employee_id = w.employee_id
        LEFT JOIN visits v ON v.employee_id = w.employee_id
        LEFT JOIN mr_outcomes o ON o.employee_id = w.employee_id
        GROUP BY w.employee_id, w.nom_employe
        ORDER BY w.nom_employe
        """,
        {"start": start, "end": end, "tz": settings.TIMEZONE},
    ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["outcome_mix"] = {
            "complete": d.pop("complete"),
            "partial_reschedule": d.pop("partial_reschedule"),
            "partial_expertise": d.pop("partial_expertise"),
            "failed": d.pop("failed"),
        }
        d["capacity_minutes"] = None
        d["utilization_pct"] = None
        out.append(d)
    return out


def reviews_in_range(conn, start: date, end: date) -> list[dict]:
    """Submitted tenant surveys in the range (by submission date), newest first."""
    rows = conn.execute(
        """
        SELECT s.survey_id,
               s.request_id,
               s.employee_id,
               s.submitted_at,
               s.satisfaction_rating::int AS rating,
               s.polite,
               s.problem_solved,
               s.comments,
               b.adresse AS building_address,
               mr.asnu
        FROM satisfaction_survey s
        JOIN maintenance_request mr ON mr.request_id = s.request_id
        LEFT JOIN building b ON b.building_id = mr.building_id
        WHERE s.submitted_at IS NOT NULL
          AND (s.submitted_at AT TIME ZONE 'America/Toronto')::date
                BETWEEN %(start)s AND %(end)s
        ORDER BY s.submitted_at DESC
        """,
        {"start": start, "end": end},
    ).fetchall()
    return [dict(r) for r in rows]
