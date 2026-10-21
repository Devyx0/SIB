-- Technician marks arrival on site. Splits travel vs on-site time for KPIs:
--   travel_minutes  = en_route_at → arrived_at
--   on_site_minutes = arrived_at → closeout_at
--   duration_minutes = en_route_at → closeout_at (total, unchanged meaning)

ALTER TYPE public.request_status ADD VALUE IF NOT EXISTS 'arrived' AFTER 'en_route';

ALTER TABLE public.maintenance_request
    ADD COLUMN IF NOT EXISTS arrived_at timestamptz;

COMMENT ON COLUMN public.maintenance_request.arrived_at IS
    'When the assigned tech marked arrived / on site; cleared conceptually by next cycle via new visit.';

ALTER TABLE public.request_visit
    ADD COLUMN IF NOT EXISTS arrived_at timestamptz,
    ADD COLUMN IF NOT EXISTS arrived_lat double precision,
    ADD COLUMN IF NOT EXISTS arrived_lng double precision,
    ADD COLUMN IF NOT EXISTS travel_minutes integer,
    ADD COLUMN IF NOT EXISTS on_site_minutes integer;

COMMENT ON COLUMN public.request_visit.arrived_at IS
    'Tech tapped Arrivé on site; null if closeout predates this column.';
COMMENT ON COLUMN public.request_visit.travel_minutes IS
    'Whole minutes en_route_at → arrived_at; set on closeout when arrived_at is set.';
COMMENT ON COLUMN public.request_visit.on_site_minutes IS
    'Whole minutes arrived_at → closeout_at; set on closeout when arrived_at is set.';

COMMENT ON TYPE public.request_status IS
    'Request lifecycle states. Auto-retry eligibility: only triage_pending and triage_failed are picked up by the retry loop. triage_clarify must NOT enter the loop — it signals a human-input requirement, not a transient error.

intake_received       — request landed; waiting for the next triage run.
triage_pending        — acquired by the triage service; triage_started_at is set.
triage_clarify        — BLOCKED: needs coordinator action before re-entering the queue.
triage_proposal       — model output pending coordinator accept/reject (deferred).
triage_failed         — retries exhausted; auto-retry after review/reset.
triaged               — on the dispatch board, NOT assigned yet.
scheduled             — assigned to a tech/contractor; not en route.
awaiting_redispatch   — closeout outcomes 3/4; unassigned, coordinator must re-dispatch.
en_route              — field worker heading to site.
arrived               — on site; work in progress until closeout. Label: « Arrivé ».
closed                — work complete and closed out.';
