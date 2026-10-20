"""Persistence for tenant satisfaction surveys."""
from __future__ import annotations

import secrets


def create_survey(conn, *, request_id: int, visit_id: int | None, employee_id: int) -> str:
    token = secrets.token_urlsafe(24)
    conn.execute(
        """
        INSERT INTO satisfaction_survey (token, request_id, visit_id, employee_id)
        VALUES (%(token)s, %(rid)s, %(vid)s, %(eid)s)
        """,
        {"token": token, "rid": request_id, "vid": visit_id, "eid": employee_id},
    )
    return token


def get_by_token(conn, token: str) -> dict | None:
    row = conn.execute(
        """
        SELECT s.survey_id, s.token, s.request_id, s.employee_id, s.submitted_at,
               e.nom_employe AS technician_name,
               b.adresse AS building_address
        FROM satisfaction_survey s
        JOIN employee e ON e.employee_id = s.employee_id
        JOIN maintenance_request mr ON mr.request_id = s.request_id
        LEFT JOIN building b ON b.building_id = mr.building_id
        WHERE s.token = %(token)s
        """,
        {"token": token},
    ).fetchone()
    return dict(row) if row else None


def submit(conn, *, token: str, polite: bool, satisfied: bool,
           problem_solved: bool, comments: str | None) -> bool:
    """Returns False if already submitted or token missing."""
    row = conn.execute(
        """
        UPDATE satisfaction_survey
        SET polite = %(polite)s,
            satisfied = %(satisfied)s,
            problem_solved = %(solved)s,
            comments = %(comments)s,
            submitted_at = now()
        WHERE token = %(token)s AND submitted_at IS NULL
        RETURNING survey_id
        """,
        {
            "token": token, "polite": polite, "satisfied": satisfied,
            "solved": problem_solved, "comments": comments,
        },
    ).fetchone()
    return row is not None
