"""Public survey get / submit (no auth)."""
from __future__ import annotations

from backend.core.exceptions import ConflictError, NotFoundError

from . import repository as repo
from .schemas import SurveyPublic, SurveySubmitBody, SurveySubmitResponse


def get_survey(conn, token: str) -> SurveyPublic:
    row = repo.get_by_token(conn, token)
    if row is None:
        raise NotFoundError("Sondage introuvable")
    return SurveyPublic(
        token=row["token"],
        request_id=row["request_id"],
        building_address=row.get("building_address"),
        technician_name=row.get("technician_name"),
        already_submitted=row["submitted_at"] is not None,
    )


def submit_survey(conn, token: str, body: SurveySubmitBody) -> SurveySubmitResponse:
    row = repo.get_by_token(conn, token)
    if row is None:
        raise NotFoundError("Sondage introuvable")
    if row["submitted_at"] is not None:
        raise ConflictError("Sondage déjà soumis")
    comments = body.comments.strip() if body.comments else None
    if not repo.submit(
        conn, token=token, polite=body.polite,
        satisfaction_rating=body.satisfaction_rating,
        problem_solved=body.problem_solved, comments=comments,
    ):
        raise ConflictError("Sondage déjà soumis")
    return SurveySubmitResponse()
