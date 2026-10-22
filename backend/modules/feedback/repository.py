"""Raw-SQL repository for the feedback module. Receives a psycopg3 connection."""
from __future__ import annotations

import json
from typing import Optional


def _row(row) -> dict:
    """Convert psycopg3 row to plain dict, normalising jsonb and timestamps."""
    d = dict(row)
    for k in ("edit_history", "triage_output"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    if d.get("edit_history") is None:
        d["edit_history"] = []
    for k in ("created_at", "updated_at"):
        v = d.get(k)
        if v is not None and not isinstance(v, str):
            d[k] = v.isoformat()
    return d


_RETURNING = """
    RETURNING feedback_id, request_id, employee_id,
              level::text AS level, reason, triage_output,
              triage_model_version, edit_history, created_at, updated_at
"""


def get_triage_snapshot(conn, request_id: int) -> Optional[dict]:
    """Return triage fields for snapshot; None if request not found."""
    row = conn.execute(
        """SELECT problem_summary,
                  urgency_tier::text         AS urgency_tier,
                  complexity_tier::text      AS complexity_tier,
                  time_estimate_bucket::text AS time_estimate_bucket,
                  other_notes,
                  ai_important_notes,
                  ai_next_steps,
                  triage_model_version
           FROM maintenance_request
           WHERE request_id = %s""",
        [request_id],
    ).fetchone()
    return dict(row) if row else None


def upsert_feedback(
    conn,
    request_id: int,
    employee_id: int,
    level: str,
    reason: Optional[str],
    snapshot: dict,
    model_version: str,
) -> dict:
    """Atomic INSERT … ON CONFLICT UPDATE.

    On conflict (same employee+request):
    - Always updates level, reason, triage_output, triage_model_version to
      current values (main row = current state).
    - Appends an edit_history entry with the OLD values only when at least
      one of (level, reason, triage_output) changed. No-op edits produce no
      history entry.
    - edit_history entry has 8 fields: edited_at, edited_by, old_level,
      new_level, old_reason, new_reason, old_triage_output,
      old_triage_model_version.
    """
    row = conn.execute(
        """
        INSERT INTO triage_notes_feedback
            (request_id, employee_id, level, reason, triage_output, triage_model_version)
        VALUES (%s, %s, %s::triage_feedback_level, %s, %s, %s)
        ON CONFLICT (request_id, employee_id) DO UPDATE
        SET level                = EXCLUDED.level,
            reason               = EXCLUDED.reason,
            triage_output        = EXCLUDED.triage_output,
            triage_model_version = EXCLUDED.triage_model_version,
            edit_history         = CASE
                WHEN triage_notes_feedback.level = EXCLUDED.level
                     AND triage_notes_feedback.reason IS NOT DISTINCT FROM EXCLUDED.reason
                     AND triage_notes_feedback.triage_output = EXCLUDED.triage_output
                THEN triage_notes_feedback.edit_history
                ELSE triage_notes_feedback.edit_history || jsonb_build_object(
                    'edited_at',                now(),
                    'edited_by',                triage_notes_feedback.employee_id,
                    'old_level',                triage_notes_feedback.level::text,
                    'new_level',                EXCLUDED.level::text,
                    'old_reason',               triage_notes_feedback.reason,
                    'new_reason',               EXCLUDED.reason,
                    'old_triage_output',        triage_notes_feedback.triage_output,
                    'old_triage_model_version', triage_notes_feedback.triage_model_version::text
                )
            END,
            updated_at = now()
        """
        + _RETURNING,
        [request_id, employee_id, level, reason,
         json.dumps(snapshot), model_version],
    ).fetchone()
    return _row(row)


def get_feedback(conn, request_id: int, employee_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT feedback_id, request_id, employee_id,"
        " level::text AS level, reason, triage_output,"
        " triage_model_version, edit_history, created_at, updated_at"
        " FROM triage_notes_feedback"
        " WHERE request_id = %s AND employee_id = %s",
        [request_id, employee_id],
    ).fetchone()
    return _row(row) if row else None
