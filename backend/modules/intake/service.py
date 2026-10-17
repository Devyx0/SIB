"""Business logic for the intake module — manual create + match-only."""
from __future__ import annotations

import json

from backend.core.security import CurrentUser
from .address import match_address, MatchResult
from .schemas import (
    CandidateBuilding, ManualCreateBody, ManualCreateResponse, MatchRequest, MatchResponse,
    access_label, animals_db_value,
)

_RAW_TITLE_MAX = 80


def _build_problems(body: ManualCreateBody) -> str:
    parts = [f"Problème : {body.problem}"]
    if body.access_details:
        parts.append(f"Précisions (accès) : {body.access_details}")
    if body.animals == "oui" and body.animal_details:
        parts.append(f"Animaux : {body.animal_details}")
    if body.attention:
        parts.append(f"⚠ ATTENTION : {body.attention}")
    if body.phone_2:
        parts.append(f"Téléphone 2 : {body.phone_2}")
    return "\n".join(parts)


def _raw_title(problem: str) -> str:
    t = problem.strip()
    return t[:_RAW_TITLE_MAX] if len(t) <= _RAW_TITLE_MAX else t[:_RAW_TITLE_MAX - 1] + "…"


def match_only(conn, body: MatchRequest) -> MatchResponse:
    """Match an address without writing anything to the DB."""
    result: MatchResult = match_address(conn, body.civic, body.street, body.apartment)

    building_adresse = None
    if result.building_id is not None:
        row = conn.execute(
            "SELECT adresse FROM building WHERE building_id = %(id)s",
            {"id": result.building_id},
        ).fetchone()
        if row:
            building_adresse = row["adresse"]

    candidate_buildings: list[CandidateBuilding] = []
    if result.candidate_building_ids:
        rows = conn.execute(
            "SELECT building_id, adresse FROM building WHERE building_id = ANY(%(ids)s)",
            {"ids": list(result.candidate_building_ids)},
        ).fetchall()
        candidate_buildings = [CandidateBuilding(building_id=r["building_id"], adresse=r["adresse"]) for r in rows]

    return MatchResponse(
        match_status=result.match_status,
        building_id=result.building_id,
        unit_id=result.unit_id,
        building_adresse=building_adresse,
        candidate_building_ids=list(result.candidate_building_ids),
        candidate_buildings=candidate_buildings,
    )


def create_manual(conn, body: ManualCreateBody, user: CurrentUser) -> ManualCreateResponse:
    if body.building_id_override is not None:
        building_id = body.building_id_override
        unit_id = body.unit_id_override
        match_status = "exact" if unit_id is not None else "building_only"
    else:
        result = match_address(conn, body.civic, body.street, body.apartment)
        building_id = result.building_id
        unit_id = result.unit_id
        match_status = result.match_status

    problems_text = _build_problems(body)
    entry_perm = access_label(body.access)
    animals_val = animals_db_value(body.animals)

    raw_caller_body = json.dumps({
        "entry_permission": entry_perm,
        "animals": animals_val,
        "problems": problems_text,
    })

    row = conn.execute(
        """
        INSERT INTO maintenance_request (
            status, body_format, external_source,
            building_id, unit_id,
            caller_name, caller_phone, caller_email,
            entry_permission, animals,
            problems, raw_title,
            attachment_url,
            created_by_employee_id,
            raw_caller_body,
            source_calendar, start_date, submission_date
        ) VALUES (
            'intake_received', 'manual', 'manual',
            %(building_id)s, %(unit_id)s,
            %(caller_name)s, %(phone_1)s, %(caller_email)s,
            %(entry_permission)s, %(animals)s,
            %(problems)s, %(raw_title)s,
            %(attachment_url)s,
            %(employee_id)s,
            %(raw_caller_body)s,
            NULL, NULL, NOW()
        )
        RETURNING request_id, building_id, unit_id
        """,
        {
            "building_id":      building_id,
            "unit_id":          unit_id,
            "caller_name":      body.caller_name,
            "phone_1":          body.phone_1,
            "caller_email":     body.caller_email,
            "entry_permission": entry_perm,
            "animals":          animals_val,
            "problems":         problems_text,
            "raw_title":        _raw_title(body.problem),
            "attachment_url":   body.attachment_url,
            "employee_id":      user.employee_id,
            "raw_caller_body":  raw_caller_body,
        },
    ).fetchone()

    request_id = row["request_id"]

    conn.execute(
        """
        INSERT INTO data_provenance
            (target_table, target_pk, target_column, source_type,
             employee_id, ingested_at)
        VALUES ('maintenance_request', %(pk)s, 'manual_create', 'app',
                %(emp)s, NOW())
        """,
        {"pk": str(request_id), "emp": user.employee_id},
    )

    return ManualCreateResponse(
        request_id=request_id,
        building_id=row["building_id"],
        unit_id=row["unit_id"],
        match_status=match_status,
    )
