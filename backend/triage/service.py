"""
Triage service — wires context_builder → system_prompt → Anthropic API → output_contract.

Status machine:
    intake_received → triage_pending → triage_proposal → open   (single + recommended_tasks[]: proposals written)
                                    ↘ triaged           (duplicate / merged addition / no tasks)
                                    ↘ triage_clarify  (human input required, NO auto-retry)
                                    ↘ triage_failed   (API/gate failure, auto-retry ok)

triage_clarify vs triage_failed:
    triage_failed  = transient error (API down, model produced invalid JSON, gate rejection).
                     The retry loop picks these up automatically.
    triage_clarify = structural blocker (no active lease, unit unresolvable). Retrying
                     produces the same result every time. The row stays triage_clarify until
                     a coordinator resolves the ambiguity and resets it to intake_received.
                     This function explicitly skips triage_clarify rows.

Concurrency: SELECT ... FOR UPDATE SKIP LOCKED sets triage_pending + triage_started_at
atomically. Other workers see triage_pending and skip. Rows stuck > _ABANDONED_MINUTES
are eligible for takeover (process crashed mid-call).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import anthropic

from .context_builder import assemble

logger = logging.getLogger("backend.triage")
from .output_contract import ValidationError, parse_response, validate
from .system_prompt import DOCUMENTS_HASH, build_system_prompt

_MODEL = os.getenv("TRIAGE_MODEL", "claude-sonnet-4-6")
_MAX_RETRIES = 3
_MAX_TOKENS = 2048  # call fields + recommended_tasks[] outgrow 1024
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
    if req.get("problem_summary"):
        parts.append(f"Résumé actuel : {req['problem_summary']}")
    if req.get("problems"):
        parts.append(f"Problèmes saisis :\n{req['problems']}")
    if req.get("entry_permission"):
        parts.append(f"Entrée : {req['entry_permission']}")
    if req.get("subcontractor_name"):
        parts.append(f"Sous-traitant brut : {req['subcontractor_name']}")
    if req.get("ft_link"):
        parts.append(f"Fiche technique : {req['ft_link']}")

    # Unit + RRIA cross-checks (rule 21)
    parts.append("\n## Unité")
    unit = ctx.get("unit")
    rr = ctx.get("rentroll") or {}
    if rr.get("lease_missing"):
        parts.append("⚠ Aucun bail actif — triage bloqué, clarification humaine.")
    elif unit is None:
        parts.append("Pas d'unité de logement — bail non applicable.")
    else:
        parts.append(f"Adresse : {unit.get('rue', '')} app. {unit.get('numero_appartement', '')} ({unit.get('grandeur', '')})")
        bail = f"Bail : {_d(unit.get('debut_bail'))} → {_d(unit.get('fin_bail'))}"
        if not unit.get("debut_bail"):
            bail += " (début inconnu)"
        if rr.get("recent_move_in"):
            bail += " (emménagement récent)"
        parts.append(bail)
        if rr.get("langue_en"):
            parts.append("Langue du bail : anglais")
        if rr.get("vacant"):
            parts.append("LOGEMENT VACANT — accès libre")
        for o in unit.get("occupants", []):
            line = o.get("nom_complet", "?")
            if o.get("telephone"):
                line += f"  {o['telephone']}"
            if o.get("courriel"):
                line += f"  {o['courriel']}"
            if o.get("capacite"):
                line += f"  [{o['capacite']}]"
            parts.append(f"  - {line}")
        if rr.get("caller_mismatch"):
            parts.append("RÉQUÉRANT ABSENT des titulaires du bail.")
        required = rr.get("required_notes") or []
        if required:
            quoted = ", ".join(f"« {p} »" for p in required)
            parts.append(f"other_notes DOIT contenir chacune de ces mentions : {quoted}.")

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

    # Duplicates — open same-unit only; labelled same vs different problem (rule 12)
    dups = ctx.get("duplicates", [])
    same = [d for d in dups if d.get("problem_relation") == "same_problem"]
    diff = [d for d in dups if d.get("problem_relation") != "same_problem"]
    parts.append(
        f"\n## Doublons / ajouts potentiels ({len(dups)} ouverts, même unité, −90j → +45j)"
    )
    parts.append(
        "Règles de fusion (client) : "
        "1) Même problème → verdict duplicate (+ DOUBLON POTENTIEL dans le titre) — ne pas fusionner. "
        "2) Problème différent + routing A1/A2/A3/A3b/A4 (catégories exclusives) → verdict single "
        "(appel distinct, jamais addition). "
        "3) Problème différent + catégorie normale (A0/A5) → verdict addition "
        "(le système fusionnera le problème dans l'appel ouvert). "
        "Sinon → single."
    )
    if same:
        parts.append(f"### Même problème ({len(same)}) — candidats duplicate")
        for d in same:
            parts.append(
                f"- #{d['request_id']} [{_d(d.get('start_date'))}] "
                f"{d.get('raw_title', '')} — {d.get('status', '')}"
            )
    if diff:
        parts.append(f"### Problème différent ({len(diff)}) — candidats addition")
        for d in diff:
            parts.append(
                f"- #{d['request_id']} [{_d(d.get('start_date'))}] "
                f"{d.get('raw_title', '')} — {d.get('status', '')}"
            )
    if not dups:
        parts.append("(aucun appel ouvert dans la fenêtre)")

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
        items = syn.get("items") or []
        cap = syn.get("link_cap") or 5
        linked, compact = items[:cap], items[cap:]
        if linked:
            parts.append(f"Liens (maximum {cap}) :")
            for s in linked:
                sat = " — samedi, pas un argument de date" if s.get("saturday_landing") else ""
                parts.append(
                    f"- #{s['request_id']} [{_d(s.get('start_date'))}] "
                    f"{s.get('raw_title', '')} [{s.get('status', '')}]{sat}"
                )
        if compact:
            parts.append(f"Compact sans lien ({len(compact)}) :")
            for s in compact:
                sat = " — samedi" if s.get("saturday_landing") else ""
                parts.append(
                    f"- #{s['request_id']} [{_d(s.get('start_date'))}] "
                    f"{s.get('raw_title', '')}{sat}"
                )
        if scope == "pest":
            for wc in syn.get("warranty_cases", []):
                parts.append(f"  Garantie active : case #{wc['case_id']} {wc.get('pest_type', '')} — expire {_d(wc.get('warranty_expiry_date'))}")
        if not items:
            parts.append("(aucune synergy dans la fenêtre)")

    # Congestion — computed, the model must copy it (skill's frozen N5 is not live).
    cg = ctx.get("congestion") or {}
    if cg.get("level"):
        parts.append(
            f"\n## Embourbement\n"
            f"État actuel : {cg['level']} — {cg.get('label', '')} "
            f"({cg.get('open_count', 0)} appels ouverts dans le territoire). "
            f"Ignore la ligne figée « État actuel : N5 » du skill. "
            f"congestion_level DOIT être exactement \"{cg['level']}\"."
        )
    hist = ctx.get("history") or {}
    if isinstance(hist, list):  # older shape
        hist = {"unit": hist, "building": [], "unit_omitted": 0, "building_omitted": 0, "scope": "unit"}
    unit_h = hist.get("unit") or []
    bldg_h = hist.get("building") or []
    parts.append(
        f"\n## Historique (−6 mois → +21 j, portée {hist.get('scope', 'unit')})"
    )

    def _hist_line(h: dict) -> str:
        cal = h.get("source_calendar") or "—"
        return (
            f"- #{h['request_id']} [{_d(h.get('start_date'))}] "
            f"[{cal}] {h.get('raw_title', '')} — "
            f"{h.get('complexity_tier', '?')}/{h.get('congestion_level', '?')}"
        )

    if unit_h:
        parts.append(f"### Unité ({len(unit_h)})")
        for h in unit_h:
            parts.append(_hist_line(h))
        if hist.get("unit_omitted"):
            parts.append(f"… et {hist['unit_omitted']} autres appels d'unité non listés")
    if bldg_h:
        parts.append(f"### Immeuble ({len(bldg_h)})")
        for h in bldg_h:
            parts.append(_hist_line(h))
        if hist.get("building_omitted"):
            parts.append(f"… et {hist['building_omitted']} autres appels d'immeuble non listés")
    if not unit_h and not bldg_h:
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
    "problem_summary", "problems", "entry_permission",
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


# Exclusive / auto-routed categories — never merge into an open same-unit call.
_EXCLUSIVE_ROUTING = frozenset({"A1", "A2", "A3", "A3b", "A4"})


def _write_proposal_tasks(cur, request_id: int, tasks: list[dict]) -> None:
    """Insert AI proposals (accepted_at NULL, source ai_recommended) under a call.

    Raw cursor SQL rather than tasks.repository.insert_task: triage runs on a
    psycopg2 connection, the repository needs psycopg3. No assignee, no due date
    (rule 37) — the dispatcher decides both on accept. Earlier un-accepted AI
    proposals for the call are replaced so a re-triage never stacks duplicates.
    """
    cur.execute(
        "DELETE FROM dispatch_task "
        "WHERE request_id = %s AND source = 'ai_recommended' AND accepted_at IS NULL",
        (request_id,),
    )
    cur.execute(
        "SELECT COALESCE(MAX(sort_order) + 1, 0) FROM dispatch_task WHERE request_id = %s",
        (request_id,),
    )
    base = cur.fetchone()[0]
    for i, t in enumerate(tasks):
        description = t["description"].strip()
        if (t.get("notes") or "").strip():
            description += "\n" + t["notes"].strip()
        cur.execute(
            """
            INSERT INTO dispatch_task
                (request_id, description, urgency_tier, vendor_id,
                 subcontractor_name, source, accepted_at, sort_order)
            VALUES (%s, %s, %s, %s, %s, 'ai_recommended', NULL, %s)
            """,
            (request_id, description, t.get("urgency_tier"), t.get("vendor_id"),
             t.get("subcontractor_name"), base + i),
        )


def _merge_addition_into_peer(cur, request_id: int, peer_id: int, parsed: dict) -> bool:
    """Append this call's problems onto the open peer, then close this request as merged.

    Returns False when the peer was not updated (missing or already closed)."""
    new_problems = parsed.get("problems") or []
    bullet = "\n".join(f"- {p}" for p in new_problems) if new_problems else None
    note = (
        f"Problème ajouté depuis l'appel #{request_id}"
        + (f"\n{bullet}" if bullet else "")
    )
    cur.execute(
        """
        UPDATE maintenance_request SET
            problems = CASE
                WHEN problems IS NULL OR BTRIM(problems) = '' THEN %s
                ELSE problems || E'\\n' || %s
            END,
            other_notes = CASE
                WHEN other_notes IS NULL OR BTRIM(other_notes) = '' THEN %s
                ELSE other_notes || E'\\n' || %s
            END
        WHERE request_id = %s
          AND status::text NOT IN ('closed')
        """,
        (bullet or note, bullet or note, note, note, peer_id),
    )
    peer_updated = cur.rowcount > 0
    # Child is kept for audit but closed so it isn't dispatched separately.
    merge_note = f"Fusionné dans l'appel ouvert #{peer_id} (ajout — même unité, problème différent)."
    if parsed.get("other_notes"):
        parsed["other_notes"] = f"{parsed['other_notes']}\n{merge_note}"
    else:
        parsed["other_notes"] = merge_note
    return peer_updated


def _write_result(cur, request_id: int, parsed: dict, model_version: str) -> None:
    cur.execute(
        f"SELECT {', '.join(_PROVENANCE_COLS)} FROM maintenance_request WHERE request_id = %s",
        (request_id,),
    )
    old_row = cur.fetchone()

    # Client merge rules: exclusive routing never merges; normal addition merges into peer.
    if parsed.get("verdict") == "addition" and parsed.get("routing_rule") in _EXCLUSIVE_ROUTING:
        parsed["verdict"] = "single"
        parsed["addition_to_request_id"] = None

    merged = False
    peer_updated = False
    add_id = parsed.get("addition_to_request_id")
    if parsed.get("verdict") == "addition" and isinstance(add_id, int):
        peer_updated = _merge_addition_into_peer(cur, request_id, add_id, parsed)
        merged = True

    # Tasks proposed for this call (single) or its peer (addition); never on a duplicate.
    tasks = [t for t in (parsed.get("recommended_tasks") or []) if isinstance(t, dict)]
    proposing = parsed.get("verdict") == "single" and bool(tasks)

    problems_text = None
    if parsed.get("problems"):
        problems_text = "\n".join(f"- {p}" for p in parsed["problems"])

    # Cardinal rule 35: rive-sud (Lévis) → Majordome calendar; else Main.
    from .calendar_route import infer_source_calendar_from_cur
    cal = infer_source_calendar_from_cur(cur, request_id)

    status = "closed" if merged else "triage_proposal" if proposing else "triaged"
    cur.execute(
        """
        UPDATE maintenance_request SET
            status                  = %(status)s::request_status,
            problem_summary         = %(title)s,
            problems                = %(problems)s,
            entry_permission        = %(entry_permission)s,
            urgency_tier            = %(urgency_tier)s,
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
            source_calendar         = %(source_calendar)s,
            triage_model_version    = %(model_version)s,
            triage_started_at       = NULL
        WHERE request_id = %(request_id)s
          AND status = 'triage_pending'
        """,
        {
            "status":             status,
            "title":              parsed.get("title"),
            "problems":           problems_text,
            "entry_permission":   parsed.get("entry_permission"),
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
            "source_calendar":    cal,
            "model_version":      model_version,
            "request_id":         request_id,
        },
    )
    if cur.rowcount == 0:
        # Status changed under us (e.g. a human action) — never overwrite it.
        logger.warning(
            "triage result for request %s discarded: status is no longer triage_pending",
            request_id,
        )
        return
    if proposing:
        _write_proposal_tasks(cur, request_id, tasks)
    elif merged and peer_updated and tasks:
        # Mid-life proposals: the peer keeps its status (not bounced to triage_proposal).
        _write_proposal_tasks(cur, add_id, tasks)
    if old_row is not None:
        _write_triage_provenance(cur, request_id, parsed, model_version, old_row)


def _mark_clarify(cur, request_id: int, reason: str) -> None:
    """No active lease on a housing unit. Stays blocked until a coordinator resets it."""
    cur.execute(
        """
        UPDATE maintenance_request
        SET status = 'triage_clarify',
            triage_started_at = NULL,
            triage_summary = %s
        WHERE request_id = %s AND status = 'triage_pending'
        """,
        (reason, request_id),
    )
    if cur.rowcount == 0:
        logger.warning(
            "triage clarify for request %s discarded: status is no longer triage_pending",
            request_id,
        )


def _mark_failed(cur, request_id: int) -> None:
    """Exhausted retries → triage_failed. Guarded: never overwrite a status a
    human set while we were retrying."""
    cur.execute(
        "UPDATE maintenance_request SET status = 'triage_failed', triage_started_at = NULL "
        "WHERE request_id = %s AND status = 'triage_pending'",
        (request_id,),
    )
    if cur.rowcount == 0:
        logger.warning(
            "triage failure for request %s discarded: status is no longer triage_pending",
            request_id,
        )


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
           model: str | None = None, dry_run: bool = False,
           lang: str = "fr") -> dict:
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
            SELECT request_id, status, triage_started_at, raw_title
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

    if isinstance(row, dict):
        current_status = row["status"]
        started_at = row["triage_started_at"]
        raw_title = row.get("raw_title")
    else:
        _, current_status, started_at, raw_title = row

    from backend.triage.context_builder import is_mechanically_excluded
    if is_mechanically_excluded(raw_title):
        conn.rollback()
        return {"result": "skipped", "reason": "mechanically excluded title (SKILL §4.2)"}

    if current_status in ("triaged", "scheduled", "awaiting_redispatch",
                          "en_route", "arrived", "closed"):
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
    output_lang = "en" if (lang or "fr").lower().startswith("en") else "fr"
    system_blocks = build_system_prompt(lang=output_lang)
    model_version = f"{model}|docs-{DOCUMENTS_HASH[:8]}|{output_lang}"

    rr = ctx.get("rentroll") or {}
    if rr.get("lease_missing"):
        if dry_run:
            conn.rollback()
        else:
            with conn.cursor() as cur:
                _mark_clarify(cur, request_id, "Aucun bail actif pour cette unité")
            conn.commit()
        return {"result": "triage_clarify", "reason": "no active lease"}

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
    from backend.core.config import settings
    api_key = settings.ANTHROPIC_API_KEY
    extra_headers = {}
    if api_key.startswith("sk-ant-api03-") and settings.ANTHROPIC_WORKSPACE_ID:
        extra_headers["anthropic-workspace-id"] = settings.ANTHROPIC_WORKSPACE_ID
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
                max_tokens=_MAX_TOKENS,
                system=system_blocks,
                messages=[{"role": "user", "content": user_message}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            raw_response = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            parsed = parse_response(raw_response)
            expected_n = (ctx.get("congestion") or {}).get("level")
            val_result, val_detail = validate(
                parsed, conn, request_id,
                expected_congestion=expected_n,
                required_notes=rr.get("required_notes") or None,
            )

            if val_result == "accepted":
                # Weather floor for "no heat" calls (art. 1864-1865 C.c.Q.).
                # Uses its own pool connection (this conn is psycopg2); never raises.
                from backend.modules.weather.service import apply_triage_escalation
                apply_triage_escalation(parsed, request_id)

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

    # All retries exhausted — surface as triage_failed (guarded, see _mark_failed).
    with conn.cursor() as cur:
        _mark_failed(cur, request_id)
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
