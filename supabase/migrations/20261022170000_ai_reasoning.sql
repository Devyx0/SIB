-- AI triage reasoning shown at the bottom of the dispatch AI card.

BEGIN;

ALTER TABLE public.maintenance_request
    ADD COLUMN IF NOT EXISTS ai_reasoning text;

COMMIT;

-- Rollback:
/*
BEGIN;
ALTER TABLE public.maintenance_request DROP COLUMN IF EXISTS ai_reasoning;
COMMIT;
*/
