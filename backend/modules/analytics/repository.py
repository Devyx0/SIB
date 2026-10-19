"""SQL aggregations for dashboard / utilization. No tenant PII columns."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .constants import (
    A_REDISPATCHER_SQL,
    A_ROUTER_SQL,
    BUCKET_MIDPOINT_MINUTES,
    UNTRIAGED_STATUSES,
)


def _board_window(today: date) -> tuple[str, str]:
    """31-day window ending today — board requires a date pair for sector filters."""
    start = today - timedelta(days=30)
    return start.isoformat(), today.isoformat()


def today_by_status(conn, today: date) -> list[dict]:
    rows = conn.execute(
        """
        SELECT mr.status::text AS status, count(*)::int AS count
        FROM maintenance_request mr
        WHERE mr.start_date = %(today)s
        GROUP BY mr.status::text
        ORDER BY mr.status::text
        """,
        {"today": today},
    ).fetchall()
    return [dict(r) for r in rows]


def load_today(conn, today: date) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.employee_id,
               e.nom_employe,
               count(*) FILTER (WHERE mr.start_date = %(today)s)::int AS assigned_count,
               count(*) FILTER (WHERE mr.status::text = 'en_route')::int AS en_route_count
        FROM employee e
        JOIN maintenance_request mr ON mr.assigned_employee_id = e.employee_id
        WHERE mr.start_date = %(today)s OR mr.status::text = 'en_route'
        GROUP BY e.employee_id, e.nom_employe
        HAVING count(*) FILTER (WHERE mr.start_date = %(today)s) > 0
            OR count(*) FILTER (WHERE mr.status::text = 'en_route') > 0
        ORDER BY e.nom_employe
        """,
        {"today": today},
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
                   WHERE mr.status::text <> 'closed' AND mr.urgency_tier::text = 'AJD'
               )::int AS "AJD",
               count(*) FILTER (
                   WHERE mr.status::text <> 'closed' AND mr.urgency_tier::text = 'ajd'
               )::int AS ajd,
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
        f"SELECT count(*)::int AS n FROM maintenance_request mr WHERE {A_REDISPATCHER_SQL}"
    ).fetchone()["n"]
    return {
        "a_router": a_router,
        "a_redispatcher": a_redispatcher,
        "a_router_link": "/board?source_calendar=unrouted",
        "a_redispatcher_link": "/board?redispatch=1",
    }


def utilization_rows(conn, start: date, end: date) -> list[dict]:
    """Active technicians/contractors plus anyone with assignments in the range."""
    case_sql = "CASE mr.time_estimate_bucket::text " + " ".join(
        f"WHEN '{k}' THEN {v}" for k, v in BUCKET_MIDPOINT_MINUTES.items()
    ) + " ELSE NULL END"

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
            JOIN maintenance_request mr ON mr.assigned_employee_id = e.employee_id
            LEFT JOIN sector s ON s.sector_id = COALESCE(mr.sector_id, e.sector_id)
            WHERE mr.start_date BETWEEN %(start)s AND %(end)s
        ),
        assigned AS (
            SELECT mr.assigned_employee_id AS employee_id,
                   count(*)::int AS calls_assigned,
                   coalesce(sum({case_sql}), 0)::int AS planned_minutes,
                   count(*) FILTER (
                       WHERE mr.time_estimate_bucket IS NULL
                          OR mr.time_estimate_bucket::text = 'TBD_ON_SITE'
                   )::int AS planned_unknown_count
            FROM maintenance_request mr
            WHERE mr.assigned_employee_id IS NOT NULL
              AND mr.start_date BETWEEN %(start)s AND %(end)s
            GROUP BY mr.assigned_employee_id
        ),
        closed AS (
            -- App closeouts only (closed_at set). Import sentinel closed → closed_at NULL.
            SELECT mr.assigned_employee_id AS employee_id,
                   count(*)::int AS calls_closed
            FROM maintenance_request mr
            WHERE mr.assigned_employee_id IS NOT NULL
              AND mr.closed_at IS NOT NULL
              AND (mr.closed_at AT TIME ZONE 'America/Toronto')::date
                    BETWEEN %(start)s AND %(end)s
            GROUP BY mr.assigned_employee_id
        ),
        visits AS (
            SELECT rv.employee_id,
                   count(*)::int AS visits_count,
                   coalesce(sum(
                       EXTRACT(EPOCH FROM (rv.closeout_at - rv.en_route_at)) / 60.0
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
               coalesce(max(v.complete), 0) AS complete,
               coalesce(max(v.partial_reschedule), 0) AS partial_reschedule,
               coalesce(max(v.partial_expertise), 0) AS partial_expertise,
               coalesce(max(v.failed), 0) AS failed
        FROM workforce w
        LEFT JOIN assigned a ON a.employee_id = w.employee_id
        LEFT JOIN closed c ON c.employee_id = w.employee_id
        LEFT JOIN visits v ON v.employee_id = w.employee_id
        GROUP BY w.employee_id, w.nom_employe
        ORDER BY w.nom_employe
        """,
        {"start": start, "end": end},
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
