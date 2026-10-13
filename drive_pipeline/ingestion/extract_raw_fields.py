"""
extract_raw_fields.py — Parse raw triage text columns into structured enum/text fields.

Handles (one pass, one dry run, one write):
  complexite_raw   → complexity_tier   (C1–C4; range → higher tier)
  embourbement_raw → congestion_level  (N1–N5)
  delegable_raw    → delegable_status  (YES/NO/CONDITIONAL)
  time_estimate_raw→ time_estimate_bucket (6 buckets; null for multi-item)
  report_raw       → report_status     (option b: NON+AJD → NOT_APPLICABLE)
  animals          → animals (normalize; split \n\n, take second part)
  entry_permission → entry_permission (map to 4 SKILL.md canonical values)

All five derived columns get full data_provenance rows (source_type='derived').
In-place normalizations (animals, entry_permission) get provenance rows only
where the written value differs from the stored value (source_type='normalized').

Run:
    uv run python -m drive_pipeline.ingestion.extract_raw_fields          # dry run
    uv run python -m drive_pipeline.ingestion.extract_raw_fields --write
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from psycopg2.extras import execute_values
from drive_pipeline.ingestion.db import get_conn

# ── Canonical SKILL.md entry_permission values ────────────────────────────────
_EP_AUTHORIZED     = "Autorisé en tout temps sans restriction"
_EP_TENANT_PRESENT = "Présence du locataire exigée"
_EP_VACANT         = "Logement vacant — accès libre"
_EP_COMMON         = "Espace commun — aucune coordination locataire requise"

# Source file label used in provenance
_THIS_FILE = "extract_raw_fields.py"


# ── Extraction functions (imported by write_maintenance_requests.py too) ──────

def _complexity(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    # Range C1-C2, C2-C3, C2-C4 → take the HIGHER tier
    m = re.match(r"^C([0-9])-C([0-9])", s)
    if m:
        return f"C{max(int(m.group(1)), int(m.group(2)))}"
    # C0 is not in the enum — null it rather than failing the cast
    m = re.match(r"^(C[1-4])", s)
    return m.group(1) if m else None


def _congestion(raw: str | None) -> str | None:
    if not raw:
        return None
    m = re.match(r"^(N[1-5])", raw.strip())
    return m.group(1) if m else None


def _delegable(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if re.match(r"^Partiell|^Partiel\b|^Possiblem", s, re.I):
        return "CONDITIONAL"
    if re.match(r"^OUI\b|^Oui\b", s):
        return "YES"
    if re.match(r"^NON\b|^Non\b", s):
        return "NO"
    return None  # N/A, doublon, S.O., À évaluer, multi-item → null


_TIME_RULES = [
    # 30min–1h BEFORE plain <30min (avoids "30 min-1h" matching <30 branch)
    ("MIN30_TO_1H",   r"30\s*min\s*[-–]\s*1\s*h|30\s*min[-–]1h|30min.*1\s*h|30\s*[-–]\s*60\s*min"),
    ("UNDER_30_MIN",  r"<\s*15|^15\s*min\b|15\s*[-–]\s*30|<\s*30|moins.*30\s*min|^30\s*min$|^5\s*min$|moins de 15"),
    ("H1_TO_2H",      r"1\s*h\s*[-–à]\s*2\s*h|1\s*[-–]\s*2\s*h|1h\s*-\s*2h|1-2\s*h|1\s*h\s*30"),
    ("H2_TO_4H",      r"2\s*h\s*[-–à]\s*[34]\s*h|2\s*[-–]\s*[34]\s*h|[23]\s*-\s*[34]\s*h"),
    ("HALF_DAY_PLUS", r"demi.?journ|half.?day|journ[eé]e?\b"),
    ("TBD_ON_SITE",   r"soumission\s*requise"),
]


def _time_bucket(raw: str | None) -> str | None:
    if not raw:
        return None
    r = raw.strip().lower()
    for bucket, pattern in _TIME_RULES:
        if re.search(pattern, r):
            return bucket
    return None  # multi-item or unrecognized → null per spec


def _report_status(raw: str | None) -> str | None:
    """Option (b): NON+AJD → NOT_APPLICABLE (report_status is about reporting, not urgency)."""
    if not raw:
        return None
    s = raw.strip()
    if re.search(r"discr[eé]tion", s, re.I):
        return "SUPERVISOR_DISCRETION"
    if re.match(r"^OUI\b|^Oui\b", s):
        return "CANNOT_WAIT"
    upper = s.upper()
    if re.match(r"^N/A|^S\.O\.|^SO\b", upper):
        return "NOT_APPLICABLE"
    if re.match(r"^Non\s+reportable|^NON\s+reportable", s, re.I):
        return "NOT_APPLICABLE"
    # NON and Aucun — both unqualified and AJD-qualified → NOT_APPLICABLE (option b)
    if re.match(r"^(Non|NON|Aucun)\b", s):
        return "NOT_APPLICABLE"
    if re.search(r"\bà court terme\b|^Acceptable\b", s, re.I):
        return "CAN_WAIT_SHORT_TERM"
    if re.search(r"planif|avant.*emm|avant.*départ|délai.fix|à faire avant", s, re.I):
        return "CAN_WAIT_SHORT_TERM"
    if re.search(r"non urgent|pas urgent|sans urgence", s, re.I):
        return "CAN_WAIT"
    return None


_PETS_RE = re.compile(
    r"^(Non|N/A|Oui|[-—])\b"
    r"|chat|chien|lapin|furet|oiseau|animaux|chaton|chienne|chiens|chats|chatte",
    re.I,
)


def _looks_like_pets(val: str) -> bool:
    return bool(_PETS_RE.search(val))


def _normalize_animals(raw: str | None) -> str | None:
    if not raw:
        return None
    # Split on \n\n (two-source format): take first line of second part
    # (problem text or ticket body is sometimes appended after the canonical answer)
    if "\n\n" in raw:
        second = raw.split("\n\n", 1)[1].strip()
        val = second.split("\n", 1)[0].strip() if second else raw.split("\n", 1)[0].strip()
    elif "\n" in raw:
        # Single-\n rows (no \n\n): first line is the original form answer
        val = raw.split("\n", 1)[0].strip()
    else:
        val = raw.strip()

    # Reject occupant headers, caller blocks, date stamps, and unrelated prose
    if not _looks_like_pets(val):
        return None

    # Normalize case/N/A variants
    lower = val.lower()
    if lower in ("non", "non.", "aucun"):
        return "Non"
    if lower in ("na", "n/a", "n/a — espace commun", "n/a — espace commun.", "-"):
        return "N/A"
    if lower == "noa":
        return "N/A"
    # Trailing period on short Non variants
    if re.match(r"^non\s*\(", val, re.I) and val.endswith("."):
        return val[:-1]
    return val


def _entry_permission(raw: str | None) -> str | None:
    """Map raw text to one of the 4 SKILL.md canonical values.
    Rule: ignore '(traitement prioritaire)' annotation entirely.
    6 known unmapped rows → null (per task decision).
    """
    if not raw:
        return None
    s = re.sub(r"\s*\(traitement prioritaire\)\.?", "", raw.strip(), flags=re.I).strip()

    # Vacant unit (check before authorized — vacant implies access too)
    if re.search(r"logement vacant|accès libre|logement.*(vide|à vider|quitter)", s, re.I):
        return _EP_VACANT
    # Common area / N/A variants
    if re.search(r"espace commun|commun\b|N/A|non applicable", s, re.I):
        return _EP_COMMON
    # Tenant presence required
    if re.search(r"présence.*(locataire|requise|exig)|locataire.*(présence|requis|exig)", s, re.I):
        return _EP_TENANT_PRESENT
    # Authorized (any form)
    if re.search(r"autoris|accès autoris", s, re.I):
        return _EP_AUTHORIZED
    return None


# ── Dry-run analysis ──────────────────────────────────────────────────────────

def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT request_id,
               complexite_raw, embourbement_raw, delegable_raw, time_estimate_raw,
               report_raw, animals, entry_permission
        FROM maintenance_request
    """)
    rows = cur.fetchall()

    results: dict[int, dict] = {}
    for (rid, c_raw, e_raw, d_raw, t_raw, r_raw, a_raw, ep_raw) in rows:
        results[rid] = {
            "complexity_tier":      _complexity(c_raw),
            "congestion_level":     _congestion(e_raw),
            "delegable_status":     _delegable(d_raw),
            "time_estimate_bucket": _time_bucket(t_raw),
            "report_status":        _report_status(r_raw),
            "animals":              _normalize_animals(a_raw),
            "entry_permission":     _entry_permission(ep_raw),
            # Keep raw values for provenance
            "_c_raw": c_raw, "_e_raw": e_raw, "_d_raw": d_raw,
            "_t_raw": t_raw, "_r_raw": r_raw,
            "_a_raw": a_raw, "_ep_raw": ep_raw,
        }

    total = len(rows)
    _print_report(rows, results, total)

    if dry_run:
        print(f"\nDRY RUN — pass --write to commit.")
        conn.close()
        return

    # ── Write ─────────────────────────────────────────────────────────────────
    cur.execute("SELECT MAX(provenance_id) FROM data_provenance")
    prov_id = cur.fetchone()[0] or 0

    # Fetch currently stored animals/entry_permission to detect changes
    cur.execute("SELECT request_id, animals, entry_permission FROM maintenance_request")
    stored = {r[0]: {"animals": r[1], "entry_permission": r[2]} for r in cur.fetchall()}

    update_rows = []
    prov_rows: list[tuple] = []

    for rid, vals in results.items():
        update_rows.append((
            vals["complexity_tier"],
            vals["congestion_level"],
            vals["delegable_status"],
            vals["time_estimate_bucket"],
            vals["report_status"],
            vals["animals"],
            vals["entry_permission"],
            rid,
        ))

        # Provenance — 5 derived columns (write when non-null)
        for db_col, raw_col, raw_val in (
            ("complexity_tier",      "complexite_raw",   vals["_c_raw"]),
            ("congestion_level",     "embourbement_raw", vals["_e_raw"]),
            ("delegable_status",     "delegable_raw",    vals["_d_raw"]),
            ("time_estimate_bucket", "time_estimate_raw",vals["_t_raw"]),
            ("report_status",        "report_raw",       vals["_r_raw"]),
        ):
            derived = vals[db_col]
            if derived is None:
                continue
            prov_id += 1
            prov_rows.append((
                prov_id, "maintenance_request", rid, db_col,
                "derived", None, _THIS_FILE, None,
                None, raw_col,
                str(raw_val)[:1000] if raw_val else None,
                str(derived),
            ))

        # Provenance — in-place normalizations (only where value actually changes)
        for db_col, raw_col, old_val, new_val in (
            ("animals",          "animals",          stored[rid]["animals"],          vals["animals"]),
            ("entry_permission", "entry_permission", stored[rid]["entry_permission"], vals["entry_permission"]),
        ):
            if new_val is None:
                continue
            if old_val == new_val:
                continue  # unchanged — existing provenance row is accurate
            prov_id += 1
            prov_rows.append((
                prov_id, "maintenance_request", rid, db_col,
                "normalized", None, _THIS_FILE, None,
                None, raw_col,
                str(old_val)[:1000] if old_val else None,
                str(new_val),
            ))

    print(f"\nWriting {len(update_rows)} row updates...")
    try:
        execute_values(
            cur,
            """UPDATE maintenance_request AS mr SET
                complexity_tier      = d.complexity_tier::complexity_tier,
                congestion_level     = d.congestion_level::congestion_level,
                delegable_status     = d.delegable_status::delegable_status,
                time_estimate_bucket = d.time_estimate_bucket::time_estimate_bucket,
                report_status        = d.report_status::report_status,
                animals              = d.animals,
                entry_permission     = d.entry_permission
               FROM (VALUES %s) AS d(
                complexity_tier, congestion_level, delegable_status,
                time_estimate_bucket, report_status, animals, entry_permission, request_id
               )
               WHERE mr.request_id = d.request_id::int""",
            update_rows,
            template="(%s, %s, %s, %s, %s, %s, %s, %s)",
            page_size=500,
        )
        conn.commit()
        print(f"  Row updates committed.")

        print(f"Writing {len(prov_rows)} provenance rows...")
        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s ON CONFLICT DO NOTHING""",
            prov_rows,
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            page_size=500,
        )
        conn.commit()
        print(f"  Provenance committed.")

        # Final counts
        print("\nPost-write counts:")
        for col in ("complexity_tier", "congestion_level", "delegable_status",
                    "time_estimate_bucket", "report_status", "animals", "entry_permission"):
            cur.execute(f"SELECT COUNT(*) FROM maintenance_request WHERE {col} IS NOT NULL")
            print(f"  {col}: {cur.fetchone()[0]}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _print_report(rows, results, total):
    from collections import Counter

    print("\n=== TASK 1 — complexity_tier ===")
    _report_col(results, "complexity_tier", total)
    _show_nulled_raw(rows, results, "complexity_tier", 1)

    print("\n=== TASK 1 — congestion_level ===")
    _report_col(results, "congestion_level", total)
    _show_nulled_raw(rows, results, "congestion_level", 2)

    print("\n=== TASK 1 — delegable_status ===")
    _report_col(results, "delegable_status", total)
    _show_nulled_raw(rows, results, "delegable_status", 3)

    print("\n=== TASK 1 — time_estimate_bucket ===")
    _report_col(results, "time_estimate_bucket", total)
    _show_nulled_raw(rows, results, "time_estimate_bucket", 4)

    print("\n=== report_status ===")
    _report_col(results, "report_status", total)
    _show_nulled_raw(rows, results, "report_status", 5)

    print("\n=== TASK 2 — animals (normalized) ===")
    _report_col(results, "animals", total)

    print("\n=== TASK 3 — entry_permission (normalized) ===")
    _report_col(results, "entry_permission", total)
    unmapped = [(r[7], r[0]) for r in rows if results[r[0]]["entry_permission"] is None and r[7]]
    if unmapped:
        print(f"  Unmapped ({len(unmapped)} rows):")
        for ep, rid in unmapped[:10]:
            print(f"    req={rid}: {repr(str(ep)[:90])}")


def _report_col(results, field, total):
    from collections import Counter
    counts = Counter(v[field] for v in results.values())
    populated = sum(n for k, n in counts.items() if k is not None)
    print(f"  Populated: {populated}/{total} ({100*populated/total:.1f}%)")
    for val, n in sorted(((k,v) for k,v in counts.items() if k is not None), key=lambda x: -x[1]):
        print(f"    {n:5d}  {val!r}")


def _show_nulled_raw(rows, results, field, col_idx, limit=8):
    from collections import Counter
    nulled = Counter()
    for row in rows:
        rid = row[0]
        raw = row[col_idx]
        if results[rid][field] is None and raw:
            nulled[str(raw).strip()[:80]] += 1
    if nulled:
        print(f"  Top raw→null ({len(nulled)} distinct):")
        for val, n in nulled.most_common(limit):
            print(f"    {n:4d}  {val!r}")


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
