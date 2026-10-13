# Backtest Status — AI Triage Service

_Last updated: 2026-10-13_

---

## What this is

We are testing the new AI triage service against 1,392 historical maintenance requests before
going live. For each request, the model produces a triage output (complexity, urgency, routing,
etc.) and we compare it against what the coordinator actually wrote at the time.

The go-live condition: **zero rule violations (A) and zero failures (D)** across all 1,392 rows.

---

## Current status

| | |
|---|---|
| Pool | 1,392 requests |
| Completed | **689** (49%) |
| Remaining | **703** (awaiting API credits) |
| Go-live gate | **NOT CLEARED** — 12 rule violations in the 689 completed so far |

---

## Results — 689 rows completed

| Bucket | Count | % | Meaning |
|--------|-------|---|---------|
| **A — Rule violation** | **12** | 2% | Model broke a hard rule (access code in text, wrong routing, financial term). **Must be 0 to go live.** |
| **D — Failure** | **0** | 0% | API error or unparseable response. **Must be 0 to go live.** ✓ |
| B? — Version gap | 353 | 51% | Model and stored value differ because the guide changed after that request was triaged. Expected. |
| C — Judgment call | 270 | 39% | Both answers are defensible — adjacent complexity tier, different wording for the same vendor, etc. Expected. |
| Agree | 54 | 8% | Exact match on all compared fields. |

---

## The 12 rule violations (A)

These are the blocker. Each is a case where the model's output broke a rule the system must enforce.

| Request | Gate | What happened |
|---------|------|---------------|
| #9575 | Routing | Routed A1 (coordinator-only) but named an external vendor |
| #1146 | Routing | Same pattern — A1 + named external vendor |
| #9416 | Routing | A3b requires a named specialist; left subcontractor blank |
| #2211 | Internal vocab | Wrote routing code "A5" in a text field |
| #10426 | Internal vocab | Same — "A5" in text |
| #2125 | Internal vocab | Same — "A5" in text |
| #8703 | Internal vocab | Same — "A5" in text |
| #10468 | Internal vocab | Wrote "follow-up terrain" (internal skill term) in text |
| #1709 | Financial | Used the word "loyer" (rent) in a note field |
| #8861 | Financial | Deposit language in financial context |
| #9016 | Financial | Wrote a coin/token price in the problems field |
| #9316 | Verdict | Marked as "addition" but gave no valid reference request ID |

Pattern: 4 of 12 are the model writing a routing code (A5) in plain text instead of keeping it
in the routing field only. 3 are routing-table gaps — the model wants to say "handle internally
unless diagnosis requires X" and the routing table has no clean slot for that. 3 are financial
terms slipping through. These are prompt and gate tuning issues, not fundamental problems.

---

## Token and cost summary

_689 calls completed. System prompt (~99K tokens — Skill v6.1 + Guide v4.39) cached across all calls._

| | Total | Per call |
|---|---|---|
| Input tokens | 2,288,858 | 3,322 |
| Cache reads | 68,654,027 | 99,643 |
| Cache writes | 0 | 0 |
| Output tokens | 333,076 | 483 |
| **Cost** | **$32.46** | **$0.047** |

Extrapolated to full 1,392 rows: **~$65.60**

---

## What's next

1. **Top up API credits** ($90 recommended — covers one full 1,392-call run plus reruns; see `api-cost-log.md`)
2. **Resume** — run `uv run python3 -m drive_pipeline.triage.backtest --full`; the 689 completed rows are saved and will not be re-called
3. **Review the 12 A violations** in the completed 703 to see if the pattern holds or new types emerge
4. **Fix and re-run** if A > 0 after the full run — the sample gives us a good signal on what to fix before spending on the full pool
