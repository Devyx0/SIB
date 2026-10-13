# How the Claude Triage Skill Works Today

_Mapped from Triage Skill v6.1 + Coordinator Guide v4.39, 2026-10-08._
_Foundation document for SoW Milestone 1 — features 3.1 (intake) and 3.3 (AI triage)._

---

## The flow, end to end

```
Tenant submits Gravity Form
        ↓
Email arrives in maintenance@sibelanger.com  (carries ASNU##### reference + photos)
        ↓
Event auto-created in Google Calendar
   · colour GREEN (colorId 2) = untriaged
   · dated on the next SATURDAY (the "landing zone", rule 29)
        ↓
┌─────────────────────────────────────────────────┐
│  CLAUDE TRIAGE  (scheduled task, hourly 7am-5pm)│
│                                                 │
│  Produces exactly three things:                 │
│    1. a normalized title                        │
│    2. a structured note ABOVE the original      │
│    3. the territory colour                      │
│                                                 │
│  Explicitly does NOT assign anyone.             │
└─────────────────────────────────────────────────┘
        ↓
Event is no longer green — it now carries a territory colour
        ↓
COORDINATOR reads the note and decides
   · who goes          ← human only, never triage
   · when
        ↓
TECHNICIAN attends
        ↓
Event turned GREY (colorId 8) = resolved  ← human only, never triage
```

---

## What your model was missing

### 1. Triage is a read-heavy enrichment step, not a classifier

Before writing anything, triage queries **four separate sources** and runs **three bounded searches**. The note is the output of all of that, not a reformatting of the request.

**Sources read:**

| Source | Purpose | Constraint |
|---|---|---|
| **RRIA** (rent roll, AI-maintained) | Occupants, lease size, start/end, language, pets | **Mandatory** for every residential unit — a blocking safeguard (rule 21). Read once per session from a master file, not per-unit |
| **Table Fondamentale** | Unit → building → project identity, territory | Authoritative for groupings |
| **Technical sheet** | Building reference — linked, never copied into the note | One read per project per session |
| **Gmail (maintenance@)** | Photos attached to the request, found by ASNU number | Checked even when the request doesn't mention a photo |

**Searches run** — all bounded, all anchored on the *event's* date, never today's:

| Search | Window |
|---|---|
| Duplicates (exact unit) | event date − 90d → + 45d |
| Synergy (project) | event date − 60d → + 21d |
| Unit history | event date − 6 months → + 21d |

### 2. There is a three-way verdict, not one path

This is the part most likely to be underestimated in the build. Step 2 of triage decides between three outcomes, and each writes different things to different places:

| Verdict | Condition | What happens |
|---|---|---|
| **SINGLE** | New problem, no active call | Normal full processing |
| **DUPLICATE** | Same unit **and** same problem | New request processed normally, but title gets `DOUBLON POTENTIEL` in capitals. **The original is never modified.** Merging/renaming/greying are human decisions |
| **ADDITION** | Same unit, **different** problem, while a non-grey call exists | The new problem is appended as a numbered item inside the *existing* call's PROBLEMS block; the existing call's title is updated; the new request is renamed "Ajout à appel existant" and linked. **This writes to two events** |

ADDITION is the only case where triage writes outside the event being processed — and the guide calls this out as one of exactly two permitted exceptions to strict write scope.

**And routing overrides consolidation:** if the addition falls into category A1–A4, it stays a standalone call rather than merging, because routing takes precedence over consolidating visits.

### 3. Synergy never mixes streams

Grouping related calls is not "same building, same week." It is stream-scoped:

- **Internal calls** → only other internal calls. Subcontractor work excluded entirely
- **Subcontractor calls** → only the *same* subcontractor. A Duclos call synergises only with Duclos
- **Pest control** → exclusive to pest files in the same building, then project, including future events and warranty-active ones

Plus a rule that matters for any date-proximity logic: **Saturdays are neutralised.** Two calls both sitting on a Saturday share no real visit date — they're both just in the landing zone. Date proximity never counts when the date is a Saturday.

---

## What triage never does

These are hard constraints, not defaults:

| Never | Rule |
|---|---|
| Assign anyone — no initials in title, `ASSIGNATION PROPOSÉE` always empty | 20 / 37 |
| Delete an event | 1 |
| Move a date without an explicit, targeted, in-session request | 2 / 30 |
| Overwrite a description — the note goes **above**, original stays intact | 3 |
| Apply grey (colorId 8) — grey means resolved, a human decision | 4 |
| Write financial data (rent, arrears, deposits, guarantors) | 10 |
| Write access info (lockboxes, codes, key/valve locations) | 11 |
| Write internal vocabulary (A1–A5, rule numbers, skill names) into an event | 7 |
| Touch `!` (admin), `X` (in progress), red (emergency) or waste-collection events | 6 |

One concurrency rule worth carrying into the build: **one request processed at a time**, marked with an `[EN TRAITEMENT]` lock, with an abandoned-lock sweep at the start of every run.

---

## What this means for Milestone 1

### The calendar disappears, but the workflow doesn't

The SoW replaces Gravity Forms with in-app intake (3.1) and the calendar with a dispatch board (3.2). But the triage logic (3.3) is explicitly *"formalizes the client's Claude triage skill"* — same behaviour, different surface.

Which means several calendar mechanics become database state:

| Calendar mechanic today | App equivalent |
|---|---|
| Green (colorId 2) = untriaged | A status field |
| Territory colour applied = triaged | Status + `sector_id` |
| Grey (colorId 8) = resolved | A status, human-set only |
| `[EN TRAITEMENT]` lock | Row-level lock or status |
| Saturday landing zone | **Disappears** — an artifact of calendar-based intake |
| `DOUBLON POTENTIEL` in title | A flag + `duplicate_of_request_id` (column already exists) |
| `AJOUT` into another call's PROBLEMS block | A real parent/child or item relationship |

### Three things the SoW will need that the current system does by convention

1. **The ADDITION mechanic writes to two records.** In the app this needs a proper relationship, not text appended into a free-text block. We have `duplicate_of_request_id` already; an addition is a different relation and has no column.

2. **Synergy is stream-scoped.** Any "related calls" feature must respect the internal / per-subcontractor / pest-control separation, or it will group things the coordinators deliberately keep apart.

3. **Triage must not assign** — the SoW already flags that dispatcher pre-suggestion conflicts with rule 37 and needs a client decision. Worth resolving before 3.3 is built, since it changes what the triage output looks like.

---

## Open question worth raising with the client

The current system runs triage on a **scheduled hourly task** against a calendar that receives requests passively. In the app, intake is synchronous — a request arrives when someone submits it.

Does triage then run **immediately on submission**, or stay batched? That changes the design: immediate means triage is in the request path and its latency is user-visible; batched means a queue and a worker, closer to today's behaviour.

The guide's "zero backlog" principle and hourly schedule suggest batching is acceptable, but it's a design decision, not a given.
