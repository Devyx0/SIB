"""Coordinator alert helpers."""
from __future__ import annotations

from . import repository as repo
from .schemas import AlertListResponse, AlertRow


def notify(conn, *, request_id: int, kind: str, summary: str) -> None:
    repo.insert_alert(conn, request_id=request_id, kind=kind, summary=summary)


def list_for_coordinator(conn, *, unread_only: bool = False) -> AlertListResponse:
    items = [
        AlertRow(
            alert_id=r["alert_id"],
            request_id=r["request_id"],
            kind=r["kind"],
            summary=r["summary"],
            created_at=r["created_at"],
            read_at=r.get("read_at"),
            raw_title=r.get("raw_title"),
        )
        for r in repo.list_alerts(conn, unread_only=unread_only)
    ]
    return AlertListResponse(items=items, unread_count=repo.unread_count(conn))


def mark_read(conn, alert_id: int, employee_id: int) -> None:
    repo.mark_read(conn, alert_id, employee_id)


def mark_all_read(conn, employee_id: int) -> int:
    return repo.mark_all_read(conn, employee_id)
