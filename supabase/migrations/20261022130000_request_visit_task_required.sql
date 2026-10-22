-- Visits hang off a dispatch_task: task_id is required on every new or updated
-- request_visit row. NOT VALID skips existing (pre-cutover) rows; the open-request
-- backfill points them at their task, after which this can be VALIDATEd and
-- swapped for a plain NOT NULL.
-- Spec: docs/superpowers/specs/2026-10-22-task-first-class-design.md (Visits)

BEGIN;

ALTER TABLE public.request_visit
    ADD CONSTRAINT request_visit_task_id_required CHECK (task_id IS NOT NULL) NOT VALID;

COMMENT ON COLUMN public.request_visit.task_id IS
    'Task this visit belongs to. Required on new rows (request_visit_task_id_required, NOT VALID until the open-request backfill).';

COMMIT;

-- ── Rollback ─────────────────────────────────────────────────────────────────
/*
ALTER TABLE public.request_visit DROP CONSTRAINT IF EXISTS request_visit_task_id_required;
*/
