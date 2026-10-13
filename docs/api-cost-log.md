# API Cost Log — SIB Triage Backtest

Pricing: Sonnet 4.6 — $3/MTok input, $3.75/MTok cache-write, $0.30/MTok cache-read, $15/MTok output.
Cost formula: `(input − cache_write) × $3 + cache_write × $3.75 + cache_read × $0.30 + output × $15`.
Note: `cache_read_tokens` is NOT included in `input_tokens` — they are reported separately by the API.

---

## What this is

**Context.** SIB (Les Immeubles Bélanger) is a property management company with ~180 buildings
across greater Québec City. Coordinators currently triage every maintenance request by hand using
a 50-rule coordinator guide (v4.39) and a triage skill document (v6.1). The SoW (Milestone 1,
feature 3.3) delivers an AI triage service that triages each incoming request automatically on
intake — classifying complexity, urgency, routing, delegation posture, and synergy — and writes
the result directly into the maintenance_request table.

**What the backtest does.** Before going live, the new service is run against 1,392 historically
closed requests that were previously triaged by the existing system. The model's output for each
request is compared field-by-field against what the coordinator actually wrote at the time. The
purpose is to measure agreement and surface any rule violations before a single live request is
touched.

**The pool — 1,392 rows.** The eligible pool is every `maintenance_request` where
`complexity_tier IS NOT NULL AND status = 'closed' AND start_date IS NOT NULL AND unit_id IS NOT
NULL`. All 1,392 are closed historical requests. The 564 excluded rows lack `unit_id` or
`start_date` — unit context is a blocking requirement for triage (the model cannot run without
it), so they are correctly out of scope.

**The go-live gate.** The run must produce **A = 0 and D = 0** across the full pool before the
service can be deployed to production.

---

## Result buckets

Each call produces one output record classified into one of four buckets by comparing the model's
fields against the stored coordinator values:

| Bucket | Name | Meaning | Go-live gate |
|--------|------|---------|--------------|
| **A** | Rule violation | The model's response was rejected by one of the deterministic validation gates — it wrote an access code, used internal vocabulary (routing codes) in a text field, violated the routing-rule/subcontractor consistency check, or similar hard rule. An A is not a judgment disagreement; it is a provable wrong answer. | **Must be 0** |
| **D** | Incoherent | The API call failed, the response could not be parsed as JSON, or required fields were missing. | **Must be 0** |
| **B?** | Version divergence | The new model and the stored coordinator value differ, but a plausible guide-version explanation exists (e.g., the request was triaged before a rule was amended, or the new model fills a field the old triage left blank). Not a model error. | Expected; no threshold |
| **C** | Judgment noise | Both values are defensible under the current guide — adjacent complexity tiers, different-but-valid subcontractor wording, urgency calls on ambiguous requests. Not a model error. | Expected; no threshold |
| **AGREE** | Exact match | New and stored values agree on all compared fields. | — |

**The validation gates (what produces an A):**

| Gate | Rule | Source |
|------|------|--------|
| 1 | No assignee field in response | Guide rule 20/37 — triage never assigns |
| 2 | No currency amounts in `problems` | Guide rule 9 |
| 3 | No financial terms in any text field (`loyer`, `dépôt` in financial context, etc.) | Guide rule 10 |
| 4 | No access-code digit near an access-context term (`code`, `clavier`, `NIP`, `boîte à clé`, etc.) | Guide rule 11 |
| 5 | No internal vocabulary (`A0`–`A5`, rule numbers, skill section names) in any text field | Guide rule 7 |
| 6 | `routing_rule` consistent with `subcontractor_name` (A2 → Body Gym, A3/A3b → non-Body-Gym vendor, A1 → no vendor) | Guide §6b |
| 7 | `addition` verdict must reference a non-closed request | Guide rule 12 |

**The flow:**

```
backtest.py --full
    ↓
Fetch 1,392 pool rows from DB
    ↓
For each row (resumable — skips rows already in JSONL with parsed output):
    ├── assemble() — builds per-request context from DB
    │     unit / lease / tenant context
    │     building / project / sector context
    │     technical sheet link
    │     duplicate candidates (−90d → +45d)
    │     synergy candidates (−60d → +21d, stream-filtered)
    │     unit history (−6mo → +21d)
    ↓
    ├── Anthropic API call (claude-sonnet-4-6, max_tokens=1024)
    │     system: Skill v6.1 + Guide v4.39 (cached, ~99K tokens)
    │             + output contract (uncached)
    │     user:   assembled context above
    ↓
    ├── parse_response() — strip markdown fences, JSON.loads
    ├── validate() — run gates 1–7; first failure returns rejected_<gate>
    └── Write to backtest_full_results.jsonl (one JSON record per row)
          includes: request_id, prompt_version, body_format, stream,
                    start_date, stored values, API result, parsed output
    ↓
_report_from_jsonl() — reads full JSONL, compares new vs stored per field,
    classifies each into A/B?/C/D/AGREE, prints bucket counts + per-request table
```

---

## TESTING (claimable, one-off)

All rows below are billable development/testing spend. Rows marked ¹ have no preserved JSONL
(files were overwritten before resume logic was added on 2026-10-12); costs are estimated at the
measured per-call rate of $0.047. The cost formula in the script was also corrected on 2026-10-12
— earlier in-script printouts understated costs and should not be used as billing figures.

Rows marked ² failed before completing any calls; all credits were consumed by a previous run.

| Date | Run | Calls OK | Input tok | Cache write | Cache read | Output tok | Cost | Notes |
|------|-----|----------|-----------|-------------|------------|------------|------|-------|
| 2026-10-09 | 50-sample run 1 | 50 | — | — | — | — | ~$2.29¹ | Gate iteration; JSONL overwritten |
| 2026-10-09 | 50-sample run 2 | 50 | — | — | — | — | ~$2.29¹ | Gate iteration; JSONL overwritten |
| 2026-10-09 | 50-sample run 3 | 50 | — | — | — | — | ~$2.29¹ | Gate iteration; JSONL overwritten |
| 2026-10-09 | 50-sample run 4 | 50 | — | — | — | — | ~$2.29¹ | Gate iteration; JSONL overwritten |
| 2026-10-09 | 50-sample run 5 | 50 | — | — | — | — | ~$2.29¹ | Gate iteration; JSONL overwritten |
| 2026-10-09 | 50-sample run 6 | 50 | 132,433 | 99,643 | 4,882,507 | 23,274 | $2.29 | First A=0 D=0; backtest_results.jsonl |
| 2026-10-10 | full-1392 (275/1392) | 275 | 896,104 | 0 | 27,401,825 | 129,981 | $12.86 | Credit exhaustion at 275/1392; no resume logic yet; JSONL archived as backtest_full_results_prefix.jsonl |
| 2026-10-12 | 50-rerun² | 0 | 0 | 0 | 0 | 0 | $0.00 | Credits empty; no calls completed |
| 2026-10-12 | 50-rerun | 50 | 144,533 | 99,643 | 4,882,507 | 23,219 | $2.32 | Post-gate-fix; post-Fix-3 prompt |
| 2026-10-12 | full-1392 (689/1392) | 689 | 2,288,858 | 0 | 68,654,027 | 333,076 | $32.46 | Credit exhaustion at 689/1392; resume logic saved work |
| 2026-10-13 | resume (703 remaining)² | 0 | 0 | 0 | 0 | 0 | $0.00 | Credits empty; 52 calls attempted, all returned 400; process killed |

**Testing total (approximate):** ~$61 across 11 runs, 1,014 completed calls.

_The $5+$5+$20+$35 = $65 in top-ups covers this with ~$4 remaining. Remaining balance was consumed
by the Oct 13 resume attempt (52 × 400 errors = $0 in tokens, but the account was already at zero)._

---

## WHY ESTIMATES WERE WRONG

**1. Per-call cost rose as the prompt grew**

The first 50-sample runs used a shorter system prompt with fewer gates and contract instructions.
Each gate iteration added to the prompt. By run 6 (first A=0 D=0) the system prompt had grown
enough that per-call cost was ~$0.047, roughly 3× higher than early runs (~$0.015/call before
all gates were added). The full-run estimate of ~$29 was sized against an earlier, lower
per-call figure.

**2. Each top-up was sized for one run with no rerun margin**

Gate debugging required six iterations of the 50-sample before reaching A=0, D=0. Each iteration
cost ~$2.29. The first four top-ups ($5, $5, $20, $35) were provisioned expecting one successful
run plus a full run — not six 50-sample iterations plus one partial 275-call run and one partial
689-call run.

**3. The actual cause of the $29 → $65 gap (2.3×) — and why the bug wasn't caught**

The $29 estimate came from the wrong cost formula. The original script computed:

```
cost = (input_tokens − cache_read_tokens) × $3 + cache_read_tokens × $0.30
```

This is wrong: `cache_read_tokens` is reported **separately** from `input_tokens` by the
Anthropic API — it is not a subset of it. Subtracting it from input produced near-zero or
negative cost estimates for heavily-cached runs, making the full pool appear far cheaper than
it was. The correct formula:

```
cost = (input_tokens − cache_write_tokens) × $3
     + cache_write_tokens × $3.75
     + cache_read_tokens × $0.30
     + output_tokens × $15
```

At 689 calls with this formula: **$32.46** → extrapolated to 1,392: **$65.58**. The per-call
cost is $0.047, and an estimate of $0.047 × 1,392 = $65.42 is what should have been used to
provision the run.

**The detection failure:** an early run printed `cost with cache: -$12.44`. A negative cost
is not an artifact or a display quirk — it is a formula error announcing itself. At the time,
the output was explained away as "savings-subtracted metric" and the run continued. The formula
was not inspected. Had the script asserted `cost > 0` before logging, it would have aborted
on the first run and the bug would have been found before any top-up was spent on a
mis-estimated full run. The lesson is not "we used the wrong formula" — it is **"an impossible
value was visible and we rationalised it."** That is the generalisable failure mode.

---

## OPERATIONAL COST (what SIB pays monthly)

Measured at steady state — 689 completed calls from the full backtest run.

**Per-call figures (warm cache):**
- Regular input (user message + context): ~3,322 tokens
- System prompt (Skill v6.1 + Guide v4.39, ~99K tokens): read from cache
- Output: ~483 tokens
- Cache write: 0 per call (system prompt cached once, read on all subsequent calls)

| Scenario | Cost/call | Monthly (1,500 req) | Annual |
|----------|-----------|---------------------|--------|
| With prompt caching | $0.047 | ~$70 | ~$840 |
| Without caching | $0.317 | ~$476 | ~$5,712 |
| **Savings from caching** | **$0.270** | **~$406** | **~$4,872** |

Caching reduces cost by ~85% (6.8×). Volume basis: 10,565 historically triaged requests over
7 months = 1,510/month.

**These figures are separate from the testing spend above and should not be summed.**
Testing is a one-time cost recoverable from the client; operational cost is the ongoing SIB
monthly expense once the service is live.

---

## PROVISIONING RULE

At the measured $0.047/call, a full 1,392-row backtest run costs **$65.42**. A 50-call rerun
for gate validation costs **$2.35**. Combined with a 25% margin for multiple gate iterations:

**Load $90 before starting a backtest run.**

Breakdown: $65.42 full run + $2.35 × 3 reruns + 20% margin = $85 → round to **$90**.

A $10 or $20 top-up is never enough for a full run. The minimum useful single top-up for backtest
work is **$70** (covers one full run, no reruns). For a gated development cycle (gates may need
iteration), load **$90**.

---

## Full run — on hold

**As of 2026-10-13, the remaining 703 calls are on hold.**

Running them now would cost ~$33 and produce more results to compare against — but those
comparisons would still be against the existing system's output, not against verified correct
answers. The client adjudication review (`docs/client-review-cases.md`) must come back first
so we know what we are measuring against.

Three prompt changes made prior to the current 689-row run are also unvalidated. Running the
full pool under the current prompt could entrench those assumptions. The gate fix for A3b
(Gate 6 incorrectly requires a non-null subcontractor for A3b calls) must also be applied
before the next full run.

**Resume condition:** client review returned, Gate 6 fixed, decision made on the 3 prompt
changes. Then: load $90, run `uv run python3 -m drive_pipeline.triage.backtest --full`.

---

## Auto-appended rows (backtest.py)

Rows below are written automatically at end of each completed run.

| Date | Run | Calls OK | Input tok | Cache write | Cache read | Output tok | Cost | Prompt version | Notes |
|------|-----|----------|-----------|-------------|------------|------------|------|----------------|-------|
| 2026-10-12 | 50-rerun | 50 | 144,533 | 99,643 | 4,882,507 | 23,219 | $2.3214 | claude-sonnet-4-6|docs-9c9029ed |  |
| 2026-10-12 | full-1392 | 689 | 2,288,858 | 0 | 68,654,027 | 333,076 | $32.4589 | claude-sonnet-4-6|docs-9c9029ed |  |
