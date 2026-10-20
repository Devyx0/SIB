"""Schemas for the intake module (manual create + address match)."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


AnimalsChoice = Literal["oui", "non", "na"]

_ANIMALS_LABELS: dict[str, str | None] = {
    "oui": "Oui",
    "non": "Non",
    "na":  "N/A espace commun",
}

AccessChoice = Literal["yes", "yes_instructions", "tenant_required", "common_area"]


class IntakePhoto(BaseModel):
    """A photo sent with the new call, base64-encoded (the web form shrinks
    it first). Same formats and size cap as closeout photos."""
    mime: Literal["image/jpeg", "image/png", "image/webp"]
    data_base64: str = Field(..., min_length=1)


MAX_INTAKE_PHOTOS = 5


class ManualCreateBody(BaseModel):
    caller_name: str = Field(..., min_length=1)
    caller_email: Optional[str] = None
    phone_1: str = Field(..., min_length=1)
    phone_2: Optional[str] = None
    building_id: int
    # Success criteria: intake requires a real DB unit (no free-text / building-only).
    unit_id: int
    access: AccessChoice
    access_details: Optional[str] = None
    # Only set when lease allows pets (oui/non). Omitted when pets not allowed.
    animals: Optional[AnimalsChoice] = None
    animal_details: Optional[str] = None
    problem: str = Field(..., min_length=1)
    category: Optional[str] = None
    # 4-axis taxonomy — mandatory at intake (success criteria Main1).
    element: str = Field(..., min_length=1)
    symptome: str = Field(..., min_length=1)
    composante: str = Field(..., min_length=1)
    emplacement: str = Field(..., min_length=1)
    intake_urgent: bool = False
    secondary_name: Optional[str] = None
    secondary_email: Optional[str] = None
    attention: Optional[str] = None
    attachment_url: Optional[str] = None
    # Recommended, optional: photos of the problem, saved with the call.
    photos: list[IntakePhoto] = Field(default_factory=list, max_length=MAX_INTAKE_PHOTOS)
    # UI language for auto-triage text fields (title, problems, notes).
    ui_lang: Literal["fr", "en"] = "fr"


_ACCESS_LABELS: dict[str, str] = {
    "yes":              "Accès autorisé (traitement prioritaire)",
    "yes_instructions": "Accès autorisé : avec instructions précises (traitement prioritaire)",
    "tenant_required":  "Présence du locataire exigée (délai prolongé, traitement non prioritaire)",
    "common_area":      "N/A Non applicable (exemple espace commun)",
}


def access_label(access: str) -> str:
    return _ACCESS_LABELS.get(access, access)


def animals_db_value(animals: str | None) -> str | None:
    """Map the animals choice to the DB value (Oui / Non / N/A / NULL)."""
    if animals is None:
        return None
    return _ANIMALS_LABELS.get(animals)


class ManualCreateResponse(BaseModel):
    request_id: int
    building_id: Optional[int] = None
    unit_id: Optional[int] = None
    match_status: str


# ── Match-only endpoint ───────────────────────────────────────────────────────

class MatchRequest(BaseModel):
    civic: str = Field(..., min_length=1)
    street: str = Field(..., min_length=1)
    apartment: Optional[str] = None


class CandidateBuilding(BaseModel):
    building_id: int
    adresse: Optional[str] = None


class MatchResponse(BaseModel):
    match_status: str                     # exact | building_only | ambiguous | no_match | garbled
    building_id: Optional[int] = None
    unit_id: Optional[int] = None
    building_adresse: Optional[str] = None  # human-readable label for exact / building_only
    candidate_building_ids: list[int] = Field(default_factory=list)
    candidate_buildings: list[CandidateBuilding] = Field(default_factory=list)
