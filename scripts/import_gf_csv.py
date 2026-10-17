"""Import a Gravity Forms CSV export into maintenance_request.

Guards:  DB_TARGET=local only. Refuses remote connections.
Idempotent: skips rows where external_source='gravity_forms' AND external_ref already exists.

Usage:
    python scripts/import_gf_csv.py --csv work/demande-de-services-2026-10-14.csv
    python scripts/import_gf_csv.py --csv work/... --dry-run   # stats only, no writes
    python scripts/import_gf_csv.py --cleanup                  # delete all gravity_forms rows

Column mapping (from the GF export):
    ID de l'entrée            → external_ref
    Date de l'entrée          → submission_date (Quebec EDT → UTC)
    Nom complet               → caller_name
    Courriel                  → caller_email
    Téléphone 1               → caller_phone
    Numéro civique + Rue + Appartement + Ville  → building_id / unit_id (address match)
    Accès au logement         → entry_permission (French label, as-is)
    Avez-vous des animaux?    → animals ('Oui' or NULL)
    Décrivez le problème…     → problems (bundled with other detail fields)
    Joindre une photo         → attachment_url (URL only, not downloaded)
    Créé par (ID utilisateur) → created_by_wp_user_id

Stripped (not imported):
    IP de l'utilisateur, Agent utilisateur, Submission Speed (ms),
    all payment columns (all empty), URL source (same on every row).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

# ── repo root on sys.path so we can import the address matcher ─────────────────
sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.modules.intake.address import match_address  # noqa: E402

# ── Guards ─────────────────────────────────────────────────────────────────────
DB_TARGET = os.environ.get("DB_TARGET", "local")
if DB_TARGET != "local":
    sys.exit("ERROR: DB_TARGET must be 'local' — refusing to write to remote")

LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
_TZ_QC = ZoneInfo("America/Toronto")

# ── Column name constants (Unicode apostrophes from the GF export) ──────────────
_COL_ID     = "ID de l’entrée"
_COL_DATE   = "Date de l’entrée"
_COL_NAME   = "Nom complet"
_COL_EMAIL  = "Courriel (Saisissez une adresse courriel)"
_COL_PHONE1 = "Téléphone 1"
_COL_PHONE2 = "Téléphone 2"
_COL_CIVIC  = "Numéro civique"
_COL_STREET = "Rue"
_COL_APT    = "Appartement"
_COL_CITY   = "Ville"
_COL_ACCESS = "Accès au logement"
_COL_PREC   = "Précisions (exemple système d’alarme, enfant qui dort, etc.)"
_COL_ATTN   = "ATTENTION"
_COL_ANIMAL = "Avez-vous des animaux?"
_COL_ATYPE  = "De quels animaux s’agit-il?"
_COL_PROB   = "Problème"
_COL_ALLDEV = "Est-ce sur tous les appareils"
_COL_REBOOT = "Avez-vous tenté de redémarrer les appareils?"
_COL_ALLRM  = "Est-ce dans toutes les pièces?"
_COL_ERRMSG = "Quel est le message d’erreur?"
_COL_DESC   = "Décrivez le problème : donnez le plus de détails possible"
_COL_PHOTO  = "Joindre une photo (s’il y a lieu)"
_COL_WPUSER = "Créé par (ID utilisateur)"
_COL_TYPE   = "De quel type de demande s’agit-il?"
_COL_PHONE2_ALT = "Téléphone 2"
_COL_OTHER  = "Autre personne à contacter au besoin"
_COL_OTHER_EMAIL = "Courriel de la deuxième personne à contacter"
_COL_MAINT  = "Type de maintenance requise"


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    # "Date de l'entrée" is Quebec local time (EDT = UTC-4)
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ_QC)
    return dt.astimezone(timezone.utc)


def _build_problems(row: dict) -> str:
    parts = []
    # Main problem type + description
    prob = row.get(_COL_PROB, "").strip()
    if prob:
        parts.append(f"Problème : {prob}")
    for col, label in [
        (_COL_ALLDEV, "Sur tous les appareils"),
        (_COL_REBOOT, "Redémarrage tenté"),
        (_COL_ALLRM,  "Dans toutes les pièces"),
        (_COL_ERRMSG, "Message d'erreur"),
    ]:
        val = row.get(col, "").strip()
        if val and val.lower() not in ("", "n/a", "non applicable"):
            parts.append(f"{label} : {val}")
    desc = row.get(_COL_DESC, "").strip()
    if desc:
        parts.append(f"Décrivez : {desc}")
    # Précisions (access-related; not written to entry_permission to avoid appending free text)
    prec = row.get(_COL_PREC, "").strip()
    if prec:
        parts.append(f"Précisions (accès) : {prec}")
    # Animal details
    atype = row.get(_COL_ATYPE, "").strip()
    if atype:
        parts.append(f"Animaux (détails) : {atype}")
    # ATTENTION flag (not written to other_notes — that's the AI field)
    attn = row.get(_COL_ATTN, "").strip()
    if attn:
        parts.append(f"⚠ ATTENTION : {attn}")
    # Second contact
    other = row.get(_COL_OTHER, "").strip()
    other_email = row.get(_COL_OTHER_EMAIL, "").strip()
    if other or other_email:
        parts.append(f"Autre contact : {other}{f' <{other_email}>' if other_email else ''}")
    # Second phone
    phone2 = row.get(_COL_PHONE2_ALT, "").strip()
    if phone2:
        parts.append(f"Téléphone 2 : {phone2}")
    return "\n".join(parts)


def _animals_val(row: dict) -> str | None:
    val = row.get(_COL_ANIMAL, "").strip()
    if val == "Oui":
        return "Oui"
    return None  # "Non" and "N/A" → NULL


def import_csv(conn, csv_path: Path, dry_run: bool = False) -> dict:
    counts = {"total": 0, "skipped": 0, "exact": 0,
              "building_only": 0, "ambiguous": 0, "no_match": 0, "garbled": 0, "error": 0}

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    counts["total"] = len(rows)

    for row in rows:
        entry_id = row[_COL_ID].strip()

        # Idempotency check
        existing = conn.execute(
            "SELECT 1 FROM maintenance_request WHERE external_source = 'gravity_forms' AND external_ref = %(ref)s",
            {"ref": entry_id},
        ).fetchone()
        if existing:
            counts["skipped"] += 1
            continue

        submission_dt = _parse_date(row.get(_COL_DATE, ""))
        problems_text = _build_problems(row)
        animals_val = _animals_val(row)
        entry_perm = row.get(_COL_ACCESS, "").strip() or None
        attachment = row.get(_COL_PHOTO, "").strip() or None
        wp_user_raw = row.get(_COL_WPUSER, "").strip()
        wp_user = int(wp_user_raw) if wp_user_raw.isdigit() else None

        civic  = row.get(_COL_CIVIC, "").strip()
        street = row.get(_COL_STREET, "").strip()
        apt    = row.get(_COL_APT, "").strip() or None

        result = match_address(conn, civic, street, apt)
        counts[result.match_status] += 1

        if dry_run:
            continue

        try:
            raw_caller_body = json.dumps({
                "entry_permission": entry_perm,
                "animals": animals_val,
                "problems": problems_text or None,
            })
            conn.execute(
                """
                INSERT INTO maintenance_request (
                    status, body_format, external_source, external_ref,
                    building_id, unit_id,
                    caller_name, caller_phone, caller_email,
                    entry_permission, animals,
                    problems, raw_title,
                    attachment_url, created_by_wp_user_id,
                    raw_caller_body,
                    source_calendar, start_date, submission_date
                ) VALUES (
                    'intake_received', 'gravity_forms', 'gravity_forms', %(ref)s,
                    %(building_id)s, %(unit_id)s,
                    %(caller_name)s, %(phone1)s, %(email)s,
                    %(entry_perm)s, %(animals)s,
                    %(problems)s, 'Maintenance non-urgente',
                    %(attachment)s, %(wp_user)s,
                    %(raw_caller_body)s,
                    NULL, NULL, %(submission_dt)s
                )
                RETURNING request_id
                """,
                {
                    "ref":             entry_id,
                    "building_id":     result.building_id,
                    "unit_id":         result.unit_id,
                    "caller_name":     row.get(_COL_NAME, "").strip() or None,
                    "phone1":          row.get(_COL_PHONE1, "").strip() or None,
                    "email":           row.get(_COL_EMAIL, "").strip() or None,
                    "entry_perm":      entry_perm,
                    "animals":         animals_val,
                    "problems":        problems_text or None,
                    "attachment":      attachment,
                    "wp_user":         wp_user,
                    "raw_caller_body": raw_caller_body,
                    "submission_dt":   submission_dt,
                },
            )
            request_id = conn.execute(
                "SELECT request_id FROM maintenance_request WHERE external_source='gravity_forms' AND external_ref=%(ref)s",
                {"ref": entry_id},
            ).fetchone()["request_id"]

            # Write provenance rows for the mapped fields
            _write_provenance(conn, request_id, entry_id, csv_path.name, row)
        except Exception as exc:
            counts["error"] += 1
            print(f"  ERROR row {entry_id}: {exc}", file=sys.stderr)
            conn.rollback()
            continue

    if not dry_run:
        conn.commit()
    return counts


def _write_provenance(conn, request_id: int, entry_id: str, filename: str, row: dict) -> None:
    col_map = [
        (_COL_DATE,    "submission_date"),
        (_COL_NAME,    "caller_name"),
        (_COL_EMAIL,   "caller_email"),
        (_COL_PHONE1,  "caller_phone"),
        (_COL_CIVIC,   "civic"),
        (_COL_STREET,  "street_raw"),
        (_COL_APT,     "unit_id"),
        (_COL_ACCESS,  "entry_permission"),
        (_COL_ANIMAL,  "animals"),
        (_COL_DESC,    "problems"),
        (_COL_PHOTO,   "attachment_url"),
        (_COL_WPUSER,  "created_by_wp_user_id"),
    ]
    prov_rows = [
        (
            str(request_id), db_col, src_col,
            row.get(src_col, "").strip() or None,
            filename, entry_id,
        )
        for src_col, db_col in col_map
        if row.get(src_col, "").strip()
    ]
    sql = """
        INSERT INTO data_provenance
            (target_table, target_pk, target_column, source_type,
             raw_value, source_file_name, source_row, ingested_at)
        VALUES ('maintenance_request', %s, %s, 'csv_import', %s, %s, %s, NOW())
    """
    for pk, db_col, _src, raw, fname, srow in prov_rows:
        conn.execute(sql, (pk, db_col, raw, fname, srow))


def cleanup(conn) -> None:
    # Child rows first (FK constraints); data_provenance has no FK so is left as audit trail.
    triage_rows = conn.execute(
        "DELETE FROM triage_log WHERE request_id IN "
        "(SELECT request_id FROM maintenance_request WHERE external_source = 'gravity_forms')"
    ).rowcount
    attach_rows = conn.execute(
        "DELETE FROM maintenance_attachment WHERE request_id IN "
        "(SELECT request_id FROM maintenance_request WHERE external_source = 'gravity_forms')"
    ).rowcount
    flog = conn.execute(
        "DELETE FROM maintenance_followup_entry WHERE request_id IN "
        "(SELECT request_id FROM maintenance_request WHERE external_source = 'gravity_forms')"
    ).rowcount
    jlog = conn.execute(
        "DELETE FROM decision_justification_log WHERE request_id IN "
        "(SELECT request_id FROM maintenance_request WHERE external_source = 'gravity_forms')"
    ).rowcount
    n = conn.execute(
        "DELETE FROM maintenance_request WHERE external_source = 'gravity_forms'"
    ).rowcount
    conn.commit()
    print(f"Deleted {n} gravity_forms request(s) — "
          f"{triage_rows} triage_log, {attach_rows} attachments, "
          f"{flog} followup entries, {jlog} justification log rows.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, help="Path to Gravity Forms CSV export")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete all gravity_forms rows and their children")
    args = parser.parse_args()

    with psycopg.connect(LOCAL_DSN, row_factory=dict_row) as conn:
        if args.cleanup:
            cleanup(conn)
        elif args.csv:
            counts = import_csv(conn, args.csv, dry_run=args.dry_run)
            tag = "[DRY RUN] " if args.dry_run else ""
            print(f"\n{tag}Import report — {args.csv.name}")
            print(f"  Total rows        : {counts['total']}")
            print(f"  Already imported  : {counts['skipped']}")
            print(f"  Match — exact     : {counts['exact']}")
            print(f"  Match — bldg only : {counts['building_only']}")
            print(f"  Match — ambiguous : {counts['ambiguous']}")
            print(f"  Match — no match  : {counts['no_match']}")
            print(f"  Garbled address   : {counts['garbled']}")
            print(f"  Errors            : {counts['error']}")
            new = counts['total'] - counts['skipped'] - counts['error']
            print(f"  Rows written      : {new if not args.dry_run else 'N/A (dry run)'}")
        else:
            parser.print_help()
