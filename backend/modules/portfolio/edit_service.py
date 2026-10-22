"""Create / edit the portfolio hierarchy and building reference info.

Every edit: lock the row, check the editor's sector scope, refuse with
STALE_DATA when the stored value differs from what the editor saw, write, and
record each changed column in data_provenance.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from pydantic import BaseModel

from backend.core.exceptions import (
    AlreadyOnLeaseError,
    ConflictError,
    LeaseRequiresTenantError,
    NoCurrentLeaseError,
    NotFoundError,
    StaleDataError,
    TenancyNotActiveError,
    UnitAtCapacityError,
    ValidationFailed,
)
from backend.core.provenance import write_provenance
from backend.core.security import CurrentUser
from backend.core.utils import today_local
from backend.modules.intake.service import allowed_sector_ids

from . import edit_repository as repo
from .geocode import geocode_address
from .schemas import (
    AddOccupantBody,
    BuildingCreateBody,
    BuildingPatch,
    CreatedOut,
    DocumentCreateBody,
    EndLeaseBody,
    EndOccupantBody,
    FicheEntryBody,
    PaintSpecFields,
    PaintSpecPatch,
    ProjectCreateBody,
    ProjectPatch,
    StartLeaseBody,
    TakeoverBody,
    TenantFields,
    TenantPatch,
    TenancyPatch,
    UnitCreateBody,
    UnitPatch,
)
from .service import _in_scope

_STALE = "Modifié entre-temps par quelqu'un d'autre — rechargez la page."
_REQUIRED = {
    "building": {"adresse"},
    "unit": {"numero_appartement"},
    "project": {"nom_unique_projet"},
    "tenant": {"nom_complet"},
}


def _text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _changes(fields: BaseModel) -> dict:
    return fields.model_dump(include=fields.model_fields_set)


def _apply(conn, user: CurrentUser, table: str, pk: int, row: dict, patch) -> None:
    """Stale check, write and provenance for one PATCH body."""
    changes = _changes(patch.changes)
    for col in _REQUIRED.get(table, ()):
        if col in changes and changes[col] is None:
            raise ValidationFailed(f"{col} est obligatoire")
    seen = patch.current.model_dump()
    changed = {k: v for k, v in changes.items() if _text(row[k]) != _text(v)}
    for col in changed:
        if _text(row[col]) != _text(seen.get(col)):
            raise StaleDataError(_STALE, details={"field": col})
    repo.update_columns(conn, table, pk, changed)
    for col, value in changed.items():
        write_provenance(conn, target_table=table, target_pk=str(pk), target_column=col,
                         employee_id=user.employee_id, previous_value=_text(row[col]),
                         new_value=_text(value))


def _record_create(conn, user: CurrentUser, table: str, pk: int, values: dict) -> None:
    for col, value in values.items():
        if value is not None:
            write_provenance(conn, target_table=table, target_pk=str(pk), target_column=col,
                             employee_id=user.employee_id, previous_value=None, new_value=_text(value))


def _require_sector(conn, user: CurrentUser, sector_id: int) -> None:
    if not repo.sector_exists(conn, sector_id) or not _in_scope(allowed_sector_ids(conn, user), sector_id):
        raise NotFoundError("Secteur introuvable ou hors de votre secteur")


def _building_in_scope(conn, user: CurrentUser, building_id: int) -> dict:
    row = repo.lock_building(conn, building_id)
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Bâtiment introuvable")
    return row


# ── Projects ──────────────────────────────────────────────────────────────────

def create_project(conn, body: ProjectCreateBody, user: CurrentUser) -> CreatedOut:
    first = body.first_building
    _require_sector(conn, user, first.sector_id)
    project_values = body.model_dump(include={"nom_unique_projet", "adresse_quickbooks", "accounting_project_number"})
    project_id = repo.insert_row(conn, "project", project_values)
    _record_create(conn, user, "project", project_id, project_values)
    building_id = _insert_building(conn, user, first.model_dump(exclude={"sector_id"}, exclude_none=True),
                                   project_id=project_id, sector_id=first.sector_id)
    return CreatedOut(project_id=project_id, building_id=building_id, sector_id=first.sector_id)


def patch_project(conn, project_id: int, body: ProjectPatch, user: CurrentUser) -> None:
    row = repo.lock_project(conn, project_id)
    allowed = allowed_sector_ids(conn, user)
    if row is None or (allowed is not None and not set(row["sector_ids"]) & allowed):
        raise NotFoundError("Projet introuvable")
    _apply(conn, user, "project", project_id, row, body)


# ── Buildings ─────────────────────────────────────────────────────────────────

_ADDRESS_COLS = frozenset({"adresse", "ville", "code_postal"})


def _geocode_building(conn, building_id: int, *, adresse, ville, code_postal) -> None:
    """Best-effort Nominatim lookup; never blocks the address write on failure."""
    result = geocode_address(adresse, ville, code_postal)
    repo.set_building_geocode(
        conn,
        building_id,
        latitude=result.latitude,
        longitude=result.longitude,
        status=result.status,
        query=result.query or None,
    )


def _insert_building(conn, user: CurrentUser, values: dict, *, project_id: int, sector_id: int) -> int:
    values = {"actif_inactif": "Actif", **values}
    building_id = repo.insert_row(conn, "building", values,
                                  {"project_id": project_id, "sector_id": sector_id})
    _record_create(conn, user, "building", building_id,
                   {**values, "project_id": project_id, "sector_id": sector_id})
    _geocode_building(
        conn, building_id,
        adresse=values.get("adresse"),
        ville=values.get("ville"),
        code_postal=values.get("code_postal"),
    )
    return building_id


def create_building(conn, body: BuildingCreateBody, user: CurrentUser) -> CreatedOut:
    _require_sector(conn, user, body.sector_id)
    if not repo.project_exists(conn, body.project_id):
        raise NotFoundError("Projet introuvable")
    values = body.model_dump(exclude={"sector_id", "project_id"}, exclude_none=True)
    building_id = _insert_building(conn, user, values, project_id=body.project_id, sector_id=body.sector_id)
    return CreatedOut(project_id=body.project_id, building_id=building_id, sector_id=body.sector_id)


def patch_building(conn, building_id: int, body: BuildingPatch, user: CurrentUser) -> None:
    row = _building_in_scope(conn, user, building_id)
    changes = _changes(body.changes)
    address_touched = bool(_ADDRESS_COLS & changes.keys())
    _apply(conn, user, "building", building_id, row, body)
    if address_touched:
        # Re-read effective address after the patch (changed fields win).
        adresse = changes["adresse"] if "adresse" in changes else row.get("adresse")
        ville = changes["ville"] if "ville" in changes else row.get("ville")
        code_postal = changes["code_postal"] if "code_postal" in changes else row.get("code_postal")
        # Only re-geocode when an address field actually changed value.
        if any(_text(row.get(c)) != _text(changes[c]) for c in _ADDRESS_COLS if c in changes):
            _geocode_building(conn, building_id, adresse=adresse, ville=ville, code_postal=code_postal)


# ── Units ─────────────────────────────────────────────────────────────────────

def _check_unique_number(conn, value: str | None, unit_id: int | None = None) -> None:
    if value and repo.unique_unit_number_taken(conn, value, unit_id):
        raise ConflictError(f"Le numéro unique « {value} » est déjà utilisé", details={"field": "unique_unit_number"})


def create_unit(conn, body: UnitCreateBody, user: CurrentUser) -> CreatedOut:
    _building_in_scope(conn, user, body.building_id)
    _check_unique_number(conn, body.unique_unit_number)
    values = body.model_dump(exclude={"building_id"}, exclude_none=True)
    unit_id = repo.insert_row(conn, "unit", values, {"building_id": body.building_id})
    _record_create(conn, user, "unit", unit_id, {**values, "building_id": body.building_id})
    return CreatedOut(unit_id=unit_id, building_id=body.building_id)


def patch_unit(conn, unit_id: int, body: UnitPatch, user: CurrentUser) -> None:
    row = repo.lock_unit(conn, unit_id)
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Unité introuvable")
    if "unique_unit_number" in body.changes.model_fields_set:
        _check_unique_number(conn, body.changes.unique_unit_number, unit_id)
    _apply(conn, user, "unit", unit_id, row, body)


# ── Fiche technique ───────────────────────────────────────────────────────────

def set_fiche_entry(conn, building_id: int, body: FicheEntryBody, user: CurrentUser) -> None:
    row = _building_in_scope(conn, user, building_id)
    fiche = row["raw_fiche_technique"] if isinstance(row["raw_fiche_technique"], dict) else {}
    stored = _text(fiche.get(body.label))
    if stored != body.current_value:
        raise StaleDataError(_STALE, details={"field": body.label})
    if stored == body.value:
        return
    repo.set_fiche_entry(conn, building_id, body.label, body.value)
    write_provenance(conn, target_table="building", target_pk=str(building_id),
                     target_column=f"raw_fiche_technique.{body.label}", employee_id=user.employee_id,
                     previous_value=stored, new_value=body.value)


# ── Paint specs ───────────────────────────────────────────────────────────────

def create_paint_spec(conn, building_id: int, body: PaintSpecFields, user: CurrentUser) -> CreatedOut:
    _building_in_scope(conn, user, building_id)
    values = body.model_dump(exclude_none=True)
    if not values:
        raise ValidationFailed("Indiquez au moins une zone, une surface ou un produit")
    paint_spec_id = repo.insert_row(conn, "building_paint_spec", values, {"building_id": building_id})
    _record_create(conn, user, "building_paint_spec", paint_spec_id, {**values, "building_id": building_id})
    return CreatedOut(paint_spec_id=paint_spec_id, building_id=building_id)


def _paint_spec_in_scope(conn, user: CurrentUser, paint_spec_id: int) -> dict:
    row = repo.lock_paint_spec(conn, paint_spec_id)
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Spécification de peinture introuvable")
    return row


def patch_paint_spec(conn, paint_spec_id: int, body: PaintSpecPatch, user: CurrentUser) -> None:
    row = _paint_spec_in_scope(conn, user, paint_spec_id)
    _apply(conn, user, "building_paint_spec", paint_spec_id, row, body)


def delete_paint_spec(conn, paint_spec_id: int, user: CurrentUser) -> None:
    row = _paint_spec_in_scope(conn, user, paint_spec_id)
    repo.delete_paint_spec(conn, paint_spec_id)
    summary = " / ".join(filter(None, (row["zone"], row["surface_label"], row["product_interior"],
                                       row["product_exterior"], row["manufacturer"])))
    write_provenance(conn, target_table="building_paint_spec", target_pk=str(paint_spec_id),
                     target_column="*deleted*", employee_id=user.employee_id,
                     previous_value=summary or None, new_value=None)


# ── Documents (links to files that still live in Drive) ───────────────────────

def create_document(conn, building_id: int, body: DocumentCreateBody, user: CurrentUser) -> CreatedOut:
    _building_in_scope(conn, user, building_id)
    document_id = repo.insert_document(conn, building_id, body.title, body.url, body.category)
    _record_create(conn, user, "building_document", document_id,
                   {"building_id": building_id, "title": body.title, "url": body.url, "category": body.category})
    return CreatedOut(document_id=document_id, building_id=building_id)


def delete_document(conn, document_id: int, user: CurrentUser) -> None:
    row = repo.get_document(conn, document_id)
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Document introuvable")
    repo.delete_document(conn, document_id)
    write_provenance(conn, target_table="building_document", target_pk=str(document_id),
                     target_column="*deleted*", employee_id=user.employee_id,
                     previous_value=row["url"], new_value=None)


# ── Tenants / tenancies / occupancy ───────────────────────────────────────────

def _unit_in_scope(conn, user: CurrentUser, unit_id: int) -> dict:
    row = repo.lock_unit(conn, unit_id)
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Unité introuvable")
    return row


def _tenancy_in_scope(conn, user: CurrentUser, tenancy_id: int) -> dict:
    row = repo.lock_tenancy(conn, tenancy_id)
    if row is None or not _in_scope(allowed_sector_ids(conn, user), row["sector_id"]):
        raise NotFoundError("Bail / locataire introuvable")
    return row


def _tenancy_is_active(row: dict, today) -> bool:
    # end_date is exclusive of "still active" (see _ACTIVE_TENANCY).
    if row["end_date"] is not None and row["end_date"] <= today:
        return False
    if row["start_date"] is not None and row["start_date"] > today:
        return False
    return True


# Unit capacity is the leading integer of grandeur ("3 1/2" → 3, "4½" → 4).
# Unparseable / missing grandeur → no hard cap (skip enforcement).
_GRANDEUR_CAP = re.compile(r"^\s*(\d+)")


def _max_occupants(grandeur: str | None) -> int | None:
    if not grandeur:
        return None
    normalized = grandeur.replace("½", " 1/2")
    m = _GRANDEUR_CAP.match(normalized)
    if not m:
        return None
    n = int(m.group(1))
    return n if n > 0 else None


def _ensure_under_capacity(
    unit: dict, *, active_count: int, adding: int = 0, removing: int = 0,
) -> None:
    cap = _max_occupants(unit.get("grandeur"))
    if cap is None:
        return
    resulting = active_count - removing + adding
    if resulting > cap:
        raise UnitAtCapacityError(
            f"Ce logement est limité à {cap} occupant(s) (grandeur {unit.get('grandeur')})",
            details={"capacity": cap, "active": active_count, "grandeur": unit.get("grandeur")},
        )


def _resolve_tenant(conn, user: CurrentUser, *, tenant_id: int | None, new_tenant: TenantFields | None) -> int:
    if tenant_id is not None:
        row = repo.lock_tenant(conn, tenant_id)
        if row is None:
            raise NotFoundError("Locataire introuvable")
        return tenant_id
    assert new_tenant is not None
    values = {k: v for k, v in new_tenant.model_dump().items() if v is not None}
    tid = repo.insert_tenant(conn, values)
    _record_create(conn, user, "tenant", tid, values)
    return tid


def patch_tenant(conn, tenant_id: int, body: TenantPatch, user: CurrentUser) -> None:
    row = repo.lock_tenant(conn, tenant_id)
    allowed = allowed_sector_ids(conn, user)
    if row is None or not repo.tenant_in_scope_sector(conn, tenant_id, allowed):
        raise NotFoundError("Locataire introuvable")
    _apply(conn, user, "tenant", tenant_id, row, body)


def patch_tenancy(conn, tenancy_id: int, body: TenancyPatch, user: CurrentUser) -> None:
    row = _tenancy_in_scope(conn, user, tenancy_id)
    today = today_local()
    if not _tenancy_is_active(row, today):
        raise TenancyNotActiveError("Seules les occupations actives peuvent être modifiées")
    # Lease must still be current for capacity edits.
    lease = repo.lock_current_lease(conn, row["unit_id"], today)
    if lease is None or lease["lease_id"] != row["lease_id"]:
        raise NoCurrentLeaseError("Aucun bail courant pour cette occupation")
    _apply(conn, user, "tenancy_record", tenancy_id, row, body)


def add_occupant(conn, unit_id: int, body: AddOccupantBody, user: CurrentUser) -> CreatedOut:
    unit = _unit_in_scope(conn, user, unit_id)
    today = today_local()
    lease = repo.lock_current_lease(conn, unit_id, today)
    if lease is None:
        raise NoCurrentLeaseError("Aucun bail courant sur ce logement")
    active = repo.count_active_tenancies(conn, lease["lease_id"], today)
    _ensure_under_capacity(unit, active_count=active, adding=1)
    tenant_id = _resolve_tenant(conn, user, tenant_id=body.tenant_id, new_tenant=body.new_tenant)
    if repo.tenant_active_on_lease(conn, lease["lease_id"], tenant_id, today):
        raise AlreadyOnLeaseError("Ce locataire est déjà sur ce bail")
    start = body.start_date or today
    tenancy_id = repo.insert_tenancy(
        conn,
        lease_id=lease["lease_id"],
        tenant_id=tenant_id,
        capacite=body.capacite,
        start_date=start,
        reason_for_change=body.reason_for_change,
    )
    _record_create(conn, user, "tenancy_record", tenancy_id, {
        "lease_id": lease["lease_id"],
        "tenant_id": tenant_id,
        "capacite": body.capacite,
        "start_date": start,
        "reason_for_change": body.reason_for_change,
    })
    return CreatedOut(tenant_id=tenant_id, tenancy_id=tenancy_id, lease_id=lease["lease_id"], unit_id=unit_id)


def takeover_occupant(conn, unit_id: int, body: TakeoverBody, user: CurrentUser) -> CreatedOut:
    unit = _unit_in_scope(conn, user, unit_id)
    today = today_local()
    lease = repo.lock_current_lease(conn, unit_id, today)
    if lease is None:
        raise NoCurrentLeaseError("Aucun bail courant sur ce logement")
    outgoing = _tenancy_in_scope(conn, user, body.outgoing_tenancy_id)
    if outgoing["unit_id"] != unit_id or outgoing["lease_id"] != lease["lease_id"]:
        raise NotFoundError("Occupation sortante introuvable sur ce logement")
    if not _tenancy_is_active(outgoing, today):
        raise TenancyNotActiveError("L'occupation sortante n'est plus active")
    # Net zero when outgoing ends on effective_date; still guard if capacity is tight
    # and effective_date leaves both briefly overlapping as "active" today.
    active = repo.count_active_tenancies(conn, lease["lease_id"], today)
    ends_today = body.effective_date <= today
    _ensure_under_capacity(
        unit,
        active_count=active,
        adding=1,
        removing=1 if ends_today else 0,
    )
    tenant_id = _resolve_tenant(conn, user, tenant_id=body.tenant_id, new_tenant=body.new_tenant)
    if tenant_id == outgoing["tenant_id"]:
        raise ValidationFailed("Le locataire entrant doit être différent du sortant")
    if repo.tenant_active_on_lease(conn, lease["lease_id"], tenant_id, today):
        raise AlreadyOnLeaseError("Ce locataire est déjà sur ce bail")

    # End outgoing (capacite unchanged); open incoming as took_over.
    if outgoing["end_date"] is None or outgoing["end_date"] != body.effective_date:
        repo.update_columns(conn, "tenancy_record", body.outgoing_tenancy_id, {
            "end_date": body.effective_date,
            **({"reason_for_change": body.reason_for_change} if body.reason_for_change else {}),
        })
        write_provenance(
            conn, target_table="tenancy_record", target_pk=str(body.outgoing_tenancy_id),
            target_column="end_date", employee_id=user.employee_id,
            previous_value=_text(outgoing["end_date"]), new_value=_text(body.effective_date),
        )
        if body.reason_for_change:
            write_provenance(
                conn, target_table="tenancy_record", target_pk=str(body.outgoing_tenancy_id),
                target_column="reason_for_change", employee_id=user.employee_id,
                previous_value=_text(outgoing["reason_for_change"]),
                new_value=_text(body.reason_for_change),
            )

    tenancy_id = repo.insert_tenancy(
        conn,
        lease_id=lease["lease_id"],
        tenant_id=tenant_id,
        capacite="took_over",
        start_date=body.effective_date,
        reason_for_change=body.reason_for_change,
    )
    _record_create(conn, user, "tenancy_record", tenancy_id, {
        "lease_id": lease["lease_id"],
        "tenant_id": tenant_id,
        "capacite": "took_over",
        "start_date": body.effective_date,
        "reason_for_change": body.reason_for_change,
    })
    return CreatedOut(tenant_id=tenant_id, tenancy_id=tenancy_id, lease_id=lease["lease_id"], unit_id=unit_id)


def end_occupant(conn, unit_id: int, tenancy_id: int, body: EndOccupantBody, user: CurrentUser) -> None:
    _unit_in_scope(conn, user, unit_id)
    today = today_local()
    row = _tenancy_in_scope(conn, user, tenancy_id)
    if row["unit_id"] != unit_id:
        raise NotFoundError("Occupation introuvable sur ce logement")
    if not _tenancy_is_active(row, today):
        raise TenancyNotActiveError("Cette occupation est déjà terminée")
    if _text(row["end_date"]) != _text(body.current_end_date):
        raise StaleDataError(_STALE, details={"field": "end_date"})
    end = body.end_date or today
    # Reject removing the last active occupant — end the lease instead.
    if repo.count_active_tenancies(conn, row["lease_id"], today) <= 1:
        raise LeaseRequiresTenantError(
            "Impossible de retirer le dernier occupant : terminez le bail à la place "
            "(End the lease instead of removing the last occupant).",
            details={"lease_id": row["lease_id"], "tenancy_id": tenancy_id},
        )
    changes = {"end_date": end}
    if body.reason_for_change is not None:
        changes["reason_for_change"] = body.reason_for_change
    repo.update_columns(conn, "tenancy_record", tenancy_id, changes)
    for col, value in changes.items():
        write_provenance(
            conn, target_table="tenancy_record", target_pk=str(tenancy_id),
            target_column=col, employee_id=user.employee_id,
            previous_value=_text(row[col]), new_value=_text(value),
        )


def end_lease(conn, unit_id: int, body: EndLeaseBody, user: CurrentUser) -> None:
    _unit_in_scope(conn, user, unit_id)
    today = today_local()
    lease = repo.lock_current_lease(conn, unit_id, today)
    if lease is None:
        raise NoCurrentLeaseError("Aucun bail courant sur ce logement")
    if _text(lease["fin_bail"]) != _text(body.current_fin_bail):
        raise StaleDataError(_STALE, details={"field": "fin_bail"})
    if body.current_statut is not None and _text(lease["statut"]) != _text(body.current_statut):
        raise StaleDataError(_STALE, details={"field": "statut"})
    # Current-lease rule is fin_bail >= today; clamp so the lease drops out immediately.
    fin = body.fin_bail if body.fin_bail < today else today - timedelta(days=1)
    changes: dict = {"fin_bail": fin}
    if body.statut is not None:
        changes["statut"] = body.statut
    repo.update_columns(conn, "lease", lease["lease_id"], changes)
    for col, value in changes.items():
        write_provenance(
            conn, target_table="lease", target_pk=str(lease["lease_id"]),
            target_column=col, employee_id=user.employee_id,
            previous_value=_text(lease[col]), new_value=_text(value),
        )
    if body.close_tenancies:
        closed = repo.close_open_tenancies(conn, lease["lease_id"], fin)
        for r in closed:
            write_provenance(
                conn, target_table="tenancy_record", target_pk=str(r["tenancy_id"]),
                target_column="end_date", employee_id=user.employee_id,
                previous_value=_text(r["end_date"]), new_value=_text(fin),
            )


def start_lease(conn, unit_id: int, body: StartLeaseBody, user: CurrentUser) -> CreatedOut:
    unit = _unit_in_scope(conn, user, unit_id)
    if not body.occupants:
        raise ValidationFailed(
            "Au moins un occupant est requis pour démarrer un bail "
            "(At least one occupant is required to start a lease).",
        )
    _ensure_under_capacity(unit, active_count=0, adding=len(body.occupants))
    today = today_local()
    current = repo.lock_current_lease(conn, unit_id, today)
    if current is not None:
        if not body.end_previous:
            raise ConflictError(
                "Un bail courant existe déjà — passez end_previous=true pour le clôturer",
                details={"lease_id": current["lease_id"]},
            )
        fin = body.previous_fin_bail if body.previous_fin_bail is not None else (
            body.debut_bail - timedelta(days=1)
        )
        repo.update_columns(conn, "lease", current["lease_id"], {"fin_bail": fin})
        write_provenance(
            conn, target_table="lease", target_pk=str(current["lease_id"]),
            target_column="fin_bail", employee_id=user.employee_id,
            previous_value=_text(current["fin_bail"]), new_value=_text(fin),
        )
        closed = repo.close_open_tenancies(conn, current["lease_id"], fin)
        for r in closed:
            write_provenance(
                conn, target_table="tenancy_record", target_pk=str(r["tenancy_id"]),
                target_column="end_date", employee_id=user.employee_id,
                previous_value=_text(r["end_date"]), new_value=_text(fin),
            )

    lease_id = repo.insert_lease(
        conn,
        unit_id=unit_id,
        debut_bail=body.debut_bail,
        fin_bail=body.fin_bail,
        statut=body.statut,
        langue_bail=body.langue_bail,
    )
    _record_create(conn, user, "lease", lease_id, {
        "unit_id": unit_id,
        "debut_bail": body.debut_bail,
        "fin_bail": body.fin_bail,
        "statut": body.statut,
        "langue_bail": body.langue_bail,
    })

    first_tenant_id = None
    first_tenancy_id = None
    for occ in body.occupants:
        tid = _resolve_tenant(conn, user, tenant_id=occ.tenant_id, new_tenant=occ.new_tenant)
        tenancy_id = repo.insert_tenancy(
            conn,
            lease_id=lease_id,
            tenant_id=tid,
            capacite=occ.capacite,
            start_date=body.debut_bail,
        )
        _record_create(conn, user, "tenancy_record", tenancy_id, {
            "lease_id": lease_id,
            "tenant_id": tid,
            "capacite": occ.capacite,
            "start_date": body.debut_bail,
        })
        if first_tenant_id is None:
            first_tenant_id, first_tenancy_id = tid, tenancy_id

    return CreatedOut(
        lease_id=lease_id,
        unit_id=unit_id,
        tenant_id=first_tenant_id,
        tenancy_id=first_tenancy_id,
    )
