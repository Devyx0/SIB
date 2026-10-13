# Calendar Parser Reference

_Built against: guide v4.39 · skill v6.1 · note format v10.6_
_Last updated: 2026-10-08_

---

## 0. Version Note — Production / Standard Divergence

**Guide v4.39 is the confirmed current standard.** The client confirmed no newer version exists as of 2026-10-08.

The client's automated Saturday triage task is running **outdated instructions**:

| | Automated Saturday task | Current standard |
|---|---|---|
| Skill version | v4.37 | v6.1 |
| Guide version | v4.34 | v4.39 |
| Note format | v10.5 | v10.6 |

The task's instructions are **five guide revisions behind**. Between v4.34 and v4.39, two rules were explicitly repealed:

- **Rule 25 (13 Jul 2026, guide v4.34→v4.35):** initials removed from titles, assignation moved to ASSIGNATION PROPOSÉE line in SECTION COORDOS.
- **Rule 37 (22 Aug 2026, guide v4.39):** ASSIGNATION PROPOSÉE field must remain EMPTY — the triage never assigns. Rule 25's assignation move is partially repealed. The automated task is unaware of rule 37 and may still write an assignee into ASSIGNATION PROPOSÉE.

The note format also diverges — detail below (§2).

**Implication:** events triaged by the automated Saturday task and events triaged in manual sessions are not produced by the same rules. The DB may contain both populations mixed together.

---

## 1. Body Format Classification

The parser in `drive_pipeline/ingestion/parse_calendar_requests.py` classifies each event's description into one of five formats, in priority order:

| Priority | Format | Detection marker | Typical era |
|---|---|---|---|
| 1 | `v10` | `<b><u>FOLLOW-UP TERRAIN</b>` or `<b><u>PROBLÈMES` (HTML) | Jul 2026 → |
| 2 | `v10_plaintext` | `FOLLOW-UP TERRAIN` or `PROBLÈMES :` or `PERMISSION D'ENTRÉE :` alone on a line (plain text) | Jul 2026 → |
| 3 | `gravity_forms` | `Date et heure de l'appel` / `Numéro unique d'unité` / `Nom complet de l'appelant` | Any |
| 4 | `belanger_compact` | `--- BÉLANGER date ---` / `--- FIN BÉLANGER ---` markers | Pre-Jul 2026 |
| 5 | `unparsed_body_format` | No marker matched | Mar–Jun 2026 (dominant) |

**Distribution in ingested data (10,565 events, Mar–Sep 2026):**

| Format | Count | % |
|---|---|---|
| `unparsed_body_format` | 8,371 | 79.2% |
| `v10_plaintext` | 1,584 | 15.0% |
| `v10` | 450 | 4.3% |
| `gravity_forms` | 148 | 1.4% |
| `belanger_compact` | 12 | 0.1% |

The high `unparsed_body_format` rate is expected: structured note formats began in July 2026. Events from March–June 2026 carry only a title and at most a brief unstructured note.

---

## 2. Note Format v10.5 vs v10.6 — SECTION TERRAIN Split

### The change

**v10.5 (14 Jul 2026):** Note body includes a `SECTION TERRAIN` heading above the PROBLÈMES block. Structure:

```
[FOLLOW-UP TERRAIN zone — ~8 blank lines]
====...====
SECTION TERRAIN          ← explicit heading present
PROBLÈMES :              ← first content block
...
```

**v10.6 (17 Jul 2026, guide v4.35):** `SECTION TERRAIN` heading removed. The zone terrain remains as a concept (all rules referencing it are still in force), but after the FOLLOW-UP TERRAIN zone the note goes directly to PROBLÈMES with no heading. Structure:

```
[FOLLOW-UP TERRAIN zone — ~8 blank lines]
====...====
PROBLÈMES :              ← directly, no SECTION TERRAIN line
...
```

Six other changes in v10.6 (irrelevant to the section label): PROBLÈMES items fully bolded + line-spaced, three blank lines after PROBLÈMES, terrain block labels bolded+underlined (`<b><u>LABEL</u> :</b>`), FOLLOW-UP zone enlarged to ~8 lines, sandwich separator before SECTION COORDOS strengthened.

### Who writes which format

- **Manual triage sessions** (coordinator + Claude, current skill v6.1): write v10.6 — no SECTION TERRAIN heading.
- **Automated Saturday triage task** (outdated, skill equivalent to v4.37, guide v4.34, note v10.5): writes v10.5 — SECTION TERRAIN heading present.

The split is by *which system triaged the event*, not by the event's start date.

### Parser handling of v10.5 SECTION TERRAIN

The parser's `_SEC_LABEL_RE` does **not** include `SECTION TERRAIN` as a recognised section label (only `SECTION COORDOS` is matched). A v10.5 event with `SECTION TERRAIN` in its body:

- The line is not matched as a section delimiter
- It is accumulated as text under whatever section was previously active (typically FOLLOW-UP TERRAIN, which is not extracted as a named DB field)
- **Net effect on parsed fields: none** — `problems`, `entry_permission`, and all other extracted columns are unaffected. The heading appears as noise in an unextracted section.

v10.5 events parse correctly for all fields we store. The SECTION TERRAIN line is silently discarded.

### Can SECTION TERRAIN be detected from the DB?

Partially. What `gravity_raw` actually contains depends on the body format:

- **`unparsed_body_format`**: `gravity_raw` stores the **entire raw description** (the `else` branch of the classifier). SECTION TERRAIN can appear here.
- **`v10` / `v10_plaintext`**: `gravity_raw` stores **only the Gravity Forms suffix below the BÉLANGER signature line** (`_v10_post_process` takes `text.rfind("BÉLANGER")` and captures everything after the next newline). The structured note sections — including any SECTION TERRAIN heading — live in the parsed fields or are silently dropped. They do **not** appear in `gravity_raw` for these formats.

Querying across all 10,565 rows:

```
gravity_raw ILIKE '%SECTION TERRAIN%'  : 20 rows — ALL unparsed_body_format
gravity_raw ILIKE '%SECTION COORDOS%'  : 122 rows — 120 unparsed, 2 v10_plaintext
gravity_raw ILIKE '%FOLLOW-UP TERRAIN%': 103 rows — 101 unparsed, 2 v10_plaintext
gravity_raw ILIKE '%PROBLÈMES%'        : 274 rows — mostly unparsed
```

The 20 SECTION TERRAIN hits are `unparsed_body_format` events with v10.5-style notes that the classifier failed to detect as `v10_plaintext` (no `<b><u>` tags, and the plain-text section markers weren't on their own lines as required by `_V10_PLAIN_MARKER`). These are misclassified v10.5 events — a parser gap — not random occurrences in the Gravity Forms text.

For correctly-classified v10/v10_plaintext events (2,034 rows): SECTION TERRAIN = 0 hits in gravity_raw. Not because those events have no SECTION TERRAIN heading, but because that heading — if present — is in the structured note body above BÉLANGER, which is parsed and dropped, never reaching gravity_raw.

**Conclusion:** The 20 misclassified unparsed events are fingerprint-able (they have SECTION TERRAIN in gravity_raw). Correctly-classified v10/v10_plaintext events from the automated task cannot be distinguished from manual-triage events based on stored fields alone.

---

## 3. Saturday Events — Automated Task Window

### The workflow model

Guide v4.32 (16 Jul 2026): new Gravity Forms calls "land on Saturday" in the calendar (Saturday is the atterrissage zone for all new calls). The automated triage task searches `today` to `today + 7 days`, Saturday events only, colorId=2 (green = untriaged).

### What the DB shows

| Window | Saturday events | All events | Saturday % |
|---|---|---|---|
| Full ingest (Mar–Sep 25, 2026) | 15 | 10,565 | 0.14% |
| Post-Jul 16 (after landing rule) | 5 | 4,653 | 0.11% |
| Phase 1 (Aug 11–Sep 25, 2026) | 2 | 2,374 | 0.08% |

**Conclusion: the Saturday landing convention is not reflected in our ingested data.** Possible explanations:

1. The Gravity Forms → Calendar integration places events on the day of submission (weekday), not on the next Saturday, at least for our data window.
2. Or: Saturday events are triaged (and color-changed away from green) before our ingest window captured them, making them indistinguishable from weekday events in the API response.

The 15 Saturday events in our DB appear to be a mix of manually-scheduled work reservations (coordinators placing specific Saturday work like move-in elevator reservations at 135 Grande Allée) and a handful of Gravity Forms calls.

**There is no statistically meaningful Saturday cohort in our DB to confirm or refute a structural format difference.** The format breakdown for Saturday events (11 unparsed, 3 v10_plaintext, 1 v10 TEST event) cannot be compared to the weekday distribution.

### Format breakdown by day of week (all events)

| DOW | v10 | v10_plaintext | gravity_forms | belanger_compact | unparsed | Total |
|---|---|---|---|---|---|---|
| 0 Sun | 0 | 1 | 0 | 0 | 13 | 14 |
| 1 Mon | 115 | 261 | 45 | 6 | 1,755 | 2,182 |
| 2 Tue | 83 | 329 | 29 | 3 | 1,837 | 2,281 |
| 3 Wed | 91 | 344 | 19 | 2 | 1,820 | 2,276 |
| 4 Thu | 77 | 310 | 28 | 0 | 1,649 | 2,064 |
| 5 Fri | 83 | 336 | 27 | 1 | 1,286 | 1,733 |
| 6 Sat | 1 | 3 | 0 | 0 | 11 | 15 |

No anomalous format concentration on Saturday. The weekday distribution is uniform across Mon–Fri.

---

## 4. Title Parsing Rules (summary)

The parser (`_parse_title`) strips from the title in order:
1. Employee code (2–5 uppercase letters, optionally hyphenated; e.g. `CHGE`, `JC-S` → `JCS`)
2. Parenthetical notes after the code: `(CODE)` stripped
3. Multiple codes and vendor codes (multi-pass loop)
4. Urgency tokens: `ajd`, `urgt`, `urgent`, `dem`, `semaine`, `2sem`, `mois`, `report`
5. Vendor names (mixed-case): Éric, ElectroDB, BoucherLortie, Fortin, WifiQuébec, etc.
6. Pre-civic keywords: `AJOUT`, `Doublons`, `Terrain`, `Urgence` + optional dash/space

Then extracts: civic number, street, problem summary (after first `:`).

**Notable strips that are NOT assigned** (`KNOWN_VENDOR_CODES`): `MAXI`, `TK`, `ERIC`, `PDQ`, `SAC`, `TEST`. `SAC` is an inter-code dispatch annotation, not a person.

**Title format changed with guide v4.34 (rule 25, 13 Jul 2026):** initials removed from title. Events before that date have employee codes in the title; events after are supposed to have no initials (except legacy pre-rule events and events triaged by the outdated automated task, which still writes initials in the v4.34 format). In practice, our data shows initials present in titles across the full window — rule 25 affected new manual triages, but the automated task continued writing code-prefixed titles.

---

## 5. Known Parser Gaps and Limitations

> **Important constraint on future parser work:** For `v10` and `v10_plaintext` events, the original triage note is **NOT recoverable from the DB**. `gravity_raw` holds only the Gravity Forms suffix (everything below the BÉLANGER signature line); the structured note — PROBLÈMES, OCCUPANTS, SECTION COORDOS, etc. — was parsed into columns on ingest and the raw text was never stored. Re-parsing, re-classifying, or correcting any parsed field for these 2,034 events requires re-fetching the full event description from the Calendar API. This is a hard constraint on any future parser improvement: improvements to extraction logic cannot be back-applied to existing v10/v10_plaintext rows without a re-fetch pass. For `unparsed_body_format` events (8,371 rows), `gravity_raw` holds the full description and re-parsing from DB is possible.

| Gap | Detail | Impact |
|---|---|---|
| Raw body stored format-dependently | For `unparsed_body_format` (79% of rows): `gravity_raw` = full original description — re-parseable from DB. For `v10`/`v10_plaintext` (19% of rows): `gravity_raw` = Gravity Forms suffix only (below BÉLANGER) — structured note is NOT in the DB. | Any parser improvement that needs to re-classify or re-extract fields from structured-format events requires a Calendar API re-fetch. See note above. |
| SECTION TERRAIN not extracted | v10.5 heading absorbed as noise in unextracted section | No field loss; heading is silently dropped |
| Multi-assignee: first code only | ~30 tickets have two employee codes in title; only first stored in `assigned_employee_id` | Second assignee in `assigned_employee_code_raw` only |
| Saturday cohort too small | 15 Saturday events in DB; landing convention not established in data | Cannot confirm automated task vs manual triage split from DB |
| Automated task fingerprint — partial | 20 misclassified `unparsed_body_format` rows have SECTION TERRAIN in `gravity_raw` and are identifiable as v10.5 events from the automated task; correctly-classified v10/v10_plaintext events from the automated task are not distinguishable from manual-triage events in stored fields | `WHERE body_format = 'unparsed_body_format' AND gravity_raw ILIKE '%SECTION TERRAIN%'` finds the 20 misclassified rows; the rest require raw Calendar API re-fetch |
| ASSIGNATION PROPOSÉE undetected | Rule 37 (no assignation) is not retroactively enforceable from DB — the field would be in unparsed raw text | Out-of-date automated task may have written assignees we never stored |
