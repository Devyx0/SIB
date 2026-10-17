"""
Triage service — wires context_builder → system_prompt → Anthropic API → output_contract.

Status machine:
    intake_received → triage_pending → triage_proposal → triaged
                                    ↘ triage_clarify  (human input required, NO auto-retry)
                                    ↘ triage_failed   (API/gate failure, auto-retry ok)

triage_clarify vs triage_failed:
    triage_failed  = transient error (API down, model produced invalid JSON, gate rejection).
                     The retry loop picks these up automatically.
    triage_clarify = structural blocker (unit unresolvable, address ambiguous). Retrying
                     produces the same result every time. The row stays triage_clarify until
                     a coordinator resolves the ambiguity and resets it to intake_received.
                     This function explicitly skips triage_clarify rows.

Concurrency: SELECT ... FOR UPDATE SKIP LOCKED sets triage_pending + triage_started_at
atomically. Other workers see triage_pending and skip. Rows stuck > _ABANDONED_MINUTES
are eligible for takeover (process crashed mid-call).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import anthropic

from .context_builder import assemble
from .output_contract import ValidationError, parse_response, validate
from .system_prompt import DOCUMENTS_HASH, build_system_prompt

_MODEL = os.getenv("TRIAGE_MODEL", "claude-sonnet-4-6")
_MAX_RETRIES = 3
_ABANDONED_MINUTES = 10


# ── JSON encoder for psycopg2 date/datetime objects ────────────────────────────

class _DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


# ── Context formatter (user message) ──────────────────────────────────────────

def _d(val) -> str:
    return val.isoformat() if val else "—"


def _format_context(ctx: dict) -> str:
    req = ctx["request"]
    parts: list[str] = []

    parts.append(f"## Demande #{req['request_id']} — {req.get('raw_title', '')}")
    parts.append(f"Date : {_d(req.get('start_date'))}")
    if req.get("urgency_raw"):
        parts.append(f"Urgence brute : {req['urgency_raw']}")
    if req.get("problem_summary"):
        parts.append(f"Résumé actuel : {req['problem_summary']}")
    if req.get("problems"):
        parts.append(f"Problèmes saisis :\n{req['problems']}")
    if req.get("entry_permission"):
        parts.append(f"Entrée : {req['entry_permission']}")
    if req.get("animals"):
        parts.append(f"Animaux : {req['animals']}")
    if req.get("subcontractor_name"):
        parts.append(f"Sous-traitant brut : {req['subcontractor_name']}")
    if req.get("ft_link"):
        parts.append(f"Fiche technique : {req['ft_link']}")

    # Unit
    parts.append("\n## Unité")
    unit = ctx.get("unit")
    if unit is None:
        parts.append("⚠ Aucun bail actif trouvé — contexte locataire indisponible.")
    else:
        parts.append(f"Adresse : {unit.get('rue', '')} app. {unit.get('numero_appartement', '')} ({unit.get('grandeur', '')})")
        parts.append(f"Bail : {_d(unit.get('debut_bail'))} → {_d(unit.get('fin_bail'))}")
        if unit.get("droit_animaux"):
            parts.append(f"Animaux autorisés : {unit['droit_animaux']}")
        for o in unit.get("occupants", []):
            line = o.get("nom_complet", "?")
            if o.get("telephone"):
                line += f"  {o['telephone']}"
            if o.get("courriel"):
                line += f"  {o['courriel']}"
            if o.get("capacite"):
                line += f"  [{o['capacite']}]"
            parts.append(f"  - {line}")

    # Building
    parts.append("\n## Immeuble")
    bldg = ctx.get("building")
    if bldg:
        parts.append(f"{bldg.get('adresse', '')} {bldg.get('ville', '')} {bldg.get('code_postal', '')}")
        parts.append(f"Projet : {bldg.get('nom_unique_projet', '')} (#{bldg.get('accounting_project_number', '')})")
        parts.append(f"Territoire : {bldg.get('territoire', '')} — {bldg.get('color_code', '')}")
        parts.append(f"Logements : {bldg.get('nb_logements', '?')}  Étages : {bldg.get('nb_etages', '?')}")
        features = [f for f in ("ascenseur", "piscine", "sauna", "gym") if bldg.get(f)]
        if features:
            parts.append(f"Équipements : {', '.join(features)}")
        if bldg.get("raw_fiche_technique"):
            ft = bldg["raw_fiche_technique"]
            ft_str = json.dumps(ft, ensure_ascii=False) if isinstance(ft, dict) else str(ft)
            parts.append(f"Fiche technique :\n{ft_str[:2000]}")

    # Duplicates
    dups = ctx.get("duplicates", [])
    parts.append(f"\n## Doublons potentiels ({len(dups)})")
    if dups:
        for d in dups:
            parts.append(f"- #{d['request_id']} [{_d(d.get('start_date'))}] {d.get('raw_title', '')} — {d.get('status', '')}")
    else:
        parts.append("(aucun dans la fenêtre −90j → +45j)")

    # Synergy
    syn = ctx.get("synergy", {})
    scope = syn.get("scope", "?")
    total = syn.get("total", 0)
    parts.append(f"\n## Synergies (portée : {scope}, {total} candidats)")
    if syn.get("narrowed_from"):
        parts.append(f"ℹ {syn['narrowed_from']}")
    if scope == "saturated":
        parts.append(f"Inventaire dense ({total} demandes). Regroupements disponibles — consulter le tableau de bord.")
    else:
        for s in syn.get("items", []):
            parts.append(f"- #{s['request_id']} [{_d(s.get('start_date'))}] {s.get('raw_title', '')} [{s.get('status', '')}]")
        if scope == "pest":
            for wc in syn.get("warranty_cases", []):
                parts.append(f"  Garantie active : case #{wc['case_id']} {wc.get('pest_type', '')} — expire {_d(wc.get('warranty_expiry_date'))}")
        if not syn.get("items"):
            parts.append("(aucune synergy dans la fenêtre)")

    # History
    hist = ctx.get("history", [])
    parts.append(f"\n## Historique de l'unité ({len(hist)} demandes, −6mo → +21j)")
    for h in hist[:20]:
        parts.append(f"- #{h['request_id']} [{_d(h.get('start_date'))}] {h.get('raw_title', '')} — {h.get('complexity_tier', '?')}/{h.get('congestion_level', '?')}")
    if not hist:
        parts.append("(aucun historique)")

    # Photos
    photos = ctx.get("photos", [])
    if photos:
        parts.append(f"\n## Photos ({len(photos)} pièces jointes)")
        for p in photos:
            parts.append(f"- {p.get('file_type', '?')} — {p.get('drive_file_id', '')}")

    return "\n".join(parts)


# ── DB write helpers ───────────────────────────────────────────────────────────

_PROVENANCE_COLS = (
    "problem_summary", "problems", "entry_permission", "animals",
    "urgency_tier", "complexity_tier", "congestion_level",
    "time_estimate_bucket", "delegable_status", "report_status",
    "routing_rule", "other_notes",
)


def _write_triage_provenance(cur, request_id: int, parsed: dict,
                              model_version: str, old_row: tuple) -> None:
    problems_text = None
    if parsed.get("problems"):
        problems_text = "\n".join(f"- {p}" for p in parsed["problems"])
    new_vals = {
        "problem_summary":    parsed.get("title"),
        "problems":           problems_text,
        "entry_permission":   parsed.get("entry_permission"),
        "animals":            parsed.get("animals"),
        "urgency_tier":       parsed.get("urgency_tier"),
        "complexity_tier":    parsed.get("complexity_tier"),
        "congestion_level":   parsed.get("congestion_level"),
        "time_estimate_bucket": parsed.get("time_estimate_bucket"),
        "delegable_status":   parsed.get("delegable_status"),
        "report_status":      parsed.get("report_status"),
        "routing_rule":       parsed.get("routing_rule"),
        "other_notes":        parsed.get("other_notes"),
    }
    rows = [
        (
            str(request_id), col,
            str(old_row[i]) if old_row[i] is not None else None,
            str(new_vals[col]) if new_vals[col] is not None else None,
            model_version,
        )
        for i, col in enumerate(_PROVENANCE_COLS)
        if (old_row[i] if old_row[i] is not None else None) != (
            str(new_vals[col]) if new_vals[col] is not None else None
        )
    ]
    if not rows:
        return
    cur.executemany(
        """
        INSERT INTO data_provenance
            (target_table, target_pk, target_column, source_type,
             previous_value, ingested_value, raw_value, source_file_name, ingested_at)
        VALUES ('maintenance_request', %s, %s, 'triage', %s, %s, NULL, %s, NOW())
        """,
        rows,
    )


def _write_result(cur, request_id: int, parsed: dict, model_version: str) -> None:
    cur.execute(
        f"SELECT {', '.join(_PROVENANCE_COLS)} FROM maintenance_request WHERE request_id = %s",
        (request_id,),
    )
    old_row = cur.fetchone()

    problems_text = None
    if parsed.get("problems"):
        problems_text = "\n".join(f"- {p}" for p in parsed["problems"])

    cur.execute(
        """
        UPDATE maintenance_request SET
            status                  = 'triaged',
            problem_summary         = %(title)s,
            problems                = %(problems)s,
            entry_permission        = %(entry_permission)s,
            animals                 = %(animals)s,
            urgency_tier            = %(urgency_tier)s::urgency_tier,
            complexity_tier         = %(complexity_tier)s::complexity_tier,
            congestion_level        = %(congestion_level)s::congestion_level,
            time_estimate_bucket    = %(time_estimate_bucket)s::time_estimate_bucket,
            delegable_status        = %(delegable_status)s::delegable_status,
            report_status           = %(report_status)s::report_status,
            routing_rule            = %(routing_rule)s,
            subcontractor_name      = %(subcontractor_name)s,
            vendor_id               = %(vendor_id)s,
            synergy_request_ids     = %(synergy_request_ids)s,
            other_notes             = %(other_notes)s,
            duplicate_of_request_id = %(dup_id)s,
            addition_to_request_id  = %(add_id)s,
            triage_model_version    = %(model_version)s,
            triage_started_at       = NULL
        WHERE request_id = %(request_id)s
        """,
        {
            "title":              parsed.get("title"),
            "problems":           problems_text,
            "entry_permission":   parsed.get("entry_permission"),
            "animals":            parsed.get("animals"),
            "urgency_tier":       parsed.get("urgency_tier"),
            "complexity_tier":    parsed.get("complexity_tier"),
            "congestion_level":   parsed.get("congestion_level"),
            "time_estimate_bucket": parsed.get("time_estimate_bucket"),
            "delegable_status":   parsed.get("delegable_status"),
            "report_status":      parsed.get("report_status"),
            "routing_rule":       parsed.get("routing_rule"),
            "subcontractor_name": parsed.get("subcontractor_name"),
            "vendor_id":          parsed.get("vendor_id"),
            "synergy_request_ids": parsed.get("synergy_request_ids") or [],
            "other_notes":        parsed.get("other_notes"),
            "dup_id":             parsed.get("duplicate_of_request_id"),
            "add_id":             parsed.get("addition_to_request_id"),
            "model_version":      model_version,
            "request_id":         request_id,
        },
    )
    if old_row is not None:
        _write_triage_provenance(cur, request_id, parsed, model_version, old_row)


def _log_attempt(cur, request_id: int, *, model_version: str, context_sent: dict,
                 raw_response: str | None, validation_result: str,
                 validation_detail: str | None, latency_ms: int,
                 input_tokens: int | None, output_tokens: int | None) -> None:
    cur.execute(
        """
        INSERT INTO triage_log (
            request_id, attempted_at, model_version, context_sent,
            raw_response, validation_result, validation_detail,
            latency_ms, input_tokens, output_tokens
        ) VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request_id, model_version,
            json.dumps(context_sent, cls=_DateEncoder),
            raw_response, validation_result, validation_detail,
            latency_ms, input_tokens, output_tokens,
        ),
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def triage(conn, request_id: int, *, max_retries: int = _MAX_RETRIES,
           model: str | None = None, dry_run: bool = False) -> dict:
    """
    Run AI triage for a single request.

    Returns dict with 'result' key:
      'triaged'       — success
      'triage_failed' — exhausted retries
      'skipped'       — already triaged, or locked by another active worker
      'dry_run'       — dry_run=True; context and formatted message returned, no API call

    dry_run skips DB writes and the API call; useful for cost-free testing.
    """
    model = model or _MODEL

    # ── Acquire soft lock ──────────────────────────────────────────────────────
    # FOR UPDATE SKIP LOCKED prevents two workers from both atomically claiming the same row.
    # After commit, the status='triage_pending' + triage_started_at acts as the ongoing lock.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT request_id, status, triage_started_at
            FROM maintenance_request
            WHERE request_id = %s
            FOR UPDATE SKIP LOCKED
            """,
            (request_id,),
        )
        row = cur.fetchone()

    if row is None:
        # Row locked by another worker right now
        conn.rollback()
        return {"result": "skipped", "reason": "row locked by another worker"}

    _, current_status, started_at = row

    if current_status in ("triaged", "en_route", "closed"):
        conn.rollback()
        return {"result": "skipped", "reason": f"already in terminal state ({current_status})"}

    if current_status == "triage_clarify":
        conn.rollback()
        return {"result": "skipped", "reason": "triage_clarify — blocked on human input; coordinator must resolve before retry"}

    if current_status == "triage_pending" and started_at is not None:
        age_min = (datetime.now(timezone.utc) - started_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
        if age_min < _ABANDONED_MINUTES:
            conn.rollback()
            return {"result": "skipped", "reason": f"in progress by another worker ({age_min:.1f} min ago)"}

    if not dry_run:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE maintenance_request SET status = 'triage_pending', triage_started_at = NOW() WHERE request_id = %s",
                (request_id,),
            )
        conn.commit()

    # ── Build context ──────────────────────────────────────────────────────────
    ctx = assemble(conn, request_id)
    user_message = _format_context(ctx)
    system_blocks = build_system_prompt()
    model_version = f"{model}|docs-{DOCUMENTS_HASH[:8]}"

    if dry_run:
        conn.rollback()
        return {
            "result":        "dry_run",
            "context":       ctx,
            "user_message":  user_message,
            "model_version": model_version,
            "char_count":    len(user_message),
            "approx_tokens": len(user_message) // 4,
        }

    # ── Retry loop ─────────────────────────────────────────────────────────────
    api_key = os.environ["ANTHROPIC_API_KEY"]
    extra_headers = {}
    if api_key.startswith("sk-ant-api03-"):
        wid = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
        if wid:
            extra_headers["anthropic-workspace-id"] = wid
    client = anthropic.Anthropic(api_key=api_key, default_headers=extra_headers, timeout=120.0)
    last_result = "triage_failed"
    last_detail = None

    for attempt in range(max_retries):
        t0 = time.monotonic()
        raw_response = None
        input_tokens = output_tokens = None

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_blocks,
                messages=[{"role": "user", "content": user_message}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            raw_response = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            parsed = parse_response(raw_response)
            val_result, val_detail = validate(parsed, conn, request_id)

            with conn.cursor() as cur:
                _log_attempt(cur, request_id, model_version=model_version,
                             context_sent=ctx, raw_response=raw_response,
                             validation_result=val_result, validation_detail=val_detail,
                             latency_ms=latency_ms, input_tokens=input_tokens,
                             output_tokens=output_tokens)
                if val_result == "accepted":
                    _write_result(cur, request_id, parsed, model_version)
            conn.commit()

            if val_result == "accepted":
                return {"result": "triaged", "attempt": attempt + 1,
                        "latency_ms": latency_ms, "model_version": model_version}

            last_result = val_result
            last_detail = val_detail
            # gate rejected — retry with same context

        except (ValidationError, anthropic.APIError) as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            with conn.cursor() as cur:
                _log_attempt(cur, request_id, model_version=model_version,
                             context_sent=ctx, raw_response=raw_response,
                             validation_result="error", validation_detail=str(exc),
                             latency_ms=latency_ms, input_tokens=input_tokens,
                             output_tokens=output_tokens)
            conn.commit()
            last_result = "error"
            last_detail = str(exc)

    # All retries exhausted — surface as triage_failed
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE maintenance_request SET status = 'triage_failed', triage_started_at = NULL WHERE request_id = %s",
            (request_id,),
        )
    conn.commit()

    return {"result": "triage_failed", "attempts": max_retries,
            "last_result": last_result, "detail": last_detail}


# ── Self-check ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    from backend.core.db import get_legacy_conn
    conn = get_legacy_conn()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT request_id FROM maintenance_request
            WHERE start_date IS NOT NULL AND unit_id IS NOT NULL AND status = 'closed'
            LIMIT 3
            """
        )
        test_ids = [r[0] for r in cur.fetchall()]

    print(f"Dry-run on {test_ids}")
    for rid in test_ids:
        result = triage(conn, rid, dry_run=True)
        msg = result["user_message"]
        print(f"\n--- #{rid}  {result['approx_tokens']:,} tokens ---")
        print(msg[:800])
        print("...")

    conn.close()
