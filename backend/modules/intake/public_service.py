"""Public tenant intake — phone/email lookup + submit (no auth)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from backend.core.config import settings
from backend.core.exceptions import NotFoundError, ValidationFailed
from backend.core.rate_limit import public_intake_limiter
from backend.core.turnstile import verify_turnstile
from backend.core.utils import today_local

from . import service as intake_service
from .schemas import (
    ManualCreateBody,
    PublicLookupBody,
    PublicLookupResponse,
    PublicSubmitBody,
    PublicSubmitResponse,
    access_label,
    animals_db_value,
)

_SESSION_TTL_MIN = 45
_SESSION_TYP = "public_intake"
_PHONE_DIGITS = re.compile(r"\D+")


def _client_key(remote_ip: str | None, contact: str) -> str:
    return f"{remote_ip or 'unknown'}:{contact}"


def _digits(phone: str) -> str:
    return _PHONE_DIGITS.sub("", phone or "")


def _format_address(adresse: str | None, apt: str | None) -> str:
    """Full building address + apt — shown so tenant can confirm before submit."""
    label = (adresse or "").strip() or "Adresse enregistrée"
    if apt:
        label = f"{label}, app. {apt}"
    return label


def _mint_session(*, tenant_id: int, unit_id: int, building_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "typ": _SESSION_TYP,
            "tid": tenant_id,
            "uid": unit_id,
            "bid": building_id,
            "iat": now,
            "exp": now + timedelta(minutes=_SESSION_TTL_MIN),
        },
        settings.session_signing_key,
        algorithm="HS256",
    )


def _read_session(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.session_signing_key,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "typ", "tid", "uid", "bid"]},
        )
    except jwt.PyJWTError as exc:
        raise ValidationFailed("Session expirée — recommencez l'identification") from exc
    if payload.get("typ") != _SESSION_TYP:
        raise ValidationFailed("Session invalide")
    return payload


# Roof / antenna revenue leases (Bell Mobility, Telus, …) must not bind the
# public tenant form — they share building emails but are not housing units.
_ANTENNA_NAME_APT = r"antenne|antenna"


def _find_active_tenant_units(conn, *, phone: str | None, email: str | None) -> list[dict]:
    today = today_local()
    phone_d = _digits(phone) if phone else ""
    email_n = (email or "").strip().casefold() or None

    clauses: list[str] = []
    params: dict[str, Any] = {"today": today}
    if phone_d:
        # Match last 10 digits when longer (NANP), else full digit string.
        needle = phone_d[-10:] if len(phone_d) >= 10 else phone_d
        params["phone_digits"] = needle
        clauses.append(
            """(
              strpos(
                regexp_replace(COALESCE(t.telephone, ''), '\\D', '', 'g'),
                %(phone_digits)s
              ) > 0
              OR strpos(
                regexp_replace(COALESCE(t.telephone_international, ''), '\\D', '', 'g'),
                %(phone_digits)s
              ) > 0
            )"""
        )
    if email_n:
        params["email"] = email_n
        clauses.append("lower(trim(t.courriel)) = %(email)s")

    if not clauses:
        return []

    sql = f"""
        SELECT
            t.tenant_id,
            t.nom_complet,
            COALESCE(t.telephone, t.telephone_international) AS phone,
            t.courriel AS email,
            u.unit_id,
            u.building_id,
            u.numero_appartement,
            u.rue,
            b.adresse AS building_adresse,
            b.sector_id,
            l.droit_animaux
        FROM tenant t
        JOIN tenancy_record tr ON tr.tenant_id = t.tenant_id
        JOIN lease l ON l.lease_id = tr.lease_id
        JOIN unit u ON u.unit_id = l.unit_id
        JOIN building b ON b.building_id = u.building_id
        WHERE ({' OR '.join(clauses)})
          AND (l.debut_bail IS NULL OR l.debut_bail <= %(today)s)
          AND (l.fin_bail IS NULL OR l.fin_bail >= %(today)s)
          AND t.nom_complet !~* '{_ANTENNA_NAME_APT}'
          AND COALESCE(u.numero_appartement, '') !~* '{_ANTENNA_NAME_APT}'
          AND lower(trim(COALESCE(u.numero_appartement, ''))) <> 'toit'
        ORDER BY t.tenant_id, u.unit_id
    """
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def lookup_tenant(
    conn,
    body: PublicLookupBody,
    *,
    remote_ip: str | None,
) -> PublicLookupResponse:
    phone = (body.phone or "").strip() or None
    email = (body.email or "").strip() or None
    if bool(phone) == bool(email):
        raise ValidationFailed("Indiquez un téléphone ou un courriel (un seul)")

    contact = phone or email or ""
    public_intake_limiter.check(
        f"lookup:ip:{remote_ip or 'unknown'}", limit=20, window_sec=900,
    )
    public_intake_limiter.check(
        f"lookup:contact:{_client_key(remote_ip, contact.casefold())}",
        limit=10, window_sec=900,
    )

    verify_turnstile(
        body.turnstile_token, expected_action="tenant_lookup", remote_ip=remote_ip,
    )

    rows = _find_active_tenant_units(conn, phone=phone, email=email)
    if not rows:
        raise NotFoundError("Aucun logement trouvé pour ces coordonnées")
    # Distinct (tenant_id, unit_id) — >1 means ambiguous placement.
    keys = {(r["tenant_id"], r["unit_id"]) for r in rows}
    if len(keys) > 1:
        raise ValidationFailed(
            "Plusieurs logements associés — contactez la maintenance"
        )

    row = rows[0]
    token = _mint_session(
        tenant_id=int(row["tenant_id"]),
        unit_id=int(row["unit_id"]),
        building_id=int(row["building_id"]),
    )
    return PublicLookupResponse(
        session_token=token,
        caller_name=(row["nom_complet"] or "").strip() or "Locataire",
        phone=row.get("phone"),
        email=row.get("email"),
        address_label=_format_address(row.get("building_adresse"), row.get("numero_appartement")),
        unit_label=row.get("numero_appartement"),
        pets_allowed=row.get("droit_animaux") is True,
    )


def create_public(
    conn,
    body: PublicSubmitBody,
    *,
    remote_ip: str | None,
) -> PublicSubmitResponse:
    public_intake_limiter.check(
        f"submit:ip:{remote_ip or 'unknown'}", limit=5, window_sec=3600,
    )
    verify_turnstile(
        body.turnstile_token, expected_action="tenant_submit", remote_ip=remote_ip,
    )

    sess = _read_session(body.session_token)
    tenant_id = int(sess["tid"])
    unit_id = int(sess["uid"])
    building_id = int(sess["bid"])

    public_intake_limiter.check(
        f"submit:tenant:{tenant_id}", limit=5, window_sec=86400,
    )

    tenant = conn.execute(
        """
        SELECT tenant_id, nom_complet,
               COALESCE(telephone, telephone_international) AS phone,
               courriel AS email
        FROM tenant WHERE tenant_id = %(id)s
        """,
        {"id": tenant_id},
    ).fetchone()
    if tenant is None:
        raise NotFoundError("Locataire introuvable")

    unit = conn.execute(
        """
        SELECT u.unit_id, u.building_id, b.sector_id
        FROM unit u
        JOIN building b ON b.building_id = u.building_id
        WHERE u.unit_id = %(uid)s AND u.building_id = %(bid)s
        """,
        {"uid": unit_id, "bid": building_id},
    ).fetchone()
    if unit is None or unit["sector_id"] is None:
        raise ValidationFailed("Logement invalide")

    if body.access == "yes_instructions" and not (body.access_details or "").strip():
        raise ValidationFailed("Précisions d'accès requises")

    # Reuse photo decode via a thin ManualCreateBody shell.
    shell = ManualCreateBody(
        caller_name=(tenant["nom_complet"] or "Locataire").strip() or "Locataire",
        caller_email=tenant["email"],
        phone_1=(tenant["phone"] or "inconnu").strip() or "inconnu",
        building_id=building_id,
        unit_id=unit_id,
        access=body.access,
        access_details=body.access_details,
        animals=body.animals,
        animal_details=body.animal_details,
        problem=body.problem,
        category=body.category,
        element=body.element,
        symptome=body.symptome,
        composante=body.composante,
        emplacement=body.emplacement,
        secondary_name=body.secondary_name,
        secondary_email=body.secondary_email,
        attention=body.attention,
        photos=body.photos,
        ui_lang=body.ui_lang,
    )
    photos = intake_service._decode_photos(shell)

    from backend.triage.calendar_route import source_calendar_for_sector

    sector_id = int(unit["sector_id"])
    sector_row = conn.execute(
        "SELECT territoire, color_code FROM sector WHERE sector_id = %(id)s",
        {"id": sector_id},
    ).fetchone()
    source_cal = source_calendar_for_sector(
        territoire=sector_row["territoire"] if sector_row else None,
        color_code=sector_row["color_code"] if sector_row else None,
    )

    problems_text = intake_service._build_problems(shell)
    entry_perm = access_label(body.access)
    animals_val = animals_db_value(body.animals)
    element = body.element.strip()
    symptome = body.symptome.strip()
    composante = body.composante.strip()
    emplacement = body.emplacement.strip()
    if not all((element, symptome, composante, emplacement)):
        raise ValidationFailed("Taxonomie incomplète (élément, symptôme, composante, emplacement)")

    category = (body.category or "").strip() or None
    from .asnu import next_asnu

    asnu = next_asnu(conn)
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
        "tenant_id": tenant_id,
        "asnu": asnu,
        "source": "tenant_web",
    })

    row = conn.execute(
        """
        INSERT INTO maintenance_request (
            status, body_format, external_source,
            building_id, unit_id, sector_id,
            caller_name, caller_phone, caller_email, caller_tenant_id,
            entry_permission, animals,
            problems, raw_title, category_raw, asnu,
            element, symptome, composante, emplacement,
            created_by_employee_id,
            raw_caller_body,
            source_calendar, start_date, submission_date
        ) VALUES (
            'intake_received', 'manual', 'tenant_web',
            %(building_id)s, %(unit_id)s, %(sector_id)s,
            %(caller_name)s, %(phone_1)s, %(caller_email)s, %(tenant_id)s,
            %(entry_permission)s, %(animals)s,
            %(problems)s, %(raw_title)s, %(category_raw)s, %(asnu)s,
            %(element)s, %(symptome)s, %(composante)s, %(emplacement)s,
            NULL,
            %(raw_caller_body)s,
            %(source_calendar)s, %(start_date)s, NOW()
        )
        RETURNING request_id
        """,
        {
            "building_id": building_id,
            "unit_id": unit_id,
            "sector_id": sector_id,
            "caller_name": shell.caller_name,
            "phone_1": shell.phone_1,
            "caller_email": shell.caller_email,
            "tenant_id": tenant_id,
            "entry_permission": entry_perm,
            "animals": animals_val,
            "problems": problems_text,
            "raw_title": intake_service._raw_title(body.problem),
            "category_raw": category,
            "asnu": asnu,
            "element": element,
            "symptome": symptome,
            "composante": composante,
            "emplacement": emplacement,
            "raw_caller_body": raw_caller_body,
            "source_calendar": source_cal,
            "start_date": today_local(),
        },
    ).fetchone()

    request_id = row["request_id"]
    conn.execute(
        """
        INSERT INTO data_provenance
            (target_table, target_pk, target_column, source_type,
             employee_id, ingested_at)
        VALUES ('maintenance_request', %(pk)s, 'manual_create', 'tenant_web',
                NULL, NOW())
        """,
        {"pk": str(request_id)},
    )
    if photos:
        intake_service._store_intake_photos(conn, request_id, None, photos)

    return PublicSubmitResponse(request_id=request_id, asnu=asnu)
