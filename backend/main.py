"""FastAPI application factory.

Dev server (with auto-reload):
    uvicorn backend.main:app --reload
"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from backend.core.db import DBTransactionMiddleware, get_db_conn
from backend.core.exceptions import AppError
from backend.middleware.error_handler import (
    app_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from backend.middleware.request_id import RequestIDMiddleware
from backend.middleware.request_logging import RequestLoggingMiddleware
from backend.modules.buildings.router import router as buildings_router
from backend.modules.employees.router import router as employees_router
from backend.modules.intake.router import router as intake_router
from backend.modules.requests.router import lookup_router, router as requests_router
from backend.modules.feedback.router import router as feedback_router
from backend.modules.units.router import router as units_router


class HealthResponse(BaseModel):
    status: str


def create_app() -> FastAPI:
    app = FastAPI(title="SIB Platform API", version="0.1.0")

    # Middleware — add_middleware applies in reverse: last-added is outermost.
    # Execution order on request: RequestID → Logging → DBTransaction → handler
    app.add_middleware(DBTransactionMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # Exception handlers — all failures use the same envelope
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    for router in (requests_router, lookup_router, intake_router, buildings_router,
                   units_router, employees_router, feedback_router):
        app.include_router(router, prefix="/api/v1")

    @app.get(
        "/health",
        operation_id="health_check",
        response_model=HealthResponse,
        tags=["health"],
    )
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/health/db",
        operation_id="health_db_check",
        response_model=HealthResponse,
        tags=["health"],
    )
    def health_db(conn=Depends(get_db_conn)) -> HealthResponse:
        conn.execute("SELECT 1")
        return HealthResponse(status="ok")

    return app


app = create_app()
