"""Create / edit the portfolio hierarchy and building reference info.

Every edit: lock the row, check the editor's sector scope, refuse with
STALE_DATA when the stored value differs from what the editor saw, write, and
record each changed column in data_provenance.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.core.exceptions import ConflictError, NotFoundError, StaleDataError, ValidationFailed
from backend.core.provenance import write_provenance
from backend.core.security import CurrentUser
from backend.modules.intake.service import allowed_sector_ids

from . import edit_repository as repo
from .schemas import (
    BuildingCreateBody,
    BuildingPatch,
    CreatedOut,
    DocumentCreateBody,
    FicheEntryBody,
    PaintSpecFields,
    PaintSpecPatch,
    ProjectCreateBody,
    ProjectPatch,
    UnitCreateBody,
    UnitPatch,
)
from .service import _in_scope

_STALE = "Modifié entre-temps par quelqu'un d'autre — rechargez la page."
_REQUIRED = {"building": {"adresse"}, "unit": {"numero_appartement"}, "project": {"nom_unique_projet"}}


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

def _insert_building(conn, user: CurrentUser, values: dict, *, project_id: int, sector_id: int) -> int:
    values = {"actif_inactif": "Actif", **values}
    building_id = repo.insert_row(conn, "building", values,
                                  {"project_id": project_id, "sector_id": sector_id})
    _record_create(conn, user, "building", building_id,
                   {**values, "project_id": project_id, "sector_id": sector_id})
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
    _apply(conn, user, "building", building_id, row, body)


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
