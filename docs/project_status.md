# SIB Platform — Project Status

_Last updated: 2026-09-22_

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

### Files 8–11 — Out of scope, no decision made

| # | File | Sensitivity | Status |
|---|---|---|---|
| 8 | Security config file | Reviewed; content: alarm codes, access-control credentials | No translation decision — pending separate sensitivity review |
| 9 | Soluvox call log | High-sensitivity flagged during review | No decision — flagged for separate handling |
| 10 | Second call log | Lower sensitivity than file 9; reviewed but not yet translated | No decision |
| 11 | Master Rent Roll | Not yet opened | No decision |

---

## 3. Known Data Gaps — Do Not Re-Discover

These were confirmed during Drive exploration and review. They are open items, not bugs.

### MÉNAGE folder — missing from both variants
The MÉNAGE (cleaning/housekeeping) subfolder does not appear in either the French or English Maintenance Drive. Its absence was confirmed but the root cause is unresolved — the folder may have been moved, deleted, or never created under this naming. No action taken.

### PEINTURE folder — confirmed empty (real source is elsewhere)
The PEINTURE (paint) subfolder exists in the Maintenance Drive but is empty. The real paint data source is `"0 - Charte des couleurs de peinture SIB"` — a distinct file confirmed via the live DB map review. It has not yet been pulled or ingested. This maps to the `building_paint_spec` table in the schema, which is also empty.

### File 10 / recurring_task_pattern source mismatch — open question
During review, it was established that `recurring_task_pattern` is sourced from the Coordinator's Guide (recurring-task rules), NOT from the Service Call Log (IA) calendar-recurrence file as originally assumed. The Service Call Log's actual data mapping is still an open question — it may turn out to be a source for `service_visit` instead, which currently has no source at all. This is not resolved here; it is recorded to prevent the same investigative work from being redone.

---

## 4. Tables with No Data Source Identified Yet

These tables exist in the schema (`schema/sql/schema.sql`) and are ready to receive data, but no source file has been identified or ingested as of this writing. Ingestion work for these is not scoped.

| Table | Notes |
|---|---|
| `entrance` | No source file. Ingestion plan: create one synthetic entrance per building (copy `building.adresse/ville/code_postal`) so `building_intercom` and `building_key_box` FKs are never dangling. |
| `equipment` | No source file at either building or unit level. |
| `service_contract` | Only unstructured year-by-year contract folders exist; nothing extracted into rows. |
| `service_visit` | Fire-protection folder holds ~106 per-building subfolders of unstructured inspection PDFs — nothing extracted. May overlap with the unresolved Service Call Log (see §3). |
| `pest_control_case` | Extermination folder near-empty with no structured tracking. |
| `tenancy_record` | Conceptual only; needs a new collection process. Stopgap: backfill from Master Rent Roll snapshots (one row per tenant per lease, `capacite = named_on_lease`). |
