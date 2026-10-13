# Proposed RLS Model — SIB Platform (v2)

_Revised after auditing SKILL.md, the client's live triage-agent rulebook. Three of the five open questions from v1 are now answered by the client's own production rules rather than by our assumptions — and one new access tier surfaced that v1 missed entirely._

---

## 0. What changed from v1, and why

SKILL.md is not a privacy policy on paper — it's an **operating privacy model already in production**, enforced on every maintenance ticket the client's AI agent writes today. Its rules are written as authoring constraints ("never put X in a note") but they encode exactly the access boundaries RLS needs to reproduce.

| v1 open question | Answer, from SKILL.md | Effect on the model |
|---|---|---|
| Should technicians see lease dates? | **Yes — and the line is drawn precisely.** Rule 10: *"Jamais de données financières du rent roll (loyers, sommes dues, dépôts, endosseurs)… Noms, téléphones, courriels, langue : permis."* The BAIL block spec permits *"grandeur — début : date — fin : date."* | v1 was too permissive on `guarantor` and too restrictive on lease dates. Now column-precise. |
| Do contractors need access codes? | **No — explicitly forbidden, with the reason stated.** Rule 11: *"Jamais d'informations d'accès dans une note (boîtes à clé, codes, emplacements de clés ou de valves) — la fiche technique liée s'en charge. **Agenda visible par l'équipe et les sous-traitants**."* | Confirms the concern that drove v1's caution. Access data is deliberately kept out of anything subcontractors read. |
| Are contractors real users? | **Partially — they are readers.** "Agenda visible par… les sous-traitants" confirms subcontractors see ticket content. Whether via login or shared calendar is not stated. | `contractor` stays a role, but read-only and narrowly scoped. |
| Can one person hold multiple roles? | Not addressed. | **Still open.** |
| Is there a compliance driver (Loi 25)? | Not addressed. | **Still open — and the highest-stakes unknown.** |

**New tier discovered (v1 missed this entirely):** SKILL.md rule 7 forbids *"vocabulaire interne"* — the A0–A5 routing codes, C1–C4 complexity codes, N1–N5 congestion codes — from appearing in any event, and rule 20 keeps `ASSIGNATION PROPOSÉE` empty on purpose so routing logic isn't exposed. The client already separates **operational data** (shareable) from **internal classification/routing logic** (hidden from field readers). See §3.

---

## 1. Roles

| Role | Who | Basis |
|---|---|---|
| `admin` | Developers/operators | Not a client role; needed for maintenance |
| `director` | CHBE (directeur) | "Direction/coordination" |
| `coordinator` | CALE, CHGE, PISI, SETO, DISP | Same grouping; rule A0 makes CHGE default |
| `technician` | Responsables techniques + Ouvriers (`employment_type='staff'`) | secteurs-et-equipe.md groupings |
| `contractor` | Ouvriers-compagnies (`employment_type='contractor_company'`) | Explicitly *"fonctionnent comme des employés"* but not staff |

**No tenant role** — confirmed out of scope. Tenants submit via unauthenticated Gravity Forms.

---

## 2. Tenant PII — now column-precise, per SKILL.md rule 10

This replaces v1's vaguer "name + phone only" proposal.

| Data | director / coordinator | technician | contractor |
|---|---|---|---|
| `tenant.nom_complet`, `.telephone`, `.courriel` | ✅ | ✅ | ✅ |
| `lease.langue_bail` | ✅ | ✅ | ✅ |
| `unit.grandeur` | ✅ | ✅ | ✅ |
| `lease.debut_bail`, `.fin_bail` | ✅ | ✅ | ✅ |
| `lease.loyer_de_base`, `.loyer_total`, `.depot`, `.somme_due_restante` | ✅ | ❌ | ❌ |
| `guarantor` (whole table) | ✅ | ❌ | ❌ |
| `lease.notes_collecte` (collections notes) | ✅ | ❌ | ❌ |
| `parking_assignment.cost`, `storage_assignment.cost` | ✅ | ❌ | ❌ |

Rule 10 names four forbidden categories verbatim: **loyers, sommes dues, dépôts, endosseurs** (rents, amounts owed, deposits, guarantors). Everything above maps directly to one of those.

**Implementation:** since RLS is row-level, the financial columns need either a separate `lease_financial` table or a restricted view. Recommend the **view** approach here (unlike credentials, §4) — these columns are tightly coupled to the lease row and splitting the table would complicate every future lease query.

---

## 3. Internal routing vocabulary — NEW tier (v1 missed this)

SKILL.md rule 7 and rule 20 deliberately keep classification/routing logic out of anything field staff and subcontractors read. The equivalent database columns:

| Column | Rule |
|---|---|
| `maintenance_request.urgency_tier` (AJD codes) | Rule 7 forbids A1–A5 vocabulary in events |
| `.complexity_tier` (C1–C4) | Rule 7 names C1–C4 explicitly |
| `.congestion_level` (N1–N5) | Rule 7 names N1–N5 explicitly |
| `.delegable_status`, `.report_status`, `.triage_summary` | Coordination mechanics — SKILL.md keeps these in SECTION COORDOS, structurally separated from the field-facing blocks by the "separator sandwich" so *"les gars de terrain ne descendent jamais là"* |
| `.proposed_assignee` | Rule 20 — kept empty on purpose |

**Proposed:** `director` and `coordinator` see these; `technician` and `contractor` do not.

**Worth flagging as a question, not a certainty:** SKILL.md's rules govern what gets *written into a calendar event* — a shared surface with weak access control. A proper database with real RLS is a different context, and it's plausible the client would be comfortable exposing more here than they can safely put in a calendar. Recommend confirming rather than assuming the same boundary applies.

---

## 4. Access credentials — two tiers, per SKILL.md rule 11

Rule 11's reasoning is explicit: access info stays out of the calendar *because* subcontractors can read it, and lives behind the linked technical sheet instead.

**Tier 1 — system credentials (most restricted).** `building_camera_system.password`, `building_access_control.ip_module_password` / `.system_login` / `.system_password`.
→ **`admin` and `director` only.** Recommend moving these 4 columns into a separate `building_security_credential` table rather than column-grants — the boundary is then obvious in the schema itself, and auditable. Parent rows stay readable (a technician can see a building has a Paradox EVO192 without seeing its password).

**Tier 2 — physical access codes.** `building_intercom.keyless_code_*`, `building_key_box.code`, `pool_access_code.code_value`, `emergency_access_code.code_value`.
→ **`admin`, `director`, `coordinator`, `technician` — NOT `contractor`.** This is the direct RLS translation of rule 11: staff need to enter buildings; subcontractors should be admitted, not self-admitting.

---

## 5. maintenance_request scoping

| Role | Visibility |
|---|---|
| director, coordinator | All requests |
| technician | Own `assigned_employee_id` + all requests in their `sector_id` + any building they hold an A5 dedication for |
| contractor | Own `assigned_employee_id` only |

**A5 dedications** (JFME→350 Ste-Foy, SAHA→Chamonix/Sully, MACH→rive-sud) are real operational scope, confirmed in SKILL.md's A5 table: *"tous les appels du périmètre, peu importe la catégorie."* Recommend an `employee_building_assignment` junction table — the data already exists in `employee.notes`.

---

## 6. Writes

**No user-facing writes initially.** Every row currently in the database has a `data_provenance` trail to a source file/tab/row/column. Direct user writes would create rows with no provenance, breaking the audit chain. If writes become a requirement, route them through an API layer that writes provenance alongside.

---

## 7. Prerequisites before any policy works

1. **`employee.auth_user_id` is null for all 41 people** — no one has a login. Every policy here keys off `auth.uid()` → employee. This is a blocker, not a follow-up.
2. **A `role` column** on `employee` (or `employee_role` table if multi-role is needed — see §8 Q1).
3. **`employee_building_assignment`** table for A5 dedications (§5).
4. **`building_security_credential`** table split (§4 Tier 1).
5. **`current_employee_id()` SECURITY DEFINER helper** — resolves `auth.uid()` once so policies don't each re-query; standard Supabase pattern, avoids recursive RLS.
6. **A financial-columns view** for `lease` (§2).

---

## 8. Still genuinely open

1. **Can one person hold multiple roles?** Not addressed anywhere in the client docs. Determines `role` column vs. `employee_role` table.
2. **Is there a compliance driver — Loi 25 or similar?** Nothing in any client document addresses this. **Highest-stakes unknown**: if this is legally driven rather than internal hygiene, access *logging* is likely required on top of access *control*, which is a separate build. SKILL.md's rules show a practical privacy instinct, not a stated legal obligation.
3. **Do contractors get real logins, or shared-calendar visibility only?** "Agenda visible par… les sous-traitants" confirms they read tickets, but not by what mechanism.
4. **Does the internal-vocabulary restriction (§3) apply in a real database**, or was it specific to the calendar being a weakly-controlled shared surface?
