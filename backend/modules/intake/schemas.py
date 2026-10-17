"""Schemas for the intake module (manual create)."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class ManualCreateBody(BaseModel):
    caller_name: str = Field(..., min_length=1)
    caller_email: Optional[str] = None
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    civic: str = Field(..., min_length=1)
    street: str = Field(..., min_length=1)
    apartment: Optional[str] = None
    city: str = Field(..., min_length=1)
    access: Literal["yes", "tenant_required", "common_area", "unknown"]
    access_details: Optional[str] = None
    has_animals: bool = False
    animal_details: Optional[str] = None
    problem: str = Field(..., min_length=1)
    attention: Optional[str] = None
    attachment_url: Optional[str] = None
    building_id_override: Optional[int] = None
    unit_id_override: Optional[int] = None


_ACCESS_LABELS: dict[str, str] = {
    "yes":             "Accès autorisé (traitement prioritaire)",
    "tenant_required": "Présence du locataire exigée (délai prolongé, traitement non prioritaire)",
    "common_area":     "N/A Non applicable (exemple espace commun)",
    "unknown":         "Accès non précisé",
}


def access_label(access: str) -> str:
    return _ACCESS_LABELS.get(access, access)


class ManualCreateResponse(BaseModel):
    request_id: int
    building_id: Optional[int] = None
    unit_id: Optional[int] = None
    match_status: str
