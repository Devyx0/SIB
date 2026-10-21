-- Task-first-class cutover backfill: open Service Calls → one accepted dispatch_task.
-- Spec: docs/superpowers/specs/2026-10-22-task-first-class-design.md (Migration of existing data)
--
-- Separate from 20261022120000 / 20261022130000 (already applied on shared DBs).
--
-- For each maintenance_request in {triaged, scheduled, en_route, arrived,
-- awaiting_redispatch} that has no dispatch_task yet:
--   1. insert one accepted task (description = problem_summary → raw_title),
--      copying assignee/vendor/subcontractor and start_date → due_at (local midnight);
--   2. status map: triaged→queued, scheduled→scheduled, en_route→en_route,
--      arrived→arrived, awaiting_redispatch→needs_expertise;
--   3. set the call to 'open';
--   4. point its open request_visit rows (closeout_at IS NULL) at the new task.
-- Closed requests are not backfilled (v1). Idempotent: re-running migrates nothing.
-- request_visit_task_id_required stays NOT VALID: closed historical visits keep NULL.

BEGIN;

CREATE OR REPLACE FUNCTION public.backfill_open_requests()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    r        record;
    v_task   integer;
    v_count  integer := 0;
BEGIN
    FOR r IN
        SELECT mr.request_id, mr.status::text AS status, mr.problem_summary, mr.raw_title,
               mr.assigned_employee_id, mr.vendor_id, mr.subcontractor_name, mr.start_date
        FROM public.maintenance_request mr
        WHERE mr.status::text IN ('triaged', 'scheduled', 'en_route', 'arrived',
                                  'awaiting_redispatch')
          AND NOT EXISTS (SELECT 1 FROM public.dispatch_task t WHERE t.request_id = mr.request_id)
        ORDER BY mr.request_id
        FOR UPDATE OF mr
    LOOP
        INSERT INTO public.dispatch_task (
            request_id, description, status, assigned_employee_id, vendor_id,
            subcontractor_name, due_at, source, accepted_at
        ) VALUES (
            r.request_id,
            COALESCE(NULLIF(btrim(r.problem_summary), ''), NULLIF(btrim(r.raw_title), ''),
                     'Intervention'),
            (CASE r.status
                WHEN 'triaged'             THEN 'queued'
                WHEN 'scheduled'           THEN 'scheduled'
                WHEN 'en_route'            THEN 'en_route'
                WHEN 'arrived'             THEN 'arrived'
                WHEN 'awaiting_redispatch' THEN 'needs_expertise'
             END)::public.dispatch_task_status,
            r.assigned_employee_id,
            r.vendor_id,
            r.subcontractor_name,
            (r.start_date::timestamp AT TIME ZONE 'America/Toronto'),
            'dispatcher',
            now()
        )
        RETURNING task_id INTO v_task;

        UPDATE public.maintenance_request
           SET status = 'open'::public.request_status
         WHERE request_id = r.request_id;

        UPDATE public.request_visit
           SET task_id = v_task
         WHERE request_id = r.request_id
           AND closeout_at IS NULL
           AND task_id IS NULL;

        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION public.backfill_open_requests() IS
    'One-shot cutover backfill: open legacy requests → one accepted dispatch_task each; call → open; open visits → task_id. Idempotent. Returns requests migrated.';

REVOKE ALL ON FUNCTION public.backfill_open_requests() FROM PUBLIC, anon, authenticated;

SELECT public.backfill_open_requests();

COMMIT;

-- ── Rollback ─────────────────────────────────────────────────────────────────
-- Data backfill is not mechanically reversible (original request statuses are
-- overwritten). Only the helper can be dropped:
/*
DROP FUNCTION IF EXISTS public.backfill_open_requests();
*/
