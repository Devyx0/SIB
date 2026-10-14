# Status Machine — 0002 Migration Proposal

Recorded 2026-10-15. Decision pending.

## Current enum (`request_status`)

```
intake_received → triage_pending → triaged → en_route → closed
                               ↘ triage_failed
                               ↘ triage_clarify
triage_proposal  (unreachable — rule 37)
```

## Identified gaps

| Gap | Problem |
|---|---|
| No state between `triaged` and `en_route` | Cannot record that a tech + time slot have been assigned without the tech having departed |
| No explicit cancellation state | Coordinator cancellations use `triaged → closed`, making cancelled and completed requests indistinguishable |
| `partial_reschedule` outcome | No status represents a rescheduled visit |

## Proposed additions

### `scheduled`
Tech and slot assigned; tech has not yet departed.

```
triaged → scheduled → en_route → closed
```

Replaces the current `triaged → en_route` direct jump.  
Who writes it: coordinator dispatch endpoint (Phase B).

### `cancelled`
Explicit terminal state for requests cancelled after triage.

```
triaged    → cancelled
scheduled  → cancelled
```

Replaces the informal `triaged → closed` cancellation path.  
Lets dashboards distinguish "completed" from "cancelled" without a separate column.

## `partial_reschedule` — no new status

A partial reschedule (tech arrived, started work, must return) is a *closeout outcome*, not a new lifecycle stage. Record it in a `closeout_outcome` field on `maintenance_request` (or a `service_visit` table). Status returns to `scheduled` (new slot assigned) or `triaged` (back to dispatch queue). No new enum value required.

## Migration

Add to `request_status` enum:
```sql
ALTER TYPE request_status ADD VALUE 'scheduled'  AFTER 'triaged';
ALTER TYPE request_status ADD VALUE 'cancelled'  AFTER 'en_route';
```

Update `domain/status_machine.py` `_TRANSITIONS` after migration:
- `triaged → scheduled`
- `scheduled → en_route`
- `scheduled → cancelled`
- `triaged → cancelled`
- Remove `triaged → en_route` (or keep for backward compat during rollout)
- Remove `triaged → closed` (use `cancelled` or `closed` from `en_route`)

## Decision needed

- [ ] Confirm `scheduled` vs keeping `triaged → en_route` for simplicity
- [ ] Confirm `cancelled` as terminal vs a `cancellation_reason` column on `closed`
- [ ] Confirm `closeout_outcome` field approach for partial reschedule
