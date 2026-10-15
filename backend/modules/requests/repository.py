"""Raw-SQL repository for the requests module. Receives a psycopg3 connection."""
from __future__ import annotations

from datetime import date
from typing import Any

from .schemas import SORT_SQL, SOURCE_CALENDAR_LABELS

_LIST_SELECT = """
    SELECT
        mr.request_id,
        mr.start_date,
        mr.asnu,
        mr.urgency_tier::text            AS urgency_tier,
        mr.urgency_raw,
        mr.raw_title,
        mr.building_id,
        b.adresse                        AS building_address,
        b.web_building_name              AS building_name,
        mr.sector_id,
        s.territoire,
        s.color_code,
        mr.assigned_employee_id,
        e.nom_employe                    AS assigned_employee_name,
        mr.subcontractor_name,
        mr.time_estimate_bucket::text    AS time_estimate_bucket,
        mr.time_estimate_raw,
        mr.source_calendar,
        mr.status::text                  AS status,
        mr.event_id,
        mr.estimated_cost,
        mr.next_follow_up_date,
        mr.next_steps,
        lf.entry_date                    AS last_followup_date,
        lf.entry_text                    AS last_followup_text
    FROM maintenance_request mr
    LEFT JOIN building  b ON b.building_id = mr.building_id
    LEFT JOIN sector    s ON s.sector_id   = mr.sector_id
    LEFT JOIN employee  e ON e.employee_id = mr.assigned_employee_id
    LEFT JOIN LATERAL (
        SELECT entry_date, entry_text
        FROM maintenance_followup_entry
        WHERE request_id = mr.request_id
        ORDER BY entry_date DESC NULLS LAST, followup_id DESC
        LIMIT 1
    ) lf ON true
"""


def _add_label(d: dict) -> dict:
    d["source_calendar_label"] = SOURCE_CALENDAR_LABELS.get(d.get("source_calendar") or "")
    return d


def list_requests(
    conn,
    *,
    start_date: date,
    end_date: date,
    status: list[str],
    building_id: int | None,
    sector_id: int | None,
    assigned_employee_id: int | None,
    urgency: str | None,
    source_calendar: str | None,
    q: str | None,
    sort_by: str,
    sort_dir: str,
    limit: int,
    offset: int,
    scope_sql: str,
    scope_params: dict[str, Any],
) -> tuple[int, list[dict]]:
    conditions: list[str] = ["mr.start_date BETWEEN %(start_date)s AND %(end_date)s"]
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date, **scope_params}

    if status:
        conditions.append("mr.status::text = ANY(%(status)s)")
        params["status"] = status
    if building_id is not None:
        conditions.append("mr.building_id = %(building_id)s")
        params["building_id"] = building_id
    if sector_id is not None:
        conditions.append("mr.sector_id = %(sector_id)s")
        params["sector_id"] = sector_id
    if assigned_employee_id is not None:
        conditions.append("mr.assigned_employee_id = %(assigned_employee_id)s")
        params["assigned_employee_id"] = assigned_employee_id
    if urgency is not None:
        conditions.append("mr.urgency_tier::text = %(urgency)s")
        params["urgency"] = urgency
    if source_calendar is not None:
        conditions.append("mr.source_calendar = %(source_calendar)s")
        params["source_calendar"] = source_calendar
    if q is not None:
        conditions.append("""(
            unaccent(mr.asnu) ILIKE unaccent(%(q_pat)s)
            OR unaccent(mr.raw_title) ILIKE unaccent(%(q_pat)s)
            OR unaccent(b.adresse) ILIKE unaccent(%(q_pat)s)
            OR unaccent(b.web_building_name) ILIKE unaccent(%(q_pat)s)
            OR unaccent(e.nom_employe) ILIKE unaccent(%(q_pat)s)
        )""")
        params["q_pat"] = f"%{q}%"

    where = " AND ".join(conditions)
    if scope_sql:
        where = f"({where}) {scope_sql}"

    sort_expr = SORT_SQL[sort_by]  # whitelisted — never from user string
    direction = "ASC" if sort_dir == "asc" else "DESC"

    total = conn.execute(
        f"""SELECT count(*) AS n
            FROM maintenance_request mr
            LEFT JOIN building b ON b.building_id = mr.building_id
            LEFT JOIN employee e ON e.employee_id = mr.assigned_employee_id
            WHERE {where}""",
        params,
    ).fetchone()["n"]

    params["_limit"] = limit
    params["_offset"] = offset

    rows = conn.execute(
        f"""
        {_LIST_SELECT}
        WHERE {where}
        ORDER BY {sort_expr} {direction} NULLS LAST, mr.request_id ASC
        LIMIT %(_limit)s OFFSET %(_offset)s
        """,
        params,
    ).fetchall()

    return total, [_add_label(dict(r)) for r in rows]


def get_request(
    conn,
    request_id: int,
    *,
    scope_sql: str,
    scope_params: dict[str, Any],
) -> dict | None:
    params: dict[str, Any] = {"request_id": request_id, **scope_params}
    where = "mr.request_id = %(request_id)s"
    if scope_sql:
        where = f"({where}) {scope_sql}"

    row = conn.execute(
        f"""
        SELECT
            mr.request_id,
            mr.start_date,
            mr.asnu,
            mr.urgency_tier::text            AS urgency_tier,
            mr.urgency_raw,
            mr.raw_title,
            mr.building_id,
            b.adresse                        AS building_address,
            b.web_building_name              AS building_name,
            mr.sector_id,
            s.territoire,
            s.color_code,
            mr.assigned_employee_id,
            e.nom_employe                    AS assigned_employee_name,
            mr.subcontractor_name,
            mr.time_estimate_bucket::text    AS time_estimate_bucket,
            mr.time_estimate_raw,
            mr.source_calendar,
            mr.status::text                  AS status,
            mr.event_id,
            mr.estimated_cost,
            mr.next_follow_up_date,
            mr.next_steps,
            mr.problem_summary,
            mr.triage_summary,
            mr.work_performed,
            mr.other_notes,
            mr.delegable_notes,
            mr.report_notes,
            mr.tenant_agreement_notes,
            mr.entry_permission,
            mr.animals,
            mr.occupants_raw,
            mr.follow_up_expected,
            mr.unit_id,
            mr.unit_label,
            mr.project_id,
            mr.project_label,
            mr.html_link,
            mr.caller_type,
            mr.caller_name,
            mr.caller_phone,
            mr.caller_email,
            mr.caller_tenant_id
        FROM maintenance_request mr
        LEFT JOIN building  b ON b.building_id = mr.building_id
        LEFT JOIN sector    s ON s.sector_id   = mr.sector_id
        LEFT JOIN employee  e ON e.employee_id = mr.assigned_employee_id
        WHERE {where}
        """,
        params,
    ).fetchone()

    if row is None:
        return None

    return _add_label(dict(row))


def list_followup_entries(conn, request_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT followup_id, entry_date, entered_by_initials, entry_text
        FROM maintenance_followup_entry
        WHERE request_id = %(request_id)s
        ORDER BY entry_date ASC NULLS LAST, followup_id ASC
        """,
        {"request_id": request_id},
    ).fetchall()
    return [dict(r) for r in rows]


def list_sectors(conn) -> list[dict]:
    return [
        dict(r) for r in conn.execute(
            "SELECT sector_id, territoire, color_code FROM sector ORDER BY territoire"
        ).fetchall()
    ]


def list_buildings(conn, sector_id: int | None) -> list[dict]:
    if sector_id is not None:
        rows = conn.execute(
            """
            SELECT building_id, adresse, web_building_name, sector_id
            FROM building WHERE sector_id = %(sector_id)s ORDER BY adresse
            """,
            {"sector_id": sector_id},
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT building_id, adresse, web_building_name, sector_id FROM building ORDER BY adresse"
        ).fetchall()
    return [dict(r) for r in rows]


def list_employees(conn, role: str | None) -> list[dict]:
    if role is not None:
        rows = conn.execute(
            """
            SELECT e.employee_id, e.nom_employe, er.role
            FROM employee e
            JOIN employee_role er ON er.employee_id = e.employee_id
            WHERE e.is_active = true AND er.role = %(role)s
            ORDER BY e.nom_employe
            """,
            {"role": role},
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT e.employee_id, e.nom_employe, er.role
            FROM employee e
            JOIN employee_role er ON er.employee_id = e.employee_id
            WHERE e.is_active = true
            ORDER BY e.nom_employe, er.role
            """
        ).fetchall()
    return [dict(r) for r in rows]
