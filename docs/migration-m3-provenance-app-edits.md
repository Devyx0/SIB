# Migration m3 — data_provenance: app-edit columns

**File:** `supabase/migrations/20261015181857_provenance_app_edits.sql`  
**Applied locally:** 2026-10-15  
**Remote:** pending

## What changed

Two nullable columns added to `data_provenance`:

| Column | Type | Purpose |
|---|---|---|
| `employee_id` | `integer → employee(employee_id)` | Acting user for app-initiated edits |
| `previous_value` | `text` | Value before the change (old field state) |

Existing ingestion rows are unaffected (both columns NULL).

## Write convention for app edits

All 7 dispatch-action endpoints write one provenance row per changed field in the same transaction as the UPDATE:

| `data_provenance` column | App-edit value |
|---|---|
| `target_table` | `'maintenance_request'` |
| `target_pk` | `str(request_id)` |
| `target_column` | field name (e.g. `'assigned_employee_id'`) |
| `source_type` | `'app'` |
| `employee_id` | signed-in employee's `employee_id` |
| `previous_value` | old value serialised to text (NULL if was NULL) |
| `raw_value` | new value as entered (same as `ingested_value`) |
| `ingested_value` | new value serialised to text (NULL if cleared) |
| `ingested_at` | `now()` |
| `source_drive_id / source_file_name / source_tab / source_row / source_column` | NULL |

## Why `source_type` needed no fix

`source_type` is plain `varchar` with no CHECK constraint — `'app'` was already a valid value.
All ingestion-specific columns (`source_drive_id`, `source_file_name`, etc.) were already nullable,
so app edits can leave them NULL without violating any constraint.
