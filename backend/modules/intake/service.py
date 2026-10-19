"""Business logic for the intake module — manual create + match-only."""
from __future__ import annotations

import json

from backend.core.exceptions import NotFoundError, PermissionDenied, ValidationFailed
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
    if body.phone_2:
        parts.append(f"Téléphone 2 : {body.phone_2}")
    if body.secondary_name or body.secondary_email:
        contact = body.secondary_name or "—"
        if body.secondary_email:
            contact = f"{contact} <{body.secondary_email}>"
        parts.append(f"Personne à contacter : {contact}")
    return "\n".join(parts)


def _raw_title(problem: str) -> str:
    t = problem.strip()
    return t[:_RAW_TITLE_MAX] if len(t) <= _RAW_TITLE_MAX else t[:_RAW_TITLE_MAX - 1] + "…"


def allowed_sector_ids(conn, user: CurrentUser) -> frozenset[int] | None:
    """Sectors a coordinator may create in / look up. None = unrestricted.

    Directors (and non-coordinator roles) are unrestricted. Coordinators are
    limited to employee.sector_id plus sectors of assigned buildings.
    If a coordinator has neither, return None (unrestricted) — locking them
    out of every sector would make the lookup dropdown empty in practice.
    """
    if "director" in user.roles or "coordinator" not in user.roles:
        return None
    ids: set[int] = set()
    row = conn.execute(
        "SELECT sector_id FROM employee WHERE employee_id = %(id)s",
        {"id": user.employee_id},
    ).fetchone()
    if row and row["sector_id"] is not None:
        ids.add(int(row["sector_id"]))
    for r in conn.execute(
        """
        SELECT DISTINCT b.sector_id
        FROM employee_building_assignment eba
        JOIN building b ON b.building_id = eba.building_id
        WHERE eba.employee_id = %(id)s AND b.sector_id IS NOT NULL
        """,
        {"id": user.employee_id},
    ).fetchall():
        ids.add(int(r["sector_id"]))
    return frozenset(ids) if ids else None


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
    if body.access == "yes_instructions" and not (body.access_details or "").strip():
        raise ValidationFailed("Précisions d'accès requises")

    bldg = conn.execute(
        "SELECT building_id, sector_id FROM building WHERE building_id = %(id)s",
        {"id": body.building_id},
    ).fetchone()
    if bldg is None:
        raise NotFoundError("Bâtiment introuvable")
    sector_id = bldg["sector_id"]
    if sector_id is None:
        raise ValidationFailed("Bâtiment sans secteur")

    allowed = allowed_sector_ids(conn, user)
    if allowed is not None and int(sector_id) not in allowed:
        raise PermissionDenied("Bâtiment hors de votre secteur")

    unit_id = body.unit_id
    if unit_id is not None:
        unit = conn.execute(
            "SELECT unit_id FROM unit WHERE unit_id = %(uid)s AND building_id = %(bid)s",
            {"uid": unit_id, "bid": body.building_id},
        ).fetchone()
        if unit is None:
            raise ValidationFailed("Unité introuvable pour ce bâtiment")

    building_id = body.building_id
    match_status = "exact" if unit_id is not None else "building_only"

    # Cardinal rule 35: Lévis / rive-sud → Majordome queue; else Main.
    from backend.triage.calendar_route import source_calendar_for_sector
    sector_row = conn.execute(
        "SELECT territoire, color_code FROM sector WHERE sector_id = %(id)s",
        {"id": sector_id},
    ).fetchone()
    source_cal = source_calendar_for_sector(
        territoire=sector_row["territoire"] if sector_row else None,
        color_code=sector_row["color_code"] if sector_row else None,
    )

    problems_text = _build_problems(body)
    entry_perm = access_label(body.access)
    animals_val = animals_db_value(body.animals)
    category = (body.category or "").strip() or None
    element = (body.element or "").strip() or None
    symptome = (body.symptome or "").strip() or None
    composante = (body.composante or "").strip() or None
    emplacement = (body.emplacement or "").strip() or None

    raw_caller_body = json.dumps({
        "entry_permission": entry_perm,
        "animals": animals_val,
        "problems": problems_text,
        "attention": body.attention or None,
        "category": category,
        "element": element,
        "symptome": symptome,
        "composante": composante,
        "emplacement": emplacement,
        "intake_urgent": body.intake_urgent,
        "secondary_name": body.secondary_name or None,
        "secondary_email": body.secondary_email or None,
        "phone_2": body.phone_2 or None,
    })

    from backend.core.utils import today_local

    row = conn.execute(
        """
        INSERT INTO maintenance_request (
            status, body_format, external_source,
            building_id, unit_id, sector_id,
            caller_name, caller_phone, caller_email,
            entry_permission, animals,
            problems, raw_title, category_raw,
            element, symptome, composante, emplacement,
            intake_urgent,
            attachment_url,
            created_by_employee_id,
            raw_caller_body,
            source_calendar, start_date, submission_date
        ) VALUES (
            'intake_received', 'manual', 'manual',
            %(building_id)s, %(unit_id)s, %(sector_id)s,
            %(caller_name)s, %(phone_1)s, %(caller_email)s,
            %(entry_permission)s, %(animals)s,
            %(problems)s, %(raw_title)s, %(category_raw)s,
            %(element)s, %(symptome)s, %(composante)s, %(emplacement)s,
            %(intake_urgent)s,
            %(attachment_url)s,
            %(employee_id)s,
            %(raw_caller_body)s,
            %(source_calendar)s, %(start_date)s, NOW()
        )
        RETURNING request_id, building_id, unit_id
        """,
        {
            "building_id":      building_id,
            "unit_id":          unit_id,
            "sector_id":        sector_id,
            "caller_name":      body.caller_name,
            "phone_1":          body.phone_1,
            "caller_email":     body.caller_email,
            "entry_permission": entry_perm,
            "animals":          animals_val,
            "problems":         problems_text,
            "raw_title":        _raw_title(body.problem),
            "category_raw":     category,
            "element":          element,
            "symptome":         symptome,
            "composante":       composante,
            "emplacement":      emplacement,
            "intake_urgent":    body.intake_urgent,
            "attachment_url":   body.attachment_url,
            "employee_id":      user.employee_id,
            "raw_caller_body":  raw_caller_body,
            "source_calendar":  source_cal,
            "start_date":       today_local(),
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
