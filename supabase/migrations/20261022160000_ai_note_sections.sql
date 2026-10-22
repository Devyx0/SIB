-- Structured AI note sections (replaces free-form other_notes for display).
-- Summary stays in problem_summary; Important / Next live here as text[].
-- existing other_notes kept for legacy rows + rentroll/weather appends until backfilled.

BEGIN;

ALTER TABLE public.maintenance_request
    ADD COLUMN IF NOT EXISTS ai_important_notes text[],
    ADD COLUMN IF NOT EXISTS ai_next_steps text[];

COMMIT;

-- Rollback:
/*
BEGIN;
ALTER TABLE public.maintenance_request
    DROP COLUMN IF EXISTS ai_next_steps,
    DROP COLUMN IF EXISTS ai_important_notes;
COMMIT;
*/
