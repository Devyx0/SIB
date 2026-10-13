# Backend Rules — Extracted from Guide v4.39 + Skill v6.1

_Source: guide-coordonnateur-maintenance-v4_39.md · SKILL.md (skill v6.1)_
_Last updated: 2026-10-08_

---

## Version Note

**Guide v4.39 is the confirmed current standard** (client confirmed 2026-10-08, no newer version exists).
The client's automated Saturday triage task runs against guide v4.34 / skill v4.37 / note format v10.5 — five guide revisions behind. Production behaviour and documented standard are not the same today. Detail in `docs/calendar-parser-reference.md §0`.

### Note format label lineage

The structured note format has gone through at least three label generations that affect how DB data was produced. Anyone parsing note content from the DB or the Calendar API needs to know these moved:

| Label / structure | Era | Guide reference | Status |
|---|---|---|---|
| `QUOI FAIRE :` | Pre–14 Jul 2026; still used by the automated Saturday task through Sep 2026 | Rule 4: "PROBLÈMES (formerly QUOI FAIRE)" | **Synonym for PROBLÈMES** — maps to `problems` column; treated identically by the parser as of 2026-10-09 |
| `PROBLÈMES :` | 14 Jul 2026 → current (guide v4.34, note v10.5) | Rule 4 | Current canonical label for the problem description section |
| `SECTION TERRAIN` heading | 14 Jul – 16 Jul 2026 (note v10.5 only) | Introduced v10.5; removed by rule 17, guide v4.35 | **Removed in v10.6 (17 Jul 2026).** Presence in a note identifies it as v10.5. Absent in all v10.6+ notes. The concept ("terrain" / field worker zone) persists but the heading is gone. |

**Practical consequence for stored data:** Events ingested from the Jul 14–16 2026 window may have `body_format = 'v10_legacy'` (recovered by the fallback parser as of 2026-10-09) or `body_format = 'unparsed_body_format'` if recovery failed. Pre-window events (before Jul 14 2026) were not produced by the structured note format at all and have no QUOI FAIRE / PROBLÈMES / SECTION TERRAIN sections. Events from the automated Saturday task may use QUOI FAIRE through any date, since the task's note format never updated past v10.5.

---

## Bucket 1 — Enforce in the Backend

Rules that become validation constraints or write-scope limits. Each entry names the source rule, what it forbids, and how a backend expresses it.

### 1.1 Never delete a maintenance request

**Source:** Skill guard-fou 1. "Jamais supprimer un événement. Même sur demande explicite."

**Backend expression:** No `DELETE` on `maintenance_request` from the application layer. Row-level: soft-delete only (add an `archived_at` timestamp column if needed); hard deletes require an admin-role override. The calendar event is the source of record — once ingested, the row must survive.

**DB constraint:** Grant no `DELETE` privilege on `maintenance_request` to the application role. RLS already restricts writes by role; extend the restriction explicitly to deletions.

### 1.2 Never move a start_date without an explicit, targeted, in-session instruction

**Source:** Skill guard-fou 2. Three cumulative conditions must hold: the instruction is **explicit**, names **this specific event**, and was given **in the current session**. A date received for one event is never transferred to another, even from the same building.

**Backend expression:** Any API endpoint that modifies `maintenance_request.start_date` must require an explicit `force_date_change: true` flag plus a reason string. Moving a date from one request to another (copying from `request_id=X` to `request_id=Y`) is never permitted programmatically.

### 1.3 No financial tenant data in a maintenance record

**Source:** Skill guard-fou 10. "Jamais de données financières du rent roll (loyers, sommes dues, dépôts, endosseurs) dans un événement. Noms, téléphones, courriels, langue : permis."

**Backend expression:** Application-layer validation: before writing any free-text field on `maintenance_request` (`problems`, `other_notes`, `gravity_raw`, `triage_summary`, etc.), the API should reject payloads that contain monetary amounts in context suggesting financial terms (regex on `\$\s*\d`, `loyer`, `dépôt`, `endosseur`). This is primarily an AI-output guard — the calendar event is the risk surface.

**Schema note:** `maintenance_request` correctly has no FK to `lease` or financial columns. That separation is structural enforcement of this rule.

**RLS cross-check (2026-10-08):** The `rls_policies.sql` file independently enforces this boundary: `lease` is `dir_coord_only` (technicians have no SELECT on financial columns); `guarantor` is `dir_coord_only` with an explicit comment citing SKILL.md rule 10; `parking_assignment` and `storage_assignment` are `dir_coord_only` to protect the cost column. Two independent readings of the same source agree: the structural boundary is fully covered. The residual gap — free-text content validation preventing an AI from writing financial data into `problems` or `other_notes` — is an application-layer concern that neither RLS nor DB constraints can address on free text, and is correctly scoped there by both documents.

### 1.4 No access credential information in a maintenance record

**Source:** Skill guard-fou 11. "Jamais d'informations d'accès dans une note (boîtes à clé, codes, emplacements de clés ou de valves) — la fiche technique liée s'en charge. Agenda visible par l'équipe et les sous-traitants."

**Backend expression:** The fiche technique link (`maintenance_request.ft_link`) is the correct place for access info — it points to the secure building data sheet. Any write to `problems`, `other_notes`, or `entry_permission` should not contain keybox codes, access codes, or valve locations. Application-layer check; cannot be a DB constraint on free text.

**Schema note:** `maintenance_request` has no `access_code` column by design. The building's access data lives in `building_fire_system`, `intercom`, and the fiche technique files — all behind coordinator-level RLS.

**RLS cross-check (2026-10-08):** `rls_policies.sql` independently enforces the structural boundary: `building_intercom`, `building_key_box`, `pool_access_code`, `emergency_access_code` are `staff_read` (director + coordinator + technician — explicitly excluding contractors, with a comment citing SKILL.md rule 11 as the source); `building_security_credential` is `admin_director_only`. Contractor SELECT policies are flagged as an open question in the RLS file header; by default, RLS denies access when no policy matches, so the current absence of a contractor policy means contractors would see nothing. Two independent readings agree: the structural separation is correct. The content-validation gap (preventing access info from being written into `entry_permission` free text) is an application-layer concern that cannot be enforced at the DB level on free text, and is correctly scoped there by both documents.

### 1.5 Never overwrite an existing description — additions only

**Source:** Skill guard-fou 3. "Jamais écraser une description. La note s'ajoute AU-DESSUS. La requête Gravity originale reste intacte en bas, toujours."

**Backend expression:** Ingest writes are append-only from the calendar's perspective. Our pipeline stores parsed fields separately; the original Gravity Forms text is preserved in `gravity_raw` and must never be overwritten by a re-parse. Any re-ingestion that finds an existing `event_id` uses `ON CONFLICT DO NOTHING`.

**Current state:** The ingest uses `ON CONFLICT DO NOTHING` on the `mr_event_id_key` partial unique index. Correct.

### 1.6 Strict write scope — only the event currently being triaged

**Source:** Skill guard-fou 13. "Le triage n'écrit QUE dans la nouvelle demande en cours. Deux exceptions balisées seulement (DOUBLON, AJOUT — section 8)."

**Backend expression:** A backend triage API endpoint must accept exactly one `event_id` as its target. Batch writes that modify multiple events in one call (except the documented AJOUT/DOUBLON merge flow) are out of spec. The AJOUT exception allows modifying an existing active request to append a new item — but only when the duplicate-detection flow has confirmed the merge.

### 1.7 No fabricated references — only real tool results

**Source:** Skill guard-fou 15. Anti-fabrication rule: "Un call dont le résultat d'outil n'est pas dans la conversation en cours n'existe pas et ne s'écrit pas." Applied to links: an `htmlLink` inserted into `historique_raw`, `doublons`, or `synergie_raw` must resolve to a real Calendar event ID in our DB.

**Backend expression:** `resolve_url_refs()` (in `parse_calendar_requests.py`) already validates that calendar links in `historique_raw`, `doublons`, and `synergie_raw` resolve to a known `event_id`. The "outside window" case is silently skipped. This is correct — do not invent FKs for events not yet ingested.

**Schema note:** `maintenance_request_history.referenced_request_id` is a real FK. The `historique_raw` free-text field preserves the raw link string for later resolution. Correct separation.

### 1.8 RRIA check is mandatory before writing occupant or bail data

**Source:** Skill guard-fou 16. "RRIA obligatoire pour toute unité de logement — garde-fou bloquant." The RRIA (Registre des Renseignements des Immeubles et Appartements) is the live rent roll. `occupants_raw` and `bail_raw` must come from a real RRIA read, not from Gravity Forms data alone.

**Backend expression:** `occupants_raw` and `bail_raw` in the DB are currently sourced from the triage note, which itself is supposed to come from a RRIA read. When these fields are populated programmatically, the source must be verified. If writing from the calendar note body (AI-produced), flag them with a provenance source of `google_calendar` — which is what the current ingest does. A future backend that writes these from Gravity Forms input alone without a RRIA cross-check would violate this rule.

**Practical impact:** our current ingestion only populates these from parsed calendar notes (AI-produced, post-RRIA). Correct. Do not add a pipeline path that writes tenant names from Gravity Forms without the RRIA cross-check.

### 1.9 No assignee written anywhere by the triage system

**Source:** Skill guard-fou 20 + rule cardinale 37 (22 Aug 2026). "Le triage n'assigne pas. Ni dans le titre, ni dans la note, ni nulle part. La ligne ASSIGNATION PROPOSÉE reste VIDE — toujours, sans exception."

**Backend expression:** `maintenance_request.proposed_assignee` must always be NULL when written by any automated pipeline or AI triage step. Only a human coordinator action may write this field. Application-layer enforcement: triage endpoints may not include `proposed_assignee` in their write payload.

**Current state:** `proposed_assignee` is 0% populated in the DB (no value was ever written by the ingest). Correct — but the column exists and a future write path could accidentally populate it. Add an explicit guard.

---

## Bucket 2 — Encode as Data

Rules that define categorical scales, routing tables, and taxonomy that belong in the DB as structured data rather than free text.

### 2.1 Complexity Scale C1-C4

**Source:** Guide §7a. Introduced 9 Jul 2026 as a replacement for the previous text labels.

| Code | Label | Definition |
|---|---|---|
| C1 | N'importe qui | No tool or skill required; natural pool for delegation to tenant |
| C2 | Ouvrier | Standard toolbox, limited training sufficient |
| C3 | Ouvrier expérimenté / spécialité | Diagnosis required, building system knowledge, real experience needed |
| C4 | Sous-traitant / expertise externe | Newtech, Fortin, roofing, elevator, enamelling, extermination — anything requiring a quote |

**Note format:** `C2 — ouvrier` (code + short label, em-dash). Label for C2 was changed from "de base" to "ouvrier" on 12 Jul 2026 (former label judged pejorative).

**Current schema state:** `complexity_tier` ENUM ('C1','C2','C3','C4') exists and is populated on 1,956 of 10,565 rows (18.5%). The **meaning** of each code is not stored anywhere in the DB — it lives only in this document.

> **Risk:** If this document is lost, the enum values become uninterpretable. Nobody can say what C3 means from the schema alone. Recommended fix: `COMMENT ON TYPE complexity_tier IS 'C1=N''importe qui, C2=Ouvrier, C3=Ouvrier expérimenté/spécialité, C4=Sous-traitant/expertise externe';` — or add a `complexity_tier_def` lookup table with a `definition` column. Either puts the meaning with the data permanently.

**Population by value (current data):** C2: 829, C1: 655, C3: 336, C4: 136.

### 2.2 Backlog / Congestion Scale N1-N5

**Source:** Guide §7b. Introduced 9 Jul 2026 as a replacement for the binary REPORTER mode.

| Level | Label | Effect on triage |
|---|---|---|
| N1 | Au-dessus de nos affaires | Fast response, minimal delegation |
| N2 | Niveau courant | Normal pace |
| N3 | En retard | Negotiate deferred scheduling for non-urgent calls; actively offer delegation |
| N4 | Très en retard | Maximum deferral; paid delegation accepted readily |
| N5 | Critique | Everything that can wait, waits; delegation and subcontracting without hesitation |

**Declared state at document creation (Jul 2026):** N5 — critique.

**Schema note:** Format in note: last line of SECTION COORDOS, dry `N5 — critique`, no parenthetical. The expression "mode REPORTER activé" is explicitly banned.

**Current schema state:** `congestion_level` ENUM ('N1','N2','N3','N4','N5') exists and is populated on 1,953 rows. N5 dominates (1,738 rows = 89% of populated rows), consistent with the declared N5 state during the Jul–Sep 2026 ingest window. The **label meanings** are not in the DB schema.

> **Risk:** Same as C1-C4. If this document is lost, a stored `N3` is uninterpretable. Recommended fix: `COMMENT ON TYPE congestion_level IS 'N1=Au-dessus de nos affaires, N2=Niveau courant, N3=En retard, N4=Très en retard, N5=Critique';` — or a lookup table with a `triage_effect` column that captures the delegation posture each level implies.

### 2.3 Automatic Routing Table A0-A5

**Source:** Guide §6b. The routing table is the mechanical assignment logic applied before any territorial/availability reasoning. Since rule 37 (22 Aug 2026), these rules feed the SOUS-TRAITANT line only — ASSIGNATION PROPOSÉE stays empty always.

| Rule | Category / Scope | Designated handler | Key constraint |
|---|---|---|---|
| **A0** | Default for all cases | CHGE (Charles Genest), coordinator | Every case without a more specific rule goes to CHGE |
| **A1** | Complexity C1 — anyone can do it: key drop, intercom label, simple check | CHGE | Exception to territorial logic — applies regardless of sector |
| **A2** | Gym equipment — broken, damaged, to repair | **Body Gym** (exclusive subcontractor) | No internal evaluation first; C4 always |
| **A3** | Doors/windows — **certain replacement**: broken glass, fogged thermal pane, demolished frame, any glazing work | **Duclos** (exclusive subcontractor) | Duclos only when replacement is certain; diagnosis must precede if cause unknown → A3b |
| **A3b** | Doors/windows — **unknown cause**: won't open/close, sticks, drafts, noise | Internal maintenance worker, sector | Diagnosis first; if replacement confirmed → escalate to A3/Duclos. Never send Duclos or direction on an uncertain call |
| **A4** | 22 specific categories (coordinator filter) | CHGE as initial human filter | List: cigarette smell · intercom · fire alarm · alarm panel · smoke detector · padlock keys · fob · extermination · bulky waste/large furniture · garbage chute smell · elevator/dumbwaiter trouble · Bell · Vidéotron · internet · appliance trouble · snow · lawn · exterior maintenance · window washing · building cleanliness · parking surface (potholes) · pruning/vegetation |
| **A5** | Dedicated perimeters — ALL calls regardless of category | (a) JFME — 350 ch. Ste-Foy; (b) SAHA — Chamonix/Sully project; (c) MACH — rive-sud de Québec (Lévis, Charny, etc., orange sector) | The dedicated employee is the local human filter; exclusive subcontractors (A2, A3, Éric) still apply but are coordinated by the dedicated employee |

**A3/A3b is conditional routing logic, not a simple trade rule.** Duclos exclusivity triggers ONLY when replacement is confirmed certain before the call is placed. An unknown-cause door/window call (won't open, sticks, drafts) goes internal for diagnosis first (A3b); Duclos is called only after the diagnosis confirms replacement is required. The guide is explicit: "jamais Duclos sur un appel dont la cause est inconnue." This distinction matters for any backend routing implementation — assigning Duclos on an A3b call violates the guide even though Duclos is the exclusive vendor for the trade.

**Open question for François — conditional escalation routing (backtest finding):**

Across three separate backtest runs (2026-10-09 to 2026-10-13, ~800 calls total), the model repeatedly produces a routing the current A0-A5 table cannot express cleanly: "handle internally, escalate to specialist X if diagnosis confirms." This manifests as two patterns caught by the gate:

- A1 + named external vendor in `subcontractor_name` (e.g. "Newtech si remplacement de disjoncteur requis" for an electrical outlet; "Fournisseur systèmes d'accès" for a parking remote). Gate 6 correctly rejects A1 + any vendor.
- A3b with empty `subcontractor_name`. A3b is described in the guide as doors/windows diagnosis, but the model applies it to unknown-cause electrical, plumbing, and HVAC calls where the routing intent is the same: internal first, specialist if needed.

Prompting has not held across three attempts. The model's intent is semantically correct — the gap is in the routing table, not the instruction.

**Options for François:**

| Option | Change | Consequence |
|---|---|---|
| **A3b is general** | Expand A3b description from "doors/windows" to "any trade — unknown cause, diagnosis first" | A3b no longer implies Duclos; Duclos only triggers when A3b → A3 escalation is confirmed. A3b `subcontractor_name` stays null until diagnosis |
| **Add A3c** | New code: "any trade — internal diagnosis, specialist TBD" | Preserves A3b as Duclos-specific; gives the model a clean slot for the general case |
| **Route to A0** | Instruct model to use A0 (coordinator default) for ambiguous diagnostic calls; document conditional escalation in `other_notes` | No schema change; coordinator reads the note. Currently A0 is the default catch-all — this formalises that it also covers pre-diagnosis calls |

The gate violations from this pattern (#9575, #1146 in the full run) are correct catches under current rules. This is flagged as a rule-set question, not a gate-tuning question.

**Data gap:** our DB cannot currently distinguish A3 from A3b calls. `subcontractor_name` captures the final SOUS-TRAITANT line result (e.g. "Oui — Duclos" vs. "Non — interne"), which reflects the routing decision already made — but does not label which routing rule produced it. A backend that implements A3/A3b routing would be **adding capability**, not reproducing one: there is no existing `auto_routing_rule` field to populate, and no historical data to validate against.

**Current schema state:** No routing-table column in `maintenance_request`. The `subcontractor_name` free-text field captures the SOUS-TRAITANT line result (e.g. "Non — interne", "Oui — Body Gym"), but the A0-A5 category classification that produced it is never stored. Adding an `auto_routing_rule` VARCHAR (e.g. 'A2', 'A3', 'A4', 'A3b') to `maintenance_request` would make the routing logic queryable.

### 2.4 Exclusive Subcontractors

**Source:** Guide §6 + §6b. Three vendors are explicitly sole-source for their trade — no other vendor is permissible without coordinator override.

| Vendor | Trade | Exclusivity rule |
|---|---|---|
| **Duclos** | Doors, windows, glass, screens | SOLE AND UNIQUE subcontractor for all door/window replacement (A3). Never for uncertain-cause calls (A3b). |
| **Body Gym** | Gym / fitness room equipment | SOLE AND UNIQUE for all gym equipment (A2), no internal evaluation first. |
| **Éric** | Extermination (ants, cockroaches, rodents, wasps) | The exterminator on file; A4 + extermination synergy rules (guide rule 9) apply. |

**Current schema state:** `vendor_contact` table exists with 176 rows. `maintenance_request.vendor_id` exists but is 0% populated (see project_status.md §8, vendor_id section). There is no `exclusivity_scope` column or constraint that marks these three vendors as sole-source. A `vendor_contact.exclusive_trade` VARCHAR or a separate `vendor_exclusivity` table would let the backend enforce A2/A3/extermination routing automatically.

### 2.5 Territory Colors (colorId → sector)

**Source:** Guide §3.

| Google colorId | Color name | Territory |
|---|---|---|
| 2 | Sage (pale green) | **Untriaged** — new Gravity Forms call, must not be set by coordinator |
| 8 | Graphite (gray) | **Resolved/closed** — human-only decision |
| 11 | Tomato (red) | Emergency on-call / shift change |
| 1 | Lavender | Vacation / OFF / absence |
| 7 | Peacock (teal) | **Ste-Foy – Sillery** |
| 5 | Banana (yellow) | **Haute-Ville** |
| 3 | Grape (purple) | **Beauport-Charlesbourg** (agenda label; maps to part of "Québec-Est" in our sector table) |
| 10 | Basil (dark green) | **Lebourgneuf-Vanier / Québec-Ouest** |
| 4 | Flamingo (pink) | **Limoilou** (agenda label; maps to part of "Québec-Est" in our sector table) |
| 6 | Tangerine (orange) | **Lévis** (Est and Ouest share the same color) |

**Rules:** colorId=2 (green) is the exclusive marker of an untriaged request. colorId=8 (gray) means resolved — the triage system never sets gray; only a human may. colorId=11 (red) is emergency on-call; the triage system never touches red events.

**Current schema state:** `sector.color_code` stores the colorId string (e.g. '7', '5') for each sector. Individual `maintenance_request` rows do not store the event's colorId — the Calendar API does not return per-event colorId except for explicit overrides; sector color is calendar-level. The untriaged/resolved/emergency distinction (colorId=2/8/11) is not stored per row in the DB. Adding a `triage_status` ENUM ('untriaged', 'triaged', 'resolved') would replicate this at the DB level without requiring a Calendar re-fetch.

### 2.6 Time Estimate Standard Buckets

**Source:** Guide §9, SECTION COORDOS line 8 (TEMPS). Standard tranches:

| Bucket | Label |
|---|---|
| `<30 min` | Under 30 minutes |
| `30 min-1h` | 30 minutes to 1 hour |
| `1h-2h` | 1 to 2 hours |
| `demi-journée` | Half-day |
| `journée+` | Full day or more |
| `soumission requise` | Quote required before estimating |

**Current schema state:** `time_estimate_bucket` ENUM exists (`UNDER_30_MIN`, `MIN30_TO_1H`, `H1_TO_2H`, `H2_TO_4H`, `HALF_DAY_PLUS`, `TBD_ON_SITE`). The enum values diverge from the guide's canonical labels: `H2_TO_4H` does not appear in the guide (the guide jumps from `1h-2h` to `demi-journée`), and `TBD_ON_SITE` maps to `soumission requise`. The French labels in the guide and the English enum names are not documented together anywhere. This document is now the canonical mapping. Recommend either aligning the enum to the guide buckets or adding a comment column.

---

## Bucket 3 — Doesn't Transfer

Calendar-specific mechanics that govern the AI triage session but have no equivalent in the backend data model. Listed so they are clearly excluded rather than overlooked.

| Mechanic | Source | Why excluded |
|---|---|---|
| Note block HTML formatting | Guide §9, SECTION TERRAIN/COORDOS templates | The backend stores parsed field values, not the rendered HTML. Format is the AI's responsibility when writing to Calendar. |
| Separator sandwich before SECTION COORDOS | Guide §9 (v10.6) | Presentation only; no data equivalent. |
| BÉLANGER + date signature | Skill guard-fou 8 | `maintenance_request.signed_date` captures the date; the "BÉLANGER" prefix is a calendar convention identifying the AI author, irrelevant to DB rows. |
| [EN TRAITEMENT] lock prefix | Guide rule 38 | A transient in-flight lock on the Calendar event title; never stored. The DB has no row-level lock equivalent for triage-in-progress. |
| Pagination — read until no nextPageToken | Guide rule 33 | The Calendar API pagination rule governs the ingest pull loop, not the DB schema. Already implemented in `_pull_events()`. |
| Bounded search windows (±90/45 days for duplicates, 60→21 for synergy) | Guide rule 40 | Query parameter to the Calendar API during triage; not a DB constraint. |
| Photo verification in Gmail by ASNU | Guide §9 step 1 | Gmail cross-check during triage; result recorded in `other_notes` free text. No structured column. |
| [EN TRAITEMENT] abandoned-lock sweep at session start | Guide rule 38c | Session management for the AI triage agent; not a DB operation. |
| Maximum 5 linked synergy entries (rest compact) | Guide §9, CALLS ACTIFS line | Rendering rule for the Calendar event note; backend stores the full `synergy_request_ids` array without a 5-link cap. |
| Description length limit 7,500 characters | Guide rule 11 | Google Calendar API limit; the DB has no equivalent constraint on text fields. |
| Notification suppression (NONE on every update) | Skill guard-fou 5 | API call parameter; no DB equivalent. |
| Saturday event date = atterrissage zone | Guide rule 32 | Workflow convention for where new calls land in the calendar; not enforced in the DB (start_date can be any day). |
| Frequency of scheduled task (0 7-17 * * *) | Guide rule 42 | Infrastructure configuration for the external cron job; not a DB rule. |

---

## Bucket 4 — Affects Existing Data

Rules from guide v4.39 / skill v6.1 that contradict or recontextualise data already in the DB.

### 4.1 Assignment rule reversal (rule 37, 22 Aug 2026) — WELL-COVERED

The detailed analysis is in `docs/calendar-parser-reference.md §0`. Summary:

- Events ingested before 22 Aug 2026 may have `assigned_employee_id` populated from the title (pre-rule-25 events, before 13 Jul 2026) or from the ASSIGNATION PROPOSÉE line of the note (post-rule-25, 13 Jul – 21 Aug 2026).
- Events ingested after 22 Aug 2026 (rule 37) should have `proposed_assignee = NULL` if the triage was done correctly; the automated Saturday task may have continued writing assignees.
- `assigned_employee_code_raw` preserves whatever was in the title — this is ground truth for the era before rule 25.
- **Nothing in the DB is wrong for its era.** The column `proposed_assignee` is correctly 0% populated from the current pipeline. No correction needed.

### 4.2 Synergy scope: only the event's OWN filière (rule 13, amended rule 35/36)

**Source:** Guide §8, CALLS ACTIFS / SYNERGIE rule. An internal call's synergy inventory includes ONLY internal calls (not subcontractor calls). A subcontractor call's inventory includes ONLY calls of the same subcontractor. The two filières are never mixed.

**Data impact:** `maintenance_request.synergy_request_ids` (integer array) currently stores any calendar cross-reference found in the `synergie_raw` text. The filière filter was a triage-time rule applied when the AI wrote the note; we don't know retrospectively which calls were excluded or which included. The array reflects what the coordinator accepted — it may include cross-filière references from before rule 13 was established (12 Jul 2026). **Use `synergy_request_ids` as an advisory signal, not as an authoritative filière-filtered list.**

### 4.3 ST Giroux calendar removed from scope (rule 36, 22 Aug 2026)

**Source:** Guide §8, rule 36. The MAIN - ST Giroux calendar was part of the triage search scope from 8 Aug to 22 Aug 2026 and was then permanently retired. Events found in that calendar during that window may appear in `historique_raw`, `doublons`, or `synergie_raw` as calendar links. Those links will not resolve via `resolve_url_refs()` because we never ingested from ST Giroux.

**Data impact:** Any unresolved `[LINK:https://...]` in `historique_raw` or `synergie_raw` that references a ST Giroux event ID will show as "outside window" in the resolution counts. This is correct behaviour, not a gap.

### 4.4 Urgency classification retroactively broadened (rule 28 amendments)

**Source:** Guide rule 28. AJD (urgent) now includes **indirect water signals**: dripping sound in a wall, expanding moisture stain, bowing ceiling = probable hidden leak = AJD even without visible water. Vermin = **always `ajd`** (lowercase), systematic.

**Data impact:** Older events triaged before this rule clarification may have `urgency_tier = NULL` or `urgency_raw = NULL` for what would now be an `ajd`-tier call. The rule was clarified progressively through Jul 2026. Events in the Mar–Jun 2026 (unparsed) cohort were triaged under an older standard and have no `urgency_tier` stored (the field comes from the structured note). **No retroactive correction is warranted** — the classification reflects the standard at the time of triage.

### 4.5 Duplicate calls: DOUBLON POTENTIEL is a title annotation, not a resolved status

**Source:** Guide rule 27. When a doublon is suspected, the title gets `DOUBLON POTENTIEL:` prepended and the DOUBLONS line of the note gets a link to the original. The final merge/gray decision is human-only.

**Data impact:** `maintenance_request.duplicate_of_request_id` is populated by `resolve_url_refs()` from the `doublons` field. This FK was set where a link in `doublons` resolved to a known request — 66 rows currently. A row with `duplicate_of_request_id` set does NOT mean the coordinator confirmed and resolved the duplicate; it means the AI flagged it and the link resolved. Do not use this FK as a "confirmed duplicate" status. A separate `duplicate_confirmed_at` timestamp or `duplicate_status` ENUM would be needed to distinguish AI flag from coordinator decision.

### 4.6 AJOUT mechanic — the merged call is not the canonical one

**Source:** Guide §8, AJOUT verdict. When a new Gravity Forms call is merged into an existing active call (same unit, different problem), the EXISTING call gets a new numbered item and an updated title. The NEW call gets renamed to `UNITÉ ADRESSE: Ajout à appel existant` and keeps its own calendar event (never deleted, never grayed by the triage).

**Data impact:** Our DB has separate rows for both the original and the "Ajout" event. The new call's `raw_title` may contain "Ajout à appel existant" and its `problems` field will be sparse (the merged content lives in the original call). `maintenance_request_history` or `duplicate_of_request_id` may link them if `doublons` or `historique_raw` referenced the original. **There is no `merged_into_request_id` column.** The relationship is currently only traceable through `historique_raw`/`doublons` text links if the triage wrote them. Consider adding a `parent_request_id` FK for the AJOUT case.
