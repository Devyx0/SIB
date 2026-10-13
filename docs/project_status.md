# SIB Platform — Project Status

_Last updated: 2026-10-08 (automated Saturday task version skew documented; backend-rules.md created)_

---

## −1. Automated Saturday Triage Task — Version Skew (2026-10-08)

The client's scheduled Saturday triage task is running outdated instructions. Confirmed by screenshots of the task configuration:

| | Automated task | Current standard |
|---|---|---|
| Skill version | v4.37 | v6.1 |
| Guide version | v4.34 | v4.39 |
| Note format | v10.5 | v10.6 |

Five guide revisions behind. The gap spans two explicitly repealed rules:

- **Rule 25 (13 Jul 2026):** initials removed from title, assignation moved to ASSIGNATION PROPOSÉE in SECTION COORDOS. The automated task predates this — it may still write initials in the title if the old code had that behavior.
- **Rule 37 (22 Aug 2026):** ASSIGNATION PROPOSÉE must remain EMPTY — the triage never assigns. The automated task is unaware of this repeal and may write an assignee into that field.

The most visible formatting difference: **v10.5 writes a `SECTION TERRAIN` heading** above the PROBLÈMES block; **v10.6 removed that heading** (Jul 17, 2026, guide v4.35). Events triaged by the automated task have the heading; manual triages do not.

### DB evidence

We checked whether Saturday events (the automated task's exclusive window) differ structurally from weekday events:

- **Saturday events in DB: 15 out of 10,565 (0.14%).** The Saturday landing convention (guide v4.32, Jul 16, 2026) was established near the end of our ingest window and is not meaningfully represented in the data.
- **SECTION TERRAIN cannot be detected from parsed DB fields.** The parser's `_SEC_LABEL_RE` does not include `SECTION TERRAIN` as a section label; its content is silently absorbed into an unextracted section. Zero hits in `gravity_raw` or `problems` do not prove absence.
- **No anomalous format split by day of week.** The v10/v10_plaintext/unparsed ratio is uniform across Mon–Fri; Saturday's 15 events are too few to compare.

### Implication for the parser

The v10.5/v10.6 difference has **no practical effect on field extraction** — the `SECTION TERRAIN` line is silently skipped as an unrecognised label. All fields (`problems`, `entry_permission`, etc.) parse correctly from both versions. See `docs/backend-rules.md §2` for full detail.

### What needs fixing (out of scope for backend pipeline)

The automated Saturday task's prompt needs updating to reference:
- Skill v6.1
- Guide v4.39
- Note format v10.6

Until updated, events triaged by the Saturday task may: (a) include a `SECTION TERRAIN` heading in the note, (b) write an assignee into ASSIGNATION PROPOSÉE (violating rule 37), and (c) still search the ST Giroux calendar (retired by rule 36).

---

## 0. Provenance Integrity — All Three Defects Resolved (2026-10-07)

265,705 total provenance rows across 53 tables. Provenance guarantees were not clean when first issued — three defects were found and resolved:

| Defect | Rows affected | Resolution | Date |
|---|---|---|---|
| `lease_history` orphaned provenance (table dropped, 5,699 rows dangled) | 5,699 deleted | Clean DELETE; no other orphaned tables found | 2026-10-06 |
| `maintenance_followup_entry` zero provenance (3,990 rows, 0 prov) | 3,990 backfilled | Reconstructed from ingest loop order — `historique_raw` / `doublons` field mapping per request; 0 no-matches, 16 ambiguous resolved by followup_id ordering | 2026-10-06 |
| `service_contract_building` partial coverage (440 rows, 196 prov) | 701 written → 440/440 composite-key covered | Source rows reconstructed via existing `service_contract` cost provenance; pest rows inferred from contract language ("Annexe A empty template"); 0 un-traceable rows | 2026-10-07 |

**Post-fix guarantees hold:** `lease_history` = 0 orphaned rows; `maintenance_followup_entry` = 3,990 / 3,990 provenance rows; `service_contract_building` = 440 / 440 fully covered (composite PK format: `contract_id,building_id`). All four ingest scripts (snow, lawn, elevator, extermination) updated to write junction provenance (`contract_id` + `building_id` columns) on future runs.

---

## 1. Fiches Techniques Pipeline — Complete

All work verified live against Drive.

| Stage | Status | Detail |
|---|---|---|
| Drive inventory catalogued | ✓ Done | 351 files across root (184), 01-Old Technical Sheets (130), 00-Archives (35), Logisco Key Box List (2) — see `drive_pipeline/fiches_techniques/links.py` |
| English file renames on Drive | ✓ Done | 80 files renamed via `rename.py`; mapping in `mapping.py` |
| Column A label translation | ✓ Done | All field labels translated FR→EN via `label_glossary.py`; audit trail in `label_translation_log.py` |
| Column B→C value translation | ✓ Done | 4,433 cells written across 343 files (root 181, Old TS 129, Archives 33); 8 low-confidence overrides applied; 44 ILO/SIB phrase variants normalized to canonical |
| Drive write-back verification | ✓ Done | All 3 write-back phases spot-checked live from Drive; 3 extra override cells confirmed 2026-09-22 |
| Known empty files | ✓ Closed | 1st Ave Québec (6800) and Isaac-Bédard Ave (6905) confirmed skeleton files — col B entirely None, correctly skipped |

**Excluded from value translation (design decisions, not gaps):**
- `0 - EMERGENCY CONTACTS AND PROCEDURES.xlsx` — sensitivity-flagged
- `Untitled.xlsx` — empty test file
- `Test Copy of St-Jean Street, Québec (636 640 646).xlsx` — test artefact

---

## 2. Maintenance Drive Pipeline — Partial

### Folder renames and cataloguing
- All 8 catalogued subfolder groups renamed on Drive (POOL, Oak 1321, EXTERMINATION, Coin-Op Laundry, Sofa, BOILERS, ELEVATORS, FIRE PROTECTION).
- Full item mapping in `drive_pipeline/maintenance/links_maintenance.py` (164 entries).

### Root file translations — 7 of 11 done

Files 1–7 translated FR→EN and written to Drive (2026-09-22). All 7 verified live from Drive.

| # | File | Status |
|---|---|---|
| 1 | Pool Access Codes - OSEN.gsheet.xlsx | ✓ Written |
| 2 | Garage Remotes (temporary file).xlsx | ✓ Written |
| 3 | Plumber Search.xlsx | ✓ Written |
| 4 | 0 - Oricom List of Files for SIB.xlsx | ✓ Written (headers only; address data preserved as-is per spec) |
| 5 | Container Rental - SI Belanger.xlsx | ✓ Written |
| 6 | Inventory - Air Conditioners and Dehumidifiers.xlsx | ✓ Written (3 sheets: 2024, 2025, 2026) |
| 7 | Maintenance and Leasing Tracking - Vacant Units.xlsx | ✓ Written |

### vendor_contact row count — 176, not 40

Earlier notes in this project referenced 40 vendor_contact rows. The correct count is **176**. The discrepancy arose because `ingest_vendor_contact.py` reads from six sources, one of which — `RENSEIGNEMENTS CONTACT IMPORTANTS IMMEUBLES ET EMPLOYÉS.xlsx` (the authoritative vendor master list) — was absent during the first write run and silently skipped. Once the file was downloaded and the script was re-run (2026-09-28), the dedup produced the correct 176 canonical vendors: the original 40 sources plus 136 from the RENSEIGNEMENTS list. All vendor FK references (equipment, building_fire_system, service_contract) were verified intact after the change; no normalized duplicates were introduced. The script now treats a missing RENSEIGNEMENTS file as a hard error.

### Files 8–11 — Out of scope, no decision made

| # | File | Sensitivity | Status |
|---|---|---|---|
| 8 | Security config file | Reviewed; content: alarm codes, access-control credentials | No translation decision — pending separate sensitivity review |
| 9 | Soluvox call log | High-sensitivity flagged during review | No decision — flagged for separate handling |
| 10 | Second call log (Tableau des Appels de Service IA) | Confirmed derived cache of Calendar; superseded by direct Calendar ingestion | Resolved — abandoned. See §3. |
| 11 | Master Rent Roll | Not yet opened | No decision |

---

## 3. Known Data Gaps — Do Not Re-Discover

These were confirmed during Drive exploration and review. They are open items, not bugs.

### MÉNAGE folder — missing from both variants
The MÉNAGE (cleaning/housekeeping) subfolder does not appear in either the French or English Maintenance Drive. Its absence was confirmed but the root cause is unresolved — the folder may have been moved, deleted, or never created under this naming. No action taken.

### PEINTURE folder — confirmed empty (real source is elsewhere)
The PEINTURE (paint) subfolder exists in the Maintenance Drive but is empty. The real paint data source is `"0 - Charte des couleurs de peinture SIB"` — a distinct file confirmed via the live DB map review. It has not yet been pulled or ingested. This maps to the `building_paint_spec` table in the schema, which is also empty.

### File 10 — Abandoned (superseded by direct Calendar ingestion)

**File:** "Tableau des Appels de Service (IA)" — Drive ID `1VLLHbK0euh-6utsGhI5XZSxmFdxQM4xrj9Ns69_OjAQ`, owner `maintenance@sibelanger.com`, inspected live 2026-09-28.

**What it is:** A Google Sheet with 2 tabs. Tab "Appels" has 20,724 data rows and 30 columns. Per SKILL.md: *"il n'est jamais une source de lien"* — it is a 15-minute-refreshed cache of Calendar events, not a source of truth.

**Why abandoned:** The corrupted local snapshot (File 10 in the local work directory) was used in an earlier pass and should not be repaired. The live sheet is also not worth ingesting:
- **Column alignment was not misaligned in the source.** The sample previously seen with "IMMEUBLE : 4775 Ste Geneviève" in what appeared to be the ASNU column was a text-extraction artifact. In the live XLSX, it is correctly in col 6 (Numéro unique unité). The implausible "Nb déplacements: 3845" was also an extraction artifact.
- **Event ID overlap is too low.** After normalizing IDs (stripping `@google.com` suffix), only 364/2,374 of our `maintenance_request` rows (15.3%) match events in the sheet. The sheet is dominated by Gravity Forms-submitted tickets (8,960 `sib…@google.com` IDs = 81% of its distinct IDs) which represent a different submission workflow than the calendar events we ingested.

**The four columns evaluated as non-redundant:**

| Column | Sheet col | Verdict | Reason |
|---|---|---|---|
| Nb déplacements | 20 | **Skip** | 93.9% = 0; implausible outliers (max 7,356); 468 cells contain `00:00:00` (wrong type). Data unreliable. |
| Historique des dates | 21 | **Skip** | Formula noise: the cell formula prepends the current timestamp on every 15-min refresh, creating chains of depth up to 3,842. Not actual reschedule history. |
| Date planifiée initiale | 18 | Would be useful, but unmatchable | Clean datetime, 100% populated, plausible range (2026-01-09 to 2027-01-08). 118/364 matched events show rescheduling. But 84.7% of our DB events have no match. |
| Date planifiée actuelle | 19 | Same | Same quality, same coverage gap. |
| Date de règlement | 22 | **Skip** | 0/364 matched events have a settlement date. The 17,199 settlement dates in the sheet belong to events not in our DB (likely Gravity Forms-only tickets that were never in the Calendar we ingested from). |

**Conclusion:** The sheet and `maintenance_request` represent different ticket populations. Ingesting any of the four columns would yield at best 15.3% coverage, with the rescheduling signal (init vs. curr date) covering only 364 rows and the settlement date covering none. Abandoning entirely is the correct outcome.

**`recurring_task_pattern` clarification (previously open):** Confirmed that `recurring_task_pattern` is sourced from the Coordinator's Guide (recurring-task rules), not from this file. This file is not a source for `service_visit` either — it is a calendar cache, not a structured service visit log. The `service_visit` table still has no identified source.

### pool_access_code.building_id — null by source limitation, not oversight (2026-09-30)

All 52 rows in `pool_access_code` have `building_id = NULL`. This was investigated and confirmed as a source limitation.

**Task 1 — Source file structure:** "Pool Access Codes - OSEN.gsheet.xlsx" (Drive ID `17Qhmtp8I8kWiaKqc5-3RXJDO2ldx1i_j`) has exactly two columns: `Code` and `Assigned To`. There is no per-row building or address identifier of any kind. 50 of 52 codes have no `Assigned To` value at all; two are assigned to "Maintenance" (code 7438) and "Construction" (code 3274). Nothing was omitted during ingestion — the source simply does not contain a building identifier.

**Task 2 — OSEN complex mapping:** The filename says "OSEN," which corresponds to the 4-building complex: 1017 Duchesneau (building_id=91) and 3140/3146/3150 France-Prime (building_ids=92–94). All four buildings have `piscine = True`. Because all four share the flag, the piscine attribute cannot narrow the codes to a single building. A complex-level mapping (all 52 codes tagged to all 4 OSEN buildings) is possible but requires client confirmation that this is a shared pool rather than one building's private pool. No mapping was applied.

**Task 3 — Gingras pool codes (recovered 2026-10-02):** The Drive shortcut for the Gingras file was dead (deleted/moved), but a local copy was recovered from Downloads. Programmatic comparison confirms: the Gingras file, the OSEN file, and the 52 rows in `pool_access_code` are all byte-for-byte identical — same codes, same order, same two special assignments (7438=Maintenance, 3274=Construction). The Gingras file is **not a separate dataset**; it is a duplicate of the OSEN list saved under a different building name. This is not a data gap.

**Revised client question (pool codes — single question):** The same 52-code list was saved under at least two building names (Gingras and OSEN). This strongly suggests it is one shared portfolio-wide code set rather than per-building codes. François should confirm: **Is this one shared access-code list for all SIB pools? Or should each pool complex have its own distinct set of codes?** No building_id assignments will be made until François answers — assigning the OSEN codes only to OSEN buildings, or to all pools, depends entirely on that answer.

---

## 4. Tables with No Data Source Identified Yet

These tables exist in the schema (`schema/sql/schema.sql`) and are ready to receive data, but no source file has been identified or ingested as of this writing. Ingestion work for these is not scoped.

| Table | Notes |
|---|---|
| `entrance` | No source file. Ingestion plan: create one synthetic entrance per building (copy `building.adresse/ville/code_postal`) so `building_intercom` and `building_key_box` FKs are never dangling. |
| `equipment` | No source file at either building or unit level. |
| `service_contract` | Phase 1 written 2026-10-02: telecom (99 buildings in `building_telecom`), pest (1 contract × 179 buildings), snow (126 contracts — 60 parking + 66 pedestrian, 38 new vendors), lawn (107 contracts, 14 new vendors). Total: 234 contracts, 440 building links, 215 vendors. vendor_id is nullable (contracts with blank vendor col get NULL + raw text in notes). See §4b. |
| `service_visit` | Fire-protection folder holds ~106 per-building subfolders of unstructured inspection PDFs — nothing extracted. May overlap with the unresolved Service Call Log (see §3). |
| `pest_control_case` | **Cannot be populated from Drive.** SIB's copy of the extermination contract (QE-2026-0002-C) covers 2 000+ units, but the treatment records — which unit was visited, when, by which technician, and what was found — live entirely in Québec Extermination's own system. SIB's Google Drive contains only the signed contract PDF and a tenant roster (sent outbound to the vendor for access scheduling). See §4b for what SIB would need from the vendor to track cases. |
| `tenancy_record` | Conceptual only; needs a new collection process. `start_date`/`end_date` are intentionally left NULL — see §4a below. |

### 4a. tenancy_record.start_date / end_date — DECISION REVERSED 2026-10-02

~~**DEFERRED:** `start_date` and `end_date` will remain NULL. Decision: do not backfill from lease dates.~~

**Decision reversed.** "Tableau des Arrivées et Départs" (Google Sheets ID `1jTTmL1Kfh3J0bTrrQnLW-kYQc9V0zrdbEtmn2nUixSM`) supersedes the rent-roll-snapshot approach. The sheet has 6 years of completed move-in/move-out history (~1,390 events), is actively maintained by the SIB team, and maps directly to `unit_turnover` and `tenancy_record` date columns.

**Ingestion plan (in progress):** `unit_turnover` (~1,200–1,300 rows from completed tabs) + `tenancy_record.start_date/end_date` backfill (~1,400–2,000 rows, 25–36% of the 5,569 total). Cession rows → `capacite='took_over'`. Dry run pending date-format verification (ISO vs DD/MM/YYYY) and unit_id resolution check.

**Permanent NULL window:** ~3,500 pre-2020 tenancies have no source. These remain NULL. The sheet's earliest data is approximately 2020; anything before that has no identified source and will not be backfilled.

See §4 for the `unit_turnover` table target (currently 0 rows).

### 4c. Prior lease terms — outgoing_fin_bail + outgoing_loyer on unit_turnover (2026-10-05)

`lease` stays current-state. Prior lease financial terms are stored on `unit_turnover`, the table that already represents the tenant-change event.

Two columns added to `unit_turnover`:
- `outgoing_fin_bail date` — the departing tenant's formal lease end date
- `outgoing_loyer numeric` — the departing tenant's rent at the time of departure

Both backfilled from the rent roll archive for turnover rows where a matching snapshot exists. Coverage is partial: 8 of 18 archive months have usable data (see below), and some turnover events fall outside that window.

#### Rent roll archive — 18 months, 8 usable

Archive folder ID: `1bBzdogeixb2xE2c5uM703Nu3xjQFJbOR` (Shared Drive — requires `supportsAllDrives=True` on every API call). Monthly range: **2025-04 through 2026-09, no month gaps.**

**Schema break point:** V1 (≤2025-10, 51 cols) → V2 (≥2025-11, 74–79 cols). Column positions shift; header-name detection (not index) is required.

Only **8 of 18 months yield usable data.** The other 10 are excluded for source defects:

| Month | Reason excluded |
|---|---|
| 2025-04, 2025-07 | All data cells blank — formula-only, values do not resolve on export |
| 2025-05 | Main tab not named "Rent roll" — parser cannot find it without a name scan |
| 2025-06, 2025-08, 2025-09, 2025-12, 2026-01 | `Nom complet` empty for every row — names formula-referenced from a master sheet that breaks on export |
| 2025-10 | Export endpoint returns 404 despite file appearing in folder listing |

These are source defects, not parser gaps. The usable months are: **2025-11, 2026-02, 2026-03, 2026-04, 2026-05, 2026-06, 2026-07, 2026-08.**

**Archive coverage of prior leases:** fin_bail ~95%, loyer ~95%, depot 23%, debut_bail 0% (column did not exist in the archive before September 2026 — unrecoverable).

#### Task 3 cross-check: 7 fin_bail gap-fills sourced from Arrivées/Départs (2026-10-05)

The 7 `lease.fin_bail` gap-fills written 2026-10-05 were sourced from col 4 of the Arrivées/Départs sheet ("DÉPART: Date de fin de bail" — the **departing** tenant's lease end). Cross-checking against the 2026-09 rent roll archive revealed a data error in 2 of the 7:

| unit_id | gap-fill written | archive fin_bail | verdict |
|---|---|---|---|
| 4291 (220-665 Grande Allée E.) | 2026-08-31 | 2027-09-30 | **Wrong** — departing tenant's date written to incoming tenant's row |
| 3410 (25-117 Sainte-Ursule) | 2026-06-30 | 2027-09-30 | **Wrong** — same error |
| 3511, 3241, 3826, 3355, 3560 | various | NULL in archive | Unverifiable (new Sept 2026 arrivals, fin_bail not yet entered in rent roll) |

The error is the same incoming/outgoing split as the 132 debut_bail conflicts — col 4 is the departing tenant's fin_bail, written into the incoming tenant's `lease` row. **Corrected 2026-10-06: both updated to 2027-09-30.**

### 4d. OLD tab lease dates — unusable for gap-filling; deliberately not written (2026-10-06)

The Arrivées/Départs sheet has an "OLD" tab covering departing tenants, with lease date columns (col 11: `debut_bail`, col 12: `fin_bail`). A dry run found **5 fin_bail + 43 debut_bail** rows that could be filled where the DB currently has NULL. Both were declined.

**Why:** The OLD tab carries no tenant identifier. When `lease.debut_bail` or `lease.fin_bail` is NULL, there is no way to confirm the date in the sheet belongs to that unit's incoming (current) lease rather than the departing tenant's historical lease. The dry run shows 461 fin_bail "conflicts" — col 12 contains the DEPARTING tenant's fin_bail, which collides with the INCOMING tenant's lease row for almost every unit. The 5 and 43 NULL-targeting cases cannot be distinguished from those conflicts without a tenant FK that the OLD tab does not provide.

**Prior error that confirms the risk (2026-10-06):** A separate source (Arrivées/Départs col 4 "Date de fin du bail") was used to gap-fill 7 `lease.fin_bail` values. 2 of 7 wrote the departing tenant's date onto the incoming tenant's lease row. Both were corrected to 2027-09-30 that same day (see §4c). 43 rows with unverifiable targeting is not worth repeating.

**Available but declined:** 5 fin_bail + 43 debut_bail = 48 rows. None written.

---

### 4b. Extermination — contract is in the DB; intervention records are not, and cannot be

**What was ingested (2026-10-02):** Contract QE-2026-0002-C with Québec Extermination ($5.78/unit/month, 24-month term Sept 2026–Aug 2028) is recorded in `service_contract`, and all 179 SIB buildings are linked via `service_contract_building`. The link covers the full portfolio because Annexe A of the contract is an unfilled template (placeholder `[●]` throughout); the only coverage language is "2 000 unités ou plus."

**What cannot be ingested:** The DB has a `pest_control_case` table designed to track individual interventions — which unit had a problem, when the exterminator attended, what treatment was applied, and what the outcome was. This data does **not exist on SIB's side at all.** SIB's extermination Drive folder contains:
- The signed contract PDF (ingested above)
- A tenant roster Excel file — this is outbound data SIB sends **to** the vendor so they know which units to access; it is not a record of what was done

All intervention records are held exclusively in Québec Extermination's own system (work orders, visit logs, chemical reports). SIB has never received structured exports of this data.

**What SIB would need from Québec Extermination to populate `pest_control_case`:**

A periodic export (monthly CSV or Excel, or a live feed) containing at minimum:
- Building address and unit number visited
- Date of visit
- Type of treatment (inspection, preventive, reactive)
- Pest type identified (if any)
- Outcome / follow-up required
- Technician name or ID (optional but useful for warranty disputes)

Without this, the `pest_control_case` table will remain empty. François may not realise this data is entirely on the vendor's side — the question to ask the vendor is: "Can you provide a monthly export of interventions by building and unit, and can the export be automated?"

---

## 5. Building Table — Known TF Data Quality Issues (for client review)

These were identified by comparing Table Fondamentale against the Fiches Techniques during ingestion. Both values are preserved in `data_provenance`; the ingested value in `building` is noted below.

### 5j. Master Rent Roll — rolling snapshot, not append-only log; monthly history may be recoverable elsewhere

A Sept 7 client note described the Rent Roll as an append-only monthly log (one row per tenant per month). Investigation found otherwise: the live source sheet (Google Sheets ID `1QH7-VxYpPzBExGbpDUVx_Tcj4ySBJq2KDcq0iJ-YYjo`, maintained since January 2025), queried directly via the Sheets API, contains only September 2026 data — 7,119 rows, single `Mois` value. The sheet is overwritten in place each month; prior months are not retained there.

**Open question for client:** Does a second artifact exist that preserves monthly history — archived monthly copies in Drive, a QuickBooks export, or an accounting-system feed? If so, 20 months of tenancy and rent history may be recoverable, which would materially improve `tenancy_record` accuracy (currently backfilled from lease dates as a documented stopgap, per §4). If no such artifact exists, historical data prior to September 2026 should be considered unavailable, and going forward we would need to capture monthly snapshots ourselves to build history.

**Technical note:** The local `.xlsx` export has mixed month labels — 5,773 rows read "September 2026" (English, translated) and 1,346 read "Septembre 2026" (French, untranslated). The 1,346 French-label rows are structural rows — formula subtotals, building group headers, and blank rows — whose cells were empty so the translation pass had nothing to translate. This is expected; no tenant data was lost. (Nine of those rows were genuine vacant units and have since been ingested — see §5k.)

### 5k. Nine vacant units present only in French structural section of Rent Roll — now ingested

During investigation of the 1,346 skipped "Septembre 2026" rows, 9 genuine unit entries were found that had no English-section counterpart: `1175-106 Chamonix`, `3072-5 Chatelets`, `690 Saint-Augustin`, `786A Abraham`, `3146-501 France-Prime`, and four units at 220 Grande Allée E. (apt 470, 665, 825, 975). All were vacant or pending-approval with $0 rent and no tenant name.

These were ingested as unit rows (unit_ids 4285–4293) with matching lease rows. No tenant or tenancy_record rows were written. The ingest script (`ingest_units_leases_tenants.py`) was also corrected to accept both "September 2026" and "Septembre 2026" as valid month values for future re-runs. Unit table total: **4,293**.

**unit_id and lease_id are not stable across refreshes.** These IDs are assigned by source-file row position; a monthly reload reassigns them from 1. This is safe because all dependent tables are truncated and rebuilt atomically by `--refresh` — no cross-table FK becomes stale. However, these IDs must **not** be used as external references (in exported reports, client systems, or any integration). The stable natural key for a unit is the "Numéro unique d'unité" value from the Rent Roll (e.g. `1175-106 Chamonix`); use that for any external reference or cross-system join. The `--write` path now pre-flights: if any unit rows already exist it aborts with an explicit error pointing to `--refresh`.

`patch_vacant_units.py` (the one-off script used to ingest the 9 units as IDs 4285–4293) is now superseded — the widened month filter means the main script picks them up in a normal run. The patch script has been moved to `drive_pipeline/ingestion/archive/` for reference.

### 5n. Boucher-Wilfrid-Caron project split — completed 2026-10-06

The single project "Boucher-Wilfrid-Caron" (project_id=11) covered two physically distinct buildings on different streets. Split into two separate projects with provenance:

| New project_id | nom_unique_projet | adresse_quickbooks | building_id |
|---|---|---|---|
| 73 | Wilfrid-Caron | 10943-10945-10947, rue Wilfrid-Caron | 22 |
| 74 | Boucher | 5-7-9, rue Boucher | 23 |

The 24 maintenance_request rows that referenced project_id=11 were split: 16 reassigned to project 73 (building 22), 8 to project 74 (building 23), using `building_id` as the exact tiebreaker. Project 11 deleted. Total projects: 74.

### 5o. Table Fondamentale — Phase 1 column ingest — completed 2026-10-06

Nine new columns ingested from live TF sheet (`1776VvxgPCtlSzXS238A6sdLjXQ0wG3Qdlf3Fy9dk5SE`):

| Column | Table | TF col | Notes |
|---|---|---|---|
| `accounting_project_number` | project | 3 | integer stored as varchar (e.g. "162") |
| `nb_units_total` | building | 7 | |
| `nb_units_residential` | building | 8 | |
| `actif_inactif` | building | 13 | "Actif" or "Inactif" |
| `municipality` | building | 16 | |
| `property_type` | building | 17 | e.g. "Multilogement", "Duplex ou triplex" |
| `dogs_allowed` | building | 52 | boolean; Oui→True, Non→False |
| `web_building_name` | building | 54 | short display name for website |
| `web_slug` | building | 55 | URL slug |

179 buildings updated, 72 projects updated, 1495 provenance rows written. 1580 Perigord was unmatched at this stage (expected — added in Task D).

**HOLD — `nb_units_commercial` (col 10):** 173/181 buildings have col10 = col7 (commercial count = total count), which is plainly wrong for residential buildings. Only 5 buildings have a plausible distinct commercial count. Column is unreliable across the portfolio and was not ingested.

**HOLD — finance cluster (cols 14/15/5):** `Prix d'achat`, `Date d'acquisition`, `Nom de Classe pour Quickbooks` require a new table with no current schema. Minimum schema needed: a `building_financial` or `project_acquisition` table with `(project_id, prix_achat numeric, date_acquisition date, nom_classe_quickbooks varchar)`. No table created; no data ingested. These three columns cover 181 buildings and are clean (numeric prices, ISO dates). Create when schema is approved.

### 5p. Unit discrepancy audit — completed 2026-10-06 (Task C)

Full audit of the 16 buildings with ±1 unit count gap between live DB and TF. Net gap: +14 DB vs TF across matched buildings (+16 surplus − 2 missing).

**Surplus (DB > TF) — no action needed:**

| Category | Count | Detail |
|---|---|---|
| TOIT/rooftop rows (grandeur=N/A) | +10 | 315-317 St-Jean (+3), 1035 Pie-XII (+2), 85 Carmichael (+2), 125 Grande Allee Ouest, 3150 France-Prime, 4244 Sauges |
| Non-residential service rows | +2 | 350 Ch Ste-Foy (Vidéotron), 888 Hypolite-Bernier (RECOUV210) |
| Null-apt entries excluded by TF | +3 | 636-640-646 St-Jean (null/N/A pair), 1180 Brown (apt=None size=5½), 200-220 Grande Allee Est (apt=None size=1955sqft) |
| Known exact duplicate (§5l) | +1 | 4298 Roses: units 3126+3127, both apt='104' |

**Missing (DB < TF) — source gaps in rent roll (see §5s):**

| Building | Gap | Detail |
|---|---|---|
| 325 Marais | −1 | Building in DB, 0 unit rows. MRR has no row for it. |
| 610-620 Grande Allee / 1190 Brown | −1 | MRR has 620/apts 1,3,4,5,6 — no apt 2. DB=11, TF=12. |

These two missing units are source gaps: absent from the MRR, not ingestion failures. Client input needed before any ingest (see §5s). The third previously-listed missing unit (4875 Saint-Georges apt 3) was resolved by the §5r correction — it was unit_id=3709 misfiled under building 147.

### 5q. 1580 Perigord — added to DB — completed 2026-10-06 (Task D)

New building added: **building_id=180**, project_id=75 ("Perigord"), sector=Quebec-Est, 38 residential units (TF-confirmed), 1988, 4 floors, 1 elevator, `actif_inactif='Actif'`, `dogs_allowed=True`, `property_type='Multilogement'`.

39 MRR rows ingested (39 = 38 residential + 1 "Local récréatif" apt 108, a common room that TF correctly excludes from its 38-unit count — same pattern as TOIT rows). Script: `drive_pipeline/ingestion/ingest_perigord_units.py`.

| Table | Rows added |
|---|---|
| building | 1 (building_id=180) |
| project | 1 (project_id=75) |
| unit | 39 (unit_ids 4294–4332) |
| lease | 39 |
| tenant | 48 (tenant_ids 6091–6138) |
| tenancy_record | 47 |
| parking_assignment | 22 |

`_UNMATCHED_BUILDING_NAMES` cleared in `ingest_units_leases_tenants.py`.

**Provenance gap — resolved 2026-10-06:** The original `flush()` call in `ingest_perigord_units.py` discarded its return value, losing the buffer. 249 provenance rows backfilled via `backfill_perigord_provenance.py` (provenance_ids 191559–191807: unit columns + tenancy_record fields). Root cause fixed: `flush_to_db(conn)` added to `provenance.py`; script updated to use it.

**FT crosswalk — Perigord still unmatched:** `build_crosswalk.py` matches FT addresses against MRR addresses. The FT has "Perigord Street" but the MRR has "rue du Périgord" — address translation needed in the crosswalk algorithm to resolve this. Building is correctly in DB; the crosswalk link requires a follow-up fix.

### 5r. 4837-4847 Saint-Georges — misfiled unit corrected — 2026-10-06

Resolved mechanically. The three apt '3' rows (unit_ids 3677, 3689, 3709) were not a triplicate. unit_id=3709 had `rue='4875, rue Saint-Georges'` but was assigned `building_id=147` (4837-4847 Saint-Georges). Building 149 is '4875 Saint-Georges', a separate building — the unit was misfiled, not duplicated.

**Evidence:** unit.rue civic (4875) falls outside building 147's civic range (4837–4847).

**Fix applied 2026-10-06:** `UPDATE unit SET building_id = 149 WHERE unit_id = 3709`

Provenance row logged (`source_type='corrected'`, rue/building_id mismatch cited as evidence).

**Verified:** building 147 → 24 units ✓ (matches TF), building 149 → 7 units ✓ (matches TF).

**Broader civic-range check (2026-10-06):** All 4331 units audited against their building's civic range. 48 rows across 7 buildings flagged. All confirmed benign:
- 4 multi-address complexes (bldg 73/Costebelle, 79/Banville, 134/Saint-Georges, 31/Carmichael): TF unit count matches DB exactly — wider address spread is structural.
- 3 TOIT/null-apt rows whose MRR source carries a neighbouring civic in `rue` (bldg 58/125 Grande Allee Ouest, bldg 140/4244 Sauges, bldg 14/1180 Brown): already classified as TF-excluded surplus in §5p.

No additional misfilings found.

### 5s. Two missing units — questions for François (source gaps confirmed 2026-10-06)

Both units appear in the Table Fondamentale's count but have no row in the Master Rent Roll. Confirmed as source gaps — not ingestion failures.

**325 Marais (building_id=120, TF: 1 unit):**
The building exists in our database with zero unit rows because the rent roll has no entry for it. The Fundamental Table counts 1 unit here.

*Question for François:* Is there a real tenant at 325 Marais? If yes, the rent roll is missing their entry and we have no lease, tenant, or rent record for them — revenue may be unrecorded. If not, should the TF's count of 1 be corrected to 0?

**620 Grande Allée O. apt 2 (building_id=16, TF: 12 units, DB: 11):**
The rent roll has apartments 1, 3, 4, 5, 6 at 620 Grande Allée O. — apartment 2 is absent. No row exists anywhere in the rent roll for this unit.

*Question for François:* Is apartment 2 at 620 Grande Allée O. currently occupied or vacant? If occupied, the tenant, lease, and rent are entirely absent from the rent roll. If vacant, the MRR should have a vacancy row so the unit exists in our DB.

### 5l. Two pairs of exact duplicate units in the rent roll — client question (2026-10-02)

The unit table contains two pairs of rows that are identical on **every column** (rue, numero_appartement, grandeur):

| unit_ids | building_id | rue | numero_appartement | grandeur |
|---|---|---|---|---|
| 3126, 3127 | 141 | 4298, rue des Roses | 104 | 4 1/2 |
| 3294, 3295 | 156 | 12085, av. Berlioz | 310 | 4 1/2 |

These originate from duplicate rows in the source Master Rent Roll. They were discovered because `build_unit_index` (unit_id resolution for maintenance tickets) uses a `(building_id, civic, apt)` key and encountered two candidates for each pair, making them unresolvable without a tiebreaker.

**Client question for François:** Are these genuinely two separate units (e.g. a subdivided apartment rented to two different tenants under the same address/number), or are they data-entry duplications in the rent roll?

If **duplications**: each pair should be merged to one unit row. Note that each of the four unit_ids currently has its own `lease` row (and possibly a `tenancy_record` row) — a merge requires deciding which lease is canonical, migrating any tenancy references to the surviving unit_id, and deleting the duplicate. This cannot be done automatically; it requires confirming with François which row is the live tenant record.

If **genuinely two separate units**: the rent roll should be corrected to use distinct apartment numbers or addresses to make them distinguishable. The current state makes them permanently unresolvable via address matching.

**Practical effect:** maintenance tickets for either address are left with `unit_id = NULL` until the ambiguity is resolved. No wrong match is written.

### 5m. building 120 (325 Marais) — camera source says "No" but cameras are documented (2026-10-02)

The security spreadsheet (`Cameras, Intercoms, Fobs, Garages - Internet Access.xlsx`) records `installed = No` for building 120. However the same row contains a fully documented camera system: `platform = hik_connect`, `ip_domain = sib325marais.dyndns.org`, `port = 8001 ou 8002`, `username = user1`. The source value is self-contradictory.

`installed` was set to `'Oui'` in the DB with `source_type='inferred'`, noting that the source value is contradicted by the platform/IP data. The source spreadsheet should be corrected to `Yes`.

### 5h. "Majordome" — resolved 2026-10-02

**Building affected:** 139 Abadie (building_id=2).

Added as `employee_id=43`: `initials='MAJO'`, `employment_type='contractor_company'`, `role='Sous-traitant — appels de service et entretien'`. Their primary function is service-call and maintenance coverage for rive-sud de Québec buildings. The cleaning assignment at Abadie 139 is temporary cover for a staffing shortage, per François. `building_employee_assignment` row written for building_id=2. Provenance_ids 181934–181935.

### 5i. Oak 1321 — resolved 2026-10-02

**Conclusion:** Oak 1321 is **correctly absent from the database**. François confirmed: *"This property can be removed from the application completely. This is my personal residence."* It is not a SIB-managed portfolio building.

All Drive artifacts that reference Oak 1321 — the Fiche Technique (`Oak av, Québec (1321) Ancienne.xlsx` in the Old Technical Sheets folder), the Maintenance Drive folder (`Oak 1321 (Important Documents)`), and the ménage assignment for Mélanie Duquette (Master du ménage R106) — relate to François's personal residence, not a portfolio property. No DB rows are needed; no action required.

### 5a. Ascenseur errors — 2 buildings where TF is wrong

TF records 0 elevators for both buildings; FT evidence contradicts this. The FT value (True) was ingested. Two provenance rows exist per building: one for the overridden TF value (`ingested_value = NULL`) and one for the FT value (`ingested_value = True`).

| building_id | adresse | TF value | FT evidence | Current DB | Status |
|---|---|---|---|---|---|
| 150 | 350 Ch Ste-Foy | False (0 elevators) | "2 Ascenseurs mécaniques au toit" | True | **Open** — awaiting client confirmation |
| 152 | 117 Ste-Anne | False (0 elevators) | Elevator vendor + contact in FT | **False** | **Resolved 2026-10-02** — client confirmed elevator belongs to 125 Ste-Anne (bldg 153), not 117 |

The FT file `Ste-Anne rue, Québec (125) (117).xlsx` covers both addresses; the elevator was incorrectly attributed to 117 during ingestion. Building 152 reverted to `ascenseur = False` via `client_correction` provenance row (provenance_id=181930).

**Open question for client (building 150 only):** Does 350 Ch Ste-Foy have elevators?

### 5c. 8 buildings with no sib_territory in Table Fondamentale

The following buildings have no territory assigned in TF. They were written to the `building` table with `sector_id` pointing to an "Inconnu" placeholder sector (sector_id=7). All belong to two projects.

| building_id | building | project |
|---|---|---|
| 33 | 1175 Chamonix (1 a 26) | Chamonix |
| 34 | 1175 Chamonix (27 a 63) | Chamonix |
| 35 | 1175 Chamonix (65 a 103) | Chamonix |
| 36 | 1175 Chamonix (104 a 143) | Chamonix |
| 37 | 1175 Chamonix (144 a 169) | Chamonix |
| 38 | 1175 Chamonix (170 a 200) | Chamonix |
| 39 | 7885 Sully (24 a 46) | Chamonix |
| 120 | 325 Marais | Marais |

**Open question for client:** What territory do Chamonix and Marais belong to? Once confirmed, update TF and re-run `ingest_building.py --write` to correct `sector_id` for these 8 buildings.

### 5e. Beauport-Charlesbourg sector gap

`secteurs-et-equipe.md` defines a **Beauport-Charlesbourg** calendar sector (colorId=3, Grape/violet) with no corresponding row in our `sector` table. Our schema merges it into `Quebec-Est` (sector_id=4, colorId=4). The reference doc's building repères list Chamonix and Sully under a heading that covers both colorId=3 and colorId=4 — so their calendar sector is ambiguous.

Of the 8 buildings currently in the "Inconnu" placeholder sector (sector_id=7, see §5c), 7 are Chamonix buildings. If Beauport-Charlesbourg becomes a distinct sector row, those 7 buildings are the likely candidates for reassignment. However, Marais (the 8th Inconnu building) is not a Beauport-Charlesbourg address and would still need its own resolution.

**Open question for client:** Should Beauport-Charlesbourg be a distinct sector? If so, which calendar colorId applies to Chamonix and Sully — colorId=3 (Beauport-Charlesbourg / Grape) or colorId=4 (Québec-Est / Flamingo)? The reference doc lists them under a heading covering both colors. Resolving this would also close the §5c open question for those 7 buildings.

Do NOT reassign buildings out of Inconnu until the client confirms — the evidence is suggestive but not conclusive.

**Non-answer 2026-10-02:** We asked François about Beauport-Charlesbourg but he answered about Beaubois and Charlemont (two different buildings) instead. The Beauport-Charlesbourg / Chamonix-Sully sector assignment question is **still open** — needs re-asking with explicit reference to the colorId=3 / colorId=4 ambiguity in §5c.

### 5f. Source-data typos in calendar ticket titles — two unresolved employee codes

Two `maintenance_request` rows carry employee codes in `assigned_employee_code_raw` that do not match any `employee.initials`. Both have `assigned_employee_id = NULL` and are intentionally left uncorrected — rewriting source data to match our assumption is avoided throughout this project.

| request_id | raw_title (excerpt) | code_raw | Resolution |
|---|---|---|---|
| 2006 | `VIBBR 640 St-Jean : Conversion électrique` | `VIBBR` | **Resolved 2026-10-02** — confirmed typo for `VIBR`. Updated: `assigned_employee_code_raw='VIBR'`, `assigned_employee_id=40`. |
| 907 | `FRBE CHBE 3150-25 France-Prime: Ajouter des paniers d'épicerie…` | `FRBE` | **Resolved 2026-10-02** — François Bélanger (Direction/coordination). Added as `employee_id=42` (`initials='FRBE'`, `employment_type='staff'`). `assigned_employee_id=42` written. |

### 5g. RLS role assignment for STBE and VIBR — requires client confirmation

STBE (Stéphane Beaudoin, *"Coordonnatrice entretien bâtiments"*) and VIBR (Vincent Brouillette, *"Heavy and preventive maintenance manager"*) are currently assigned the `technician` RLS role, which scopes their visibility to their own sector and assigned tickets. Their job titles and the Contacts file's role field suggest coordinator-level responsibility, but `secteurs-et-equipe.md`'s explicit coordinator list (CALE, CHGE, PISI, SETO, DISP) excludes them. VIBR is observed in calendar data delegating work to other employees and vendors, consistent with a coordinator role.

**Open question for client:** Should STBE and/or VIBR have coordinator-level access — meaning visibility into all maintenance requests portfolio-wide, plus tenant financial data (rents, amounts owed, deposits) and guarantor records? Changing this is a one-line UPDATE to `employee_role` once confirmed.

### 5d. Suspicious QuickBooks address overlaps

Detected during project deduplication — two pairs of projects share the same QB address, which may indicate a data entry error in TF:

| Project A | Project B | Shared QB address |
|---|---|---|
| Place de l'Entente | Confluent | 4032-4040, rue du Confluent |
| Norvege | Le Claridge | 200-220, Grande Allée Est |

**Open question for client:** Are these correct (same address, different project codes) or a TF entry error?

### 5b. Année de construction discrepancies — values differ between TF and FT

TF value was ingested per precedence rule; FT value is preserved as a second provenance row (`ingested_value = NULL`) so the discrepancy is queryable. No winner was chosen — these are flagged for client review.

40 buildings flagged. Some FT entries contain non-numeric values (noted); these are format differences where the year itself agrees. The remaining ones are genuine numeric disagreements.

| building_id | adresse | TF year | FT year | Note |
|---|---|---|---|---|
| 13 | 1897 Bastien | 1972 | 1970 | |
| 15 | 580 Grande Allee / 1185-1195 Brown | 1954 | 1958 Batiment pièce sur pièce | FT has extra text |
| 18 | 2240-2254 Bergemont | 1950 | 1949 | |
| 20 | 4069 Blain | 1994 | 1995 | |
| 21 | 4071 Blain | 1991 | 1995 | |
| 60 | 3040 a 3050 Chatelets | 1962 | 1964 | |
| 61 | 3054 a 3062 Chatelets | 1962 | 1964 | |
| 62 | 3066 a 3080 Chatelets | 1962 | 1964 | |
| 63 | 3084 a 3094 Chatelets | 1962 | 1964 | |
| 64 | 2829 Chemin St-Louis | 1972 | 1969 (permis de construction) | FT has extra text |
| 72 | 4032-4034-4040 Confluent | 1972 | 1970 | |
| 73–81 | 5835–5895 Costebelle / 5890+5930 Banville (9 buildings) | 1976 | 1972-1976 | FT has range; TF year is within it |
| 85 | 135 Des Cedres | 1972 | 1970 | |
| 89 | 2415-2431 Evangeline / 2654-2658 Mgr-Gosselin | 1950 | 1968 (permis de construction portiques d'entrée) | FT refers to addition, not original |
| 91 | 1017 Duchesneau | 1971 | 1968 | |
| 109 | 420-432 49e Rue Ouest | 1972 | 1971 | |
| 110 | 435-437 48e Rue Ouest | 1977 | 1972 | |
| 111 | 440 48e Rue Ouest | 1977 | 1972 | |
| 112 | 442-462 49e Rue Ouest | 1970 | 1971 | |
| 114 | 460 48e Rue Ouest | 1977 | 1972 | |
| 115 | 476 49e Rue Ouest | 1972 | 1971 | |
| 119 | 3034-3038-3052-3054 Lechasseur | 1965 | 1965 (permis de construction) | Same year, format only |
| 121 | 860 Marguerite-Bourgeoys / 1410 Longueuil | 1950 | 1949 | |
| 128 | 636-640-646 St-Jean | 1973 | 1972 | |
| 132 | 3485-3495 Petitclerc | 1970 | 1969 | |
| 138 | 846 Ch Ste-Foy | 1971 | 1974 | |
| 143 | 4410 Roses | 1971 | 1969 | |
| 149 | 4875 Saint-Georges | 1965 | 1970 | |
| 152 | 117 Ste-Anne | 1820-1916 | 1914 | TF has range; FT has single year |
| 153 | 125 Ste-Anne / 25 Ste-Ursule | 1820-1916 | 1914 | TF has range; FT has single year |
| 157 | 4775 Ste-Genevieve | 1977 | 1982 | |
| 159 | 7-11 Terrasse Orleans | 1970 | 1968 | |

**Open question for client:** Which year is authoritative for each building — the year in Table Fondamentale or the Fiche Technique? Several patterns to note:
- **Costebelle group (9 buildings):** FT says "1972-1976" (a range); TF says 1976. These may both be correct — TF records completion, FT records the construction period.
- **Ste-Anne (2 buildings):** TF has "1820-1916" (range for historic buildings); FT says 1914. Both may be correct.
- **Chatelets group (4 buildings):** All share TF=1962, FT=1964 — suggests a systematic difference in which date each source records.
- **Lechasseur:** Same year (1965) in both; FT has "permis de construction" suffix. Not a genuine discrepancy — no action needed.

---

## 9. Schema — Dead Columns and Deferred Fields

### 9a. sector.secteur — DEAD, recommend drop

The `sector` table has a `secteur` column that is 0% populated across all 7 rows and is written by no ingestion script. The DBML comment describes it as related to a "File 3 CONTACTS concept — do NOT merge, relationship TBD." That relationship was never implemented. No RLS policy, view, or query references `secteur`. It is dead schema.

**Recommendation:** `ALTER TABLE sector DROP COLUMN secteur;` and remove the column from `schema/sql/schema.sql` and `schema/dbml/2_complete_system_updated.dbml`.

### 9b. building.legacy_code — cross-system consistency check (2026-09-29)

`legacy_code` is now filled for 175/179 buildings (4 null: terrain parcels 10, 11; Corail 44; Marais 120). The column is a cross-reference to the fire-protection filing system's A-code scheme and is NOT unique — 31 A-codes span 2 or more buildings because the fire-protection system uses a coarser, project-level grain than our building table.

**The two systems agree on 29 of 31 multi-building A-codes.** For those 29, every building sharing an A-code also shares a `project_id` — a direct cross-validation between Table Fondamentale's project groupings and the fire-protection filing system's property codes. These are independent client sources; agreement is meaningful.

**Two A-codes disagree with project_id — flagged as client questions:**

| A-code | Fire-protection view | TF view | Discrepancy |
|---|---|---|---|
| **A060** | All four Petitclerc addresses (3365, 3410-3420, 3465, 3485-3495) are one property | TF splits 3485-3495 into a separate project (`project_id=52`, "Petitclerc 3485-3495") | Should 3485-3495 be its own project, or merged with Petitclerc (`project_id=51`)? |
| **A076** | All six Saint-Georges addresses (4837–4875 and 6791–6799) are one property | TF distinguishes "Saint-Georges" (4837–4875, `project_id=57`) from "Place de l'Entente" (6791–6799, `project_id=54`) | Are these genuinely separate projects, or were they once one and split in TF? |

**13 projects hold buildings with different A-codes — expected, not a discrepancy.** Fire protection assigns a unique code per civic address or tight cluster; TF groups geographically-distributed buildings into one management project. Examples:
- "Le 48" (project_id=41) spans buildings on 4th Ave, 48th Rue, and 49th Rue — three separate A-codes (A003, A005, A006), one TF project.
- "Roses-Platanes-Sauges" (project_id=56) covers Roses, Platanes, and Sauges streets — three separate A-codes (A066, A067, A061), one TF project.
- "France-Prime-Duchesneau" (project_id=34): 1017 Duchesneau = A030; 3140/3146/3150 France-Prime = A036. Two civic clusters, two A-codes, one TF project.

These are different filing philosophies, not errors.

### 9c. service_visit records inspection SCHEDULES, not RESULTS

The 170 rows in `service_visit` represent **fire inspection due dates** — when an inspection is scheduled to happen. They do not represent completed inspections. As of 2026-09-29:

- `completed_date`: 1/170 populated (0.6%)
- `result`: 0/170 populated
- `deficiencies`: 86/170 populated (from the fire protection source spreadsheet — known deficiencies already noted before inspections)

**The system currently answers "when is the next fire inspection due" but cannot answer "did it pass."** Closing that loop requires an operational process: either someone enters outcomes manually after each inspection, or actual inspection reports (PDFs in the fire-protection per-building folders) are ingested. This is not a code fix — it is an operational gap.

### 9d. building_fire_system status columns are sparse because the SOURCE is sparse

The `building_fire_system` table has 170 rows (one per building), but the status columns are near-empty:

| Column | Populated |
|---|---|
| `panel_control_status` | 1.2% |
| `smoke_detector_status` | 0.6% |
| `sprinkler_status` | 7.1% |
| `emergency_panel_status` | 5.9% |
| `hose_status` | 5.9% |
| `co2_status` | 4.7% |

This is **not a parsing failure.** The source spreadsheet (`Fire_Protection_EN.xlsx`, MASTER sheet) simply did not have data in these cells for most buildings. The ingestion script read what was there.

**Client data-quality question:** The fire protection tracking spreadsheet is the canonical source for panel/sprinkler/smoke-detector status per building. If this information exists in annual inspection reports or elsewhere, it should be entered into the spreadsheet (or ingested from the reports directly). Until the source is populated, these DB columns will remain near-empty.

### 9e. building_fire_system — two columns added 2026-10-02 (plumbing, not recovered data)

Two columns were added to `building_fire_system` and wired up in `ingest_fire_protection.py`:

| Column | Source col | Current population | Notes |
|---|---|---|---|
| `corrective_actions_date` (date) | r[7] "Date corrective actions completed" | **0 rows** | Only non-null source value is the string `'Pending'`, which cannot be stored as a date → NULL. Column is wired; will populate when SIB enters real completion dates. |
| `piezzo_status` (varchar) | r[11] "Piezzo dans logement" | **1 row** — building 150: `'To be installed'` | Was previously appended into `notes` as `"Piezzo: {value}"`; now lives in its own column. The `"Piezzo: To be installed"` fragment was stripped from building 150's notes. |

These are not recovered data — the source simply hasn't been filled in. The schema is now correctly wired so future source updates flow through on re-ingest (note: re-ingest requires truncating `building_fire_system` first, as the script uses plain INSERT with no ON CONFLICT).

---

## 8. maintenance_request — Populated Fields Summary (2026-10-06)

### unit_id — 5,353 rows populated (50.7%)

Both write phases computed unit_id at write time via `build_unit_index` / `resolve_unit_id`. A full re-resolution pass was run on 2026-10-06 across all 10,565 rows; it found 1 additional row (request_id=2264, 4875-3 Saint-Georges → unit_id=3709 — newly resolvable after the §5r building-id correction).

**Combined rate: 5,353 / 10,565 = 50.7%**

| Phase | Rows | unit_id populated | Rate |
|---|---|---|---|
| Phase 1 (Aug 11→Sep 25) | 2,374 | 1,233 | 51.9% |
| Phase 2 (Mar 01→Aug 10) | 8,191 | 4,120 | 50.3% |
| **Total** | **10,565** | **5,353** | **50.7%** |

Resolution rate splits nearly identically across phases — title-only March–June tickets carry unit labels as often as structured ones. The rate difference between formats comes from body structure, not ticket era:

| body_format | n | unit_id populated | Rate |
|---|---|---|---|
| v10_plaintext | 1,584 | 1,181 | 74.6% |
| v10 | 450 | 263 | 58.4% |
| unparsed_body_format | 8,371 | 3,837 | 45.8% |
| gravity_forms | 148 | 67 | 45.3% |
| belanger_compact | 12 | 5 | 41.7% |

`v10_plaintext` leads because v10 events carry an explicit `UNITE:` field in the body, yielding a clean unit label. The `unparsed_body_format` rate (45.8%) is nearly identical to gravity_forms — title-only tickets extract their unit label from the title and match at the same frequency.

**NULL breakdown (5,212 remaining):**
- No unit_label at all (no extractable unit in the title, common-area events, admin tickets): 3,113 rows
- Ambiguous apartment number — same apt number in multiple units under the same building (multi-address buildings like Wilfrid-Caron 10943/10945/10947 all sharing apts 1–8): 1,143 rows
- apt-only label with no match in unit table (includes Chamonix 1175-* units absent from rent roll): 350 rows
- Civic+apt label with no matching unit: 137 rows
- Label has a non-numeric, non-civic-apt pattern (common-area descriptors): 469 rows

The "apt-only fallback" tier (accepting civic mismatch when apt is unambiguous) was evaluated and dropped after inspection revealed civic gaps of 120–325 and in one case a completely different street name — not format variants, but likely wrong labels.

### vendor_id — intentionally 0% (client question open)

`vendor_id` on `maintenance_request` was not populated and is not planned for automatic population. Reason:

`subcontractor_name` is a free-text coordinator decision log (552 distinct values across 2,374 rows). It records **whether** an external vendor was considered and **why**, not **which vendor worked the ticket**. Examples of what the field contains:

- `"Non — interne"` (524 occurrences) — internal handling, no vendor
- `"Non — interne (Fortin à considérer si…)"` — conditional on diagnosis; vendor not assigned
- `"Oui — Boucher Lortie / Newtech (électricité)"` — two vendors, ambiguous
- `"À déterminer après diagnostic"` — unresolved at ticket creation
- Multi-line structured notes with dates, initials, and follow-up instructions

Only ~65 of 2,374 rows (~3%) name a single vendor in a cleanly extractable pattern (`"Oui — [vendor name]"`). Populating `vendor_id` from the remaining 97% would assert false facts — e.g. a ticket saying `"Non — interne (Fortin si refoulement avéré)"` would become `vendor_id = Plomberie Fortin`, which is wrong.

**Client question for François:** if SIB wants "which vendor actually worked this ticket" as a queryable fact, it needs to be captured at a different point in the workflow — either:
1. A separate field filled at ticket **close** (when the vendor assignment is known, not estimated)
2. A structured `vendor_assignment` record linked to `maintenance_request`, written when the vendor is dispatched

The current `subcontractor_name` field is useful as a coordinator planning note but cannot be trusted as a vendor FK.

---

## 8. maintenance_request — Ingestion Watermark

### What was ingested

Two write runs cover the full ingest window. Events are non-overlapping; combined coverage is **2026-03-01 → 2026-09-25**.

| Write | Date | Window | maintenance_request | maintenance_followup_entry |
|---|---|---|---|---|
| Phase 1 | 2026-09-26 | 2026-08-11 → 2026-09-25 | 2,374 rows | 2,402 rows |
| Phase 2 | 2026-10-06 | 2026-03-01 → 2026-08-10 | 8,191 rows | 1,588 rows |
| **Total** | | | **10,565** | **3,990** |

Calendars ingested:

| Calendar key | Calendar ID |
|---|---|
| `main` | `maintenance@sibelanger.com` |
| `st_maj` | `8d55093fb316f4eda1504cd853462fea86f64a4e78556e0924f3c994d2c63bf8@group.calendar.google.com` |

data_provenance rows for maintenance_request events: **117,446** total (44,337 Phase 1 + 73,109 Phase 2).

### There is no scheduled refresh

The ingestion was a single manual run. There is no cron job, webhook, or recurring task that keeps the DB in sync with the calendar. Events added, edited, or cancelled after 2026-09-25 are not reflected in the DB.

### There is no watermark

Checked every table and column in the `public` schema. No `last_synced_at`, `watermark`, `sync_state`, or equivalent field exists anywhere in the database.

### Re-running the script today would not create duplicates

A partial unique index guards against re-insertion of known events:

```sql
CREATE UNIQUE INDEX mr_event_id_key ON maintenance_request (event_id)
WHERE event_id IS NOT NULL;
```

The write uses `ON CONFLICT DO NOTHING`. A re-run against the same 45-day window would insert 0 rows for existing events and add only any new events that appeared after the original run. This is safe but not useful — it only covers the original window. Events outside that window are ignored.

### URL cross-reference resolution — Phase 2 results (2026-10-06)

After extending the window back to March 2026 and re-running `resolve_url_refs()` across all 10,565 rows:

| Resolved references | Before Phase 2 | After Phase 2 | Net new |
|---|---|---|---|
| `maintenance_request_history` entries | 83 | 417 | +334 |
| `duplicate_of_request_id` populated | 32 | 66 | +34 |
| `synergy_request_ids` populated | 12 | 55 | +43 |

Of the 474 rows with calendar URL references in `historique_raw`, the outside-window rate dropped from ~82% (Aug–Sep window only) to ~12% (full Mar–Sep window). The 57 still-unresolved references point to events prior to March 2026 and remain in `historique_raw` only.

**Diminishing returns past March 2026:** Going from a 45-day window to a 7-month window moved the resolution rate from 18% to 88% — a 70-percentage-point gain. The remaining 12% (57 references) point to events before March 2026. Each further month of backfill before March would recover a small share of those 57. This empirical result — roughly 1 in 8 references still unresolvable at the current window — is the baseline for any future decision about extending the backfill. The marginal return on extending before March 2026 is sharply lower than it was extending from August to March.

### What incremental sync would require

Neither prerequisite currently exists:

1. **A sync state table** recording the last successfully ingested `updated_at` timestamp per calendar, so the next run knows where to start. The Calendar API supports `updatedMin` filtering; the script does not use it.

2. **A `updated_at` / `last_modified` filter in the Calendar API call** in `parse_calendar_requests.py`. Currently the script pulls by date range only (`timeMin`/`timeMax`), which will miss edits to old events.

Building recurring sync from the current state requires adding both: a `calendar_sync_state` table (or equivalent) and an `updatedMin`-based query path in the Calendar client.

### Body format — July 2026 workflow change (why ~89% of early events are title-only)

Google Calendar ticket bodies transitioned to structured formats in **July 2026**. Events from March through June 2026 were created with an older convention: the title carries the full ticket description and the body field is empty or contains only an unstructured note.

The parser reports `body_format = 'unparsed_body_format'` for events where no known format was detected. For the March–June cohort this rate is approximately **89%** — a correct count, not a parser failure. There is no body structure to parse in that period.

The structured formats (`gravity_forms`, `belanger_compact`, `v10`, `v10_plaintext`) appear only in July 2026 and later. The `problems`, `triage_summary`, and `tri_raw` columns are correspondingly NULL for most March–June tickets; the information exists only in the ticket title (stored in `title_raw` and partially extracted into `problem_summary` via title-only parsing).

### building_id match ceiling — 89.3% (real causes, not parser gaps)

Approximately **89.3%** of the 10,565 tickets can be matched to a `building_id`. The remaining ~10.7% are not parser failures — they are cases where the address in the title is structurally unmatchable to any building row:

- **Parenthetical time annotations** — e.g. `"3140-205 France-Prime (avant 2 mars)"` where the parenthetical suffix corrupts the civic pattern and confuses the matcher.
- **Abbreviated ordinal streets** — e.g. `"48e"` and `"41e"` used as street references in ticket titles; these do not match the canonical DB address format (`"48e Rue Ouest"`, etc.).
- **3-part civic numbers** — e.g. `"3086-202-302"` (building-apt-unit or building-floor-apt style); the parser extracts only the first civic segment and the remainder mismatch the building's stored address.
- **Non-building events** — tickets labelled "Facture", "Osen", "DISP" and similar administrative or portfolio-level headings with no buildable address; these legitimately have `building_id = NULL`.

These four categories account for essentially all unmatched rows. Improving the ceiling above 89.3% would require address normalisation rules for each pattern — feasible but low priority given that the already-matched 89.3% covers the operational ticket volume.

### Multi-assignee tickets — only first assignee stored

Approximately **30 tickets** carry multiple employee codes in the title — e.g. `CHBE ANSI 3140-205 France-Prime: Réparer la fenêtre`. The parser extracts only the **first** recognisable code and stores it as `assigned_employee_id`. The full raw string (e.g. `"CHBE ANSI"`) is preserved in `assigned_employee_code_raw`.

This is a deliberate limitation: the schema has a single `assigned_employee_id` FK. Multi-code patterns appear to represent delegation or joint dispatch — the first code is typically the coordinator, the second the assigned technician. Without a `ticket_assignment` join table the second assignee cannot be stored relationally. The raw string in `assigned_employee_code_raw` is the ground truth; relational lookup via `assigned_employee_id` covers the primary assignee only.

### Inferred employees — 7 codes added, unconfirmed (worth asking François)

Seven employee codes appear in the March–August 2026 corpus that are not in the SIB Contacts file. They were added to the `employee` table with `source_confidence = 'inferred_from_calendar'` and `employment_type = 'unknown'`. They may be former staff, sub-contractors known to coordinators but not in Contacts, or retired employees.

| initials | employee_id | occurrences |
|---|---|---|
| MAPI | 44 | 103 |
| GELE | 45 | 31 |
| ANSI | 46 | 30 |
| YVLI | 47 | 11 |
| MAMO | 48 | 4 |
| JMBO | 49 | 4 |
| ALHA | 50 | 2 |

Four single-occurrence codes (GALS, FRLE, CH, NICO) were **not** given employee rows — they remain in `KNOWN_EMPLOYEE_CODES` for address stripping only and produce no `assigned_employee_id`. CALLE (1 occurrence, probable typo for CALE) is handled the same way.

**Recommended question for François:** Do you recognise any of these initials — MAPI, GELE, ANSI, YVLI, MAMO, JMBO, ALHA? They appear repeatedly in maintenance tickets from March–August 2026 but are not listed in the Contacts file. Are they current or former employees?

### KNOWN_VENDOR_CODES — general strip-but-don't-assign list (not vendor-only)

`KNOWN_VENDOR_CODES` in `parse_calendar_requests.py` strips tokens from the address path without writing them to `assigned_employee_code_raw`. Despite the name, the set is not limited to vendors:

- `MAXI`, `TK` — ascenseurs vendors
- `ERIC` — extermination vendor
- `PDQ` — garage door vendor at Châtelets
- `SAC` — **inter-code dispatch annotation** (appears between two employee codes, e.g. `PISI SAC CHGE`; it is not a person or vendor)
- `TEST` — test-event token; not a vendor or employee

`SAC` was the key non-obvious entry: inspecting all uppercase-SAC matches in the DB confirmed it always appears between two known employee codes, never as a primary assignee. It was added to this set (not to `KNOWN_EMPLOYEE_CODES`) so it is stripped cleanly without creating a spurious employee assignment.

---

## 7. Ingestion Process — Lessons and Guards

### 7a. maintenance_request free-text is French by accident

All `problems`, `problem_summary`, `triage_summary`, `tri_raw`, `historique_raw`, and prose-field columns in `maintenance_request` are stored in French. This is the correct and desirable outcome — it preserves the words that field staff write and read natively, and matches what tenants and technicians actually said.

**It was not intentional.** `write_maintenance_requests.py` contains a translation step (Phase 4: `_cal._translate_prose_fields(record)`) that was verified producing English output in dry-run testing. During the actual `--write` run that populated the DB, this step executed but silently produced no change — the `ANTHROPIC_WORKSPACE_ID` header was missing from the API call at the time, causing the translation to fail without raising an exception. The DB received the pre-translation French values.

**Do not wire in the translation.** French is the correct storage language for operational free-text. Do not enable this translation step or add a flag to run it. The current DB state is correct.

**What this exposes — the post-write verification gap.** A verified dry-run result does not prove the write path does the same thing. The translation worked correctly in the dry-run context but silently failed in the write run. This pattern — a transformation that parses, buffers, and writes in sequence — can break at the write step without surfacing an error if the transformation is not idempotent and not verified against the DB.

**Rule for future ingestion scripts with a transformation step:** after any `--write` run that includes a translation, normalization, or computed field, verify the transformation by reading back from the database — not from the in-process buffer. A one-query spot-check confirming that the written value differs from the raw source (when it should) is the minimum. Reading from the local buffer only confirms that the code ran, not that it committed the right thing.

---

## 6. Sector Scheme — Source Reconciliation

Two client sources define sectors for the portfolio and they do not fully agree. This section records how the divergence was resolved so it is not re-derived from scratch.

### Sources

**Master du ménage (Territoire/Secteur hierarchy)** — used to populate the `sector` table and assign `building.sector_id`. Produces 6 named sectors plus an "Inconnu" placeholder, and splits Lévis into two rows:

| sector_id | territoire |
|-----------|-----------|
| 1 | Haute-Ville |
| 2 | Levis-Est |
| 3 | Levis-Ouest |
| 4 | Quebec-Est |
| 5 | Quebec-Ouest |
| 6 | Sainte-Foy |
| 7 | Inconnu (placeholder) |

**`secteurs-et-equipe.md` (Google Calendar colorIds)** — used to populate `sector.color_code`. Defines 6 geographic sectors; Lévis is unified under one colorId, and there is a Beauport-Charlesbourg sector absent from the table above:

| colorId | Sector label |
|---------|-------------|
| 7 | Ste-Foy – Sillery |
| 5 | Haute-Ville |
| 3 | Beauport-Charlesbourg |
| 10 | Lebourgneuf-Vanier / Québec-Ouest |
| 4 | Limoilou / Québec-Est |
| 6 | Lévis (Est et Ouest) |

### Divergence points and resolutions

**Lévis split vs. unified.** Master du ménage splits Lévis into Est (sector_id=2) and Ouest (sector_id=3); the calendar treats it as a single color. Resolution: kept the 7-row schema (the Est/Ouest split is useful for building routing and does not conflict with color assignment). Both Lévis rows were assigned `color_code='6'`. The calendar's `color_id` field on individual maintenance_request rows is null for all events — Google Calendar only populates per-event colorId on explicit overrides; sector color is set at the calendar level and not stored on individual events.

**Beauport-Charlesbourg absent from `sector` table.** The calendar defines colorId=3 for Beauport-Charlesbourg with no corresponding DB row. The buildings the doc lists under "Québec-Est (violet 3 / rose 4)" — Cardinal-Villeneuve, Petitclerc, Courtemanche, des Roses, Gros-Pin, Carmichael, Tadoussac — are all assigned to `Quebec-Est` (sector_id=4) in the DB and receive `color_code='4'`. Chamonix and Sully, which may belong to colorId=3 territory, are in `Inconnu` (sector_id=7) because TF has no territory for them. Resolution: `Quebec-Est` was assigned `color_code='4'`; colorId=3 is unrepresented in the schema. See §5e for the client question that would resolve this.

**Naming differences resolved by substance, not string equality:**

| DB territoire | Mapped to calendar label | colorId assigned |
|--------------|--------------------------|-----------------|
| Sainte-Foy | Ste-Foy – Sillery | 7 |
| Haute-Ville | Haute-Ville | 5 |
| Quebec-Ouest | Lebourgneuf-Vanier / Québec-Ouest | 10 |
| Quebec-Est | Limoilou / Québec-Est | 4 |
| Levis-Est | Lévis | 6 |
| Levis-Ouest | Lévis | 6 |

---

## 10. RLS — View security_invoker Bug (Found and Fixed 2026-09-29)

### Background: PostgreSQL 15+ view security semantics

In PostgreSQL 15, `WITH (security_invoker = true)` was added as a view option. The critical
subtlety: the **default in PG 15+ is still security definer** (view-owner privileges), not
security invoker. If the view owner has `BYPASSRLS = true` (as `postgres` does in Supabase),
a view without explicit `security_invoker = true` runs every query as the view owner and
bypasses Row-Level Security entirely — regardless of what role issued the query.

This means: `CREATE OR REPLACE VIEW foo AS SELECT ...` on a Supabase-hosted PG 17 database
silently disables RLS for anyone reading through that view.

### What was found

During verification of `maintenance_request_tech_view` (recreated when dead columns were dropped),
`reloptions` was empty — meaning `security_invoker` was NOT set. The original RLS tests had tested
the base tables directly and never caught this, because the bug only manifests when querying
through the view.

A three-role simulation (technician / coordinator / director via JWT-claim injection) confirmed
the gap:
- Through the **base table** (`maintenance_request`): technician correctly saw 736 rows (their
  scoped subset); coordinator/director saw all 2374.
- Through the **view** (without `security_invoker`): all three roles saw all 2374 rows — RLS
  fully bypassed.

A full audit found **all four views** in the public schema were affected:

| View | Underlying table | Policy | Technician should see |
|------|-----------------|--------|-----------------------|
| `maintenance_request_tech_view` | `maintenance_request` | tech_scoped + dir_coord_all | 736 (sector + assigned) |
| `lease_field_view` | `lease` | dir_coord_only | 0 |
| `parking_assignment_field_view` | `parking_assignment` | dir_coord_only | 0 |
| `storage_assignment_field_view` | `storage_assignment` | dir_coord_only | 0 |

`lease_field_view` was the highest-stakes gap: technicians could read `unit_id, debut_bail,
fin_bail, langue_bail, statut` for all 4,293 leases, bypassing the `dir_coord_only` policy.

### Fix applied

```sql
ALTER VIEW maintenance_request_tech_view    SET (security_invoker = true);
ALTER VIEW lease_field_view                 SET (security_invoker = true);
ALTER VIEW parking_assignment_field_view    SET (security_invoker = true);
ALTER VIEW storage_assignment_field_view    SET (security_invoker = true);
```

`ingest_rls_schema.py` DDL updated — all four `CREATE OR REPLACE VIEW` statements now include
`WITH (security_invoker = true)` so any future recreate preserves the setting.

### Post-fix verification (three-role × four-view)

| View | technician (NIRO) | coordinator (CALE) | director (CHBE) | postgres total |
|------|-------------------|--------------------|-----------------|----------------|
| maintenance_request_tech_view | 736 | 2374 | 2374 | 2374 |
| lease_field_view | 0 | 4293 | 4293 | 4293 |
| parking_assignment_field_view | 0 | 3133 | 3133 | 3133 |
| storage_assignment_field_view | 0 | 1321 | 1321 | 1321 |

All results match expected policy behaviour.

### Standing rule for future views

Any view created for RLS purposes **must**:
1. Include `WITH (security_invoker = true)` in the DDL — never omit it and rely on the default.
2. Be tested by querying **through the view** (not just the base table) as a non-privileged role
   with a valid JWT claim injected, confirming the scoped row count matches the policy expectation.
| Inconnu | — (left null) | — |
