-- rls_policies.sql — SELECT policies for SIB platform.
--
-- Prerequisites:
--   1. rls_functions.sql applied (current_employee_id, has_role, technician_building_ids)
--   2. employee_role table populated (ingest_employee_roles.py --write)
--   3. employee_building_assignment populated (ingest_rls_schema.py --write)
--   4. building_security_credential migrated (ingest_rls_schema.py --write)
--
-- Not covered here (intentional):
--   - contractor role policies (open question: real logins vs. calendar access)
--   - write (INSERT/UPDATE/DELETE) policies — no user-facing writes until API layer
--   - tables not listed: data_provenance, on_call_schedule, cleaning_task_checklist,
--     staff_shift, and other internal/operational tables
--
-- RLS is already enabled on all tables (confirmed). No ALTER TABLE ... ENABLE needed.
-- Apply via Supabase SQL editor or psql.


-- ── Broadly readable — director + coordinator + technician ───────────────────
-- Reference and operational data that all field staff need.

CREATE POLICY "staff_read" ON building
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON entrance
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON project
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON sector
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON unit
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON equipment
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON building_fire_system
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON service_visit
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON service_contract
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON service_contract_building
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON building_paint_spec
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON vendor_contact
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON tenancy_record
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON tenant
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON building_document
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON building_vendor
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON employee
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));


-- ── Physical access codes — Tier 2 (staff only, not contractor) ──────────────
-- SKILL.md rule 11: access info stays out of contractor-readable surfaces.
-- Technicians need codes to enter buildings; subcontractors are admitted, not self-admitting.

CREATE POLICY "staff_read" ON building_intercom
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON building_key_box
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON pool_access_code
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON emergency_access_code
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));


-- ── Camera and access control — system info (credentials already migrated out) ─
-- After ingest_rls_schema.py drops the credential columns, only non-sensitive
-- fields remain (platform, ip_domain, brand, panel_type, etc.).

CREATE POLICY "staff_read" ON building_camera_system
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));

CREATE POLICY "staff_read" ON building_access_control
FOR SELECT USING (has_role('director') OR has_role('coordinator') OR has_role('technician'));


-- ── maintenance_request — row-scoped for technicians ─────────────────────────
-- Director/coordinator: all 2374 rows.
-- Technician: own assigned_employee_id + sector buildings + A5 buildings.

CREATE POLICY "dir_coord_all" ON maintenance_request
FOR SELECT USING (has_role('director') OR has_role('coordinator'));

CREATE POLICY "tech_scoped" ON maintenance_request
FOR SELECT USING (
    has_role('technician') AND (
        assigned_employee_id = current_employee_id()
        OR building_id IN (SELECT building_id FROM technician_building_ids())
    )
);


-- ── maintenance_followup_entry — same row scope as maintenance_request ────────

CREATE POLICY "dir_coord_all" ON maintenance_followup_entry
FOR SELECT USING (has_role('director') OR has_role('coordinator'));

CREATE POLICY "tech_scoped" ON maintenance_followup_entry
FOR SELECT USING (
    has_role('technician') AND request_id IN (
        SELECT request_id FROM maintenance_request
        WHERE assigned_employee_id = current_employee_id()
           OR building_id IN (SELECT building_id FROM technician_building_ids())
    )
);


-- ── Lease — director + coordinator full table ─────────────────────────────────
-- Technicians use lease_field_view (col-restricted) not this table.
-- Financial columns (loyer, depot, somme_due_restante, notes_collecte) are hidden
-- from technicians at the row level — they have no SELECT policy on this table.

CREATE POLICY "dir_coord_only" ON lease
FOR SELECT USING (has_role('director') OR has_role('coordinator'));


-- ── Guarantor — director + coordinator only ───────────────────────────────────
-- SKILL.md rule 10 explicitly forbids endosseurs (guarantors) from field staff.

CREATE POLICY "dir_coord_only" ON guarantor
FOR SELECT USING (has_role('director') OR has_role('coordinator'));


-- ── Parking + storage — director + coordinator only (cost column) ─────────────
-- Technicians use parking_assignment_field_view / storage_assignment_field_view.

CREATE POLICY "dir_coord_only" ON parking_assignment
FOR SELECT USING (has_role('director') OR has_role('coordinator'));

CREATE POLICY "dir_coord_only" ON storage_assignment
FOR SELECT USING (has_role('director') OR has_role('coordinator'));


-- ── building_security_credential — admin + director only ─────────────────────
-- System credentials (camera passwords, access panel login/password).
-- No coordinator or technician access — SKILL.md rule 11.

CREATE POLICY "admin_director_only" ON building_security_credential
FOR SELECT USING (has_role('admin') OR has_role('director'));
