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
    " AND mr.status::text NOT IN ('closed', 'en_route', 'arrived')"
    " AND (mr.submission_date >= NOW() - INTERVAL '90 days' OR mr.submission_date IS NULL)"
)

# Accepted task still waiting on a coordinator: expertise or return visit, and no
# accepted child yet. Matches the task board « À redispatcher » filter
# (needs_expertise / return_visit, has_followup = false). `mr` is the call.
A_REDISPATCHER_SQL = (
    "EXISTS ("
    " SELECT 1 FROM dispatch_task t"
    " WHERE t.request_id = mr.request_id"
    " AND t.accepted_at IS NOT NULL"
    " AND t.status::text IN ('needs_expertise', 'return_visit')"
    " AND NOT EXISTS ("
    "  SELECT 1 FROM dispatch_task c"
    "  WHERE c.parent_task_id = t.task_id AND c.accepted_at IS NOT NULL"
    " )"
    ")"
)

# Same predicate, counted from the task (the board lists tasks, not calls).
REDISPATCH_TASK_SQL = (
    "t.accepted_at IS NOT NULL"
    " AND t.status::text IN ('needs_expertise', 'return_visit')"
    " AND NOT EXISTS ("
    "  SELECT 1 FROM dispatch_task c"
    "  WHERE c.parent_task_id = t.task_id AND c.accepted_at IS NOT NULL"
    " )"
)
