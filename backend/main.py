"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI

from backend.core.exceptions import AppError
from backend.middleware.error_handler import app_error_handler
from backend.middleware.request_id import RequestIDMiddleware
from backend.middleware.request_logging import RequestLoggingMiddleware
from backend.modules.buildings.router import router as buildings_router
from backend.modules.employees.router import router as employees_router
from backend.modules.intake.router import router as intake_router
from backend.modules.requests.router import router as requests_router
from backend.modules.units.router import router as units_router


def create_app() -> FastAPI:
    app = FastAPI(title="SIB Platform API", version="0.1.0")

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(AppError, app_error_handler)

    for router in (requests_router, intake_router, buildings_router,
                   units_router, employees_router):
        app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
