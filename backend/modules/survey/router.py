"""Public (unauthenticated) satisfaction survey endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.db import get_db_conn

from . import service
from .schemas import SurveyPublic, SurveySubmitBody, SurveySubmitResponse

router = APIRouter(prefix="/survey", tags=["survey"])


@router.get("/{token}", operation_id="survey_get", response_model=SurveyPublic)
def survey_get(token: str, conn=Depends(get_db_conn)) -> SurveyPublic:
    return service.get_survey(conn, token)


@router.post(
    "/{token}",
    operation_id="survey_submit",
    response_model=SurveySubmitResponse,
)
def survey_submit(
    token: str, body: SurveySubmitBody, conn=Depends(get_db_conn),
) -> SurveySubmitResponse:
    return service.submit_survey(conn, token, body)
