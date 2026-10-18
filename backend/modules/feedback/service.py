"""Business logic for triage notes feedback."""
from __future__ import annotations

from backend.core.exceptions import NotFoundError, ValidationFailed

from . import repository as repo
from .schemas import FeedbackBody, FeedbackResponse


def get_feedback(conn, request_id: int, employee_id: int) -> FeedbackResponse:
    row = repo.get_feedback(conn, request_id, employee_id)
    if row is None:
        raise NotFoundError("No feedback for this employee on this request")
    return FeedbackResponse(**row)


def upsert_feedback(
    conn, request_id: int, employee_id: int, body: FeedbackBody
) -> FeedbackResponse:
    snapshot = repo.get_triage_snapshot(conn, request_id)
    if snapshot is None:
        raise NotFoundError("Request not found")
    if not snapshot.get("triage_model_version"):
        raise ValidationFailed("Triage has not run for this request")

    row = repo.upsert_feedback(
        conn,
        request_id,
        employee_id,
        body.level,
        body.reason,
        snapshot,
        snapshot["triage_model_version"],
    )
    return FeedbackResponse(**row)
