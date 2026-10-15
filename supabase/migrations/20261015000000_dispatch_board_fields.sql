-- Migration 0002: Dispatch board fields
-- Adds three nullable columns to maintenance_request and three missing indexes.
-- Existing rows remain NULL; no data migration required.
--
-- Columns added:
--   estimated_cost       numeric(10,2)  — cost estimate in CAD, must be ≥ 0
--   next_follow_up_date  date           — when coordinator expects to follow up
--   next_steps           text           — forward-looking instructions
--
-- Indexes added:
--   mr_start_date_idx   — standalone start_date; the existing composite
--                         mr_status_start_date_idx(status, start_date) cannot
--                         serve queries that omit status from the WHERE clause.
--   mr_sector_id_idx    — sector filter on the list endpoint; no index exists.
--   mfe_request_id_idx  — detail view joins maintenance_followup_entry by
--                         request_id; only the PK (followup_id) exists today.

BEGIN;

-- ── Columns ──────────────────────────────────────────────────────────────────

ALTER TABLE public.maintenance_request
    ADD COLUMN IF NOT EXISTS estimated_cost       numeric(10,2)
        CONSTRAINT mr_estimated_cost_nonneg CHECK (estimated_cost >= 0),
    ADD COLUMN IF NOT EXISTS next_follow_up_date  date,
    ADD COLUMN IF NOT EXISTS next_steps           text;

-- ── Indexes ──────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS mr_start_date_idx
    ON public.maintenance_request (start_date);

CREATE INDEX IF NOT EXISTS mr_sector_id_idx
    ON public.maintenance_request (sector_id);

CREATE INDEX IF NOT EXISTS mfe_request_id_idx
    ON public.maintenance_followup_entry (request_id);

COMMIT;

-- ── Rollback ─────────────────────────────────────────────────────────────────
/*
BEGIN;

DROP INDEX IF EXISTS public.mfe_request_id_idx;
DROP INDEX IF EXISTS public.mr_sector_id_idx;
DROP INDEX IF EXISTS public.mr_start_date_idx;

ALTER TABLE public.maintenance_request
    DROP COLUMN IF EXISTS next_steps,
    DROP COLUMN IF EXISTS next_follow_up_date,
    DROP COLUMN IF EXISTS estimated_cost;

COMMIT;
*/
