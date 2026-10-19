-- Analytics / utilization indexes (dashboard + utilization aggregations).
-- Local only until approved; apply via psql to postgres + sib_test.

BEGIN;

CREATE INDEX IF NOT EXISTS request_visit_employee_en_route_idx
    ON public.request_visit (employee_id, en_route_at);

CREATE INDEX IF NOT EXISTS mr_sector_status_idx
    ON public.maintenance_request (sector_id, status)
    WHERE sector_id IS NOT NULL;

COMMIT;
