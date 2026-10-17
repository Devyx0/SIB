"""
DB connections.
  DBTransactionMiddleware — one pool connection per request; commits before response.
  get_db_conn()           — FastAPI dependency (pulls from request.state).
  get_legacy_conn()       — psycopg2, for frozen triage (context_builder uses psycopg2.extras).
"""
from __future__ import annotations

import logging

import psycopg2
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import settings

logger = logging.getLogger("backend.db")

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if settings.DB_TARGET == "local":
            conninfo = (
                f"host={settings.LOCAL_DB_HOST} port={settings.LOCAL_DB_PORT}"
                f" user={settings.LOCAL_DB_USER} password={settings.LOCAL_DB_PASSWORD}"
                f" dbname={settings.LOCAL_DB_NAME}"
            )
        else:
            conninfo = (
                f"host={settings.SUPABASE_HOST} port=5432"
                f" user=postgres.{settings.SUPABASE_PROJECT_REF}"
                f" password={settings.DATABASE_PASSWORD}"
                f" dbname=postgres sslmode=require"
            )
        _pool = ConnectionPool(
            conninfo, open=True,
            min_size=2, max_size=10, timeout=5.0,
            kwargs={"row_factory": dict_row},
        )
    return _pool


class DBTransactionMiddleware(BaseHTTPMiddleware):
    """
    Acquires one connection per request from the pool, stores it on
    request.state.db_conn, runs the handler, then commits before returning
    the buffered response to the client.

    BaseHTTPMiddleware.call_next buffers the full response body before
    returning, so conn.commit() below runs BEFORE any bytes reach the client.
    A commit failure returns 500 — the handler's response is discarded.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            conn_ctx = get_pool().connection()
        except PoolTimeout:
            rid = getattr(request.state, "request_id", None)
            logger.warning("Pool exhausted  req=%s  path=%s", rid, request.url.path)
            return JSONResponse(
                status_code=503,
                content={"error": {
                    "code":       "SERVICE_UNAVAILABLE",
                    "message":    "Server is busy — please retry",
                    "request_id": rid,
                    "details":    None,
                }},
            )
        with conn_ctx as conn:
            request.state.db_conn = conn
            try:
                response = await call_next(request)
            except Exception:
                conn.rollback()
                raise
            if response.status_code >= 400:
                conn.rollback()
                return response
            try:
                conn.commit()
            except Exception:
                conn.rollback()
                rid = getattr(request.state, "request_id", None)
                logger.error(
                    "DB commit failed  req=%s  path=%s",
                    rid, request.url.path, exc_info=True,
                )
                return JSONResponse(
                    status_code=500,
                    content={"error": {
                        "code":       "INTERNAL_ERROR",
                        "message":    "An unexpected error occurred",
                        "request_id": rid,
                        "details":    None,
                    }},
                )
            return response


def get_db_conn(request: Request):
    """FastAPI dependency: returns the per-request connection set by DBTransactionMiddleware."""
    return request.state.db_conn


def get_legacy_conn():
    """
    psycopg2 connection for frozen triage code.
    # ponytail: triage has import psycopg2.extras at module level; psycopg3 migration
    # waits until the triage freeze lifts.
    """
    if settings.DB_TARGET == "local":
        return psycopg2.connect(
            host=settings.LOCAL_DB_HOST,
            port=settings.LOCAL_DB_PORT,
            user=settings.LOCAL_DB_USER,
            password=settings.LOCAL_DB_PASSWORD,
            dbname=settings.LOCAL_DB_NAME,
        )
    return psycopg2.connect(
        host=settings.SUPABASE_HOST,
        port=5432,
        user=f"postgres.{settings.SUPABASE_PROJECT_REF}",
        password=settings.DATABASE_PASSWORD,
        dbname="postgres",
        sslmode="require",
        options="-c statement_timeout=0",
    )
