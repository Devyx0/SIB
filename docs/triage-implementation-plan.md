# AI Triage Service — Implementation Plan

_SoW Milestone 1, feature 3.3 (39h quoted). Synchronous triage on intake._
_Built against Triage Skill v6.1 + Coordinator Guide v4.39._

---

## 1. Architecture decision: static rules, deterministic context

**Not RAG.** The reasoning matters because it shapes everything below.

Every cardinal rule applies to every request. Rule 20 (never assign) is not relevant only when a request mentions assignment — it is relevant always. Rule 11 (no access codes) applies even when the request says nothing about keys. Semantic retrieval fetches what *looks* relevant to the request text, which is precisely wrong for safeguards: they govern what must *not* happen, and the request never mentions those things.

The rules are also small enough not to need retrieval — both documents together are roughly 50K tokens, a quarter of the 200K context window.

```
SYSTEM PROMPT — static, byte-identical on every call
├── Triage Skill v6.1 (full)
├── Coordinator Guide v4.39 (full)
└── Output contract (JSON schema, §4 below)
    ~50K tokens · prompt-cached · ~90% cost reduction after first call

USER MESSAGE — assembled per request from our own database
├── The request (intake fields)
├── Unit / lease / tenant context          ← SQL
├── Building / project / sector context    ← SQL
├── Technical sheet link                   ← SQL
├── Duplicate candidates                   ← SQL, −90d → +45d
├── Synergy candidates                     ← SQL, −60d → +21d, stream-scoped
└── Unit history                           ← SQL, −6mo → +21d
    a few K tokens
```

Every lookup the skill performs is a bounded query the guide specifies exactly. Those are `WHERE` clauses, not similarity search.

**Where model judgement is genuinely required:** deciding whether a candidate *is* a duplicate. The guide says compare "the nature of the problem, not just the address" — same problem however worded. Retrieval of candidates is deterministic; the comparison is the model's job.

**Properties this buys:** reproducible (same request + same DB state → same context), auditable (we can log exactly what the model saw), cheap (caching beats an embedding index), and no safeguard can silently fail to be retrieved.

---

## 2. Context builder — the SQL layer

One function per block. All windows anchored on the **request's own date**, never `now()` (guide §4.1).

| Block | Query | Window |
|---|---|---|
| Unit context | `unit` → `lease` → `tenancy_record` → `tenant` | current |
| Building context | `building` → `project` → `sector` | — |
| Technical sheet | `building.raw_fiche_technique` / FT link | — |
| Duplicates | `maintenance_request` same `unit_id` | −90d → +45d |
| Synergy | `maintenance_request` same `project_id`, stream-filtered | −60d → +21d |
| History | `maintenance_request` same `unit_id` | −6mo → +21d |

### Mechanical exclusions, applied in SQL before the model sees anything

Guide §4.2 — discard without examining:

- recurring-series events (winter shelters, fire inspection, mats, compressors, batteries, window washing)
- waste-collection
- administrative (`!` prefix) and building lists
- the request being triaged

### Stream scoping on synergy — not optional

Guide rule 13. A naive "same project, same window" query groups things coordinators deliberately keep apart:

```sql
-- internal call → internal only, subcontractors excluded
WHERE vendor_id IS NULL AND subcontractor_name NOT ILIKE 'Oui%'

-- subcontractor call → same subcontractor only
WHERE vendor_id = :this_vendor_id

-- pest control → pest files only, same building then project,
--   including future events and warranty-active ones
WHERE category = 'extermination'
```

### RRIA equivalence

The skill reads an external AI-maintained rent roll. **We don't need it** — `tenant`, `lease` and `tenancy_record` hold the same facts, sourced from the same Master Rent Roll. The guide's "mandatory RRIA check" (rule 21) becomes: unit context must resolve before triage proceeds. If it doesn't, that is a blocking condition, same as today.

### Occupant inference — stated assumption

`tenancy_record.start_date` and `tenancy_record.end_date` are NULL on all MRR-backfilled rows (5,558 of 5,616 total). "Current occupants as of the request date" is therefore derived from `lease.debut_bail` and `lease.fin_bail`, not from tenancy period dates.

**Consequence:** a unit where the lease continued through a cession, a roommate addition, or a partial changeover will return whoever is named on the current lease, which may not match who actually lives there today. This is acceptable for triage — coordinators need a name and phone to call, and the lease tenant is the correct starting point. It mirrors what coordinators see in the existing RRIA check today.

The 58 tenancy_record rows that DO have real partial dates (52 with `start_date` from recent arrivals, 6 with `end_date` from departures, sourced from the unit_turnover backfill) are **not** preferred over the lease-derived path. Mixing them would create a two-track system where 1% of queries use actual tenancy dates and 99% use lease approximations — the inconsistency is worse than the uniformity.

### Synergy scope narrowing

A fixed cap truncates silently, which the guide explicitly forbids — a call already assigned with a firm date must appear in the synergy list because it is the best grouping opportunity. Instead:

1. Query at **project scope** — if result ≤ `_SYNERGY_THRESHOLD` (100), return it.
2. If project exceeds threshold, re-query at **building scope** — if ≤ threshold, return it with a `narrowed_from` note.
3. If building scope also exceeds threshold, return `scope='saturated'`, empty items, and the exact count — the model knows the stream is large, not absent.

Threshold of 100 is calibrated to our data: at 300 tokens/candidate, 100 synergy items ≈ 30K tokens for that block alone, leaving ample room in the 200K context window. In practice, 87% of projects in our corpus have < 100 tickets in any 81-day window; the remaining 13% are our busiest multi-building projects where narrowing or saturation reporting correctly signals density.

---

## 3. Synchronous execution and failure handling

The request must never be lost because a model call failed. Intake and triage are separated by a status, not by a transaction.

```
POST /maintenance-request
    ↓
INSERT maintenance_request (status='intake_received')   ← COMMITTED
    ↓                                                      request is safe
    ├── 201 returned to the user immediately
    ↓
Triage invoked
    ↓
  ┌─ success ──→ status='triaged', fields written, provenance logged
  ├─ timeout ──→ status='triage_pending', queued for retry
  ├─ API error → status='triage_pending', queued for retry
  └─ 3 failed retries → status='triage_failed', surfaced on the
                        coordinator's board for manual handling
```

Three points worth being explicit about:

1. **The insert commits before triage runs.** A failed triage leaves an untriaged request, which is exactly today's "green event" state — a known, handled condition, not data loss.
2. **The user is not held waiting on the model.** Return on insert; triage completes asynchronously-but-immediately. "Synchronous" here means *triggered on submission*, not *blocking the response*.
3. **`triage_failed` is visible, not silent.** It appears on the dispatch board as needing attention — the guide's own "zero backlog" principle applied.

### Concurrency — the `[EN TRAITEMENT]` lock

Guide §3: one request processed at a time, with an abandoned-lock sweep each run. In the app:

- `SELECT ... FOR UPDATE SKIP LOCKED` on the request row
- a `triage_started_at` timestamp; anything older than N minutes is swept and retried
- not a global lock — per-request, so throughput isn't capped at one

---

## 4. Output contract

The model returns JSON, validated before any write. Nothing is written from free text.

```json
{
  "verdict": "single | duplicate | addition",
  "duplicate_of_request_id": null,
  "addition_to_request_id": null,
  "title": "...",
  "problems": ["..."],
  "entry_permission": "...",
  "animals": "...",
  "urgency_tier": "AJD | null",
  "complexity_tier": "C1|C2|C3|C4",
  "congestion_level": "N1|N2|N3|N4|N5",
  "time_estimate_bucket": "...",
  "delegable_status": "YES|NO|CONDITIONAL",
  "report_status": "...",
  "routing_rule": "A0|A1|A2|A3|A3b|A4|A5",
  "subcontractor_name": "...",
  "vendor_id": null,
  "synergy_request_ids": [],
  "other_notes": "..."
}
```

### Validation gates — reject the response, don't sanitise it

| Gate | Rule |
|---|---|
| No assignee field exists in the schema at all | 20 / 37 |
| `problems` contains no currency amounts | 9 |
| No financial terms (rent, deposit, arrears, guarantor) | 10 |
| No access-code patterns (lockbox, code, key location) | 11 |
| No internal vocabulary (`A1`–`A5`, rule numbers, skill names) in any text field | 7 |
| `routing_rule` consistent with `subcontractor_name` (A2→Body Gym, A3→Duclos) | 6b |
| If `verdict='addition'`, `addition_to_request_id` must reference a non-resolved request | 12 |

A failed gate means the response is rejected and retried, then escalated to `triage_failed`. We do not strip offending content and write the remainder — a response that violated a safeguard is not trustworthy in its other fields either.

### Gate 4 (access-code detection) — development history

The gate evolved through four iterations before stabilising. The 24-case self-test in `output_contract.py` covers all four and prevents regression.

| Iteration | Change | Problem solved |
|---|---|---|
| 1. Bare regex `\b\d{4,8}\b` | — | 48/50 false positives in first backtest: civic addresses (2160, 3485), years (2026), request IDs all matched |
| 2. Proximity | Digit only fires when an access-context term (code, clavier, NIP, combinaison, cadenas, keybox, lockbox, serrure, digicode, boîte à clé) appears within ±40 chars | Dropped false-positive count to 3 |
| 3. Year exclusion | Skip `\b(19|20)\d{2}\b` before proximity check | Eliminates dates like "serrure à vérifier avant 2026-09-15" |
| 4. Civic address exclusion | Skip a digit sequence immediately followed by `-\d{1,4}` (e.g. "3485-103") | Eliminates unit addresses that appear near "serrure" in model notes, e.g. "serrure principale 3485-103 — historique" |
| 5. Request ID exclusion | Skip a digit sequence immediately preceded by `#` | Eliminates request references like `#7722 (boîte à clés, réglé)` — model correctly cross-references history, gate must not fire on the ticket number |
| 6. French preposition exclusion | Skip a digit sequence immediately preceded (within 4 chars) by `\b(du\|au\|de)\s+` | French prepositions introducing building addresses: "keybox 2 du 3094 Châtelets", "serrure au 5875 Costebelle" — "du/au NNNN" is never an access code |

Run `uv run python3 -m drive_pipeline.triage.output_contract` before any gate change. 34 self-tests.

### Prompt authoring constraint — never name the forbidden token

In backtest run 5, the output contract contained:

> "routing_rule = 'A3b' ALWAYS requires a non-null subcontractor_name."

This caused the model to write `(A3b, interne)` in `other_notes` for an unrelated pest request — it learned "A3b" was salient vocabulary and used it in text. Gate 5 (internal vocabulary) correctly rejected it. Fix: rewrite as:

> "When routing a door or window problem to a specialist for unknown-cause diagnosis, always name the specialist in subcontractor_name."

**Rule for all future prompt edits:** any instruction about what NOT to appear in text must describe the *condition* triggering the rule, never name the forbidden token. Naming it teaches the model to produce it.

This applies to all internal vocabulary: routing codes, rule numbers, skill names, section headers. "Never write A3b in text fields" is self-defeating — the model now knows A3b belongs in text-adjacent contexts and will use it. Describe the work, not the code.

---

## 5. Schema additions required

| Column / table | Purpose |
|---|---|
| `maintenance_request.status` | intake_received / triage_pending / triaged / triage_failed / en_route / closed |
| `maintenance_request.addition_to_request_id` | The ADDITION relation — currently only `duplicate_of_request_id` exists |
| `maintenance_request.routing_rule` | A0–A5 classification; today the category that produced the routing is never stored |
| `maintenance_request.triage_started_at` | Lock sweep |
| `maintenance_request.triage_model_version` | Which skill/guide version produced this triage — the rules change weekly |
| `triage_log` (new) | Full request/response per call: context sent, raw response, validation result, latency, token counts |

`triage_log` is worth its own table rather than reusing `data_provenance`. Provenance records *where a value came from*; this records *what the model was asked and what it said*, including rejected responses. Different purpose, different retention.

---

## 6. Build sequence

| Step | Depends on | Notes |
|---|---|---|
| 1. Schema additions (§5) | — | Smallest, unblocks everything |
| 2. Context builder (§2) | 1 | Testable standalone against the 10,565 existing rows |
| 3. System prompt assembly + caching | — | Parallel with 2 |
| 4. Output contract + validation gates (§4) | 1 | Gates are testable without the model |
| 5. Triage service + status machine (§3) | 2, 3, 4 | |
| 6. Backtest | 5 | See below |

### Backtest pool — 1,392 rows

The eligible pool is `maintenance_request` rows where:

```sql
complexity_tier IS NOT NULL
AND status = 'closed'
AND start_date IS NOT NULL
AND unit_id IS NOT NULL
```

This yields **1,392 rows**. The 1,956 figure that appeared in earlier versions of this document is the raw `complexity_tier IS NOT NULL` count. All 1,956 are already closed, so `status = 'closed'` is a guard against future rows, not a filter. The 564 excluded rows are closed administrative requests with null `start_date` or `unit_id` — triage cannot run on them because unit context is a blocking requirement (guide rule 21 / RRIA equivalence, §2). The earlier "~1,400" edit was made to match observed behaviour rather than a deliberate filter; this supersedes it.

### Backtest before go-live

We hold 10,565 historically triaged requests, 1,392 of which form the go-live pool (see above). Running the new service against those and comparing output to what the existing skill produced is a real accuracy measure, available before a single live request.

**50-sample results (6 runs to reach A=0, D=0):**

| Bucket | Count | Interpretation |
|---|---|---|
| A — gate violation | 0 | Go-live gate: cleared |
| D — incoherent | 0 | Go-live gate: cleared |
| B? — version divergence | 28 (56%) | Expected; requires guide-version citation per field |
| C — judgment noise | 20 (40%) | Both values defensible; no action needed |
| AGREE | 2 (4%) | Perfect match |

**B? breakdown (28 total):**
- 5 are exclusively `report_status` blank→populated: old triage left the field null; new model fills it. Not a real disagreement — the new output is more complete.
- 5 are pre-rule-25 era drift: guide changed on 2026-07-13; these requests were triaged before that, so the old value correctly reflected the rules at the time.
- 18 are mixed: `report_status` blank→populated **plus** C-level judgment noise (adjacent tier, urgency call, subcontractor text wording). If report_status were excluded, these 18 would be C.

**C breakdown (20 total) — by field:**

| Field | Requests | Note |
|---|---|---|
| report_status | 13 | Non-blank old value → different new value (e.g., SUPERVISOR_DISCRETION → CANNOT_WAIT) |
| complexity_tier | 11 | Adjacent tiers (C2↔C3) — both defensible |
| delegable_status | 10 | Judgment call on C1 vs C2 tasks |
| subcontractor_name | 9 | Same vendor, different text wording |
| urgency_tier | 4 | AJD vs null on post-R37 requests |
| duplicate_of_request_id / congestion_level | 4 | Judgment calls |

**Normalization applied before comparison** (prevents inflation by format artifacts):
- `urgency_tier` compared uppercase ('ajd' == 'AJD')
- `subcontractor_name` strips old-format "Oui/Non — " prefix and "ENTENTE : décrire..." template before comparing
- `report_status` NOT_APPLICABLE/null → new model populates → classified B?, not C

54 stored rows had these artifacts; without normalization the C rate would be overstated.

Worth setting an agreement threshold with the client in advance rather than after seeing the number. The 56% B? rate is dominated by report_status completeness and era drift — neither is a model error. The 40% C rate is genuine judgment noise across complex, multi-factor decisions.

---

## 7. Prompt and gate freeze — pending client adjudication

**Effective 2026-10-13. Do not make prompt or gate changes until the client review returns.**

We have made three prompt changes based on disagreements that nobody verified:
(1) blocking A5 routing codes from text fields, (2) removing contingency-vendor reasoning
on A0/A1 calls, (3) instructing the model to always name a specialist on A3b calls.
We do not know which of those changes improved the output and which degraded it.

The 689 completed rows also contain roughly 350 judgment calls (C bucket) and 270 cases
where the two outputs diverge because the guide changed after the original triage (B?).
None of those are confirmed model errors — they are disagreements with an old system, not
violations of the current rules.

**What remains actionable without the review:**
- **A bucket** (rule violation): gate rejects are provable wrong answers — fix them.
- **D bucket** (API failure/parse error): fix them.

Everything else — C, B?, AGREE, and any further prompt tuning — waits for the client
adjudication file (`docs/client-review-cases.md`) to come back.

**The full 703-call run is also on hold** until the review returns. Running it now would
add more unadjudicated disagreements for ~$33 without telling us anything new about
correctness. See api-cost-log.md.

---

## 8. Open items

| Item | Needs |
|---|---|
| **Dispatcher pre-suggestion** | Client decision. The SoW flags it as conflicting with rule 37. It changes the output contract — resolve before step 4 |
| **Guide version drift** | Rules change weekly; the client's own scheduled task is 5 revisions behind. `triage_model_version` records which version ran, but someone must own updating the system prompt |
| **Photo handling** | Today triage searches Gmail by ASNU for attachments. In-app intake captures photos directly (feature 3.1) — confirm the ASNU lookup disappears entirely rather than running alongside |
| **Agreement threshold** | What backtest agreement rate is acceptable before go-live |
