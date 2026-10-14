# Schema Audit — 2026-10-14

Catalogued findings from Step 5 (10 read-only database checks) and follow-up
queries F1–F6′. All data re-queried on 2026-10-14 against PostgreSQL 17.6 via
the Supabase session pooler unless noted otherwise.

---

## Step 5 Checks

### Check 1 — View `security_invoker` reloptions

All 4 public views carry `security_invoker=true` in `reloptions`. Queried via
`pg_class.reloptions`.

| View | security_invoker |
|---|---|
| `lease_field_view` | true |
| `maintenance_request_tech_view` | true |
| `parking_assignment_field_view` | true |
| `storage_assignment_field_view` | true |

---

### Check 2 — SECURITY DEFINER functions

Queried via `pg_proc.prosecdef = true` in namespace `public`.

| Function | prosecdef | search_path |
|---|---|---|
| `current_employee_id()` | true | `public, auth` ⚠ |
| `has_role(role_name text)` | true | `public, auth` ⚠ |
| `rls_auto_enable()` | true | `pg_catalog` ✓ |
| `technician_building_ids()` | true | `public, auth` ⚠ |

`rls_auto_enable` with `search_path=pg_catalog` is the **safer** setting — it
cannot resolve objects outside system catalogs.

The three functions with `search_path=public, auth` can resolve names in both
the `public` and `auth` schemas while executing under the definer's privileges.
The relevant risk is **object shadowing**: if a role with CREATE privilege in
`public` creates a function or type whose name shadows something from the `auth`
schema, a SECURITY DEFINER function could silently call the wrong object.

`has_schema_privilege` on remote (queried 2026-10-14):

| Role | CREATE in public | USAGE in public |
|---|---|---|
| `anon` | **false** | true |
| `authenticated` | **false** | true |

Neither anon nor authenticated can create objects in public, so the shadowing
risk is not exploitable by those roles. The remaining concern is postgres and
service_role, which can CREATE in public and are already in a privileged
position. Flag for review if logic is ever added to these three functions.

---

### Check 3 — PK catalog (see F3′ for full re-query)

See **F3′** below for the authoritative fresh catalog. Summary:

- 54 public tables total
- 3 composite-PK tables: `building_employee_assignment`, `building_vendor`,
  `service_contract_building`
- 1 varchar-PK table: `laundry_contract` (PK `uln`)
- 5 sequence-backed PKs: `building_security_credential`, `employee_building_assignment`,
  `employee_role`, `maintenance_request_history`, `triage_log`
- 45 caller-supplied integer PKs (no default/sequence/identity)

---

### Check 4 — `maintenance_request.status`

| Attribute | Value |
|---|---|
| Column type | `USER-DEFINED` enum `request_status` |
| Nullable | NOT NULL |
| Default | none |

Allowed enum values: `intake_received`, `triage_pending`, `triaged`,
`triage_clarify`, `triage_proposal`, `triage_failed`, `en_route`, `closed`.

See **F1** for which values `service.py` writes.

---

### Check 5 — `unit` table duplicate pairs

Queried 2026-10-14:

| Uniqueness scope | Duplicate groups |
|---|---|
| `(building_id, numero_appartement)` | 317 |
| `(building_id, rue, numero_appartement)` | **2** |

The 315 apparent duplicates under the two-column scope are multi-civic-address
buildings (same apartment number, different `rue`). The 2 true triples:

| building_id | rue | numero_appartement | row count |
|---|---|---|---|
| 141 | `4298, rue des Roses` | `104` | 2 |
| 156 | `12085, av. Berlioz` | `310` | 2 |

---

### Check 6 — MRR "Unique Unit Number" column

The Master Rent Roll column is **"Unique Unit Number"** (spreadsheet column
index 1, 0-based). Format: `{civic}-{apt} {street abbreviation}`, e.g.
`405-1 41e Rue O.`

In `data_provenance`: `target_table='unit'`, `source_file_name='Master Rent
Roll - All SIB Units.xlsx'`, `source_tab='Rent roll'`.

---

### Check 7 — Sparse / uncertain columns

Queried 2026-10-14 from `maintenance_request` (10 565 rows) and `employee`
(50 rows).

| Column | Total rows | Filled | % | DBML note | Verdict |
|---|---|---|---|---|---|
| `maintenance_request.banked_queue_date` | 10 565 | 0 | 0% | bare entry, no note | **Deprecate** |
| `maintenance_request.triage_started_at` | 10 565 | 0 | 0% | set by triage lock | Keep (fills post-deploy) |
| `maintenance_request.submission_date` | 10 565 | 0 | 0% | gravity_forms date | Keep (fixable; see F6′) |
| `maintenance_request.gravity_raw` | 10 565 | 10 502 | 99.4% | pre-form technician notes | Keep |
| `maintenance_request.assigned_employee_id` | 10 565 | 2 366 | 22.4% | FK to employee | Keep |
| `employee.sector_id` | 50 | 10 | 20% | nullable by design | Reuse |

---

### Check 8 — `timestamp without time zone` columns

| Table | Column | Nullable | Written with |
|---|---|---|---|
| `data_provenance` | `ingested_at` | YES | Python `datetime.utcnow()` (ingest scripts) |
| `maintenance_request` | `triage_started_at` | YES | SQL `NOW()` (service.py line 289) |
| `triage_log` | `attempted_at` | NO | SQL `NOW()` (service.py line 222) |

Server timezone: UTC. Both `NOW()` values land as naive UTC; consistent with
the Python-side `datetime.utcnow()` arithmetic in the abandoned-lock detection.

**Decision (2026-10-14):** Do NOT convert `triage_started_at` or
`triage_log.attempted_at` to `timestamptz`. Triage's abandoned-lock check
(`datetime.utcnow() - started_at`) would break against an aware value.
Conversion deferred until the post-freeze triage port to psycopg3.

---

### Check 9 — RLS: tables with RLS on but no policies

24 tables have `relrowsecurity=true` and zero policies.

**RLS bypass:** `service_role` and `postgres` have BYPASSRLS in Supabase's
default configuration, and `relforcerowsecurity=false` on all tables (confirmed
in prior check). Backend FastAPI calls use service_role and are not affected.

**Who is actually blocked:** `anon` and `authenticated` roles accessing tables
directly via PostgREST. With no policies, any `SELECT`/`INSERT`/`UPDATE`/
`DELETE` from those roles returns zero rows or an error.

From the backend code, the only no-policy tables referenced by application
code are `triage_log` (service.py, via service_role — not blocked),
`pest_control_case` and `unit_turnover` (context_builder.py, via service_role —
not blocked). The remaining 21 tables are not yet accessed by any code path.

None of the 24 tables are intended for direct anon/authenticated PostgREST
access at this time. The RLS-on-no-policy state is the correct enforcement
posture until explicit policies are written.

```
building_employee_assignment    maintenance_attachment
building_telecom                maintenance_request_history
cleaning_task_checklist         on_call_schedule
data_provenance                 pest_control_case
elevator_reservation            recurring_task_pattern
employee_building_assignment    staff_shift
employee_role                   tenant_equipment_loan
laundry_contract                triage_log
                                unit_appliance
                                unit_turnover
                                unit_turnover_furniture_item
                                unit_turnover_settlement
                                vacant_unit_task
                                vacant_unit_task_item
                                vendor_category_exclusivity
                                waste_collection_schedule
```

---

### Check 10 — pg_dump version mismatch

| Component | Version |
|---|---|
| Server | PostgreSQL 17.6 |
| Local pg_dump (Homebrew) | 18.3 |

pg_dump 18.x is backward-compatible for dumping 17.x servers but may emit
18.x-only syntax options. Supabase CLI `db dump` (uses server-side pg_dump)
avoids this entirely and is preferred for Phase B.

---

## F-series Follow-up Findings

### F1 — `maintenance_request.status`

Type: `USER-DEFINED` enum `request_status`.

| Enum value | Written by `backend/triage/service.py` | Notes |
|---|---|---|
| `intake_received` | No | Set by intake layer |
| `triage_pending` | **Yes** (line 289 — lock) | |
| `triaged` | **Yes** (line 166 — success) | |
| `triage_clarify` | No | service.py skips rows in this state |
| `triage_proposal` | No | In enum; not written anywhere |
| `triage_failed` | **Yes** (line 375 — retries exhausted) | |
| `en_route` | No | Downstream dispatch |
| `closed` | No | Terminal; triage skips it |

---

### F2 — Timestamp write mechanism

| Column | Written with | Abandoned-lock detection |
|---|---|---|
| `maintenance_request.triage_started_at` | SQL `NOW()` (naive UTC) | `datetime.utcnow() - started_at` — deprecated in Python 3.12+ |
| `triage_log.attempted_at` | SQL `NOW()` (naive UTC) | N/A |

**Decision:** No conversion to `timestamptz` until post-freeze triage port (see Check 8).

---

### F3′ — Full PK catalog (re-queried 2026-10-14)

Query used `pg_constraint`, `pg_class`, `pg_namespace`, `pg_attribute`;
`attidentity`, `atthasdef`, `pg_get_serial_sequence()` (avoided in max() pass
due to Supabase pooler trigger on "migrations" table).

#### All 54 public tables

| Table | PK col(s) | Count | Type | Source |
|---|---|---|---|---|
| `building` | `building_id` | 1 | integer | none |
| `building_access_control` | `access_control_id` | 1 | integer | none |
| `building_camera_system` | `camera_system_id` | 1 | integer | none |
| `building_document` | `document_id` | 1 | integer | none |
| `building_employee_assignment` | `building_id, employee_id` | 2 | integer, integer | none, none |
| `building_fire_system` | `fire_system_id` | 1 | integer | none |
| `building_intercom` | `intercom_id` | 1 | integer | none |
| `building_key_box` | `box_id` | 1 | integer | none |
| `building_paint_spec` | `paint_spec_id` | 1 | integer | none |
| `building_security_credential` | `credential_id` | 1 | integer | **sequence** |
| `building_telecom` | `building_id` | 1 | integer | none |
| `building_vendor` | `building_id, vendor_id` | 2 | integer, integer | none, none |
| `cleaning_task_checklist` | `checklist_id` | 1 | integer | none |
| `data_provenance` | `provenance_id` | 1 | integer | none |
| `elevator_reservation` | `reservation_id` | 1 | integer | none |
| `emergency_access_code` | `access_code_id` | 1 | integer | none |
| `employee` | `employee_id` | 1 | integer | none |
| `employee_building_assignment` | `assignment_id` | 1 | integer | **sequence** |
| `employee_role` | `employee_role_id` | 1 | integer | **sequence** |
| `entrance` | `entrance_id` | 1 | integer | none |
| `equipment` | `equipment_id` | 1 | integer | none |
| `guarantor` | `guarantor_id` | 1 | integer | none |
| `laundry_contract` | `uln` | 1 | character varying | none |
| `lease` | `lease_id` | 1 | integer | none |
| `maintenance_attachment` | `attachment_id` | 1 | integer | none |
| `maintenance_followup_entry` | `followup_id` | 1 | integer | none |
| `maintenance_request` | `request_id` | 1 | integer | none |
| `maintenance_request_history` | `history_id` | 1 | integer | **sequence** |
| `on_call_schedule` | `on_call_id` | 1 | integer | none |
| `parking_assignment` | `parking_id` | 1 | integer | none |
| `pest_control_case` | `case_id` | 1 | integer | none |
| `pool_access_code` | `pool_code_id` | 1 | integer | none |
| `project` | `project_id` | 1 | integer | none |
| `recurring_task_pattern` | `pattern_id` | 1 | integer | none |
| `sector` | `sector_id` | 1 | integer | none |
| `service_contract` | `contract_id` | 1 | integer | none |
| `service_contract_building` | `contract_id, building_id` | 2 | integer, integer | none, none |
| `service_visit` | `visit_id` | 1 | integer | none |
| `staff_shift` | `shift_id` | 1 | integer | none |
| `storage_assignment` | `storage_id` | 1 | integer | none |
| `tenancy_record` | `tenancy_id` | 1 | integer | none |
| `tenant` | `tenant_id` | 1 | integer | none |
| `tenant_equipment_loan` | `loan_id` | 1 | integer | none |
| `triage_log` | `log_id` | 1 | integer | **sequence** |
| `unit` | `unit_id` | 1 | integer | none |
| `unit_appliance` | `unit_appliance_id` | 1 | integer | none |
| `unit_turnover` | `turnover_id` | 1 | integer | none |
| `unit_turnover_furniture_item` | `furniture_item_id` | 1 | integer | none |
| `unit_turnover_settlement` | `settlement_id` | 1 | integer | none |
| `vacant_unit_task` | `task_id` | 1 | integer | none |
| `vacant_unit_task_item` | `item_id` | 1 | integer | none |
| `vendor_category_exclusivity` | `exclusivity_id` | 1 | integer | none |
| `vendor_contact` | `vendor_id` | 1 | integer | none |
| `waste_collection_schedule` | `schedule_id` | 1 | integer | none |

#### 45 no-default single-integer-PK tables: max(pk)

`None` = table is empty. All IDs are caller-supplied (COALESCE/MAX-offset
counters in ingestion scripts or monotone counters starting at 1).

| Table | PK column | max(pk) | Ingestion script(s) |
|---|---|---|---|
| `building` | `building_id` | 180 | `write_building.py` |
| `building_access_control` | `access_control_id` | 81 | `ingest_security.py` |
| `building_camera_system` | `camera_system_id` | 166 | `ingest_security.py` |
| `building_document` | `document_id` | None | — (no script yet) |
| `building_fire_system` | `fire_system_id` | 170 | `ingest_fire_protection.py` |
| `building_intercom` | `intercom_id` | 114 | `ingest_security.py` |
| `building_key_box` | `box_id` | None | — (no script yet) |
| `building_paint_spec` | `paint_spec_id` | 563 | `ingest_building_paint_spec.py` |
| `building_telecom` | `building_id` | 175 | `ingest_telecom.py` |
| `cleaning_task_checklist` | `checklist_id` | None | — (no script yet) |
| `data_provenance` | `provenance_id` | 271 545 | `provenance.py` (shared helper) |
| `elevator_reservation` | `reservation_id` | None | — (no script yet) |
| `emergency_access_code` | `access_code_id` | 14 | `ingest_emergency_access_code.py` |
| `employee` | `employee_id` | 50 | `ingest_employees.py` |
| `entrance` | `entrance_id` | 179 | `ingest_security.py` |
| `equipment` | `equipment_id` | 62 | `ingest_equipment.py` |
| `guarantor` | `guarantor_id` | 527 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `lease` | `lease_id` | 4 332 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `maintenance_attachment` | `attachment_id` | None | — (no script yet) |
| `maintenance_followup_entry` | `followup_id` | 3 990 | `write_maintenance_requests.py` |
| `maintenance_request` | `request_id` | 10 566 | `write_maintenance_requests.py` |
| `on_call_schedule` | `on_call_id` | None | — (no script yet) |
| `parking_assignment` | `parking_id` | 3 155 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `pest_control_case` | `case_id` | None | — (no script yet) |
| `pool_access_code` | `pool_code_id` | 52 | `ingest_pool_access_codes.py` |
| `project` | `project_id` | 75 | `write_building.py` |
| `recurring_task_pattern` | `pattern_id` | None | — (no script yet) |
| `sector` | `sector_id` | 7 | `write_building.py` |
| `service_contract` | `contract_id` | 252 | `ingest_elevator_contracts.py`, `ingest_extermination_contract.py`, `ingest_lawn_contracts.py`, `ingest_snow_contracts.py` |
| `service_visit` | `visit_id` | 376 | `ingest_fire_protection.py`, `ingest_fire_inspection_pdf.py` |
| `staff_shift` | `shift_id` | None | — (no script yet) |
| `storage_assignment` | `storage_id` | 1 321 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `tenancy_record` | `tenancy_id` | 5 616 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `tenant` | `tenant_id` | 6 138 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `tenant_equipment_loan` | `loan_id` | None | — (no script yet) |
| `unit` | `unit_id` | 4 332 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `unit_appliance` | `unit_appliance_id` | 2 229 | `ingest_units_leases_tenants.py`, `ingest_perigord_units.py` |
| `unit_turnover` | `turnover_id` | 691 | `ingest_unit_turnover.py` |
| `unit_turnover_furniture_item` | `furniture_item_id` | None | — (no script yet) |
| `unit_turnover_settlement` | `settlement_id` | None | — (no script yet) |
| `vacant_unit_task` | `task_id` | None | — (no script yet) |
| `vacant_unit_task_item` | `item_id` | None | — (no script yet) |
| `vendor_category_exclusivity` | `exclusivity_id` | None | — (no script yet) |
| `vendor_contact` | `vendor_id` | 215 | `ingest_vendor_contact.py`, `ingest_lawn_contracts.py`, `ingest_snow_contracts.py` |
| `waste_collection_schedule` | `schedule_id` | None | — (no script yet) |

**ID generation pattern (all no-default tables):** scripts maintain a monotone
counter starting at 1 or `COALESCE(MAX(pk), 0) + offset`. No sequences, no
IDENTITY — every PK value is caller-supplied. A re-run without prior truncation
will hit PK conflicts on the first row.

---

### F4′ — MRR "Unique Unit Number" → `unit` table resolution (re-queried 2026-10-14)

Source: `Master Rent Roll - All SIB Units.xlsx`, sheet "Rent roll", 4 357
distinct residential unit keys (revenue keys — PARKING, STATIONNEMENT,
BUANDERIE, ANTENNA — excluded).

Resolution logic (mirrors `ingest_units_leases_tenants.py`):
1. Look up `building_id` via MRR column 77 ("Unique Building Name") → `building.adresse`
2. Look up `unit` row via `(building_id, rue, numero_appartement)` where
   `rue` = MRR col 2, `numero_appartement` = MRR col 3

| Outcome | Count | % |
|---|---|---|
| Key → exactly 1 unit | 4 327 | 99.3% |
| Key → 0 units | 26 | 0.6% |
| Key → >1 unit | 4 | 0.1% |

**Zero-match causes (sample):**
- `'STAT_41eRue-Gros-Pins_J'` — revenue-format key not caught by `_is_revenue()` filter; building found but (bid, rue, apt) not in unit table
- `'TOTAL'`, `'Total'` — MRR summary rows with no building (bldg_col77=None)

**Multi-match keys (4):**
These correspond to the 2 known duplicate (building_id, rue, numero_appartement) triples:

| Key | Maps to unit_ids |
|---|---|
| `4298-104 Roses` | 3126, 3127 |
| `Ancienne locataire 4298-104 Roses` | 3126, 3127 |
| `12085-310 Berlioz` | 3294, 3295 |
| `Ancien locataire 12085-310 Berlioz` | 3294, 3295 |

**Units with >1 key (4 units):** Same 4 units as above — each is pointed to by both the current and the `Ancienne/Ancien locataire` key variant.

**DB units with no MRR key: 1**

| unit_id | building_id | building | rue | apt |
|---|---|---|---|---|
| 3709 | 149 | 4875 Saint-Georges | `4875, rue Saint-Georges` | `3` |

Provenance: two `master_rent_roll` entries pointing at MRR row 6179, plus one
`corrected` entry (`manual correction 2026-10-06`). The MRR key at row 6179
resolves to the original (building_id, rue, apt) before the manual correction;
the corrected coordinates (`rue='4875, rue Saint-Georges'`, apt=`3`) no longer
match any MRR key because the correction changed the unit's address. The unit
is genuine — it appears in MRR — but the coordinate change orphaned it from
the key resolution path.

**5 example mappings (key → unit_id):**

| Unique Unit Number | unit_id |
|---|---|
| `405-1 41e Rue O.` | 1 |
| `405-2 41e Rue O.` | 2 |
| `405-3 41e Rue O.` | 3 |
| `405-4 41e Rue O.` | 4 |
| `405-5 41e Rue O.` | 5 |

---

### F5 — `banked_queue_date` column

Searched `docs/backend-rules.md`, `docs/client-ai-system/guide-*.md`,
`docs/client-ai-system/SKILL.md`, `docs/current-triage-workflow.md`,
`backend/triage/output_contract.py` for "banque", "banked", "bank",
"file d'attente".

Zero hits on the concept. One guide hit (`guide` line 745: "file de dossiers
de supervision") is CHBE supervision queue — unrelated. The column has no DBML
note, no write path in any ingestion or triage script, and is absent from
`output_contract.py`'s validated schema.

**Verdict: Deprecate.** Confirmed 0/10 565 rows filled.

---

### F6′ — `_GF_LABEL_MAP` key matchability audit

`_gf_nrm_label()` pipeline: lowercase → NFD decompose → strip Mn (non-spacing
mark) characters → collapse whitespace. Apostrophe characters (U+0027 `'`,
U+2019 `'`, U+02BC `ʼ`) are category `Po`/`Pf`/`Lm` — **not Mn** — so they
survive the filter and appear in the normalized label, but all map keys that
contain them use a space instead.

| Map key | Expected source label | NORM(source) | Matches? | Mapped field |
|---|---|---|---|---|
| `date et heure de l appel` | `Date et heure de l'appel` | `date et heure de l'appel` | **No** | `submission_date` |
| `type de l appelant` | `Type de l'appelant` | `type de l'appelant` | **No** | `caller_type` |
| `numero unique d unite` | `Numéro unique d'unité` | `numero unique d'unite` | **No** | `unit_number` |
| `nom complet de l appelant` | `Nom complet de l'appelant` | `nom complet de l'appelant` | **No** | `caller_name` |
| `telephone de l appelant` | `Téléphone de l'appelant` | `telephone de l'appelant` | **No** | `caller_phone` |
| `courriel de l appelant` | `Courriel de l'appelant` | `courriel de l'appelant` | **No** | `caller_email` |
| `urgent ou non-urgent` | `Urgent ou non-urgent` | `urgent ou non-urgent` | **Yes** | `urgency_raw` |
| `categorie` | `Catégorie` | `categorie` | **Yes** | `category_raw` |
| `adresse de l urgence` | `Adresse de l'urgence` | `adresse de l'urgence` | **No** | `address_urgency` |
| `details, commentaires ou autre` | `Détails, commentaires ou autre` | `details, commentaires ou autre` | **Yes** | `message` |
| `acces au logement` | `Accès au logement` | `acces au logement` | **Yes** | `entry_permission` |
| `avez-vous des animaux?` | `Avez-vous des animaux?` | `avez-vous des animaux?` | **Yes** | `animals` |
| `avez-vous des animaux` | `Avez-vous des animaux` | `avez-vous des animaux` | **Yes** | `animals` (duplicate) |
| `j ai avise des frais, si applicable` | `J'ai avisé des frais, si applicable` | `j'ai avise des frais, si applicable` | **No** | `fees_advised` |
| `j ai avise des frais si applicable` | `J'ai avisé des frais, si applicable` | `j'ai avise des frais, si applicable` | **No** | `fees_advised` (duplicate) |

**Keys that can never match: 9** (all apostrophe-elided variants).

**Affected fields and observed fill rate across all 148 `gravity_forms` rows:**

| Field | Key matchable? | Observed fill (148 rows) |
|---|---|---|
| `submission_date` | **No** | 0/148 (0%) |
| `caller_type` | **No** | 0/148 (0%) |
| `unit_number` (→ `asnu`?) | **No** | not queried |
| `caller_name` | **No** | 0/148 (0%) |
| `caller_phone` | **No** | 0/148 (0%) |
| `caller_email` | **No** | 0/148 (0%) |
| `urgency_raw` | Yes | 0/148 (0%) — *structural issue* |
| `category_raw` | Yes | 0/148 (0%) — *structural issue* |
| `address_urgency` | **No** | 0/148 (0%) |
| `message` | Yes | 0/148 (0%) — *structural issue* |
| `entry_permission` | Yes | 0/148 (0%) — *structural issue* |
| `animals` | Yes | 0/148 (0%) — *structural issue* |
| `fees_advised` | **No** | 0/148 (0%) |

**`unit_number` field routing:**
`_GF_LABEL_MAP["numero unique d unite"]` → parsed dict key `unit_number` →
written to `unit_label` via `write_maintenance_requests.py` line ~501:
`record.get("unite") or record.get("unit") or record.get("unit_number")`.
Because the apostrophe bug makes `unit_number` always `None`, the `unit_label`
fill for gravity_forms rows comes from other parsing paths only.

| Column | gravity_forms fill | Source |
|---|---|---|
| `unit_label` | 105/148 (71%) | from `unite`/`unit` sections (v10 parser), NOT from `unit_number` |
| `asnu` | 3/148 (2%) | purpose unclear; gravity_forms path does not explicitly set it |

Even the 6 structurally-matchable keys yield 0% fill, indicating a second bug:
the paragraph-splitting delimiter (`\n\s*\n`) does not match the actual Gravity
Forms email format. The form likely uses single `\n` (converted from `<br>`)
with no blank lines between label:value pairs, so all fields land in one
paragraph and only the first label is extracted. Root cause of both bugs is not
fixed here — reported only.

---

## Decisions recorded

| Decision | Rationale |
|---|---|
| Do NOT convert `triage_started_at` / `triage_log.attempted_at` to `timestamptz` | Triage's `datetime.utcnow() - started_at` subtraction would break against an aware value. Deferred to post-freeze psycopg3 port. |
| `banked_queue_date` → Deprecate | Zero fills, no source, no write path, no DBML note, not in output contract. |
| `unit.unique_unit_number` backfill | Walk `unit` → `data_provenance` → MRR row → Unique Unit Number key, skipping `Ancien`/`Ancienne` key variants. **Ambiguous** is defined in both directions: a unit that has more than one candidate key (after excluding `Ancien`/`Ancienne`), OR a key that maps to more than one unit. Both stay NULL. Units 3126, 3127, 3294, 3295 (the two known duplicate-unit pairs at 4298-104 Roses and 12085-310 Berlioz) stay NULL until the client resolves the duplicate-units question — they are on the open client list. Coordinate-based matching (`building_id + rue + apt`) is not used in this backfill path. |

---

## Phase B — Step 3 diff scope

When comparing local (after `supabase db reset`) against remote, the diff must
cover:

- `information_schema.columns` — table columns, types, defaults, nullability
- `pg_policies` — RLS policy names, roles, commands, expressions
- **`pg_event_trigger`** — name, event, owner, tags, function; `ensure_rls`
  must be present locally (either provisioned by `supabase start` or added
  manually to the baseline)
- **Views with `reloptions`** — `pg_class.reloptions` for all views; confirm
  `security_invoker=true` on all four views
- **Functions** — `pg_proc` for all public functions: `proname`, `prosecdef`,
  `proconfig` (search_path), `prokind`; confirm SECURITY DEFINER status and
  search_path for the four known functions
- **Grants** — `information_schema.table_privileges` for anon/authenticated/
  service_role; `pg_namespace.nspacl` for schema-level USAGE; `pg_default_acl`
  for default privileges on tables, sequences, functions
