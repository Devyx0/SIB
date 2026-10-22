"""Coordinator in-app alert schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

AlertKind = Literal[
    "call_completed",
    "tech_log",
    "followup_added",
    "expertise_needed",
]


class AlertRow(BaseModel):
    alert_id: int
    request_id: int
    kind: AlertKind
    summary: str
    created_at: datetime
    read_at: Optional[datetime] = None
    raw_title: Optional[str] = None
    asnu: Optional[str] = None


class AlertListResponse(BaseModel):
    items: list[AlertRow]
    unread_count: int
