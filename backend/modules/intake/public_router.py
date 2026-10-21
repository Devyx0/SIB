"""Unauthenticated public intake (WordPress iframe)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from backend.core.db import get_db_conn

from . import public_service
from .schemas import (
    PublicLookupBody,
    PublicLookupResponse,
    PublicSubmitBody,
    PublicSubmitResponse,
)

router = APIRouter(prefix="/public/intake", tags=["public-intake"])


def _remote_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


@router.post(
    "/lookup",
    operation_id="public_intake_lookup",
    response_model=PublicLookupResponse,
)
def public_intake_lookup(
    body: PublicLookupBody,
    request: Request,
    conn=Depends(get_db_conn),
) -> PublicLookupResponse:
    return public_service.lookup_tenant(conn, body, remote_ip=_remote_ip(request))


@router.post(
    "/submit",
    operation_id="public_intake_submit",
    response_model=PublicSubmitResponse,
    status_code=201,
)
def public_intake_submit(
    body: PublicSubmitBody,
    request: Request,
    background_tasks: BackgroundTasks,
    conn=Depends(get_db_conn),
) -> PublicSubmitResponse:
    result = public_service.create_public(conn, body, remote_ip=_remote_ip(request))
    from backend.modules.requests import service as req_service
    from backend.modules.requests.router import _run_triage_background

    req_service.action_trigger_triage(conn, result.request_id)
    background_tasks.add_task(_run_triage_background, result.request_id, body.ui_lang)
    return result
