-- Fix for 20261022140000: the NOT EXISTS (any task) filter skipped legacy-status
-- requests that already had a proposal (accepted_at IS NULL) or manual task, leaving
-- them in a legacy status with unattached visits.
--
-- For every request still in {triaged, scheduled, en_route, arrived, awaiting_redispatch}:
--   1. no ACCEPTED task → insert one accepted cutover task (same status map as before);
--      an existing accepted task is kept — never a second cutover task;
--   2. always set the call to 'open';
--   3. always attach open visits (closeout_at IS NULL, task_id IS NULL) to an accepted
--      task of that request: the new cutover task, else the earliest accepted by task_id.
-- Idempotent: once a call is 'open' it no longer matches. Returns requests migrated.

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
        ORDER BY mr.request_id
        FOR UPDATE OF mr
    LOOP
        SELECT t.task_id INTO v_task
          FROM public.dispatch_task t
         WHERE t.request_id = r.request_id AND t.accepted_at IS NOT NULL
         ORDER BY t.task_id
         LIMIT 1;

        IF v_task IS NULL THEN
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
        END IF;

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
    'Cutover backfill: legacy-status requests → open; one accepted dispatch_task each (reuses an existing accepted task, else inserts one); open visits → that task. Idempotent. Returns requests migrated.';

REVOKE ALL ON FUNCTION public.backfill_open_requests() FROM PUBLIC, anon, authenticated;

SELECT public.backfill_open_requests();

COMMIT;

-- ── Rollback ─────────────────────────────────────────────────────────────────
-- Re-apply the body from 20261022140000 (data changes are not reversible).
