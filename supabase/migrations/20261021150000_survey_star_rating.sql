-- Survey Q2 becomes a 1–5 star rating (was yes/no `satisfied`).
-- Legacy `satisfied` column is kept for rows submitted before this change.
-- Local only until approved; apply via psql to postgres + sib_test.

BEGIN;

ALTER TABLE public.satisfaction_survey
    ADD COLUMN satisfaction_rating smallint
        CHECK (satisfaction_rating BETWEEN 1 AND 5);

-- Utilization: submitted reviews per technician over a date range.
CREATE INDEX satisfaction_survey_employee_submitted_idx
    ON public.satisfaction_survey (employee_id, submitted_at)
    WHERE submitted_at IS NOT NULL;

COMMIT;

-- ── Rollback ─────────────────────────────────────────────────────────────────
/*
BEGIN;
DROP INDEX IF EXISTS public.satisfaction_survey_employee_submitted_idx;
ALTER TABLE public.satisfaction_survey DROP COLUMN IF EXISTS satisfaction_rating;
COMMIT;
*/
