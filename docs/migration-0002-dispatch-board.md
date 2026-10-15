# Migration 0002 — Dispatch Board Gaps

Recorded 2026-10-15. Decision pending before implementing.

## Missing columns on `maintenance_request`

These three fields appear in the SoW 3.2 dispatch board spec but have no
corresponding DB column. The API exposes them as `null` today.

| Board column | Proposed column | Type | Notes |
|---|---|---|---|
| Estimated cost | `cost_estimate_cents INTEGER` | nullable | Integer cents avoids float precision issues. Add a `cost_estimate_currency CHAR(3) DEFAULT 'CAD'` alongside if multi-currency is ever needed. |
| Next follow-up date | `next_follow_up_date DATE` | nullable | `follow_up_expected` (boolean) exists but is always false in current data; a date column is what the board actually needs. |
| Next steps | `next_steps TEXT` | nullable | Closest existing field is `other_notes` (14% fill) but that is general-purpose. Coordinators need a dedicated field for forward-looking instructions. |

## Missing indexes

These three index gaps do not block the API at current data volumes
(~10k rows, ~2.4k followup entries) but will degrade as data grows.

| Table | Missing index | Why needed |
|---|---|---|
| `maintenance_request` | `(start_date)` single-column | The default list query filters by date range with no status constraint. The existing `mr_status_start_date_idx(status, start_date)` is unusable when `status` is not in the WHERE clause (leading column). |
| `maintenance_request` | `(sector_id)` | Sector filter on the list endpoint requires a full scan without it. |
| `maintenance_followup_entry` | `(request_id)` | Every detail-view fetch joins this table; only the PK `(followup_id)` exists, so each join scans all rows. |

## Call-type gap

The SoW requested a "call type" column (maintenance category). No such column
exists or is being ingested:

- `source_calendar` (`main` / `st_maj`) is the calendar origin, not a work category.
- `caller_type` (type of caller: Locataire actuel, etc.) is 1% filled.
- `category_raw` is 0% filled across all 10 565 rows.

The API exposes `source_calendar` with human-readable labels
(`main` → "Main calendar", `st_maj` → "Butler/Majordome") as the closest
available proxy. A true work-category field would require a new column and
ingestion support.
