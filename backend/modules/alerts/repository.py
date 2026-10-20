"""Persistence for coordinator alerts."""
from __future__ import annotations


def insert_alert(conn, *, request_id: int, kind: str, summary: str) -> int:
    row = conn.execute(
        """
        INSERT INTO coordinator_alert (request_id, kind, summary)
        VALUES (%(rid)s, %(kind)s, %(summary)s)
        RETURNING alert_id
        """,
        {"rid": request_id, "kind": kind, "summary": summary},
    ).fetchone()
    return row["alert_id"]


def list_alerts(conn, *, unread_only: bool, limit: int = 50) -> list[dict]:
    where = "WHERE a.read_at IS NULL" if unread_only else ""
    rows = conn.execute(
        f"""
        SELECT a.alert_id, a.request_id, a.kind, a.summary,
               a.created_at, a.read_at, mr.raw_title
        FROM coordinator_alert a
        JOIN maintenance_request mr ON mr.request_id = a.request_id
        {where}
        ORDER BY a.created_at DESC
        LIMIT %(lim)s
        """,
        {"lim": limit},
    ).fetchall()
    return [dict(r) for r in rows]


def unread_count(conn) -> int:
    row = conn.execute(
        "SELECT count(*)::int AS n FROM coordinator_alert WHERE read_at IS NULL"
    ).fetchone()
    return row["n"]


def mark_read(conn, alert_id: int, employee_id: int) -> bool:
    row = conn.execute(
        """
        UPDATE coordinator_alert
        SET read_at = now(), read_by_employee_id = %(eid)s
        WHERE alert_id = %(aid)s AND read_at IS NULL
        RETURNING alert_id
        """,
        {"aid": alert_id, "eid": employee_id},
    ).fetchone()
    return row is not None


def mark_all_read(conn, employee_id: int) -> int:
    rows = conn.execute(
        """
        UPDATE coordinator_alert
        SET read_at = now(), read_by_employee_id = %(eid)s
        WHERE read_at IS NULL
        RETURNING alert_id
        """,
        {"eid": employee_id},
    ).fetchall()
    return len(rows)
