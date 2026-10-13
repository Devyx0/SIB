"""
Stratified backtest for the AI triage service.

Selects 50 historical requests, runs new triage against stored values.
Does NOT write to the database — purely read + API.
Results saved to docs/backtest_results.jsonl and printed as structured report.

Pool (--full): closed maintenance_requests where complexity_tier IS NOT NULL
AND start_date IS NOT NULL AND unit_id IS NOT NULL.
Currently 1,392 rows. The 1,956 figure cited elsewhere is the raw complexity_tier
count; 564 rows are excluded because start_date or unit_id is null (administrative
requests that were triaged but have no unit attachment). All 1,956 are already closed,
so status='closed' is a guard against future rows, not the cause of the discrepancy.

Usage:
    uv run python3 -m drive_pipeline.triage.backtest [--sample-only]
    uv run python3 -m drive_pipeline.triage.backtest --rerun   # replay the last 50 IDs
    uv run python3 -m drive_pipeline.triage.backtest --full    # full 1,392-row pool, resumable
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import anthropic
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from drive_pipeline.triage.context_builder import assemble
from drive_pipeline.triage.output_contract import ValidationError, parse_response, validate
from drive_pipeline.triage.service import _format_context
from drive_pipeline.triage.system_prompt import DOCUMENTS_HASH, build_system_prompt

_MODEL = os.getenv("TRIAGE_MODEL", "claude-sonnet-4-6")

# Rule-change dates for B-bucket heuristic
_RULE25_DATE = date(2026, 7, 13)   # rule 25 revised
_RULE37_DATE = date(2026, 8, 22)   # rule 37 (never assign) introduced

_COMPARE_FIELDS = [
    "complexity_tier",
    "congestion_level",
    "delegable_status",
    "report_status",
    "urgency_tier",
    "subcontractor_name",
    "duplicate_of_request_id",
]

_OUT          = Path(__file__).parent.parent.parent / "docs" / "backtest_results.jsonl"
_RERUN_OUT    = Path(__file__).parent.parent.parent / "docs" / "backtest_results_rerun.jsonl"
_FULL_OUT     = Path(__file__).parent.parent.parent / "docs" / "backtest_full_results.jsonl"
_SAMPLE_IDS   = Path(__file__).parent.parent.parent / "docs" / "backtest_sample_ids.json"
_COST_LOG     = Path(__file__).parent.parent.parent / "docs" / "api-cost-log.md"

# Sonnet 4.6 pricing (USD per token)
_PRICE_INPUT        = 3.00  / 1_000_000  # regular (uncached) input
_PRICE_CACHE_WRITE  = 3.75  / 1_000_000  # cache_creation tokens (premium vs regular)
_PRICE_CACHE_READ   = 0.30  / 1_000_000  # cache_read tokens (NOT part of input_tokens)
_PRICE_OUTPUT       = 15.00 / 1_000_000  # output


def _compute_cost(inp: int, cc: int, cr: int, out: int) -> float:
    """
    inp = input_tokens from API (includes cache_creation_tokens; does NOT include cache_read)
    cc  = cache_creation_tokens (subset of inp)
    cr  = cache_read_tokens (separate from inp)
    """
    return (inp - cc) * _PRICE_INPUT + cc * _PRICE_CACHE_WRITE + cr * _PRICE_CACHE_READ + out * _PRICE_OUTPUT

# ── Pool query ─────────────────────────────────────────────────────────────────

_POOL_SQL = """
SELECT
    mr.request_id,
    mr.start_date,
    mr.body_format,
    mr.unit_id,
    mr.subcontractor_name,
    mr.vendor_id,
    mr.duplicate_of_request_id,
    mr.synergy_request_ids,
    mr.complexity_tier,
    mr.congestion_level,
    mr.delegable_status,
    mr.report_status,
    mr.urgency_tier,
    mr.unit_label,
    CASE
        WHEN mr.subcontractor_name ~* 'extermin|punais|coquerelle|fourmi|gu[eê]pe|abeille|rongeur|insecte|souris'
            THEN 'pest'
        WHEN mr.vendor_id IS NOT NULL OR mr.subcontractor_name ILIKE 'Oui%%'
            THEN 'subcontractor'
        ELSE 'internal'
    END AS stream
FROM maintenance_request mr
WHERE mr.complexity_tier IS NOT NULL
  AND mr.status = 'closed'
  AND mr.start_date IS NOT NULL
  AND mr.unit_id IS NOT NULL
ORDER BY RANDOM()
"""

_BLOCKING_SQL = """
SELECT mr.request_id
FROM maintenance_request mr
WHERE mr.complexity_tier IS NOT NULL
  AND mr.status = 'closed'
  AND mr.start_date IS NOT NULL
  AND mr.unit_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM lease l
      WHERE l.unit_id = mr.unit_id
        AND (l.debut_bail IS NULL OR l.debut_bail <= mr.start_date)
        AND (l.fin_bail IS NULL OR l.fin_bail >= mr.start_date)
  )
LIMIT 50
"""


def _fetch_pool(cur):
    cur.execute(_POOL_SQL)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_by_ids(cur, ids: list[int]) -> list[dict]:
    """Fetch pool rows for specific IDs, preserving input order."""
    placeholders = ",".join(["%s"] * len(ids))
    cur.execute(
        f"""SELECT mr.request_id, mr.start_date, mr.body_format, mr.unit_id,
               mr.subcontractor_name, mr.vendor_id, mr.duplicate_of_request_id,
               mr.synergy_request_ids, mr.complexity_tier, mr.congestion_level,
               mr.delegable_status, mr.report_status, mr.urgency_tier, mr.unit_label,
               CASE
                   WHEN mr.subcontractor_name ~* 'extermin|punais|coquerelle|fourmi|gu[eê]pe|abeille|rongeur|insecte|souris'
                       THEN 'pest'
                   WHEN mr.vendor_id IS NOT NULL OR mr.subcontractor_name ILIKE 'Oui%%'
                       THEN 'subcontractor'
                   ELSE 'internal'
               END AS stream
            FROM maintenance_request mr
            WHERE mr.request_id IN ({placeholders})""",
        ids,
    )
    cols = [d[0] for d in cur.description]
    by_id = {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}
    return [{**by_id[i], "_stratum": "rerun"} for i in ids if i in by_id]


def _fetch_blocking_ids(cur) -> set[int]:
    cur.execute(_BLOCKING_SQL)
    return {row[0] for row in cur.fetchall()}


# ── Stratified sampling ────────────────────────────────────────────────────────

def select_sample(conn) -> list[dict]:
    """
    50 requests spanning body formats, streams, rule-change eras, dup/synergy,
    and blocking (no active lease). Returns list of metadata dicts.

    Strata are filled in priority order; deduplication ensures total = 50.
    belanger_compact and gravity_forms are absent from the 1,956 triaged rows
    — noted in the composition report.
    """
    with conn.cursor() as cur:
        pool = _fetch_pool(cur)
        blocking_ids = _fetch_blocking_ids(cur)

    selected: dict[int, dict] = {}

    def add(rows: list[dict], n: int, tag: str) -> int:
        added = 0
        for r in rows:
            if len(selected) >= 50 or added >= n:
                break
            if r["request_id"] not in selected:
                selected[r["request_id"]] = {**r, "_stratum": tag}
                added += 1
        return added

    # Priority 1 — rare strata first so they're guaranteed
    add([r for r in pool if r["request_id"] in blocking_ids], 5, "blocking")
    add([r for r in pool if r.get("duplicate_of_request_id")], 5, "has_dup")
    add([r for r in pool if r.get("synergy_request_ids")], 5, "has_synergy")
    add([r for r in pool if r.get("start_date") and r["start_date"] < _RULE25_DATE], 5, "pre_rule25")

    # Priority 2 — stream coverage
    add([r for r in pool if r.get("stream") == "pest"], 6, "stream:pest")
    add([r for r in pool if r.get("stream") == "subcontractor"], 6, "stream:subcontractor")

    # Priority 3 — post-rule37 era
    add([r for r in pool if r.get("start_date") and r["start_date"] >= _RULE37_DATE], 8, "post_rule37")

    # Priority 4 — body format coverage (v10 minority)
    add([r for r in pool if r.get("body_format") == "v10"], 5, "fmt:v10")

    # Fill to 50 — all remaining are mid-era internal v10_plaintext
    add(pool, 50 - len(selected), "fill")

    return list(selected.values())


def print_composition(sample: list[dict]) -> None:
    fmt = {}
    stream = {}
    era = {"pre_rule25 (<2026-07-13)": 0, "mid_era (Jul13–Aug22)": 0, "post_rule37 (>=2026-08-22)": 0}
    n_blocking = sum(1 for r in sample if r.get("_stratum") == "blocking")
    n_dup = sum(1 for r in sample if r.get("duplicate_of_request_id"))
    n_syn = sum(1 for r in sample if r.get("synergy_request_ids"))

    for r in sample:
        k = r.get("body_format") or "NULL"
        fmt[k] = fmt.get(k, 0) + 1
        k = r.get("stream") or "internal"
        stream[k] = stream.get(k, 0) + 1
        d = r.get("start_date")
        if d and d < _RULE25_DATE:
            era["pre_rule25 (<2026-07-13)"] += 1
        elif d and d < _RULE37_DATE:
            era["mid_era (Jul13–Aug22)"] += 1
        else:
            era["post_rule37 (>=2026-08-22)"] += 1

    print("=" * 62)
    print(f"BACKTEST SAMPLE COMPOSITION  (n={len(sample)})")
    print("=" * 62)
    print("Body format (note: belanger_compact/gravity_forms absent from")
    print("  triaged rows — those formats were never AI-triaged):")
    for k, v in sorted(fmt.items(), key=lambda x: -x[1]):
        print(f"  {k:<30} {v:3d}")
    print("\nStream:")
    for k, v in sorted(stream.items(), key=lambda x: -x[1]):
        print(f"  {k:<30} {v:3d}")
    print("\nRule-change era:")
    for k, v in era.items():
        print(f"  {k:<30} {v:3d}")
    print(f"\nWith duplicate_of_request_id:  {n_dup}")
    print(f"With synergy_request_ids:      {n_syn}")
    print(f"Blocking (no active lease):    {n_blocking}")
    print("=" * 62)


# ── Resume support ─────────────────────────────────────────────────────────────

def _load_done_ids(out_path: Path) -> set[int]:
    """Return request_ids that have parsed model output in the JSONL (non-api_error rows)."""
    if not out_path.exists():
        return set()
    done: set[int] = set()
    with open(out_path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("parsed") is not None:
                    done.add(r["request_id"])
            except json.JSONDecodeError:
                pass
    return done


def _report_from_jsonl(out_path: Path) -> None:
    """Generate full bucket/cost report by reading the complete JSONL (for post-resume summary)."""
    sample, results = [], []
    with open(out_path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec["request_id"]
            stored = rec.get("stored") or {}
            result_fields = rec.get("result") or {}
            raw_date = rec.get("start_date")
            try:
                start_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
            except ValueError:
                start_date = None
            row = {
                "request_id": rid,
                "start_date": start_date,
                "body_format": rec.get("body_format"),
                "stream": rec.get("stream"),
                **{f: stored.get(f) for f in _COMPARE_FIELDS},
            }
            sample.append(row)
            results.append({**result_fields, "parsed": rec.get("parsed")})
    print(f"\n(Summary covers all {len(sample)} rows in JSONL)")
    print_report(sample, results)


# ── API call ───────────────────────────────────────────────────────────────────

def _run_one(client, ctx: dict, system_blocks: list[dict],
             user_message: str, model: str) -> dict:
    t0 = time.monotonic()
    raw_response = None
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_blocks,
            messages=[{"role": "user", "content": user_message}],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        raw_response = resp.content[0].text
        # Cache-aware token counts (SDK >= 0.21)
        usage = resp.usage
        return {
            "ok": True,
            "raw_response":          raw_response,
            "latency_ms":            latency_ms,
            "input_tokens":          usage.input_tokens,
            "output_tokens":         usage.output_tokens,
            "cache_creation_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_tokens":     getattr(usage, "cache_read_input_tokens", 0) or 0,
        }
    except anthropic.APIError as exc:
        return {
            "ok": False,
            "error":      f"api_error: {exc}",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }


def _parse_validate(result: dict, conn, request_id: int) -> dict:
    if not result.get("ok"):
        return result
    try:
        parsed = parse_response(result["raw_response"])
        # conn=None: skip Gate 7 DB check — all historical rows are 'closed'
        val_result, val_detail = validate(parsed, None, request_id)
        return {**result, "parsed": parsed, "validation_result": val_result,
                "validation_detail": val_detail}
    except ValidationError as exc:
        return {**result, "ok": False, "error": f"parse_error: {exc}",
                "validation_result": "error", "validation_detail": str(exc)}


# ── Disagreement categorisation ────────────────────────────────────────────────
#
# Heuristic only — human review required for definitive classification.
# A: RULE VIOLATION        — gate rejected, or output provably breaks a rule
# B?: VERSION DIVERGENCE   — plausible guide-version explanation
# C: JUDGEMENT NOISE       — both values defensible
# D: INCOHERENT            — parse error, missing required fields, impossible combo

def _normalize_sub(s) -> str | None:
    """Strip old-format 'Oui/Non — ' prefix and template appendix before comparison."""
    if not s:
        return None
    import re as _re
    s = _re.sub(r"^(Oui|Non)\s*[—-]\s*", "", s, flags=_re.IGNORECASE)
    s = _re.sub(r"\s*\n\nENTENTE.*", "", s, flags=_re.DOTALL)
    s = s.strip()
    if s.lower() == "interne":
        return None   # "interne" alone = no external vendor
    return s or None


_ADJACENT = {
    ("complexity_tier", frozenset({"C1", "C2"})),
    ("complexity_tier", frozenset({"C2", "C3"})),
    ("complexity_tier", frozenset({"C3", "C4"})),
    ("congestion_level", frozenset({"N1", "N2"})),
    ("congestion_level", frozenset({"N2", "N3"})),
    ("congestion_level", frozenset({"N3", "N4"})),
    ("congestion_level", frozenset({"N4", "N5"})),
}


def _cat(field: str, new_val, old_val, start_date) -> tuple[str, str]:
    if str(new_val) == str(old_val):
        return "AGREE", ""
    pair = (field, frozenset({str(new_val), str(old_val)}))
    if pair in _ADJACENT:
        return "C", "adjacent tier"
    # report_status: old triage left field blank/NOT_APPLICABLE; new model populates it
    if field == "report_status" and old_val in (None, "NOT_APPLICABLE", "None"):
        return "B?", "new model populated field (old triage left blank)"
    if field == "urgency_tier" and start_date and start_date < _RULE37_DATE:
        return "B?", f"urgency possibly revised in v4.39 (pre {_RULE37_DATE})"
    if start_date and start_date < _RULE25_DATE:
        return "B?", f"predates rule-25 change ({_RULE25_DATE})"
    if field in ("delegable_status", "report_status"):
        return "C", "routing judgment call"
    if field == "subcontractor_name":
        if bool(new_val) != bool(old_val):
            return "C", "subcontractor presence disagrees — review routing"
        return "C", "subcontractor name text differs"
    return "C", "judgment call"


def compare(row: dict, result: dict) -> dict:
    rid = row["request_id"]
    start_date = row.get("start_date")

    if not result.get("ok"):
        return {"request_id": rid, "bucket": "D", "status": "FAILED",
                "error": result.get("error"), "disagreements": []}

    val_result = result.get("validation_result", "")
    if val_result != "accepted":
        return {"request_id": rid, "bucket": "A", "status": "GATE_REJECTED",
                "gate": val_result, "gate_detail": result.get("validation_detail"),
                "raw_response": result.get("raw_response"), "disagreements": []}

    parsed = result["parsed"]
    disags = []
    for field in _COMPARE_FIELDS:
        new_v = parsed.get(field)
        old_v = row.get(field)
        # normalise before comparison to eliminate known format artifacts
        if field == "urgency_tier":
            if new_v: new_v = str(new_v).upper()
            if old_v: old_v = str(old_v).upper()
        elif field == "subcontractor_name":
            new_v = _normalize_sub(new_v)
            old_v = _normalize_sub(old_v)
        new_s = str(new_v) if new_v is not None else None
        old_s = str(old_v) if old_v is not None else None
        if new_s == old_s:
            continue
        bucket, note = _cat(field, new_s, old_s, start_date)
        disags.append({"field": field, "new": new_s, "old": old_s, "bucket": bucket, "note": note})

    if not disags:
        bucket = "AGREE"
    else:
        buckets = {d["bucket"] for d in disags}
        if "A" in buckets:
            bucket = "A"
        elif "D" in buckets:
            bucket = "D"
        elif "B?" in buckets:
            bucket = "B?"
        else:
            bucket = "C"

    return {
        "request_id":      rid,
        "bucket":          bucket,
        "status":          "OK",
        "disagreements":   disags,
        "new_routing":     parsed.get("routing_rule"),
        "new_verdict":     parsed.get("verdict"),
        "new_complexity":  parsed.get("complexity_tier"),
        "new_congestion":  parsed.get("congestion_level"),
    }


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(sample: list[dict], results: list[dict]) -> None:
    n = len(results)
    comparisons = [compare(r, res) for r, res in zip(sample, results)]

    by_bucket: dict[str, list] = {"AGREE": [], "A": [], "B?": [], "C": [], "D": []}
    for c in comparisons:
        b = c["bucket"]
        by_bucket.setdefault(b, []).append(c)

    gate_rejected = [c for c in comparisons if c.get("status") == "GATE_REJECTED"]
    failed = [c for c in comparisons if c.get("status") == "FAILED"]
    agreed = len(by_bucket["AGREE"])

    # Token accounting
    total_input   = sum(r.get("input_tokens") or 0 for r in results)
    total_output  = sum(r.get("output_tokens") or 0 for r in results)
    cache_created = sum(r.get("cache_creation_tokens") or 0 for r in results)
    cache_read    = sum(r.get("cache_read_tokens") or 0 for r in results)
    ok_n = sum(1 for r in results if r.get("ok"))

    # Cost estimate (Sonnet 4.6: $3/MTok input, $3.75/MTok cache-write, $0.30/MTok cache-read, $15/MTok output)
    # cache_read_tokens are NOT included in input_tokens — they are reported separately.
    cost_actual   = _compute_cost(total_input, cache_created, cache_read, total_output)
    # Without caching: cache_read tokens become regular input; no cache_creation premium.
    cost_no_cache = (total_input + cache_read) * _PRICE_INPUT + total_output * _PRICE_OUTPUT
    # Extrapolate to full pool assuming same per-call rate
    if ok_n:
        avg_cc   = cache_created / ok_n
        avg_cr   = cache_read    / ok_n
        avg_inp  = total_input   / ok_n
        avg_out  = total_output  / ok_n
        cost_per_call = _compute_cost(avg_inp, avg_cc, avg_cr, avg_out)
        extrap_full   = cost_per_call * 1392
    else:
        cost_per_call = extrap_full = 0

    print("\n" + "=" * 62)
    print("BACKTEST RESULTS")
    print("=" * 62)
    print(f"Requests run:           {n}")
    print(f"API successful:         {ok_n}")
    print(f"Agreement:              {agreed}/{n}  ({agreed/n*100:.0f}%)")
    print()
    print(f"  A  RULE VIOLATION:    {len(by_bucket['A'])}   ← must be 0 to go-live")
    print(f"  D  INCOHERENT:        {len(by_bucket['D'])}   ← must be 0 to go-live")
    print(f"  B? VERSION DIVERGENCE:{len(by_bucket['B?'])}   (expected; cite rule)")
    print(f"  C  JUDGEMENT NOISE:   {len(by_bucket['C'])}   ({len(by_bucket['C'])/n*100:.0f}% of sample)")
    print(f"  Gate rejected:        {len(gate_rejected)}")
    print(f"  Failed (API/parse):   {len(failed)}")

    print("\n── Token & cost summary ──")
    print(f"  Total input tokens:          {total_input:>9,}")
    print(f"    of which cache_created:    {cache_created:>9,}")
    print(f"    of which cache_read:       {cache_read:>9,}")
    print(f"  Total output tokens:         {total_output:>9,}")
    print(f"  Avg input per call:          {total_input//max(1,ok_n):>9,}")
    print(f"  Avg output per call:         {total_output//max(1,ok_n):>9,}")
    print(f"  Cost this run (with cache):  ${cost_actual:>8.4f}")
    print(f"  Cost without caching:        ${cost_no_cache:>8.4f}  (savings: ${cost_no_cache-cost_actual:.4f})")
    print(f"  Extrap. cost for 1,392:      ${extrap_full:>8.2f}")

    if gate_rejected:
        print("\n── Gate rejections (each individually) ──")
        for c in gate_rejected:
            rid = c["request_id"]
            row = next(r for r in sample if r["request_id"] == rid)
            print(f"  #{rid}  stream={row.get('stream')}  date={row.get('start_date')}  fmt={row.get('body_format')}")
            print(f"    gate:   {c['gate']}")
            print(f"    detail: {c.get('gate_detail')}")
            raw = c.get("raw_response", "") or ""
            print(f"    raw (first 300):\n      {raw[:300]!r}")
            print()

    for bucket, label in [("A", "RULE VIOLATION"), ("D", "INCOHERENT"), ("B?", "VERSION DIVERGENCE"), ("C", "JUDGEMENT NOISE")]:
        items = by_bucket.get(bucket, [])
        if not items:
            continue
        print(f"\n── {bucket}: {label} ({len(items)} requests) ──")
        for c in items:
            rid = c["request_id"]
            row = next(r for r in sample if r["request_id"] == rid)
            print(f"  #{rid}  stream={row.get('stream')}  date={row.get('start_date')}  fmt={row.get('body_format')}")
            for d in c.get("disagreements", []):
                print(f"    {d['field']:30s}  old={d['old']!r:20}  →  new={d['new']!r:20}  [{d['note']}]")

    print("\n── Per-request summary ──")
    header = f"{'ID':>8}  {'fmt':18}  {'stream':14}  {'era':8}  {'bkt':5}  {'#d':3}  {'routing':7}  {'verdict':10}"
    print(header)
    print("-" * len(header))
    for row, result, cmp in zip(sample, results, comparisons):
        rid = row["request_id"]
        d = row.get("start_date")
        if d and d < _RULE25_DATE:
            era = "pre-R25"
        elif d and d < _RULE37_DATE:
            era = "mid"
        else:
            era = "post-R37"
        ok = "✓" if cmp["status"] == "OK" else ("✗G" if cmp["status"] == "GATE_REJECTED" else "✗F")
        print(f"  {ok}{rid:>6}  {(row.get('body_format') or '?')[:17]:18}  "
              f"{(row.get('stream') or '?')[:13]:14}  {era:8}  "
              f"{cmp['bucket']:5}  {len(cmp.get('disagreements',[])): 3}  "
              f"{(cmp.get('new_routing') or '?')[:7]:7}  "
              f"{(cmp.get('new_verdict') or '?')[:10]:10}")


# ── Cost log ───────────────────────────────────────────────────────────────────

def _append_cost_log(
    run_label: str,
    calls_ok: int,
    inp: int,
    cc: int,
    cr: int,
    out: int,
    prompt_version: str,
    notes: str = "",
) -> None:
    """Append one row to docs/api-cost-log.md (creates the file if absent)."""
    cost = _compute_cost(inp, cc, cr, out)
    per_call = cost / calls_ok if calls_ok else 0
    assert cost > 0, f"Cost formula produced non-positive value ${cost:.4f} — formula bug (negative = cache_read subtracted from input)"
    assert 0.001 <= per_call <= 1.00, f"Per-call cost ${per_call:.4f} outside plausible $0.001–$1.00 band — check token counts"
    today = date.today().isoformat()
    row = (
        f"| {today} | {run_label} | {calls_ok:,} | {inp:,} | {cc:,} | {cr:,} | {out:,} "
        f"| ${cost:.4f} | {prompt_version} | {notes} |"
    )
    if not _COST_LOG.exists():
        _COST_LOG.write_text(
            "# API Cost Log\n\n"
            "Auto-appended by backtest.py after each run.\n"
            "Pricing: Sonnet 4.6 — $3/MTok input, $3.75/MTok cache-write, $0.30/MTok cache-read, $15/MTok output.\n\n"
            "| Date | Run | Calls OK | Input tok | Cache write | Cache read | Output tok | Cost | Prompt version | Notes |\n"
            "|------|-----|----------|-----------|-------------|------------|------------|------|----------------|-------|\n",
            encoding="utf-8",
        )
    with open(_COST_LOG, "a", encoding="utf-8") as f:
        f.write(row + "\n")
    print(f"Cost log updated → {_COST_LOG}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    sample_only = "--sample-only" in sys.argv
    rerun       = "--rerun"       in sys.argv
    full_run    = "--full"        in sys.argv

    conn = psycopg2.connect(
        host=os.environ["SUPABASE_HOST"], port=5432,
        user=f"postgres.{os.environ['SUPABASE_PROJECT_REF']}",
        password=os.environ["DATABASE_PASSWORD"],
        dbname="postgres", sslmode="require",
    )

    done_ids: set[int] = set()
    out_path = _FULL_OUT if full_run else (_RERUN_OUT if rerun else _OUT)

    if rerun:
        print("Loading previous sample IDs…")
        with open(_SAMPLE_IDS) as f:
            saved_ids = json.load(f)
        with conn.cursor() as cur:
            sample = _fetch_by_ids(cur, saved_ids)
        print(f"Replaying {len(sample)} requests from previous run.")
    elif full_run:
        print("Fetching full eligible pool…")
        with conn.cursor() as cur:
            sample = _fetch_pool(cur)
        pool_total = len(sample)
        print(f"Full pool: {pool_total} requests.")
        done_ids = _load_done_ids(out_path)
        if done_ids:
            before = len(sample)
            sample = [r for r in sample if r["request_id"] not in done_ids]
            print(f"Resuming: {before - len(sample)} already processed, {len(sample)} remaining.")
    else:
        print("Selecting stratified sample…")
        sample = select_sample(conn)
        with open(_SAMPLE_IDS, "w") as f:
            json.dump([r["request_id"] for r in sample], f)

    print_composition(sample)

    if sample_only:
        print("\n--sample-only: stopping. Rerun without flag to fire API calls.")
        conn.close()
        return

    api_key = os.environ["ANTHROPIC_API_KEY"]
    # Only send workspace header for org-scoped keys (sk-ant-api03-).
    # User keys and direct account keys work without it.
    extra_headers = {}
    if api_key.startswith("sk-ant-api03-"):
        wid = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
        if wid:
            extra_headers["anthropic-workspace-id"] = wid
    client  = anthropic.Anthropic(api_key=api_key, default_headers=extra_headers)
    sys_blk = build_system_prompt()
    mv      = f"{_MODEL}|docs-{DOCUMENTS_HASH[:8]}"

    # Resume: append if we skipped already-done rows, otherwise overwrite.
    resuming = full_run and bool(done_ids)
    file_mode = "a" if resuming else "w"
    if resuming:
        print(f"Appending to {out_path}")
    print(f"\nRunning {len(sample)} API calls (model={_MODEL}). Ctrl-C to abort.\n")

    results: list[dict] = []
    n_total = len(sample)
    w = len(str(n_total))
    with open(out_path, file_mode, encoding="utf-8") as f:
        for i, row in enumerate(sample, 1):
            rid = row["request_id"]
            sys.stdout.write(f"  [{i:{w}d}/{n_total}] #{rid:<6} ")
            sys.stdout.flush()

            try:
                ctx = assemble(conn, rid)
                user_msg = _format_context(ctx)
            except Exception as exc:
                print(f"ctx_err: {exc}")
                r = {"ok": False, "error": f"context_error: {exc}", "latency_ms": 0}
                results.append(r)
                f.write(json.dumps({"request_id": rid, "context_error": str(exc)}) + "\n")
                continue

            r = _run_one(client, ctx, sys_blk, user_msg, _MODEL)
            r = _parse_validate(r, conn, rid)
            results.append(r)

            vr = r.get("validation_result") or r.get("error") or "?"
            cache_hit = bool(r.get("cache_read_tokens"))
            mark = "✓" if vr == "accepted" else f"✗ {vr}"
            print(f"{r.get('latency_ms',0):5d}ms  {'[cached]' if cache_hit else '[cold]  '}  {mark}")

            record = {
                "request_id":    rid,
                "prompt_version": mv,
                "body_format":   row.get("body_format"),
                "stream":        row.get("stream"),
                "start_date":    str(row.get("start_date")) if row.get("start_date") else None,
                "stored": {f: str(row.get(f)) if row.get(f) is not None else None for f in _COMPARE_FIELDS},
                "result":        {k: v for k, v in r.items() if k not in ("parsed",)},
                "parsed":        r.get("parsed"),
            }
            f.write(json.dumps(record, default=str) + "\n")

    print(f"\nRaw results → {out_path}")
    if full_run and resuming:
        # After a resumed full run, report across the entire JSONL (all sessions combined).
        _report_from_jsonl(out_path)
    else:
        print_report(sample, results)

    # Write cost row — aggregate tokens from successful results only.
    _ok = [r for r in results if r.get("ok")]
    if _ok:
        _inp = sum(r.get("input_tokens") or 0 for r in _ok)
        _cc  = sum(r.get("cache_creation_tokens") or 0 for r in _ok)
        _cr  = sum(r.get("cache_read_tokens") or 0 for r in _ok)
        _out = sum(r.get("output_tokens") or 0 for r in _ok)
        _label = "50-rerun" if rerun else ("full-1392" if full_run else "50-sample")
        _append_cost_log(_label, len(_ok), _inp, _cc, _cr, _out, mv)

    conn.close()


if __name__ == "__main__":
    main()
