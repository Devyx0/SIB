"""Shared analytics constants — single source of truth for filters and midpoints."""

# Statuses that count as « non triés » on the territory table (tooltip lists these).
UNTRIAGED_STATUSES: frozenset[str] = frozenset({
    "intake_received",
    "triage_pending",
    "triage_failed",
    "triage_clarify",
})

# Provisional TEMPS bucket midpoints (minutes). TBD_ON_SITE excluded from sums.
BUCKET_MIDPOINT_MINUTES: dict[str, int] = {
    "UNDER_30_MIN": 20,
    "MIN30_TO_1H": 45,
    "H1_TO_2H": 90,
    "H2_TO_4H": 180,
    "HALF_DAY_PLUS": 300,
}

# Same predicates as requests/repository list_requests (keep in sync).
A_ROUTER_SQL = (
    "mr.source_calendar IS NULL"
    " AND mr.status::text NOT IN ('closed', 'en_route')"
    " AND (mr.submission_date >= NOW() - INTERVAL '90 days' OR mr.submission_date IS NULL)"
)

A_REDISPATCHER_SQL = (
    "mr.status::text = 'triaged' AND mr.assigned_employee_id IS NULL"
    " AND mr.closeout_outcome::text IN ('partial_expertise', 'failed')"
)
