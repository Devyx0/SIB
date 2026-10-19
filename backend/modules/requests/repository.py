"""Raw-SQL repository for the requests module. Receives a psycopg3 connection."""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from typing import Any

from .schemas import SORT_SQL, SOURCE_CALENDAR_LABELS

_SENTINEL_EMAIL = 'info@sibelanger.com'
_SENTINEL_PHONE = '(000) 000-0000'

_UPDATABLE_FIELDS: dict[str, str] = {
    "assigned_employee_id": "assigned_employee_id = %(v)s",
    "start_date":            "start_date = %(v)s",
    "urgency_tier":          "urgency_tier = %(v)s::urgency_tier",
    "next_follow_up_date":   "next_follow_up_date = %(v)s",
    "next_steps":            "next_steps = %(v)s",
    "estimated_cost":        "estimated_cost = %(v)s",
    "status":                "status = %(v)s::request_status",
    "en_route_at":           "en_route_at = %(v)s",
    "closed_at":             "closed_at = %(v)s",
    "closeout_outcome":      "closeout_outcome = %(v)s::closeout_outcome",
    "closeout_urgent":       "closeout_urgent = %(v)s",
    "work_performed":        "work_performed = %(v)s",
}

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
        lf.entry_text                    AS last_followup_text,
        COALESCE(mr.unit_label, u.numero_appartement) AS unit_label,
        mr.en_route_at,
        mr.closeout_outcome::text        AS closeout_outcome,
        mr.closeout_urgent
    FROM maintenance_request mr
    LEFT JOIN building  b ON b.building_id = mr.building_id
    LEFT JOIN sector    s ON s.sector_id   = mr.sector_id
    LEFT JOIN employee  e ON e.employee_id = mr.assigned_employee_id
    LEFT JOIN unit      u ON u.unit_id     = mr.unit_id
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


def _normalise_contacts(d: dict) -> dict:
    d["caller_email_placeholder"] = d.get("caller_email") == _SENTINEL_EMAIL
    d["caller_phone_placeholder"] = d.get("caller_phone") == _SENTINEL_PHONE
    if d["caller_email_placeholder"]:
        d["caller_email"] = None
    if d["caller_phone_placeholder"]:
        d["caller_phone"] = None
    return d


def list_requests(
    conn,
    *,
    start_date: date | None,
    end_date: date | None,
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
    redispatch: bool = False,
) -> tuple[int, list[dict]]:
    conditions: list[str] = []
    params: dict[str, Any] = {**scope_params}

    if source_calendar == "unrouted":
        # 90-day window on submission_date; start_date is NULL on intake rows,
        # so any date range is ignored here.
        conditions.append(
            "mr.source_calendar IS NULL"
            " AND mr.status::text NOT IN ('closed', 'en_route')"
            " AND (mr.submission_date >= NOW() - INTERVAL '90 days' OR mr.submission_date IS NULL)"
        )
    elif start_date is not None:
        conditions.append("mr.start_date BETWEEN %(start_date)s AND %(end_date)s")
        params["start_date"] = start_date
        params["end_date"] = end_date

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
    if source_calendar is not None and source_calendar != "unrouted":
        conditions.append("mr.source_calendar = %(source_calendar)s")
        params["source_calendar"] = source_calendar
    if redispatch:
        # « À redispatcher »: returned by closeout outcomes 3/4, awaiting the
        # coordinator — triaged, unassigned, last outcome expertise/failed.
        conditions.append(
            "mr.status::text = 'triaged' AND mr.assigned_employee_id IS NULL"
            " AND mr.closeout_outcome::text IN ('partial_expertise', 'failed')"
        )
    if q is not None:
        conditions.append("""(
            unaccent(mr.asnu) ILIKE unaccent(%(q_pat)s)
            OR unaccent(mr.raw_title) ILIKE unaccent(%(q_pat)s)
            OR unaccent(b.adresse) ILIKE unaccent(%(q_pat)s)
            OR unaccent(b.web_building_name) ILIKE unaccent(%(q_pat)s)
            OR unaccent(e.nom_employe) ILIKE unaccent(%(q_pat)s)
        )""")
        params["q_pat"] = f"%{q}%"

    where = " AND ".join(conditions) if conditions else "TRUE"
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


def list_dossiers(
    conn,
    *,
    outcome: str | None,
    employee_id: int | None,
    start_date: date | None,
    end_date: date | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict]]:
    """Calls with at least one visit (any status), newest last-visit first.
    Driven from request_visit (DISTINCT ON picks the latest visit per
    request) so only visited requests are scanned, not every call.
    photo_count counts rows exactly as action_upload_photo writes them
    (file_type='photo', photo_context='closeout')."""
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if outcome is not None:
        conditions.append("lv.outcome::text = %(outcome)s")
        params["outcome"] = outcome
    if employee_id is not None:
        # « A fait une visite » — matches ANY visit, not just the latest.
        conditions.append(
            "EXISTS (SELECT 1 FROM request_visit ve"
            " WHERE ve.request_id = lv.request_id AND ve.employee_id = %(employee_id)s)"
        )
        params["employee_id"] = employee_id
    if start_date is not None:
        conditions.append(
            "(lv.en_route_at AT TIME ZONE 'America/Toronto')::date"
            " BETWEEN %(start_date)s AND %(end_date)s"
        )
        params["start_date"] = start_date
        params["end_date"] = end_date
    if q is not None:
        conditions.append("""(
            unaccent(mr.asnu) ILIKE unaccent(%(q_pat)s)
            OR unaccent(mr.raw_title) ILIKE unaccent(%(q_pat)s)
            OR unaccent(b.adresse) ILIKE unaccent(%(q_pat)s)
            OR unaccent(b.web_building_name) ILIKE unaccent(%(q_pat)s)
            OR unaccent(e.nom_employe) ILIKE unaccent(%(q_pat)s)
            OR unaccent(COALESCE(mr.unit_label, u.numero_appartement)) ILIKE unaccent(%(q_pat)s)
        )""")
        params["q_pat"] = f"%{q}%"

    where = " AND ".join(conditions) if conditions else "TRUE"
    base = """
        FROM (
            SELECT DISTINCT ON (v.request_id)
                   v.request_id, v.en_route_at, v.closeout_at, v.outcome, v.employee_id
            FROM request_visit v
            ORDER BY v.request_id, v.en_route_at DESC, v.visit_id DESC
        ) lv
        JOIN maintenance_request mr ON mr.request_id = lv.request_id
        LEFT JOIN building  b ON b.building_id = mr.building_id
        LEFT JOIN sector    s ON s.sector_id   = mr.sector_id
        LEFT JOIN employee  e ON e.employee_id = lv.employee_id
        LEFT JOIN unit      u ON u.unit_id     = mr.unit_id
    """

    total = conn.execute(
        f"SELECT count(*) AS n {base} WHERE {where}", params
    ).fetchone()["n"]

    params["_limit"] = limit
    params["_offset"] = offset
    rows = conn.execute(
        f"""
        SELECT
            mr.request_id,
            lv.en_route_at                   AS last_en_route_at,
            lv.closeout_at                   AS last_closeout_at,
            COALESCE(mr.unit_label, u.numero_appartement) AS unit_label,
            mr.raw_title,
            s.territoire,
            s.color_code,
            e.nom_employe                    AS employee_name,
            lv.outcome::text                 AS last_outcome,
            (SELECT count(*) FROM maintenance_attachment a
              WHERE a.request_id = mr.request_id
                AND a.file_type = 'photo'
                AND a.photo_context = 'closeout')                           AS photo_count,
            (SELECT count(*) FROM request_visit vc
              WHERE vc.request_id = mr.request_id)                          AS visit_count,
            mr.closeout_urgent,
            mr.status::text                  AS status
        {base}
        WHERE {where}
        ORDER BY lv.en_route_at DESC, mr.request_id DESC
        LIMIT %(_limit)s OFFSET %(_offset)s
        """,
        params,
    ).fetchall()
    return total, [dict(r) for r in rows]


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
            COALESCE(mr.unit_label, u.numero_appartement) AS unit_label,
            mr.project_id,
            mr.project_label,
            mr.html_link,
            mr.caller_type,
            mr.caller_name,
            mr.caller_phone,
            mr.caller_email,
            mr.caller_tenant_id,
            mr.raw_caller_body,
            mr.problems,
            mr.triage_model_version,
            mr.ft_link,
            mr.ft_name,
            mr.en_route_at,
            mr.closeout_outcome::text        AS closeout_outcome,
            mr.closeout_urgent
        FROM maintenance_request mr
        LEFT JOIN building  b ON b.building_id = mr.building_id
        LEFT JOIN sector    s ON s.sector_id   = mr.sector_id
        LEFT JOIN employee  e ON e.employee_id = mr.assigned_employee_id
        LEFT JOIN unit      u ON u.unit_id     = mr.unit_id
        WHERE {where}
        """,
        params,
    ).fetchone()

    if row is None:
        return None

    return _normalise_contacts(_add_label(dict(row)))


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


def lock_request(conn, request_id: int) -> dict | None:
    """SELECT FOR UPDATE — returns mutable snapshot needed for concurrency checks."""
    row = conn.execute(
        """
        SELECT request_id, status::text, assigned_employee_id, start_date,
               urgency_tier::text AS urgency_tier, next_follow_up_date,
               next_steps, estimated_cost, source_calendar, en_route_at,
               closed_at, closeout_outcome::text AS closeout_outcome,
               closeout_urgent, work_performed
        FROM maintenance_request
        WHERE request_id = %(request_id)s
        FOR UPDATE
        """,
        {"request_id": request_id},
    ).fetchone()
    return dict(row) if row else None


def is_valid_assignee(conn, employee_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM employee e
        JOIN employee_role er ON er.employee_id = e.employee_id
        WHERE e.employee_id = %(emp_id)s AND e.is_active = true
          AND er.role IN ('technician', 'contractor')
        LIMIT 1
        """,
        {"emp_id": employee_id},
    ).fetchone()
    return row is not None


def update_field(conn, request_id: int, column: str, value: Any) -> None:
    # ponytail: column is validated against _UPDATABLE_FIELDS — never from user string
    sql_frag = _UPDATABLE_FIELDS[column]
    conn.execute(
        f"UPDATE maintenance_request SET {sql_frag} WHERE request_id = %(request_id)s",
        {"v": value, "request_id": request_id},
    )


def add_log_entry(conn, request_id: int, entry_text: str, initials: str, entry_date: date) -> int:
    row = conn.execute(
        """
        INSERT INTO maintenance_followup_entry (request_id, entry_text, entered_by_initials, entry_date)
        VALUES (%(request_id)s, %(entry_text)s, %(initials)s, %(entry_date)s)
        RETURNING followup_id
        """,
        {"request_id": request_id, "entry_text": entry_text,
         "initials": initials, "entry_date": entry_date},
    ).fetchone()
    return row["followup_id"]


def write_justification(
    conn, *, request_id: int, employee_id: int, decision_type: str,
    before_value: dict | None, after_value: dict | None, text: str, input_method: str,
) -> None:
    conn.execute(
        """
        INSERT INTO decision_justification_log
            (request_id, employee_id, decision_type, before_value, after_value,
             justification_text, input_method)
        VALUES (%(request_id)s, %(employee_id)s, %(decision_type)s,
                %(before_value)s::jsonb, %(after_value)s::jsonb,
                %(text)s, %(input_method)s)
        """,
        {
            "request_id": request_id, "employee_id": employee_id,
            "decision_type": decision_type,
            "before_value": json.dumps(before_value) if before_value is not None else None,
            "after_value":  json.dumps(after_value)  if after_value  is not None else None,
            "text": text, "input_method": input_method,
        },
    )


def get_open_visit(conn, employee_id: int) -> dict | None:
    """The employee's open visit (closeout_at IS NULL) with its call title, if any."""
    row = conn.execute(
        """
        SELECT v.visit_id, v.request_id, v.en_route_at, mr.raw_title
        FROM request_visit v
        JOIN maintenance_request mr ON mr.request_id = v.request_id
        WHERE v.employee_id = %(employee_id)s AND v.closeout_at IS NULL
        """,
        {"employee_id": employee_id},
    ).fetchone()
    return dict(row) if row else None


def insert_visit(
    conn, *, request_id: int, employee_id: int,
    lat: float | None, lng: float | None,
) -> int:
    row = conn.execute(
        """
        INSERT INTO request_visit (request_id, employee_id, en_route_lat, en_route_lng)
        VALUES (%(request_id)s, %(employee_id)s, %(lat)s, %(lng)s)
        RETURNING visit_id
        """,
        {"request_id": request_id, "employee_id": employee_id, "lat": lat, "lng": lng},
    ).fetchone()
    return row["visit_id"]


def insert_outbox(
    conn, *, request_id: int, visit_id: int, channel: str, recipient: str | None,
    subject: str | None, body: str, employee_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO message_outbox
            (request_id, visit_id, channel, recipient, subject, body, created_by_employee_id)
        VALUES (%(request_id)s, %(visit_id)s, %(channel)s, %(recipient)s,
                %(subject)s, %(body)s, %(employee_id)s)
        """,
        {"request_id": request_id, "visit_id": visit_id, "channel": channel,
         "recipient": recipient, "subject": subject, "body": body,
         "employee_id": employee_id},
    )


def next_attachment_id(conn) -> int:
    """Reserve an attachment id so the storage path is known BEFORE the file
    is uploaded — the row is only inserted after the upload succeeds."""
    return conn.execute(
        "SELECT nextval(pg_get_serial_sequence('maintenance_attachment', 'attachment_id')) AS id"
    ).fetchone()["id"]


def insert_photo(
    conn, *, attachment_id: int, request_id: int, employee_id: int, storage_path: str,
) -> None:
    """Insert the attachment row for an already-uploaded file. The explicit id
    comes from next_attachment_id (same sequence — no drift)."""
    conn.execute(
        """
        INSERT INTO maintenance_attachment
            (attachment_id, request_id, file_type, photo_context,
             uploaded_by_employee_id, storage_path)
        VALUES (%(attachment_id)s, %(request_id)s, 'photo', 'closeout',
                %(employee_id)s, %(storage_path)s)
        """,
        {"attachment_id": attachment_id, "request_id": request_id,
         "employee_id": employee_id, "storage_path": storage_path},
    )


def get_photo(conn, request_id: int, attachment_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT a.attachment_id, a.storage_path, a.uploaded_by_employee_id,
               a.visit_id, mr.assigned_employee_id
        FROM maintenance_attachment a
        JOIN maintenance_request mr ON mr.request_id = a.request_id
        WHERE a.attachment_id = %(aid)s AND a.request_id = %(rid)s
        """,
        {"aid": attachment_id, "rid": request_id},
    ).fetchone()
    return dict(row) if row else None


def count_usable_photos(conn, request_id: int, employee_id: int, attachment_ids: list[int]) -> int:
    """Photos among *attachment_ids* that belong to this request, were uploaded
    by this employee, and were not consumed by a previous closeout."""
    return conn.execute(
        """
        SELECT count(*) AS n FROM maintenance_attachment
        WHERE attachment_id = ANY(%(ids)s)
          AND request_id = %(rid)s
          AND uploaded_by_employee_id = %(emp)s
          AND photo_context = 'closeout'
          AND visit_id IS NULL
        """,
        {"ids": attachment_ids, "rid": request_id, "emp": employee_id},
    ).fetchone()["n"]


def close_visit(
    conn, *, visit_id: int, outcome: str, comment: str,
    lat: float | None, lng: float | None,
) -> None:
    conn.execute(
        """
        UPDATE request_visit
        SET closeout_at = NOW(), outcome = %(outcome)s::closeout_outcome,
            closeout_comment = %(comment)s,
            closeout_lat = %(lat)s, closeout_lng = %(lng)s
        WHERE visit_id = %(visit_id)s
        """,
        {"visit_id": visit_id, "outcome": outcome, "comment": comment,
         "lat": lat, "lng": lng},
    )


def mark_photos_used(conn, visit_id: int, attachment_ids: list[int]) -> None:
    conn.execute(
        "UPDATE maintenance_attachment SET visit_id = %(v)s WHERE attachment_id = ANY(%(ids)s)",
        {"v": visit_id, "ids": attachment_ids},
    )


def list_visits(conn, request_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT v.visit_id, v.employee_id, e.nom_employe AS employee_name,
               v.en_route_at, v.closeout_at, v.outcome::text AS outcome,
               v.closeout_comment,
               COALESCE(array_agg(a.attachment_id) FILTER (WHERE a.attachment_id IS NOT NULL),
                        '{}') AS photo_ids
        FROM request_visit v
        LEFT JOIN employee e ON e.employee_id = v.employee_id
        LEFT JOIN maintenance_attachment a ON a.visit_id = v.visit_id
        WHERE v.request_id = %(request_id)s
        GROUP BY v.visit_id, e.nom_employe
        ORDER BY v.en_route_at ASC
        """,
        {"request_id": request_id},
    ).fetchall()
    return [dict(r) for r in rows]


def get_message_context(conn, request_id: int) -> dict:
    """Address + cleaned tenant contact for the en-route notification."""
    row = conn.execute(
        """
        SELECT b.adresse,
               COALESCE(mr.unit_label, u.numero_appartement) AS unit_label,
               mr.caller_phone, mr.caller_email
        FROM maintenance_request mr
        LEFT JOIN building b ON b.building_id = mr.building_id
        LEFT JOIN unit     u ON u.unit_id     = mr.unit_id
        WHERE mr.request_id = %(request_id)s
        """,
        {"request_id": request_id},
    ).fetchone()
    return _normalise_contacts(dict(row))


def write_provenance(
    conn, *, target_table: str, target_pk: str, target_column: str,
    employee_id: int, previous_value: str | None, new_value: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO data_provenance
            (target_table, target_pk, target_column, source_type, employee_id,
             previous_value, raw_value, ingested_value, ingested_at)
        VALUES (%(target_table)s, %(target_pk)s, %(target_column)s, 'app', %(employee_id)s,
                %(previous_value)s, %(new_value)s, %(new_value)s, NOW())
        """,
        {
            "target_table": target_table, "target_pk": target_pk,
            "target_column": target_column, "employee_id": employee_id,
            "previous_value": previous_value, "new_value": new_value,
        },
    )


def list_justification_entries(conn, request_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, decision_type, before_value, after_value, justification_text,
               input_method, created_at::text AS created_at, employee_id
        FROM decision_justification_log
        WHERE request_id = %(request_id)s
        ORDER BY created_at ASC, id ASC
        """,
        {"request_id": request_id},
    ).fetchall()
    return [dict(r) for r in rows]


def list_units(conn, building_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT unit_id, rue, numero_appartement FROM unit
           WHERE building_id = %(bid)s AND numero_appartement IS NOT NULL""",
        {"bid": building_id},
    ).fetchall()
    units = [dict(r) for r in rows]

    def _sort_key(u: dict) -> tuple:
        try:
            civic_num = int(u["rue"].split(",")[0].strip()) if u["rue"] else 10 ** 9
        except (ValueError, AttributeError):
            civic_num = 10 ** 9
        digits = re.sub(r"\D", "", u["numero_appartement"] or "")
        apt_num = int(digits) if digits else 10 ** 9
        return (civic_num, apt_num, u["numero_appartement"] or "")

    return sorted(units, key=_sort_key)


def list_sectors(conn, sector_ids: frozenset[int] | None = None) -> list[dict]:
    """List sectors. If sector_ids is set, only those ids are returned."""
    if sector_ids is not None:
        if not sector_ids:
            return []
        rows = conn.execute(
            """
            SELECT sector_id, territoire, color_code FROM sector
            WHERE sector_id = ANY(%(ids)s) ORDER BY territoire
            """,
            {"ids": list(sector_ids)},
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sector_id, territoire, color_code FROM sector ORDER BY territoire"
        ).fetchall()
    return [dict(r) for r in rows]


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


def get_triage_status(conn, request_id: int) -> dict | None:
    row = conn.execute(
        "SELECT status::text AS status, triage_started_at FROM maintenance_request WHERE request_id = %(rid)s",
        {"rid": request_id},
    ).fetchone()
    return dict(row) if row else None


def list_routed_unscheduled(
    conn,
    *,
    scope_sql: str,
    scope_params: dict[str, Any],
    building_id: int | None,
    sector_id: int | None,
    assigned_employee_id: int | None,
    urgency: str | None,
    source_calendar: str | None,
    status: list[str],
    q: str | None,
) -> list[dict]:
    """Routed calls with no start_date yet — shown as 'À planifier' group."""
    conditions: list[str] = [
        "mr.source_calendar IS NOT NULL",
        "mr.start_date IS NULL",
        "mr.status::text NOT IN ('closed', 'en_route')",
    ]
    params: dict[str, Any] = {**scope_params}
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
    if status:
        conditions.append("mr.status::text = ANY(%(status)s)")
        params["status"] = status
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
    rows = conn.execute(
        f"""
        {_LIST_SELECT}
        WHERE {where}
        ORDER BY mr.submission_date ASC NULLS LAST, mr.request_id ASC
        """,
        params,
    ).fetchall()
    return [_add_label(dict(r)) for r in rows]


def route_request(
    conn, *, request_id: int, source_calendar: str,
    old_source_calendar: str | None, employee_id: int,
) -> None:
    conn.execute(
        "UPDATE maintenance_request SET source_calendar = %(cal)s WHERE request_id = %(rid)s",
        {"cal": source_calendar, "rid": request_id},
    )
    write_provenance(conn,
        target_table="maintenance_request", target_pk=str(request_id),
        target_column="source_calendar", employee_id=employee_id,
        previous_value=old_source_calendar, new_value=source_calendar,
    )
