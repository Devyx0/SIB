-- Expertise / failed closeout returns: dedicated status instead of reusing triaged.
-- Matches board « À redispatcher » queue (was inferred from outcome + unassigned).

ALTER TYPE public.request_status ADD VALUE IF NOT EXISTS 'awaiting_redispatch' AFTER 'triaged';

COMMENT ON TYPE public.request_status IS
    'Request lifecycle states. Auto-retry eligibility: only triage_pending and triage_failed are picked up by the retry loop. triage_clarify must NOT enter the loop — it signals a human-input requirement, not a transient error.

intake_received       — request landed; waiting for the next triage run.
triage_pending        — acquired by the triage service; triage_started_at is set.
triage_clarify        — BLOCKED: needs coordinator action before re-entering the queue.
triage_proposal       — model output pending coordinator accept/reject (deferred).
triage_failed         — retries exhausted; auto-retry after review/reset.
triaged               — on the dispatch board; may or may not be assigned.
awaiting_redispatch   — closeout outcomes 3/4 (expertise/failed); unassigned, coordinator must re-dispatch. Label: « À redispatcher ».
en_route              — field worker heading to site.
closed                — work complete and closed out.';

UPDATE public.maintenance_request
SET status = 'awaiting_redispatch'
WHERE status = 'triaged'
  AND assigned_employee_id IS NULL
  AND closeout_outcome::text IN ('partial_expertise', 'failed');
