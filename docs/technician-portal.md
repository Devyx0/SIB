# Technician portal — 3.5 En route + 3.6 Closeout (SoW 3.5, 3.6)

Recorded 2026-10-19. Plan approved by client-side (Maaz) with changes; this doc is
the plan of record. Build proceeds in three stops; **stops 1 and 2 built
2026-10-19** (stop-1 review fixes applied same day), stop 3 not started. Local
only — nothing committed, no SMS/email sent, no Google writes.

Client sources: `docs/francois-milestone1-reference.md` §5 (En route), §6
(Closeout), §9 (Majordome evidence); ticket decisions dated Oct 13 (mobile web,
SMS **and** email, location points on actions not tracking, closure with photo
required before moving on). Everything not from a client source is marked
**our choice**.

## Status / outcome mapping

`request_status` already has `en_route` and `closed` (baseline migration).
`closeout_outcome` enum currently `('complete','partial_reschedule','failed')`
— the SoW 3-outcome version. §6.1: "The client defines four, with an urgent
flag on #3 and #4. The client's version should win."

| François's outcome (labels verbatim in UI) | status after | closeout_outcome |
|---|---|---|
| 1 « Call fermé, terminé complètement » | `closed` | `complete` |
| 2 « Call partiellement fait, je dois revenir » — he picks the date, stays his | `triaged`, assignment unchanged, `start_date` = his date | `partial_reschedule` |
| 3 « Call partiellement fait, besoin d'une expertise » (urgent checkbox) | `triaged`, `assigned_employee_id` → NULL | `partial_expertise` (new value, migration) |
| 4 « Call pas du tout fait, besoin d'une expertise / envoyer à dispatch » (urgent checkbox) | same as 3 | `failed` (**our choice**: reuse) |

No new `request_status` values. Code change: add `en_route → triaged` to
`backend/domain/status_machine.py`. `scheduled`/`cancelled`
(docs/status-machine-proposal.md) stay pending and are not needed.

**En route accepted from:** the same open statuses the existing assign action
accepts — `action_assign` (service.py:197) gates only via `_check_not_closed`
(service.py:173, rejects `status == 'closed'` with RequestClosedError), and
`is_valid_assignee` (repository.py:284) checks role/activity, not status. So
en route accepts **any status except `closed` and `en_route`**:
intake_received, triage_pending, triaged, triage_clarify, triage_proposal,
triage_failed. `status_machine._TRANSITIONS` gains `X → en_route` for each
(stop 2). Not derived from dev-data counts.

## Scoping decisions (changed from first draft)

- **/tech « Mes appels » lists ONLY `assigned_employee_id = me`** — for
  technicians too. The existing `_scope` (service.py) adds sector buildings;
  it is NOT used for this list. Implemented by passing
  `assigned_employee_id = me` to the existing `GET /requests` filter, which is
  ANDed with the scope. Covered by a test: a technician with a sector does not
  see sector calls that aren't assigned to him in this list.
- Call view keeps the existing `_scope` + case-scoped PII rule
  (`_CASE_SCOPED_PII`, service.py:47) unchanged: tenant contact visible only
  to coordinator/director or the directly-assigned employee.

## Screens

1. `/tech` — Mes appels: ALL calls assigned to me with status <> `closed`,
   any date (no date window — the list endpoint's date pair is now optional,
   provided together or not at all). Open `en_route` call pinned with banner;
   then sections « En retard » (date < today, America/Toronto), « Aujourd'hui »,
   « À venir », « Sans date ». Closed-today section skipped (optional in
   review; add on request). Mobile-first, fr-CA. Home-screen shortcut via
   `manifest.webmanifest` + icons (**our choice:** no service worker/offline).
   Role redirect: technician/contractor **without** coordinator/director →
   `/tech`; everyone else unchanged (`/board`).
2. `/tech/appels/:id` — read-only call view: address, problem, technical
   sheet link (`ft_link`/`ft_name` — added to the GET detail response),
   follow-up log, tenant contact per existing case-scoped rule.
   Review fixes (post case 11603): the problem shown is the TENANT's version
   from `raw_caller_body` (problems + entry permission + animals), never
   `problem_summary` or other AI fields; fallback when `raw_caller_body` is
   absent = raw `problems` labelled « Problème ». FT data comes in three
   shapes (link in ft_link / name only / "name (url)" mashed into ft_name) —
   the view extracts the URL from either field and shows « Fiche technique
   non disponible » when there is none (request 15927: both fields null).
   Unit (« app. X ») shown on every list card and on the call view address.
3. En route — one tap; `navigator.geolocation` with short timeout, null on
   deny (Oct 13: points on actions, not tracking).
4. `/tech/appels/:id/cloture` — 4 outcomes with verbatim labels; photos
   (capture or library, min 1, not saved to gallery — native
   `<input type="file" accept="image/*" capture="environment">`); explanation
   textarea + shared MicButton (already fr-CA); outcome 2 → native date input;
   outcomes 3/4 → « Urgent » checkbox.

## API endpoints (stops 2–3)

| Endpoint | Roles (403 otherwise) | Behaviour |
|---|---|---|
| `POST /requests/{id}/en-route` | technician/contractor AND assigned | Stale check (`current_status`, `current_start_date` — same pattern as dispatch actions, 409 StaleDataError). Guard: caller already has an open call → 409 with that call's id/title. Writes: status → `en_route`, `en_route_at`, `request_visit` row (nullable lat/lng), **two `message_outbox` rows (sms + email), status `'not_sent'`**, provenance per column. |
| `POST /requests/{id}/photos` | same | Multipart; mime allowlist **jpeg/png/webp** (heic dropped per review); 10 MiB cap (**our choice**); upload to private bucket via service key; insert `maintenance_attachment` (`photo_context='closeout'`); `attachment_id` gets identity in the stop-3 migration. |
| `POST /requests/{id}/closeout` | same | `{outcome, comment, attachment_ids (min 1, caller's own), next_date (iff outcome 2), urgent (3/4), current_status}`. Applies mapping above; elapsed from the open visit; followup entry; `work_performed`; provenance; justification row on the 3/4 un-assignment (**our choice**). |
| `GET /requests/{id}/photos/{attachment_id}` | assigned tech/contractor + coordinator/director | 302 to short-lived signed URL. |

## Coordinator board (stop 3 addition, per review)

Returned calls (outcomes 3/4) appear on the dispatch board in a visible
« À redispatcher » group/filter (triaged + unassigned + closeout_outcome in
partial_expertise/failed), with an urgent badge when `closeout_urgent`. The
coordinator DetailPanel shows closeout outcome, photos (signed URLs), comment,
and elapsed time per visit (from `request_visit`).

## Outbox + message template

`message_outbox(id, request_id, visit_id, channel CHECK in ('sms','email'),
recipient NULL, subject NULL, body, status CHECK in
('not_sent','sent','failed') DEFAULT 'not_sent', created_at, sent_at NULL,
created_by_employee_id)`. No sender code exists in V1 — "never send" is
satisfied by having no send path.

- Recipient = the **cleaned** contact exactly as the API already computes it
  (`_normalise_contacts`, requests/repository.py:70 — placeholders
  info@sibelanger.com / (000) 000-0000 → null).
- Null recipient → row still written, and the technician sees
  « Aucun contact pour aviser le locataire » after en route.
- Template start (client source, §5 S5 EN ROUTE): « Bonjour, Ce message est
  destiné aux occupants, aux locataires du XXX. » — **XXX = unit (civic +
  apartment)**, our choice per review. Body after the first sentence:
  **our choice**, pending François.

## Schema migrations (timestamped, one per stop; none applied yet)

- Stop 2 — **built**: `supabase/migrations/20261019140000_en_route.sql`:
  `request_visit` table (visit_id identity, request_id FK, employee_id FK,
  en_route_at NOT NULL, en_route_lat/lng, closeout_at NULL, closeout_lat/lng,
  outcome closeout_outcome NULL; elapsed computed, not stored);
  `request_visit_one_open_idx` partial unique index (one-open-call rule as a
  DB constraint); `message_outbox`; RLS enabled, no policies (FastAPI /
  service_role only — same as decision_justification_log). Applied to local
  dev and sib_test via psql; `supabase db diff --local` → no schema changes.
- Stop 3 — `202610191401xx_closeout.sql`: `ALTER TYPE closeout_outcome ADD
  VALUE 'partial_expertise'`; `maintenance_request.closeout_urgent boolean`;
  `maintenance_attachment.attachment_id` → identity + setval; bucket
  declaration.

## Stop 1 — built 2026-10-19 (this doc's commit of record)

Scope: role redirect, `/tech` list (assigned only, en_route pinned — empty of
en_route until stop 2), `/tech/appels/:id` read-only view, manifest + icons,
mobile styles, fr-CA. **No schema change, no new write endpoints.** Backend
delta limited to exposing `ft_link`/`ft_name` on the existing GET detail
(read-only field addition; the ticket's call view requires the technical
sheet link and the API didn't return it).

**Our choices in stop 1:** solid-colour placeholder icons (real logo
pending); technicians keep read access to sector calls on the detail view
(only the list is assigned-only). Review fix 2026-10-19: no date window —
`GET /requests` accepts the date pair as optional (both or neither; 31-day
cap unchanged when provided), and the portal fetches assigned + all open
statuses, grouped client-side by Toronto date.

## Tests

Stop 1 (see evidence in handover message): backend — sector technician with
`assigned_employee_id` filter sees only assigned; ft_link/ft_name present on
detail. Existing suite already covers: 404 out-of-scope technician, 404
contractor other request, PII shown/hidden by assignment, coordinator/director
see all. Frontend — routing by role (tech-only → /tech, coordinator → /board
unchanged), assigned-only fetch param, en_route pinned banner, call-view
contact shown/hidden, 404 state.

Stops 2–3: test_en_route (status flip, visit row, 2 outbox rows not_sent,
null recipient row + message, provenance, location null on deny, 409 open
call / stale / closed, 403 coordinator & unassigned), test_closeout (4
outcomes' effects, min-1-photo 422, outcome-2 date required, elapsed,
followup + provenance), test_photos (mocked storage, mime/size rejection,
signed-URL scoping), status-machine `en_route → triaged`, coordinator
« À redispatcher » group + DetailPanel closeout display. Storage and
geolocation mocked; all against sib_test.

## Open questions (for François unless noted)

1. Message body after the template's first sentence; sender identity; SMS via
   Quo or other.
2. Outcome 4 enum mapping: reuse `failed` (our default) or dedicated value.
3. Confirm outcomes 3/4 clear `assigned_employee_id` (§6.1 "returns to the
   maintenance mailbox; coordinator decides and re-dispatches").
4. `tenant_present` toggle on the closeout form? (column exists from m1; not
   in the ticket — left out of V1).
5. Elapsed when a call has multiple visits: per visit (stored) vs summed to
   "final follow-up" (S4 00:57:02) — both derivable from request_visit.
6. Photo retention; 10 MiB cap.
7. §9: "no source says Majordome = only Mahmoud" — other Majordome workers
   would need their own employee row + contractor role; no portal change.
8. How a coordinator unblocks a technician who forgot to close a call — the
   one-open-visit index blocks every new en route until the visit is closed.
   Likely a coordinator action that closes the visit administratively
   (closeout_at set, no outcome, provenance row). Not built; needs François.
