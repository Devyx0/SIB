-- Assigned board work gets its own status. triaged = on board, unassigned.
-- scheduled = tech (+ optional date) assigned, not yet en route.
-- Outcome 2 (partial_reschedule) returns to scheduled, not triaged.

ALTER TYPE public.request_status ADD VALUE IF NOT EXISTS 'scheduled' AFTER 'triaged';

COMMENT ON TYPE public.request_status IS
    'Request lifecycle states. Auto-retry eligibility: only triage_pending and triage_failed are picked up by the retry loop. triage_clarify must NOT enter the loop — it signals a human-input requirement, not a transient error.

intake_received       — request landed; waiting for the next triage run.
triage_pending        — acquired by the triage service; triage_started_at is set.
triage_clarify        — BLOCKED: needs coordinator action before re-entering the queue.
triage_proposal       — model output pending coordinator accept/reject (deferred).
triage_failed         — retries exhausted; auto-retry after review/reset.
triaged               — on the dispatch board, NOT assigned yet.
scheduled             — assigned to a tech/contractor (first visit or return); not en route. Label: « Planifié ».
awaiting_redispatch   — closeout outcomes 3/4; unassigned, coordinator must re-dispatch. Label: « À redispatcher ».
en_route              — field worker heading to site.
closed                — work complete and closed out.';

-- Existing assigned "triaged" rows → scheduled.
UPDATE public.maintenance_request
SET status = 'scheduled'
WHERE status = 'triaged'
  AND assigned_employee_id IS NOT NULL;
