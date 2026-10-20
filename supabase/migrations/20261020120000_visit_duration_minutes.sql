-- Persist en-route → closeout duration on request_visit for technician KPIs.
-- Timestamps remain source of truth for new closes; this column is the KPI-ready value.

BEGIN;

ALTER TABLE public.request_visit
    ADD COLUMN IF NOT EXISTS duration_minutes integer;

COMMENT ON COLUMN public.request_visit.duration_minutes IS
    'Whole minutes from en_route_at to closeout_at; set on closeout for tech KPIs.';

-- Backfill closed visits that predate this column.
UPDATE public.request_visit
SET duration_minutes = GREATEST(
    0,
    ROUND(EXTRACT(EPOCH FROM (closeout_at - en_route_at)) / 60.0)::integer
)
WHERE closeout_at IS NOT NULL
  AND duration_minutes IS NULL;

COMMIT;

-- ── Rollback ─────────────────────────────────────────────────────────────────
/*
BEGIN;
ALTER TABLE public.request_visit DROP COLUMN IF EXISTS duration_minutes;
COMMIT;
*/
