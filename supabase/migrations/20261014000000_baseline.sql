


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "public";


ALTER SCHEMA "public" OWNER TO "pg_database_owner";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE TYPE "public"."access_status_enum" AS ENUM (
    'Oui_Paradox',
    'Oui_Akuvox',
    'Oui',
    'Non',
    'Installation_prevue'
);


ALTER TYPE "public"."access_status_enum" OWNER TO "postgres";


CREATE TYPE "public"."camera_platform" AS ENUM (
    'hik_connect',
    'cloud_generic',
    'ubox',
    'blink'
);


ALTER TYPE "public"."camera_platform" OWNER TO "postgres";


CREATE TYPE "public"."checklist_format_type" AS ENUM (
    'structured',
    'day_rotation',
    'single_line',
    'freetext'
);


ALTER TYPE "public"."checklist_format_type" OWNER TO "postgres";


CREATE TYPE "public"."complexity_tier" AS ENUM (
    'C1',
    'C2',
    'C3',
    'C4'
);


ALTER TYPE "public"."complexity_tier" OWNER TO "postgres";


COMMENT ON TYPE "public"."complexity_tier" IS 'Guide §7a (introduced 2026-07-09). C1=N''importe qui — no tool or skill required, natural pool for delegation to tenant; C2=Ouvrier — standard toolbox, limited training sufficient (label changed from "de base" on 2026-07-12, former label judged pejorative); C3=Ouvrier expérimenté/spécialité — diagnosis required, building system knowledge, real experience needed; C4=Sous-traitant/expertise externe — Newtech, Fortin, roofing, elevator, enamelling, extermination, anything requiring a quote';



CREATE TYPE "public"."congestion_level" AS ENUM (
    'N1',
    'N2',
    'N3',
    'N4',
    'N5'
);


ALTER TYPE "public"."congestion_level" OWNER TO "postgres";


COMMENT ON TYPE "public"."congestion_level" IS 'Guide §7b (introduced 2026-07-09). N1=Au-dessus de nos affaires — fast response, minimal delegation; N2=Niveau courant — normal pace; N3=En retard — negotiate deferred scheduling for non-urgent calls, actively offer delegation; N4=Très en retard — maximum deferral, paid delegation accepted readily; N5=Critique — everything that can wait waits, delegation and subcontracting without hesitation';



CREATE TYPE "public"."delegable_status" AS ENUM (
    'YES',
    'NO',
    'CONDITIONAL'
);


ALTER TYPE "public"."delegable_status" OWNER TO "postgres";


CREATE TYPE "public"."employment_type" AS ENUM (
    'staff',
    'contractor_company',
    'unknown'
);


ALTER TYPE "public"."employment_type" OWNER TO "postgres";


CREATE TYPE "public"."entrance_access_method" AS ENUM (
    'key',
    'fob',
    'keypad',
    'intercom_release'
);


ALTER TYPE "public"."entrance_access_method" OWNER TO "postgres";


CREATE TYPE "public"."equipment_type" AS ENUM (
    'furnace',
    'boiler',
    'heat_pump',
    'elevator',
    'freight_elevator',
    'pool',
    'barbecue',
    'terrace',
    'heating',
    'dhw',
    'other'
);


ALTER TYPE "public"."equipment_type" OWNER TO "postgres";


CREATE TYPE "public"."intercom_status" AS ENUM (
    'to_do',
    'done',
    'call_placed'
);


ALTER TYPE "public"."intercom_status" OWNER TO "postgres";


CREATE TYPE "public"."key_method" AS ENUM (
    'remise_directe',
    'boite_a_cle',
    'bureau'
);


ALTER TYPE "public"."key_method" OWNER TO "postgres";


CREATE TYPE "public"."loan_status" AS ENUM (
    'RETIRE',
    'ACHAT'
);


ALTER TYPE "public"."loan_status" OWNER TO "postgres";


CREATE TYPE "public"."move_reason" AS ENUM (
    'lease_end',
    'lease_assignment',
    'eviction'
);


ALTER TYPE "public"."move_reason" OWNER TO "postgres";


CREATE TYPE "public"."move_type" AS ENUM (
    'depart',
    'arrivee'
);


ALTER TYPE "public"."move_type" OWNER TO "postgres";


CREATE TYPE "public"."pay_rule_type" AS ENUM (
    'overage',
    'percentage',
    'rental'
);


ALTER TYPE "public"."pay_rule_type" OWNER TO "postgres";


CREATE TYPE "public"."payment_type" AS ENUM (
    'coin',
    'card',
    'both'
);


ALTER TYPE "public"."payment_type" OWNER TO "postgres";


CREATE TYPE "public"."report_status" AS ENUM (
    'CANNOT_WAIT',
    'SUPERVISOR_DISCRETION',
    'CAN_WAIT_SHORT_TERM',
    'CAN_WAIT',
    'NOT_APPLICABLE'
);


ALTER TYPE "public"."report_status" OWNER TO "postgres";


COMMENT ON TYPE "public"."report_status" IS 'Triage reporting-obligation scale (guide §9 RAPPORT SUPERVISEUR line). CANNOT_WAIT=inform supervisor immediately; SUPERVISOR_DISCRETION=inform supervisor, timing at their discretion; CAN_WAIT_SHORT_TERM=flag for next supervisor touchpoint; CAN_WAIT=no near-term supervisor action required; NOT_APPLICABLE=report obligation does not apply to this call type';



CREATE TYPE "public"."request_status" AS ENUM (
    'intake_received',
    'triage_pending',
    'triaged',
    'triage_clarify',
    'triage_proposal',
    'triage_failed',
    'en_route',
    'closed'
);


ALTER TYPE "public"."request_status" OWNER TO "postgres";


COMMENT ON TYPE "public"."request_status" IS 'Request lifecycle states. Auto-retry eligibility: only triage_pending and triage_failed are picked up by the retry loop. triage_clarify must NOT enter the loop — it signals a human-input requirement, not a transient error.

intake_received   — request landed (Gravity form, robot call, or in-app intake); waiting for the next triage run.
triage_pending    — acquired by the triage service; triage_started_at is set. Other workers skip. Rows stuck > 10 min = abandoned lock, eligible for takeover.
triage_clarify    — BLOCKED: triage could not proceed (ambiguous unit, address unresolvable). Requires coordinator action before the row may re-enter the queue. NEVER auto-retry: the same ambiguity will recur.
triage_proposal   — model output written and passed validation; coordinator review pending before the row appears on the dispatch board. Coordinator either accepts (triaged) or rejects and edits (triage_pending for one retry).
triage_failed     — all retries exhausted due to API error or repeated gate rejection. Auto-retry is permitted after coordinator review or manual reset.
triaged           — coordinator accepted the proposal; row is on the dispatch board. assigned_employee_id/code may or may not be set (unassigned = triaged + no employee; assigned = triaged + employee set). No separate status for those sub-states.
en_route          — field worker confirmed and heading to site. Triggers tenant SMS.
closed            — work complete and closed out. All rows ingested before 2026-10-09 carry this value as a backfill sentinel — it does not mean work was verified complete.';



CREATE TYPE "public"."service_contract_category" AS ENUM (
    'snow',
    'lawn',
    'pool',
    'pest',
    'fire',
    'elevator',
    'telecom',
    'waste',
    'snow_parking',
    'snow_pedestrian'
);


ALTER TYPE "public"."service_contract_category" OWNER TO "postgres";


CREATE TYPE "public"."service_visit_type" AS ENUM (
    'fire_inspection',
    'elevator_service',
    'boiler_shutdown',
    'boiler_restart',
    'other'
);


ALTER TYPE "public"."service_visit_type" OWNER TO "postgres";


CREATE TYPE "public"."shift_type" AS ENUM (
    'ouverture',
    'fermeture',
    'terrain',
    'off',
    'vacances',
    'garde_urgence'
);


ALTER TYPE "public"."shift_type" OWNER TO "postgres";


CREATE TYPE "public"."source_confidence" AS ENUM (
    'documented',
    'inferred_from_calendar'
);


ALTER TYPE "public"."source_confidence" OWNER TO "postgres";


CREATE TYPE "public"."task_item_type" AS ENUM (
    'jeter',
    'menage',
    'peinture',
    'plancher',
    'comptoir',
    'armoires',
    'ajout_electros'
);


ALTER TYPE "public"."task_item_type" OWNER TO "postgres";


CREATE TYPE "public"."tenancy_capacity" AS ENUM (
    'named_on_lease',
    'added_occupant',
    'took_over'
);


ALTER TYPE "public"."tenancy_capacity" OWNER TO "postgres";


CREATE TYPE "public"."time_estimate_bucket" AS ENUM (
    'UNDER_30_MIN',
    'MIN30_TO_1H',
    'H1_TO_2H',
    'H2_TO_4H',
    'HALF_DAY_PLUS',
    'TBD_ON_SITE'
);


ALTER TYPE "public"."time_estimate_bucket" OWNER TO "postgres";


COMMENT ON TYPE "public"."time_estimate_bucket" IS 'Guide §9 TEMPS line. UNDER_30_MIN=<30 min; MIN30_TO_1H=30 min–1h; H1_TO_2H=1h–2h; H2_TO_4H has no direct guide equivalent (guide jumps from 1h–2h to demi-journée, retained as intermediate bucket); HALF_DAY_PLUS=demi-journée ou journée+; TBD_ON_SITE=soumission requise (quote required before estimating — guide label and enum name diverge)';



CREATE TYPE "public"."time_slot" AS ENUM (
    'slot_8_11',
    'slot_11_14',
    'slot_14_17',
    'slot_17_20'
);


ALTER TYPE "public"."time_slot" OWNER TO "postgres";


CREATE TYPE "public"."urgency_tier" AS ENUM (
    'AJD',
    'ajd',
    'none'
);


ALTER TYPE "public"."urgency_tier" OWNER TO "postgres";


COMMENT ON TYPE "public"."urgency_tier" IS 'AJD = aujourd''hui = urgent, handle today (guide rule 28). Both ''AJD'' and ''ajd'' exist as a data-quality artefact from source ingestion; triage service normalises to uppercase. ''none'' is a legacy ingestion artefact; the output contract uses NULL for non-urgent calls, not the string ''none''';



CREATE TYPE "public"."vendor_scope" AS ENUM (
    'portfolio_wide',
    'building_specific'
);


ALTER TYPE "public"."vendor_scope" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."current_employee_id"() RETURNS integer
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public', 'auth'
    AS $$
  SELECT employee_id FROM employee WHERE auth_user_id = auth.uid() LIMIT 1;
$$;


ALTER FUNCTION "public"."current_employee_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."has_role"("role_name" "text") RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public', 'auth'
    AS $$
  SELECT EXISTS (
    SELECT 1 FROM employee_role
    WHERE employee_id = current_employee_id()
      AND role = role_name
  );
$$;


ALTER FUNCTION "public"."has_role"("role_name" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."rls_auto_enable"() RETURNS "event_trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'pg_catalog'
    AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$$;


ALTER FUNCTION "public"."rls_auto_enable"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."technician_building_ids"() RETURNS TABLE("building_id" integer)
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public', 'auth'
    AS $$
  SELECT b.building_id
  FROM building b
  JOIN employee e ON b.sector_id = e.sector_id
  WHERE e.employee_id = current_employee_id()
  UNION
  SELECT eba.building_id
  FROM employee_building_assignment eba
  WHERE eba.employee_id = current_employee_id()
$$;


ALTER FUNCTION "public"."technician_building_ids"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."building" (
    "building_id" integer NOT NULL,
    "project_id" integer NOT NULL,
    "sector_id" integer NOT NULL,
    "adresse" character varying,
    "ville" character varying,
    "code_postal" character varying,
    "annee_construction" character varying,
    "nb_etages" character varying,
    "nb_logements" character varying,
    "ascenseur" boolean,
    "piscine" boolean,
    "sauna" boolean,
    "gym" boolean,
    "chauffage" character varying,
    "systeme_incendie" character varying,
    "boite_a_cle_ext" character varying,
    "boite_a_cle_int" character varying,
    "raw_fiche_technique" "jsonb",
    "legacy_code" character varying,
    "sib_territory" character varying,
    "furnished" character varying,
    "building_structure" character varying,
    "nb_elevateurs" integer,
    "num_service_elevators" integer,
    "internet" character varying,
    "terrasse_commune" boolean,
    "num_bbqs" integer,
    "coworking_space" boolean,
    "reception_loft" boolean,
    "chauffage_details" "text",
    "chauffe_eau" character varying,
    "individual_heat_pumps" boolean,
    "heat_pump_details" "text",
    "nb_units_total" integer,
    "nb_units_residential" integer,
    "actif_inactif" character varying,
    "municipality" character varying,
    "property_type" character varying,
    "dogs_allowed" boolean,
    "web_building_name" character varying,
    "web_slug" character varying
);


ALTER TABLE "public"."building" OWNER TO "postgres";


COMMENT ON COLUMN "public"."building"."boite_a_cle_ext" IS 'Kept for backward compat; new key-box detail lives on building_key_box, which will eventually hang off entrance rather than building directly.';



COMMENT ON COLUMN "public"."building"."raw_fiche_technique" IS 'Raw JSONB from the fiches techniques translation pipeline (jsonb for queryability).';



COMMENT ON COLUMN "public"."building"."legacy_code" IS 'A002–A112 style code from the Fire Protection master table RÉF. tab. 4th building-identifier system in this schema (alongside building_id, project_id, and laundry ULN). Nullable.';



CREATE TABLE IF NOT EXISTS "public"."building_access_control" (
    "access_control_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "brand" character varying,
    "panel_type" character varying,
    "connection_option" character varying,
    "panel_serial_or_ip" character varying
);


ALTER TABLE "public"."building_access_control" OWNER TO "postgres";


COMMENT ON COLUMN "public"."building_access_control"."brand" IS 'Known values: Paradox, Akuvox';



CREATE TABLE IF NOT EXISTS "public"."building_camera_system" (
    "camera_system_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "installed" "public"."access_status_enum",
    "accessible_remote" character varying,
    "functional" character varying,
    "platform" "public"."camera_platform",
    "ip_domain" character varying,
    "port" character varying,
    "username" character varying
);


ALTER TABLE "public"."building_camera_system" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."building_document" (
    "document_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "category" character varying,
    "drive_file_id" character varying,
    "title" character varying,
    "url" character varying
);


ALTER TABLE "public"."building_document" OWNER TO "postgres";


COMMENT ON COLUMN "public"."building_document"."category" IS 'Allowed values (not enforced by constraint): elevator_contract / fire_protection / paint_spec / install_guide / plumbing_reference / other';



CREATE TABLE IF NOT EXISTS "public"."building_employee_assignment" (
    "building_id" integer NOT NULL,
    "employee_id" integer NOT NULL,
    "weekly_hours_summer" numeric,
    "weekly_hours_winter" numeric,
    "access_notes" "text"
);


ALTER TABLE "public"."building_employee_assignment" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."building_fire_system" (
    "fire_system_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "panel_brand_model" character varying,
    "panel_control_status" character varying,
    "emergency_panel_status" character varying,
    "smoke_detector_status" character varying,
    "sprinkler_status" character varying,
    "sprinkler_vendor_id" integer,
    "hose_status" character varying,
    "pressurization_pump_status" character varying,
    "co2_status" character varying,
    "co2_vendor_id" integer,
    "dossier_link" character varying,
    "current_fire_vendor_id" integer,
    "notes" "text",
    "corrective_actions_date" "date",
    "piezzo_status" character varying
);


ALTER TABLE "public"."building_fire_system" OWNER TO "postgres";


COMMENT ON TABLE "public"."building_fire_system" IS 'Source: "0 - Master Tableau Protection Incendie.xlsx" — confirmed real and fully populated. Static per-building fire-system configuration; distinct from service_visit which logs inspection events.';



COMMENT ON COLUMN "public"."building_fire_system"."sprinkler_vendor_id" IS 'Nullable: vendor contracted for sprinkler system. Not all buildings have sprinklers.';



COMMENT ON COLUMN "public"."building_fire_system"."co2_vendor_id" IS 'Nullable: vendor contracted for CO2 suppression. Not all buildings have CO2 systems.';



COMMENT ON COLUMN "public"."building_fire_system"."current_fire_vendor_id" IS 'Nullable: primary fire-protection vendor currently under contract for this building.';



CREATE TABLE IF NOT EXISTS "public"."building_intercom" (
    "intercom_id" integer NOT NULL,
    "entrance_id" integer NOT NULL,
    "brand" character varying,
    "dyndns_address" character varying,
    "panel_model" character varying,
    "is_master_building" boolean,
    "keyless_code_general" character varying,
    "keyless_code_maintenance" character varying,
    "keyless_code_tenant" character varying
);


ALTER TABLE "public"."building_intercom" OWNER TO "postgres";


COMMENT ON COLUMN "public"."building_intercom"."brand" IS 'Known values: Mircom, Akuvox';



CREATE TABLE IF NOT EXISTS "public"."building_key_box" (
    "box_id" integer NOT NULL,
    "entrance_id" integer NOT NULL,
    "box_number_onsite" character varying,
    "code" character varying,
    "location_description" "text",
    "keyless_intercom_code" character varying,
    "last_validated_date" "date",
    "last_validated_by" character varying
);


ALTER TABLE "public"."building_key_box" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."building_paint_spec" (
    "paint_spec_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "zone" character varying,
    "surface_label" character varying,
    "product_interior" character varying,
    "product_exterior" character varying,
    "manufacturer" character varying
);


ALTER TABLE "public"."building_paint_spec" OWNER TO "postgres";


COMMENT ON TABLE "public"."building_paint_spec" IS 'Real source confirmed: "0 - Charte des couleurs de peinture SIB" — distinct from the empty PEINTURE folder and from "Charte des couleurs SIB.xlsx". Not yet ingested.';



CREATE TABLE IF NOT EXISTS "public"."building_security_credential" (
    "credential_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "camera_password" character varying,
    "access_ip_module_password" character varying,
    "access_system_login" character varying,
    "access_system_password" character varying
);


ALTER TABLE "public"."building_security_credential" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."building_security_credential_credential_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."building_security_credential_credential_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."building_security_credential_credential_id_seq" OWNED BY "public"."building_security_credential"."credential_id";



CREATE TABLE IF NOT EXISTS "public"."building_telecom" (
    "building_id" integer NOT NULL,
    "internet_provider" "text",
    "internet_broadcast_provider" "text",
    "tech_support_provider" "text",
    "telephone_provider" "text"
);


ALTER TABLE "public"."building_telecom" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."building_vendor" (
    "building_id" integer NOT NULL,
    "vendor_id" integer NOT NULL,
    "vendor_account_number" character varying,
    "notes" "text"
);


ALTER TABLE "public"."building_vendor" OWNER TO "postgres";


COMMENT ON COLUMN "public"."building_vendor"."vendor_account_number" IS 'Confirmed NOT strictly 1:1 — one vendor account number can cover multiple buildings.';



CREATE TABLE IF NOT EXISTS "public"."cleaning_task_checklist" (
    "checklist_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "format" character varying,
    "element" character varying,
    "frequency_per_week" numeric,
    "hours_per_visit" numeric,
    "season" character varying,
    "total" numeric,
    "freetext_content" "text",
    "format_type" "public"."checklist_format_type",
    "raw_content" "text"
);


ALTER TABLE "public"."cleaning_task_checklist" OWNER TO "postgres";


COMMENT ON COLUMN "public"."cleaning_task_checklist"."format" IS 'LEGACY: free-text format string from original Ménage source. Superseded by format_type enum; retained for migration reference only.';



COMMENT ON COLUMN "public"."cleaning_task_checklist"."freetext_content" IS 'LEGACY: unstructured note field from original source. Superseded by raw_content; retained for migration reference only.';



COMMENT ON COLUMN "public"."cleaning_task_checklist"."format_type" IS 'NEW — checklist_format_type enum: structured | day_rotation | single_line | freetext. Source: Ménage cleaning sheets show 4 distinct layout patterns. Drives how raw_content is rendered.';



COMMENT ON COLUMN "public"."cleaning_task_checklist"."raw_content" IS 'NEW — stores the full cell content for day_rotation, single_line, and freetext rows. Null for structured rows (element + frequency fields are the canonical representation).';



CREATE TABLE IF NOT EXISTS "public"."data_provenance" (
    "provenance_id" integer NOT NULL,
    "target_table" character varying NOT NULL,
    "target_pk" character varying(256) NOT NULL,
    "target_column" character varying NOT NULL,
    "source_type" character varying,
    "source_drive_id" character varying,
    "source_file_name" character varying,
    "source_tab" character varying,
    "source_row" character varying,
    "source_column" character varying,
    "raw_value" "text",
    "ingested_value" "text",
    "ingested_at" timestamp without time zone
);


ALTER TABLE "public"."data_provenance" OWNER TO "postgres";


COMMENT ON TABLE "public"."data_provenance" IS 'One row per field per record for every ingestion script. Enables full field-level lineage tracing.';



COMMENT ON COLUMN "public"."data_provenance"."target_table" IS 'Destination table name (e.g. ''building'')';



COMMENT ON COLUMN "public"."data_provenance"."target_pk" IS 'Primary key value in the destination table';



COMMENT ON COLUMN "public"."data_provenance"."target_column" IS 'Source category: FT (Fiches Techniques xlsx), MRR (Master Rent Roll xlsx), CROSSWALK';



COMMENT ON COLUMN "public"."data_provenance"."source_type" IS 'Source category: FT (Fiches Techniques xlsx), MRR (Master Rent Roll xlsx), CROSSWALK';



COMMENT ON COLUMN "public"."data_provenance"."source_drive_id" IS 'Google Drive file ID of the source file';



COMMENT ON COLUMN "public"."data_provenance"."source_file_name" IS 'Human-readable filename of the source';



COMMENT ON COLUMN "public"."data_provenance"."source_tab" IS 'Worksheet/tab name within the xlsx (null for single-sheet files)';



COMMENT ON COLUMN "public"."data_provenance"."source_row" IS '1-based row number or label within the source sheet';



COMMENT ON COLUMN "public"."data_provenance"."source_column" IS 'Column reference within the source (letter or header name)';



COMMENT ON COLUMN "public"."data_provenance"."raw_value" IS 'Exact value as read from the source, before any coercion';



COMMENT ON COLUMN "public"."data_provenance"."ingested_value" IS 'Value as written to the destination column, after coercion/normalization';



COMMENT ON COLUMN "public"."data_provenance"."ingested_at" IS 'UTC timestamp when this provenance row was written';



CREATE TABLE IF NOT EXISTS "public"."elevator_reservation" (
    "reservation_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "elevator_label" character varying,
    "date" "date",
    "unit_id" integer NOT NULL,
    "move_type" "public"."move_type",
    "time_slot" "public"."time_slot",
    "tenant_id" integer NOT NULL,
    "confirmed" boolean
);


ALTER TABLE "public"."elevator_reservation" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."emergency_access_code" (
    "access_code_id" integer NOT NULL,
    "building_id" integer,
    "zone_name" character varying,
    "code_type" character varying,
    "code_value" character varying
);


ALTER TABLE "public"."emergency_access_code" OWNER TO "postgres";


COMMENT ON COLUMN "public"."emergency_access_code"."building_id" IS 'Nullable: some codes are zone-level, not building-level.';



CREATE TABLE IF NOT EXISTS "public"."employee" (
    "employee_id" integer NOT NULL,
    "nom_employe" character varying,
    "telephone" character varying,
    "courriel" character varying,
    "temps_hebdo_ete" numeric,
    "temps_hebdo_hiver" numeric,
    "outils_fournis" boolean,
    "disponibilites" "text",
    "sector_id" integer,
    "role" character varying,
    "initials" character varying,
    "employment_type" "public"."employment_type" DEFAULT 'unknown'::"public"."employment_type" NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "auth_user_id" "uuid",
    "source_confidence" "public"."source_confidence",
    "notes" "text"
);


ALTER TABLE "public"."employee" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."employee_building_assignment" (
    "assignment_id" integer NOT NULL,
    "employee_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "assignment_type" character varying NOT NULL,
    "notes" "text"
);


ALTER TABLE "public"."employee_building_assignment" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."employee_building_assignment_assignment_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."employee_building_assignment_assignment_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."employee_building_assignment_assignment_id_seq" OWNED BY "public"."employee_building_assignment"."assignment_id";



CREATE TABLE IF NOT EXISTS "public"."employee_role" (
    "employee_role_id" integer NOT NULL,
    "employee_id" integer NOT NULL,
    "role" character varying NOT NULL,
    CONSTRAINT "employee_role_role_check" CHECK ((("role")::"text" = ANY ((ARRAY['admin'::character varying, 'director'::character varying, 'coordinator'::character varying, 'technician'::character varying, 'contractor'::character varying])::"text"[])))
);


ALTER TABLE "public"."employee_role" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."employee_role_employee_role_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."employee_role_employee_role_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."employee_role_employee_role_id_seq" OWNED BY "public"."employee_role"."employee_role_id";



CREATE TABLE IF NOT EXISTS "public"."entrance" (
    "entrance_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "civic_number" character varying,
    "street" character varying,
    "postal_code" character varying,
    "access_method" "public"."entrance_access_method",
    "notes" "text"
);


ALTER TABLE "public"."entrance" OWNER TO "postgres";


COMMENT ON TABLE "public"."entrance" IS 'No source file exists yet. Until real per-entrance data is captured, ingestion should create exactly one synthetic entrance per building (copying building.adresse/ville/code_postal) so building_intercom and building_key_box always have somewhere valid to point.';



CREATE TABLE IF NOT EXISTS "public"."equipment" (
    "equipment_id" integer NOT NULL,
    "building_id" integer,
    "unit_id" integer,
    "equipment_type" "public"."equipment_type",
    "make" character varying,
    "model" character varying,
    "install_year" integer,
    "seasonal_shutdown_date" "date",
    "seasonal_restart_date" "date",
    "maintained_by_vendor_id" integer,
    "notes" "text",
    "criticality" character varying,
    "assigned_vendor_id" integer,
    "maintenance_frequency" character varying,
    "last_maintenance_date" "date",
    "next_maintenance_date" "date",
    "maintenance_status" character varying,
    "maintenance_note" "text",
    "urgency" character varying,
    "action_priority" character varying,
    "device_condition" character varying,
    "replacement_priority" character varying,
    "service_area" character varying,
    "component" character varying,
    "quantity" integer,
    "power" character varying,
    "efficiency" character varying,
    "power_source" character varying,
    "energy_supplier" character varying
);


ALTER TABLE "public"."equipment" OWNER TO "postgres";


COMMENT ON COLUMN "public"."equipment"."building_id" IS 'Nullable: set when this is building-level equipment. At least one of building_id or unit_id must be set.';



COMMENT ON COLUMN "public"."equipment"."unit_id" IS 'Nullable: set when this is unit-level equipment (e.g. an apartment''s own heat pump). Single-table consolidation for both levels per live-map design — confirm against real data once a source exists. No source file exists yet.';



COMMENT ON COLUMN "public"."equipment"."maintained_by_vendor_id" IS 'Nullable: vendor who maintains this piece of equipment. Not always known.';



COMMENT ON COLUMN "public"."equipment"."assigned_vendor_id" IS 'Nullable: "Entrepreneur attitré" from Boilers source. Primary vendor assigned to this equipment.';



COMMENT ON COLUMN "public"."equipment"."service_area" IS '"Desserte" from Boilers source — geographic zone or building wing served by this equipment.';



COMMENT ON COLUMN "public"."equipment"."component" IS '"Composante" from Boilers source — sub-component or circuit identifier within the unit.';



COMMENT ON COLUMN "public"."equipment"."power" IS '"Puissance" — kept varchar; units vary across equipment types (kW, BTU, HP, etc.).';



COMMENT ON COLUMN "public"."equipment"."power_source" IS '"Alimentation" — energy feed type: electrical circuit, gas line, etc.';



CREATE TABLE IF NOT EXISTS "public"."guarantor" (
    "guarantor_id" integer NOT NULL,
    "lease_id" integer NOT NULL,
    "tenant_id" integer NOT NULL,
    "notes" "text"
);


ALTER TABLE "public"."guarantor" OWNER TO "postgres";


COMMENT ON TABLE "public"."guarantor" IS 'CAUTION: nom/telephone/courriel were REMOVED and replaced by tenant_id FK. This field-level change is inferred from map wording rather than a directly quoted field list — confirm before treating as final.';



CREATE TABLE IF NOT EXISTS "public"."laundry_contract" (
    "uln" character varying NOT NULL,
    "building_id" integer,
    "payment_type" "public"."payment_type",
    "contract_expiry" "date",
    "suite_count" integer,
    "suite_to_set_ratio" integer,
    "washer_count" integer,
    "dryer_count" integer,
    "wash_rate" numeric,
    "dry_rate" numeric,
    "loads_per_suite_pmpd" numeric,
    "collections_pmpd" numeric,
    "pay_rule_type" "public"."pay_rule_type",
    "pay_rule_pct" numeric,
    "min_commission" numeric,
    "monthly_rental_fee" numeric,
    "revenue_month" numeric,
    "commission_month" numeric,
    "commission_pct_month" numeric,
    "revenue_per_set_month" numeric,
    "commission_per_set_month" numeric,
    "revenue_per_suite_month" numeric,
    "commission_per_suite_month" numeric
);


ALTER TABLE "public"."laundry_contract" OWNER TO "postgres";


COMMENT ON COLUMN "public"."laundry_contract"."building_id" IS 'Nullable: laundry contracts use their own address format (7th naming system in SIB) — confirmed still unreconciled per live map. FK may not resolve for all rows.';



COMMENT ON COLUMN "public"."laundry_contract"."monthly_rental_fee" IS 'Only populated when pay_rule_type = ''rental''.';



CREATE TABLE IF NOT EXISTS "public"."lease" (
    "lease_id" integer NOT NULL,
    "unit_id" integer NOT NULL,
    "mois" "date",
    "debut_bail" "date",
    "fin_bail" "date",
    "date_fin_confirmee" "date",
    "date_limite_preavis" "date",
    "statut" character varying,
    "langue_bail" character varying,
    "droit_animaux" boolean,
    "depot" numeric,
    "loyer_de_base" numeric,
    "loyer_total" numeric,
    "mode_paiement_habituel" character varying,
    "somme_due_restante" numeric,
    "disponibilite_tableau_location" character varying,
    "notes_collecte" "text"
);


ALTER TABLE "public"."lease" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."lease_field_view" WITH ("security_invoker"='true') AS
 SELECT "unit_id",
    "debut_bail",
    "fin_bail",
    "langue_bail",
    "statut"
   FROM "public"."lease";


ALTER VIEW "public"."lease_field_view" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."maintenance_attachment" (
    "attachment_id" integer NOT NULL,
    "request_id" integer NOT NULL,
    "drive_file_id" character varying,
    "file_type" character varying
);


ALTER TABLE "public"."maintenance_attachment" OWNER TO "postgres";


COMMENT ON COLUMN "public"."maintenance_attachment"."file_type" IS 'Known values: photo, video';



CREATE TABLE IF NOT EXISTS "public"."maintenance_followup_entry" (
    "followup_id" integer NOT NULL,
    "request_id" integer NOT NULL,
    "entry_text" "text",
    "entry_date" "date",
    "entered_by_initials" character varying
);


ALTER TABLE "public"."maintenance_followup_entry" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."maintenance_request" (
    "request_id" integer NOT NULL,
    "building_id" integer,
    "unit_id" integer,
    "project_id" integer,
    "source_calendar" character varying,
    "urgency_tier" "public"."urgency_tier",
    "sector_id" integer,
    "equipment_id" integer,
    "banked_queue_date" "date",
    "triage_summary" "text",
    "delegable_status" "public"."delegable_status",
    "delegable_notes" "text",
    "report_status" "public"."report_status",
    "report_notes" "text",
    "duplicate_of_request_id" integer,
    "synergy_request_ids" integer[],
    "synergy_reason" "text",
    "unit_label" character varying,
    "project_label" character varying,
    "time_estimate_bucket" "public"."time_estimate_bucket",
    "time_estimate_raw" character varying,
    "complexity_tier" "public"."complexity_tier",
    "vendor_id" integer,
    "subcontractor_name" character varying,
    "proposed_assignee" character varying,
    "tenant_agreement_notes" "text",
    "other_notes" "text",
    "congestion_level" "public"."congestion_level",
    "caller_tenant_id" integer,
    "caller_name" character varying,
    "caller_phone" character varying,
    "dispatched" boolean,
    "work_performed" "text",
    "tenant_present" boolean,
    "follow_up_expected" boolean,
    "event_id" character varying,
    "html_link" "text",
    "start_date" "date",
    "raw_title" "text",
    "body_format" character varying,
    "parse_status" character varying,
    "source_calendar_id" character varying,
    "assigned_employee_code_raw" character varying,
    "urgency_raw" character varying,
    "civic" character varying,
    "street_raw" "text",
    "problem_summary" "text",
    "problems" "text",
    "entry_permission" "text",
    "animals" "text",
    "occupants_raw" "text",
    "bail_raw" "text",
    "ft_link" "text",
    "ft_name" "text",
    "historique_raw" "text",
    "tri_raw" "text",
    "delegable_raw" "text",
    "report_raw" "text",
    "doublons" "text",
    "synergie_raw" "text",
    "complexite_raw" character varying,
    "embourbement_raw" "text",
    "gravity_raw" "text",
    "signed_date" character varying,
    "submission_date" character varying,
    "caller_type" character varying,
    "caller_email" character varying,
    "fees_advised" character varying,
    "category_raw" character varying,
    "address_urgency" "text",
    "assigned_employee_id" integer,
    "status" "public"."request_status" NOT NULL,
    "addition_to_request_id" integer,
    "routing_rule" character varying,
    "triage_started_at" timestamp without time zone,
    "triage_model_version" character varying,
    "asnu" character varying(20),
    CONSTRAINT "mr_addition_not_self" CHECK (("addition_to_request_id" <> "request_id"))
);


ALTER TABLE "public"."maintenance_request" OWNER TO "postgres";


COMMENT ON COLUMN "public"."maintenance_request"."source_calendar" IS 'Source calendar name. Known values: MAIN - Calls, MAIN - Calls ST Majordome Québec';



COMMENT ON COLUMN "public"."maintenance_request"."synergy_request_ids" IS 'Typed integer array of related request IDs (synergy group). Queryable with = ANY(synergy_request_ids).';



COMMENT ON COLUMN "public"."maintenance_request"."project_label" IS 'Legacy fallback: raw project name for rows not yet matched to a project_id. Populated only when project_id is NULL.';



COMMENT ON COLUMN "public"."maintenance_request"."subcontractor_name" IS 'Legacy fallback: typed-in vendor name for rows not yet matched to a vendor_id. Populated only when vendor_id is NULL.';



COMMENT ON COLUMN "public"."maintenance_request"."proposed_assignee" IS 'Structurally always empty per Coordinator''s Guide rule 37 — confirmed 2026-09. Retained for schema fidelity; do not populate.';



COMMENT ON COLUMN "public"."maintenance_request"."caller_name" IS 'Legacy fallback for unmatched or non-tenant callers (neighbours, family members, staff). Set when caller_tenant_id is NULL.';



COMMENT ON COLUMN "public"."maintenance_request"."caller_phone" IS 'Legacy fallback for unmatched or non-tenant callers. Set when caller_tenant_id is NULL.';



COMMENT ON COLUMN "public"."maintenance_request"."status" IS 'Request lifecycle — see COMMENT ON TYPE request_status for full state descriptions.
Lifecycle: intake_received → triage_pending → (triage_clarify | triage_proposal | triage_failed) → triaged → en_route → closed.
All 10,565 rows ingested before 2026-10-09 carry ''closed'' as a backfill sentinel — it does not mean work was verified complete.';



COMMENT ON COLUMN "public"."maintenance_request"."addition_to_request_id" IS 'ADDITION relation from Coordinator Guide rule 12 — a request that adds to an existing open ticket. Nullable; complement to duplicate_of_request_id (the DUPLICATE verdict). Self-reference forbidden: CHECK (addition_to_request_id != request_id).';



COMMENT ON COLUMN "public"."maintenance_request"."routing_rule" IS 'A0–A5 rule that produced the routing decision. Records WHICH rule fired; subcontractor_name records the decision itself. NULL for historical rows triaged before this app.';



CREATE TABLE IF NOT EXISTS "public"."maintenance_request_history" (
    "history_id" integer NOT NULL,
    "request_id" integer NOT NULL,
    "referenced_request_id" integer NOT NULL,
    "relation_type" character varying NOT NULL,
    CONSTRAINT "maintenance_request_history_check" CHECK (("request_id" <> "referenced_request_id"))
);


ALTER TABLE "public"."maintenance_request_history" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."maintenance_request_history_history_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."maintenance_request_history_history_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."maintenance_request_history_history_id_seq" OWNED BY "public"."maintenance_request_history"."history_id";



CREATE OR REPLACE VIEW "public"."maintenance_request_tech_view" WITH ("security_invoker"='true') AS
 SELECT "request_id",
    "building_id",
    "unit_id",
    "project_id",
    "source_calendar",
    "sector_id",
    "equipment_id",
    "banked_queue_date",
    "delegable_notes",
    "report_notes",
    "duplicate_of_request_id",
    "synergy_request_ids",
    "synergy_reason",
    "unit_label",
    "project_label",
    "time_estimate_bucket",
    "time_estimate_raw",
    "vendor_id",
    "subcontractor_name",
    "tenant_agreement_notes",
    "other_notes",
    "caller_tenant_id",
    "caller_name",
    "caller_phone",
    "dispatched",
    "work_performed",
    "tenant_present",
    "follow_up_expected",
    "event_id",
    "html_link",
    "start_date",
    "raw_title",
    "body_format",
    "parse_status",
    "source_calendar_id",
    "assigned_employee_code_raw",
    "urgency_raw",
    "civic",
    "street_raw",
    "problem_summary",
    "problems",
    "entry_permission",
    "animals",
    "occupants_raw",
    "bail_raw",
    "ft_link",
    "ft_name",
    "historique_raw",
    "tri_raw",
    "delegable_raw",
    "report_raw",
    "doublons",
    "synergie_raw",
    "complexite_raw",
    "embourbement_raw",
    "gravity_raw",
    "signed_date",
    "submission_date",
    "caller_type",
    "caller_email",
    "fees_advised",
    "category_raw",
    "address_urgency",
    "assigned_employee_id"
   FROM "public"."maintenance_request";


ALTER VIEW "public"."maintenance_request_tech_view" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."on_call_schedule" (
    "on_call_id" integer NOT NULL,
    "employee_id" integer NOT NULL,
    "start_date" "date",
    "end_date" "date",
    "swap_notes" "text"
);


ALTER TABLE "public"."on_call_schedule" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."parking_assignment" (
    "parking_id" integer NOT NULL,
    "lease_id" integer NOT NULL,
    "mode" character varying,
    "location_type" character varying,
    "count" integer,
    "cost" numeric
);


ALTER TABLE "public"."parking_assignment" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."parking_assignment_field_view" WITH ("security_invoker"='true') AS
 SELECT "parking_id",
    "lease_id",
    "mode",
    "location_type",
    "count"
   FROM "public"."parking_assignment";


ALTER VIEW "public"."parking_assignment_field_view" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."pest_control_case" (
    "case_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "vendor_id" integer,
    "pest_type" character varying,
    "first_reported_date" "date",
    "warranty_active" boolean,
    "warranty_expiry_date" "date",
    "notes" "text"
);


ALTER TABLE "public"."pest_control_case" OWNER TO "postgres";


COMMENT ON TABLE "public"."pest_control_case" IS 'No source file exists yet. Extermination folder is near-empty with no structured tracking.';



CREATE TABLE IF NOT EXISTS "public"."pool_access_code" (
    "pool_code_id" integer NOT NULL,
    "building_id" integer,
    "code_value" character varying,
    "notes" "text"
);


ALTER TABLE "public"."pool_access_code" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."project" (
    "project_id" integer NOT NULL,
    "nom_unique_projet" character varying,
    "adresse_quickbooks" character varying,
    "accounting_project_number" character varying,
    "purchase_price" numeric,
    "acquisition_date" "date",
    "quickbooks_class" character varying
);


ALTER TABLE "public"."project" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."recurring_task_pattern" (
    "pattern_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "assigned_employee_id" integer NOT NULL,
    "task_type" character varying,
    "recurrence_rule" character varying,
    "standing_instructions" "text"
);


ALTER TABLE "public"."recurring_task_pattern" OWNER TO "postgres";


COMMENT ON TABLE "public"."recurring_task_pattern" IS 'SOURCE: Coordinator''s Guide recurring-task rules — NOT the Service Call Log (IA) calendar-recurrence file. The Service Call Log''s actual mapping is still an open question; it may turn out to be a source for service_visit instead, which currently has no source at all.';



CREATE TABLE IF NOT EXISTS "public"."sector" (
    "sector_id" integer NOT NULL,
    "territoire" character varying,
    "color_code" character varying
);


ALTER TABLE "public"."sector" OWNER TO "postgres";


COMMENT ON COLUMN "public"."sector"."territoire" IS 'Broader geographic region (e.g. "QUÉBEC-EST"). Distinct from the narrower secteur/color_code concept sourced from File 3 (CONTACTS). Do not merge or assume these two hierarchies are the same thing — relationship to be reconciled once confirmed.';



CREATE TABLE IF NOT EXISTS "public"."service_contract" (
    "contract_id" integer NOT NULL,
    "vendor_id" integer,
    "category" "public"."service_contract_category",
    "term_start" "date",
    "term_end" "date",
    "cost" numeric,
    "renews" boolean,
    "notes" "text"
);


ALTER TABLE "public"."service_contract" OWNER TO "postgres";


COMMENT ON TABLE "public"."service_contract" IS 'No source file exists yet (only unstructured year-by-year contract folders). One contract can legitimately cover several buildings via service_contract_building.';



CREATE TABLE IF NOT EXISTS "public"."service_contract_building" (
    "contract_id" integer NOT NULL,
    "building_id" integer NOT NULL
);


ALTER TABLE "public"."service_contract_building" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."service_visit" (
    "visit_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "vendor_id" integer,
    "equipment_id" integer,
    "visit_type" "public"."service_visit_type",
    "due_date" "date",
    "completed_date" "date",
    "result" character varying,
    "deficiencies" "text",
    "next_due_date" "date"
);


ALTER TABLE "public"."service_visit" OWNER TO "postgres";


COMMENT ON TABLE "public"."service_visit" IS 'No source file exists yet. Fire-protection folder holds ~106 per-building subfolders of unstructured inspection PDFs — nothing has been extracted into rows. The Service Call Log (IA) calendar-recurrence file may turn out to be a source here (still an open question — see recurring_task_pattern comment).';



CREATE TABLE IF NOT EXISTS "public"."staff_shift" (
    "shift_id" integer NOT NULL,
    "employee_id" integer NOT NULL,
    "shift_type" "public"."shift_type",
    "start_date" "date",
    "end_date" "date"
);


ALTER TABLE "public"."staff_shift" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."storage_assignment" (
    "storage_id" integer NOT NULL,
    "lease_id" integer NOT NULL,
    "mode" character varying,
    "count" integer,
    "cost" numeric
);


ALTER TABLE "public"."storage_assignment" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."storage_assignment_field_view" WITH ("security_invoker"='true') AS
 SELECT "storage_id",
    "lease_id",
    "mode",
    "count"
   FROM "public"."storage_assignment";


ALTER VIEW "public"."storage_assignment_field_view" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tenancy_record" (
    "tenancy_id" integer NOT NULL,
    "lease_id" integer NOT NULL,
    "tenant_id" integer NOT NULL,
    "capacite" "public"."tenancy_capacity",
    "start_date" "date",
    "end_date" "date",
    "reason_for_change" "text"
);


ALTER TABLE "public"."tenancy_record" OWNER TO "postgres";


COMMENT ON TABLE "public"."tenancy_record" IS 'No source file exists yet. Can be backfilled approximately from Master Rent Roll snapshots (one row per tenant per lease, capacite = named_on_lease, start/end = lease dates) as a stopgap until a real collection process exists.';



CREATE TABLE IF NOT EXISTS "public"."tenant" (
    "tenant_id" integer NOT NULL,
    "nom_complet" character varying,
    "telephone" character varying,
    "courriel" character varying,
    "telephone_international" character varying,
    "ville" character varying,
    "code_postal" character varying,
    "informations_pour_make" "text"
);


ALTER TABLE "public"."tenant" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tenant_equipment_loan" (
    "loan_id" integer NOT NULL,
    "unit_id" integer NOT NULL,
    "tenant_id" integer NOT NULL,
    "equipment_type" character varying,
    "quantity" integer,
    "status" "public"."loan_status",
    "loan_start_date" "date",
    "expected_end_date" "date",
    "has_contract" boolean,
    "notes" "text",
    "payment_status" character varying,
    "payment_date" "date",
    "payment_amount" numeric
);


ALTER TABLE "public"."tenant_equipment_loan" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."triage_log" (
    "log_id" integer NOT NULL,
    "request_id" integer NOT NULL,
    "attempted_at" timestamp without time zone NOT NULL,
    "model_version" character varying,
    "context_sent" "jsonb",
    "raw_response" "text",
    "validation_result" character varying,
    "validation_detail" "text",
    "latency_ms" integer,
    "input_tokens" integer,
    "output_tokens" integer
);


ALTER TABLE "public"."triage_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."triage_log" IS 'One row per model call attempt, including rejected and errored ones. A rejected row is the most interesting: it means a validation gate fired. Separate from data_provenance: provenance records WHERE a value came from; this records WHAT the model was asked and WHAT it said.';



COMMENT ON COLUMN "public"."triage_log"."context_sent" IS 'Assembled user message sent to the model (JSONB). Enables exact reproduction of what the model saw.';



COMMENT ON COLUMN "public"."triage_log"."raw_response" IS 'Verbatim model output, before validation or parsing.';



COMMENT ON COLUMN "public"."triage_log"."validation_result" IS 'Outcome: accepted | rejected_<gate> | error | timeout. rejected_<gate> names the specific gate that fired (e.g. rejected_no_financial_terms).';



COMMENT ON COLUMN "public"."triage_log"."validation_detail" IS 'Gate name, error message, or NULL for accepted responses.';



CREATE SEQUENCE IF NOT EXISTS "public"."triage_log_log_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."triage_log_log_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."triage_log_log_id_seq" OWNED BY "public"."triage_log"."log_id";



CREATE TABLE IF NOT EXISTS "public"."unit" (
    "unit_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "rue" character varying,
    "numero_appartement" character varying,
    "grandeur" character varying
);


ALTER TABLE "public"."unit" OWNER TO "postgres";


COMMENT ON COLUMN "public"."unit"."unit_id" IS 'Natural key = Numéro unique d''unité in the source system.';



CREATE TABLE IF NOT EXISTS "public"."unit_appliance" (
    "unit_appliance_id" integer NOT NULL,
    "lease_id" integer NOT NULL,
    "item" character varying,
    "included" boolean,
    "responsibility" character varying
);


ALTER TABLE "public"."unit_appliance" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."unit_turnover" (
    "turnover_id" integer NOT NULL,
    "unit_id" integer NOT NULL,
    "move_reason" "public"."move_reason",
    "lease_end_date" "date",
    "move_out_confirmed_date" "date",
    "assignment_desired_date" "date",
    "move_out_time" time without time zone,
    "move_out_email_sent_date" "date",
    "key_return_method" character varying,
    "lease_start_date" "date",
    "move_in_confirmed_date" "date",
    "move_in_time" time without time zone,
    "move_in_email_sent_date" "date",
    "key_pickup_method" character varying,
    "intercom_status" "public"."intercom_status",
    "cleaning_status" character varying,
    "parking_remote_status" character varying,
    "internet_transfer_current" boolean,
    "internet_transfer_new" boolean,
    "parking_stall_current" character varying,
    "parking_stall_new" character varying,
    "furnished_status_current" character varying,
    "furnished_status_new" character varying,
    "incoming_tenant_id" integer,
    "outgoing_tenant_id" integer,
    "pre_departure_inspection_notes" "text",
    "general_notes" "text",
    "room_count" character varying,
    "mattress_size" character varying,
    "source_turnover_id" integer,
    "incoming_tenant_name_raw" character varying,
    "outgoing_tenant_name_raw" character varying,
    "outgoing_loyer" numeric,
    "outgoing_fin_bail" "date"
);


ALTER TABLE "public"."unit_turnover" OWNER TO "postgres";


COMMENT ON COLUMN "public"."unit_turnover"."source_turnover_id" IS 'Optional FK linking an informal calendar intake entry to a formal maintenance_request ticket.';



CREATE TABLE IF NOT EXISTS "public"."unit_turnover_furniture_item" (
    "furniture_item_id" integer NOT NULL,
    "turnover_id" integer NOT NULL,
    "appliance_type" character varying,
    "included_current" boolean,
    "included_new" boolean
);


ALTER TABLE "public"."unit_turnover_furniture_item" OWNER TO "postgres";


COMMENT ON COLUMN "public"."unit_turnover_furniture_item"."appliance_type" IS 'Known values: internet, cuisiniere, refrigerateur, lave-vaisselle, laveuse, secheuse';



CREATE TABLE IF NOT EXISTS "public"."unit_turnover_settlement" (
    "settlement_id" integer NOT NULL,
    "turnover_id" integer NOT NULL,
    "deposit_amount_owed" numeric,
    "deposit_received" boolean,
    "deposit_refund_status" character varying,
    "amount_owed_by_tenant" numeric,
    "tal_dossier_open" boolean,
    "edl_received" boolean,
    "edl_satisfactory" boolean,
    "notes" "text"
);


ALTER TABLE "public"."unit_turnover_settlement" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."vacant_unit_task" (
    "task_id" integer NOT NULL,
    "unit_id" integer NOT NULL,
    "priority" integer,
    "access_status" character varying,
    "listing_status" character varying,
    "promised_lease_date" "date",
    "lease_start_date" "date",
    "future_tenant_name" character varying,
    "future_tenant_contact" character varying,
    "notes_free" "text",
    "internal_notes" "text"
);


ALTER TABLE "public"."vacant_unit_task" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."vacant_unit_task_item" (
    "item_id" integer NOT NULL,
    "task_id" integer NOT NULL,
    "task_type" "public"."task_item_type",
    "status" character varying,
    "notes" "text"
);


ALTER TABLE "public"."vacant_unit_task_item" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."vendor_category_exclusivity" (
    "exclusivity_id" integer NOT NULL,
    "vendor_id" integer NOT NULL,
    "category_label" character varying,
    "scope" "public"."vendor_scope",
    "rule_code" character varying
);


ALTER TABLE "public"."vendor_category_exclusivity" OWNER TO "postgres";


COMMENT ON COLUMN "public"."vendor_category_exclusivity"."rule_code" IS 'Allowed values: A0–A5';



CREATE TABLE IF NOT EXISTS "public"."vendor_contact" (
    "vendor_id" integer NOT NULL,
    "trade" character varying,
    "nom" character varying,
    "telephone" character varying,
    "notes" "text"
);


ALTER TABLE "public"."vendor_contact" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."waste_collection_schedule" (
    "schedule_id" integer NOT NULL,
    "building_id" integer NOT NULL,
    "collection_days" character varying,
    "instructions_text" "text",
    "embedded_access_code" character varying
);


ALTER TABLE "public"."waste_collection_schedule" OWNER TO "postgres";


COMMENT ON COLUMN "public"."waste_collection_schedule"."embedded_access_code" IS 'Confirmed rare — 1 of 12 buildings sampled had a code embedded in collection instructions.';



ALTER TABLE ONLY "public"."building_security_credential" ALTER COLUMN "credential_id" SET DEFAULT "nextval"('"public"."building_security_credential_credential_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."employee_building_assignment" ALTER COLUMN "assignment_id" SET DEFAULT "nextval"('"public"."employee_building_assignment_assignment_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."employee_role" ALTER COLUMN "employee_role_id" SET DEFAULT "nextval"('"public"."employee_role_employee_role_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."maintenance_request_history" ALTER COLUMN "history_id" SET DEFAULT "nextval"('"public"."maintenance_request_history_history_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."triage_log" ALTER COLUMN "log_id" SET DEFAULT "nextval"('"public"."triage_log_log_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."building_access_control"
    ADD CONSTRAINT "building_access_control_pkey" PRIMARY KEY ("access_control_id");



ALTER TABLE ONLY "public"."building_camera_system"
    ADD CONSTRAINT "building_camera_system_pkey" PRIMARY KEY ("camera_system_id");



ALTER TABLE ONLY "public"."building_document"
    ADD CONSTRAINT "building_document_pkey" PRIMARY KEY ("document_id");



ALTER TABLE ONLY "public"."building_employee_assignment"
    ADD CONSTRAINT "building_employee_assignment_pkey" PRIMARY KEY ("building_id", "employee_id");



ALTER TABLE ONLY "public"."building_fire_system"
    ADD CONSTRAINT "building_fire_system_pkey" PRIMARY KEY ("fire_system_id");



ALTER TABLE ONLY "public"."building_intercom"
    ADD CONSTRAINT "building_intercom_pkey" PRIMARY KEY ("intercom_id");



ALTER TABLE ONLY "public"."building_key_box"
    ADD CONSTRAINT "building_key_box_pkey" PRIMARY KEY ("box_id");



ALTER TABLE ONLY "public"."building_paint_spec"
    ADD CONSTRAINT "building_paint_spec_pkey" PRIMARY KEY ("paint_spec_id");



ALTER TABLE ONLY "public"."building"
    ADD CONSTRAINT "building_pkey" PRIMARY KEY ("building_id");



ALTER TABLE ONLY "public"."building_security_credential"
    ADD CONSTRAINT "building_security_credential_building_id_key" UNIQUE ("building_id");



ALTER TABLE ONLY "public"."building_security_credential"
    ADD CONSTRAINT "building_security_credential_pkey" PRIMARY KEY ("credential_id");



ALTER TABLE ONLY "public"."building_telecom"
    ADD CONSTRAINT "building_telecom_pkey" PRIMARY KEY ("building_id");



ALTER TABLE ONLY "public"."building_vendor"
    ADD CONSTRAINT "building_vendor_pkey" PRIMARY KEY ("building_id", "vendor_id");



ALTER TABLE ONLY "public"."cleaning_task_checklist"
    ADD CONSTRAINT "cleaning_task_checklist_pkey" PRIMARY KEY ("checklist_id");



ALTER TABLE ONLY "public"."data_provenance"
    ADD CONSTRAINT "data_provenance_pkey" PRIMARY KEY ("provenance_id");



ALTER TABLE ONLY "public"."elevator_reservation"
    ADD CONSTRAINT "elevator_reservation_pkey" PRIMARY KEY ("reservation_id");



ALTER TABLE ONLY "public"."emergency_access_code"
    ADD CONSTRAINT "emergency_access_code_pkey" PRIMARY KEY ("access_code_id");



ALTER TABLE ONLY "public"."employee_building_assignment"
    ADD CONSTRAINT "employee_building_assignment_employee_id_building_id_key" UNIQUE ("employee_id", "building_id");



ALTER TABLE ONLY "public"."employee_building_assignment"
    ADD CONSTRAINT "employee_building_assignment_pkey" PRIMARY KEY ("assignment_id");



ALTER TABLE ONLY "public"."employee"
    ADD CONSTRAINT "employee_initials_unique" UNIQUE ("initials");



ALTER TABLE ONLY "public"."employee"
    ADD CONSTRAINT "employee_pkey" PRIMARY KEY ("employee_id");



ALTER TABLE ONLY "public"."employee_role"
    ADD CONSTRAINT "employee_role_employee_id_role_key" UNIQUE ("employee_id", "role");



ALTER TABLE ONLY "public"."employee_role"
    ADD CONSTRAINT "employee_role_pkey" PRIMARY KEY ("employee_role_id");



ALTER TABLE ONLY "public"."entrance"
    ADD CONSTRAINT "entrance_pkey" PRIMARY KEY ("entrance_id");



ALTER TABLE ONLY "public"."equipment"
    ADD CONSTRAINT "equipment_pkey" PRIMARY KEY ("equipment_id");



ALTER TABLE ONLY "public"."guarantor"
    ADD CONSTRAINT "guarantor_pkey" PRIMARY KEY ("guarantor_id");



ALTER TABLE ONLY "public"."laundry_contract"
    ADD CONSTRAINT "laundry_contract_pkey" PRIMARY KEY ("uln");



ALTER TABLE ONLY "public"."lease"
    ADD CONSTRAINT "lease_pkey" PRIMARY KEY ("lease_id");



ALTER TABLE ONLY "public"."maintenance_attachment"
    ADD CONSTRAINT "maintenance_attachment_pkey" PRIMARY KEY ("attachment_id");



ALTER TABLE ONLY "public"."maintenance_followup_entry"
    ADD CONSTRAINT "maintenance_followup_entry_pkey" PRIMARY KEY ("followup_id");



ALTER TABLE ONLY "public"."maintenance_request_history"
    ADD CONSTRAINT "maintenance_request_history_pkey" PRIMARY KEY ("history_id");



ALTER TABLE ONLY "public"."maintenance_request_history"
    ADD CONSTRAINT "maintenance_request_history_request_id_referenced_request_i_key" UNIQUE ("request_id", "referenced_request_id", "relation_type");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_pkey" PRIMARY KEY ("request_id");



ALTER TABLE ONLY "public"."on_call_schedule"
    ADD CONSTRAINT "on_call_schedule_pkey" PRIMARY KEY ("on_call_id");



ALTER TABLE ONLY "public"."parking_assignment"
    ADD CONSTRAINT "parking_assignment_pkey" PRIMARY KEY ("parking_id");



ALTER TABLE ONLY "public"."pest_control_case"
    ADD CONSTRAINT "pest_control_case_pkey" PRIMARY KEY ("case_id");



ALTER TABLE ONLY "public"."pool_access_code"
    ADD CONSTRAINT "pool_access_code_pkey" PRIMARY KEY ("pool_code_id");



ALTER TABLE ONLY "public"."project"
    ADD CONSTRAINT "project_pkey" PRIMARY KEY ("project_id");



ALTER TABLE ONLY "public"."recurring_task_pattern"
    ADD CONSTRAINT "recurring_task_pattern_pkey" PRIMARY KEY ("pattern_id");



ALTER TABLE ONLY "public"."sector"
    ADD CONSTRAINT "sector_pkey" PRIMARY KEY ("sector_id");



ALTER TABLE ONLY "public"."service_contract_building"
    ADD CONSTRAINT "service_contract_building_pkey" PRIMARY KEY ("contract_id", "building_id");



ALTER TABLE ONLY "public"."service_contract"
    ADD CONSTRAINT "service_contract_pkey" PRIMARY KEY ("contract_id");



ALTER TABLE ONLY "public"."service_visit"
    ADD CONSTRAINT "service_visit_pkey" PRIMARY KEY ("visit_id");



ALTER TABLE ONLY "public"."staff_shift"
    ADD CONSTRAINT "staff_shift_pkey" PRIMARY KEY ("shift_id");



ALTER TABLE ONLY "public"."storage_assignment"
    ADD CONSTRAINT "storage_assignment_pkey" PRIMARY KEY ("storage_id");



ALTER TABLE ONLY "public"."tenancy_record"
    ADD CONSTRAINT "tenancy_record_pkey" PRIMARY KEY ("tenancy_id");



ALTER TABLE ONLY "public"."tenant_equipment_loan"
    ADD CONSTRAINT "tenant_equipment_loan_pkey" PRIMARY KEY ("loan_id");



ALTER TABLE ONLY "public"."tenant"
    ADD CONSTRAINT "tenant_pkey" PRIMARY KEY ("tenant_id");



ALTER TABLE ONLY "public"."triage_log"
    ADD CONSTRAINT "triage_log_pkey" PRIMARY KEY ("log_id");



ALTER TABLE ONLY "public"."unit_appliance"
    ADD CONSTRAINT "unit_appliance_pkey" PRIMARY KEY ("unit_appliance_id");



ALTER TABLE ONLY "public"."unit"
    ADD CONSTRAINT "unit_pkey" PRIMARY KEY ("unit_id");



ALTER TABLE ONLY "public"."unit_turnover_furniture_item"
    ADD CONSTRAINT "unit_turnover_furniture_item_pkey" PRIMARY KEY ("furniture_item_id");



ALTER TABLE ONLY "public"."unit_turnover"
    ADD CONSTRAINT "unit_turnover_pkey" PRIMARY KEY ("turnover_id");



ALTER TABLE ONLY "public"."unit_turnover_settlement"
    ADD CONSTRAINT "unit_turnover_settlement_pkey" PRIMARY KEY ("settlement_id");



ALTER TABLE ONLY "public"."vacant_unit_task_item"
    ADD CONSTRAINT "vacant_unit_task_item_pkey" PRIMARY KEY ("item_id");



ALTER TABLE ONLY "public"."vacant_unit_task"
    ADD CONSTRAINT "vacant_unit_task_pkey" PRIMARY KEY ("task_id");



ALTER TABLE ONLY "public"."vendor_category_exclusivity"
    ADD CONSTRAINT "vendor_category_exclusivity_pkey" PRIMARY KEY ("exclusivity_id");



ALTER TABLE ONLY "public"."vendor_contact"
    ADD CONSTRAINT "vendor_contact_pkey" PRIMARY KEY ("vendor_id");



ALTER TABLE ONLY "public"."waste_collection_schedule"
    ADD CONSTRAINT "waste_collection_schedule_pkey" PRIMARY KEY ("schedule_id");



CREATE UNIQUE INDEX "mr_event_id_key" ON "public"."maintenance_request" USING "btree" ("event_id") WHERE ("event_id" IS NOT NULL);



ALTER TABLE ONLY "public"."building_access_control"
    ADD CONSTRAINT "building_access_control_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building_camera_system"
    ADD CONSTRAINT "building_camera_system_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building_document"
    ADD CONSTRAINT "building_document_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building_employee_assignment"
    ADD CONSTRAINT "building_employee_assignment_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building_employee_assignment"
    ADD CONSTRAINT "building_employee_assignment_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "public"."employee"("employee_id");



ALTER TABLE ONLY "public"."building_fire_system"
    ADD CONSTRAINT "building_fire_system_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building_fire_system"
    ADD CONSTRAINT "building_fire_system_co2_vendor_id_fkey" FOREIGN KEY ("co2_vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."building_fire_system"
    ADD CONSTRAINT "building_fire_system_current_fire_vendor_id_fkey" FOREIGN KEY ("current_fire_vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."building_fire_system"
    ADD CONSTRAINT "building_fire_system_sprinkler_vendor_id_fkey" FOREIGN KEY ("sprinkler_vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."building_intercom"
    ADD CONSTRAINT "building_intercom_entrance_id_fkey" FOREIGN KEY ("entrance_id") REFERENCES "public"."entrance"("entrance_id");



ALTER TABLE ONLY "public"."building_key_box"
    ADD CONSTRAINT "building_key_box_entrance_id_fkey" FOREIGN KEY ("entrance_id") REFERENCES "public"."entrance"("entrance_id");



ALTER TABLE ONLY "public"."building_paint_spec"
    ADD CONSTRAINT "building_paint_spec_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building"
    ADD CONSTRAINT "building_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."project"("project_id");



ALTER TABLE ONLY "public"."building"
    ADD CONSTRAINT "building_sector_id_fkey" FOREIGN KEY ("sector_id") REFERENCES "public"."sector"("sector_id");



ALTER TABLE ONLY "public"."building_security_credential"
    ADD CONSTRAINT "building_security_credential_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."building_telecom"
    ADD CONSTRAINT "building_telecom_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building_vendor"
    ADD CONSTRAINT "building_vendor_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."building_vendor"
    ADD CONSTRAINT "building_vendor_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."cleaning_task_checklist"
    ADD CONSTRAINT "cleaning_task_checklist_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."elevator_reservation"
    ADD CONSTRAINT "elevator_reservation_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."elevator_reservation"
    ADD CONSTRAINT "elevator_reservation_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "public"."tenant"("tenant_id");



ALTER TABLE ONLY "public"."elevator_reservation"
    ADD CONSTRAINT "elevator_reservation_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "public"."unit"("unit_id");



ALTER TABLE ONLY "public"."emergency_access_code"
    ADD CONSTRAINT "emergency_access_code_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."employee_building_assignment"
    ADD CONSTRAINT "employee_building_assignment_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."employee_building_assignment"
    ADD CONSTRAINT "employee_building_assignment_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "public"."employee"("employee_id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."employee_role"
    ADD CONSTRAINT "employee_role_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "public"."employee"("employee_id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."employee"
    ADD CONSTRAINT "employee_sector_id_fkey" FOREIGN KEY ("sector_id") REFERENCES "public"."sector"("sector_id");



ALTER TABLE ONLY "public"."entrance"
    ADD CONSTRAINT "entrance_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."equipment"
    ADD CONSTRAINT "equipment_assigned_vendor_id_fkey" FOREIGN KEY ("assigned_vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."equipment"
    ADD CONSTRAINT "equipment_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."equipment"
    ADD CONSTRAINT "equipment_maintained_by_vendor_id_fkey" FOREIGN KEY ("maintained_by_vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."equipment"
    ADD CONSTRAINT "equipment_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "public"."unit"("unit_id");



ALTER TABLE ONLY "public"."guarantor"
    ADD CONSTRAINT "guarantor_lease_id_fkey" FOREIGN KEY ("lease_id") REFERENCES "public"."lease"("lease_id");



ALTER TABLE ONLY "public"."guarantor"
    ADD CONSTRAINT "guarantor_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "public"."tenant"("tenant_id");



ALTER TABLE ONLY "public"."laundry_contract"
    ADD CONSTRAINT "laundry_contract_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."lease"
    ADD CONSTRAINT "lease_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "public"."unit"("unit_id");



ALTER TABLE ONLY "public"."maintenance_attachment"
    ADD CONSTRAINT "maintenance_attachment_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."maintenance_followup_entry"
    ADD CONSTRAINT "maintenance_followup_entry_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_addition_to_request_id_fkey" FOREIGN KEY ("addition_to_request_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_assigned_employee_id_fkey" FOREIGN KEY ("assigned_employee_id") REFERENCES "public"."employee"("employee_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_caller_tenant_id_fkey" FOREIGN KEY ("caller_tenant_id") REFERENCES "public"."tenant"("tenant_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_duplicate_of_request_id_fkey" FOREIGN KEY ("duplicate_of_request_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_equipment_id_fkey" FOREIGN KEY ("equipment_id") REFERENCES "public"."equipment"("equipment_id");



ALTER TABLE ONLY "public"."maintenance_request_history"
    ADD CONSTRAINT "maintenance_request_history_referenced_request_id_fkey" FOREIGN KEY ("referenced_request_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."maintenance_request_history"
    ADD CONSTRAINT "maintenance_request_history_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."project"("project_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_sector_id_fkey" FOREIGN KEY ("sector_id") REFERENCES "public"."sector"("sector_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "public"."unit"("unit_id");



ALTER TABLE ONLY "public"."maintenance_request"
    ADD CONSTRAINT "maintenance_request_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."on_call_schedule"
    ADD CONSTRAINT "on_call_schedule_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "public"."employee"("employee_id");



ALTER TABLE ONLY "public"."parking_assignment"
    ADD CONSTRAINT "parking_assignment_lease_id_fkey" FOREIGN KEY ("lease_id") REFERENCES "public"."lease"("lease_id");



ALTER TABLE ONLY "public"."pest_control_case"
    ADD CONSTRAINT "pest_control_case_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."pest_control_case"
    ADD CONSTRAINT "pest_control_case_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."pool_access_code"
    ADD CONSTRAINT "pool_access_code_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."recurring_task_pattern"
    ADD CONSTRAINT "recurring_task_pattern_assigned_employee_id_fkey" FOREIGN KEY ("assigned_employee_id") REFERENCES "public"."employee"("employee_id");



ALTER TABLE ONLY "public"."recurring_task_pattern"
    ADD CONSTRAINT "recurring_task_pattern_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."service_contract_building"
    ADD CONSTRAINT "service_contract_building_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."service_contract_building"
    ADD CONSTRAINT "service_contract_building_contract_id_fkey" FOREIGN KEY ("contract_id") REFERENCES "public"."service_contract"("contract_id");



ALTER TABLE ONLY "public"."service_contract"
    ADD CONSTRAINT "service_contract_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."service_visit"
    ADD CONSTRAINT "service_visit_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."service_visit"
    ADD CONSTRAINT "service_visit_equipment_id_fkey" FOREIGN KEY ("equipment_id") REFERENCES "public"."equipment"("equipment_id");



ALTER TABLE ONLY "public"."service_visit"
    ADD CONSTRAINT "service_visit_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."staff_shift"
    ADD CONSTRAINT "staff_shift_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "public"."employee"("employee_id");



ALTER TABLE ONLY "public"."storage_assignment"
    ADD CONSTRAINT "storage_assignment_lease_id_fkey" FOREIGN KEY ("lease_id") REFERENCES "public"."lease"("lease_id");



ALTER TABLE ONLY "public"."tenancy_record"
    ADD CONSTRAINT "tenancy_record_lease_id_fkey" FOREIGN KEY ("lease_id") REFERENCES "public"."lease"("lease_id");



ALTER TABLE ONLY "public"."tenancy_record"
    ADD CONSTRAINT "tenancy_record_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "public"."tenant"("tenant_id");



ALTER TABLE ONLY "public"."tenant_equipment_loan"
    ADD CONSTRAINT "tenant_equipment_loan_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "public"."tenant"("tenant_id");



ALTER TABLE ONLY "public"."tenant_equipment_loan"
    ADD CONSTRAINT "tenant_equipment_loan_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "public"."unit"("unit_id");



ALTER TABLE ONLY "public"."triage_log"
    ADD CONSTRAINT "triage_log_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."unit_appliance"
    ADD CONSTRAINT "unit_appliance_lease_id_fkey" FOREIGN KEY ("lease_id") REFERENCES "public"."lease"("lease_id");



ALTER TABLE ONLY "public"."unit"
    ADD CONSTRAINT "unit_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



ALTER TABLE ONLY "public"."unit_turnover_furniture_item"
    ADD CONSTRAINT "unit_turnover_furniture_item_turnover_id_fkey" FOREIGN KEY ("turnover_id") REFERENCES "public"."unit_turnover"("turnover_id");



ALTER TABLE ONLY "public"."unit_turnover"
    ADD CONSTRAINT "unit_turnover_incoming_tenant_id_fkey" FOREIGN KEY ("incoming_tenant_id") REFERENCES "public"."tenant"("tenant_id");



ALTER TABLE ONLY "public"."unit_turnover"
    ADD CONSTRAINT "unit_turnover_outgoing_tenant_id_fkey" FOREIGN KEY ("outgoing_tenant_id") REFERENCES "public"."tenant"("tenant_id");



ALTER TABLE ONLY "public"."unit_turnover_settlement"
    ADD CONSTRAINT "unit_turnover_settlement_turnover_id_fkey" FOREIGN KEY ("turnover_id") REFERENCES "public"."unit_turnover"("turnover_id");



ALTER TABLE ONLY "public"."unit_turnover"
    ADD CONSTRAINT "unit_turnover_source_turnover_id_fkey" FOREIGN KEY ("source_turnover_id") REFERENCES "public"."maintenance_request"("request_id");



ALTER TABLE ONLY "public"."unit_turnover"
    ADD CONSTRAINT "unit_turnover_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "public"."unit"("unit_id");



ALTER TABLE ONLY "public"."vacant_unit_task_item"
    ADD CONSTRAINT "vacant_unit_task_item_task_id_fkey" FOREIGN KEY ("task_id") REFERENCES "public"."vacant_unit_task"("task_id");



ALTER TABLE ONLY "public"."vacant_unit_task"
    ADD CONSTRAINT "vacant_unit_task_unit_id_fkey" FOREIGN KEY ("unit_id") REFERENCES "public"."unit"("unit_id");



ALTER TABLE ONLY "public"."vendor_category_exclusivity"
    ADD CONSTRAINT "vendor_category_exclusivity_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."vendor_contact"("vendor_id");



ALTER TABLE ONLY "public"."waste_collection_schedule"
    ADD CONSTRAINT "waste_collection_schedule_building_id_fkey" FOREIGN KEY ("building_id") REFERENCES "public"."building"("building_id");



CREATE POLICY "admin_director_only" ON "public"."building_security_credential" FOR SELECT USING (("public"."has_role"('admin'::"text") OR "public"."has_role"('director'::"text")));



ALTER TABLE "public"."building" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_access_control" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_camera_system" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_document" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_employee_assignment" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_fire_system" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_intercom" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_key_box" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_paint_spec" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_security_credential" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_telecom" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."building_vendor" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cleaning_task_checklist" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."data_provenance" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "dir_coord_all" ON "public"."maintenance_followup_entry" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text")));



CREATE POLICY "dir_coord_all" ON "public"."maintenance_request" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text")));



CREATE POLICY "dir_coord_only" ON "public"."guarantor" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text")));



CREATE POLICY "dir_coord_only" ON "public"."lease" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text")));



CREATE POLICY "dir_coord_only" ON "public"."parking_assignment" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text")));



CREATE POLICY "dir_coord_only" ON "public"."storage_assignment" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text")));



ALTER TABLE "public"."elevator_reservation" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."emergency_access_code" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."employee" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."employee_building_assignment" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."employee_role" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."entrance" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."equipment" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."guarantor" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."laundry_contract" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."lease" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."maintenance_attachment" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."maintenance_followup_entry" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."maintenance_request" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."maintenance_request_history" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."on_call_schedule" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."parking_assignment" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."pest_control_case" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."pool_access_code" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."project" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."recurring_task_pattern" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."sector" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."service_contract" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."service_contract_building" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."service_visit" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "staff_read" ON "public"."building" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_access_control" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_camera_system" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_document" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_fire_system" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_intercom" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_key_box" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_paint_spec" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."building_vendor" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."emergency_access_code" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."employee" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."entrance" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."equipment" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."pool_access_code" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."project" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."sector" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."service_contract" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."service_contract_building" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."service_visit" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."tenancy_record" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."tenant" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."unit" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



CREATE POLICY "staff_read" ON "public"."vendor_contact" FOR SELECT USING (("public"."has_role"('director'::"text") OR "public"."has_role"('coordinator'::"text") OR "public"."has_role"('technician'::"text")));



ALTER TABLE "public"."staff_shift" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."storage_assignment" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "tech_scoped" ON "public"."maintenance_followup_entry" FOR SELECT USING (("public"."has_role"('technician'::"text") AND ("request_id" IN ( SELECT "maintenance_request"."request_id"
   FROM "public"."maintenance_request"
  WHERE (("maintenance_request"."assigned_employee_id" = "public"."current_employee_id"()) OR ("maintenance_request"."building_id" IN ( SELECT "technician_building_ids"."building_id"
           FROM "public"."technician_building_ids"() "technician_building_ids"("building_id"))))))));



CREATE POLICY "tech_scoped" ON "public"."maintenance_request" FOR SELECT USING (("public"."has_role"('technician'::"text") AND (("assigned_employee_id" = "public"."current_employee_id"()) OR ("building_id" IN ( SELECT "technician_building_ids"."building_id"
   FROM "public"."technician_building_ids"() "technician_building_ids"("building_id"))))));



ALTER TABLE "public"."tenancy_record" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."tenant" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."tenant_equipment_loan" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."triage_log" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."unit" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."unit_appliance" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."unit_turnover" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."unit_turnover_furniture_item" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."unit_turnover_settlement" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."vacant_unit_task" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."vacant_unit_task_item" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."vendor_category_exclusivity" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."vendor_contact" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."waste_collection_schedule" ENABLE ROW LEVEL SECURITY;


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON FUNCTION "public"."current_employee_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."current_employee_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."current_employee_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."has_role"("role_name" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."has_role"("role_name" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."has_role"("role_name" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."rls_auto_enable"() TO "anon";
GRANT ALL ON FUNCTION "public"."rls_auto_enable"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."rls_auto_enable"() TO "service_role";



GRANT ALL ON FUNCTION "public"."technician_building_ids"() TO "anon";
GRANT ALL ON FUNCTION "public"."technician_building_ids"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."technician_building_ids"() TO "service_role";



GRANT ALL ON TABLE "public"."building" TO "anon";
GRANT ALL ON TABLE "public"."building" TO "authenticated";
GRANT ALL ON TABLE "public"."building" TO "service_role";



GRANT ALL ON TABLE "public"."building_access_control" TO "anon";
GRANT ALL ON TABLE "public"."building_access_control" TO "authenticated";
GRANT ALL ON TABLE "public"."building_access_control" TO "service_role";



GRANT ALL ON TABLE "public"."building_camera_system" TO "anon";
GRANT ALL ON TABLE "public"."building_camera_system" TO "authenticated";
GRANT ALL ON TABLE "public"."building_camera_system" TO "service_role";



GRANT ALL ON TABLE "public"."building_document" TO "anon";
GRANT ALL ON TABLE "public"."building_document" TO "authenticated";
GRANT ALL ON TABLE "public"."building_document" TO "service_role";



GRANT ALL ON TABLE "public"."building_employee_assignment" TO "anon";
GRANT ALL ON TABLE "public"."building_employee_assignment" TO "authenticated";
GRANT ALL ON TABLE "public"."building_employee_assignment" TO "service_role";



GRANT ALL ON TABLE "public"."building_fire_system" TO "anon";
GRANT ALL ON TABLE "public"."building_fire_system" TO "authenticated";
GRANT ALL ON TABLE "public"."building_fire_system" TO "service_role";



GRANT ALL ON TABLE "public"."building_intercom" TO "anon";
GRANT ALL ON TABLE "public"."building_intercom" TO "authenticated";
GRANT ALL ON TABLE "public"."building_intercom" TO "service_role";



GRANT ALL ON TABLE "public"."building_key_box" TO "anon";
GRANT ALL ON TABLE "public"."building_key_box" TO "authenticated";
GRANT ALL ON TABLE "public"."building_key_box" TO "service_role";



GRANT ALL ON TABLE "public"."building_paint_spec" TO "anon";
GRANT ALL ON TABLE "public"."building_paint_spec" TO "authenticated";
GRANT ALL ON TABLE "public"."building_paint_spec" TO "service_role";



GRANT ALL ON TABLE "public"."building_security_credential" TO "anon";
GRANT ALL ON TABLE "public"."building_security_credential" TO "authenticated";
GRANT ALL ON TABLE "public"."building_security_credential" TO "service_role";



GRANT ALL ON SEQUENCE "public"."building_security_credential_credential_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."building_security_credential_credential_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."building_security_credential_credential_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."building_telecom" TO "anon";
GRANT ALL ON TABLE "public"."building_telecom" TO "authenticated";
GRANT ALL ON TABLE "public"."building_telecom" TO "service_role";



GRANT ALL ON TABLE "public"."building_vendor" TO "anon";
GRANT ALL ON TABLE "public"."building_vendor" TO "authenticated";
GRANT ALL ON TABLE "public"."building_vendor" TO "service_role";



GRANT ALL ON TABLE "public"."cleaning_task_checklist" TO "anon";
GRANT ALL ON TABLE "public"."cleaning_task_checklist" TO "authenticated";
GRANT ALL ON TABLE "public"."cleaning_task_checklist" TO "service_role";



GRANT ALL ON TABLE "public"."data_provenance" TO "anon";
GRANT ALL ON TABLE "public"."data_provenance" TO "authenticated";
GRANT ALL ON TABLE "public"."data_provenance" TO "service_role";



GRANT ALL ON TABLE "public"."elevator_reservation" TO "anon";
GRANT ALL ON TABLE "public"."elevator_reservation" TO "authenticated";
GRANT ALL ON TABLE "public"."elevator_reservation" TO "service_role";



GRANT ALL ON TABLE "public"."emergency_access_code" TO "anon";
GRANT ALL ON TABLE "public"."emergency_access_code" TO "authenticated";
GRANT ALL ON TABLE "public"."emergency_access_code" TO "service_role";



GRANT ALL ON TABLE "public"."employee" TO "anon";
GRANT ALL ON TABLE "public"."employee" TO "authenticated";
GRANT ALL ON TABLE "public"."employee" TO "service_role";



GRANT ALL ON TABLE "public"."employee_building_assignment" TO "anon";
GRANT ALL ON TABLE "public"."employee_building_assignment" TO "authenticated";
GRANT ALL ON TABLE "public"."employee_building_assignment" TO "service_role";



GRANT ALL ON SEQUENCE "public"."employee_building_assignment_assignment_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."employee_building_assignment_assignment_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."employee_building_assignment_assignment_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."employee_role" TO "anon";
GRANT ALL ON TABLE "public"."employee_role" TO "authenticated";
GRANT ALL ON TABLE "public"."employee_role" TO "service_role";



GRANT ALL ON SEQUENCE "public"."employee_role_employee_role_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."employee_role_employee_role_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."employee_role_employee_role_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."entrance" TO "anon";
GRANT ALL ON TABLE "public"."entrance" TO "authenticated";
GRANT ALL ON TABLE "public"."entrance" TO "service_role";



GRANT ALL ON TABLE "public"."equipment" TO "anon";
GRANT ALL ON TABLE "public"."equipment" TO "authenticated";
GRANT ALL ON TABLE "public"."equipment" TO "service_role";



GRANT ALL ON TABLE "public"."guarantor" TO "anon";
GRANT ALL ON TABLE "public"."guarantor" TO "authenticated";
GRANT ALL ON TABLE "public"."guarantor" TO "service_role";



GRANT ALL ON TABLE "public"."laundry_contract" TO "anon";
GRANT ALL ON TABLE "public"."laundry_contract" TO "authenticated";
GRANT ALL ON TABLE "public"."laundry_contract" TO "service_role";



GRANT ALL ON TABLE "public"."lease" TO "anon";
GRANT ALL ON TABLE "public"."lease" TO "authenticated";
GRANT ALL ON TABLE "public"."lease" TO "service_role";



GRANT ALL ON TABLE "public"."lease_field_view" TO "anon";
GRANT ALL ON TABLE "public"."lease_field_view" TO "authenticated";
GRANT ALL ON TABLE "public"."lease_field_view" TO "service_role";



GRANT ALL ON TABLE "public"."maintenance_attachment" TO "anon";
GRANT ALL ON TABLE "public"."maintenance_attachment" TO "authenticated";
GRANT ALL ON TABLE "public"."maintenance_attachment" TO "service_role";



GRANT ALL ON TABLE "public"."maintenance_followup_entry" TO "anon";
GRANT ALL ON TABLE "public"."maintenance_followup_entry" TO "authenticated";
GRANT ALL ON TABLE "public"."maintenance_followup_entry" TO "service_role";



GRANT ALL ON TABLE "public"."maintenance_request" TO "anon";
GRANT ALL ON TABLE "public"."maintenance_request" TO "authenticated";
GRANT ALL ON TABLE "public"."maintenance_request" TO "service_role";



GRANT ALL ON TABLE "public"."maintenance_request_history" TO "anon";
GRANT ALL ON TABLE "public"."maintenance_request_history" TO "authenticated";
GRANT ALL ON TABLE "public"."maintenance_request_history" TO "service_role";



GRANT ALL ON SEQUENCE "public"."maintenance_request_history_history_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."maintenance_request_history_history_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."maintenance_request_history_history_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."maintenance_request_tech_view" TO "anon";
GRANT ALL ON TABLE "public"."maintenance_request_tech_view" TO "authenticated";
GRANT ALL ON TABLE "public"."maintenance_request_tech_view" TO "service_role";



GRANT ALL ON TABLE "public"."on_call_schedule" TO "anon";
GRANT ALL ON TABLE "public"."on_call_schedule" TO "authenticated";
GRANT ALL ON TABLE "public"."on_call_schedule" TO "service_role";



GRANT ALL ON TABLE "public"."parking_assignment" TO "anon";
GRANT ALL ON TABLE "public"."parking_assignment" TO "authenticated";
GRANT ALL ON TABLE "public"."parking_assignment" TO "service_role";



GRANT ALL ON TABLE "public"."parking_assignment_field_view" TO "anon";
GRANT ALL ON TABLE "public"."parking_assignment_field_view" TO "authenticated";
GRANT ALL ON TABLE "public"."parking_assignment_field_view" TO "service_role";



GRANT ALL ON TABLE "public"."pest_control_case" TO "anon";
GRANT ALL ON TABLE "public"."pest_control_case" TO "authenticated";
GRANT ALL ON TABLE "public"."pest_control_case" TO "service_role";



GRANT ALL ON TABLE "public"."pool_access_code" TO "anon";
GRANT ALL ON TABLE "public"."pool_access_code" TO "authenticated";
GRANT ALL ON TABLE "public"."pool_access_code" TO "service_role";



GRANT ALL ON TABLE "public"."project" TO "anon";
GRANT ALL ON TABLE "public"."project" TO "authenticated";
GRANT ALL ON TABLE "public"."project" TO "service_role";



GRANT ALL ON TABLE "public"."recurring_task_pattern" TO "anon";
GRANT ALL ON TABLE "public"."recurring_task_pattern" TO "authenticated";
GRANT ALL ON TABLE "public"."recurring_task_pattern" TO "service_role";



GRANT ALL ON TABLE "public"."sector" TO "anon";
GRANT ALL ON TABLE "public"."sector" TO "authenticated";
GRANT ALL ON TABLE "public"."sector" TO "service_role";



GRANT ALL ON TABLE "public"."service_contract" TO "anon";
GRANT ALL ON TABLE "public"."service_contract" TO "authenticated";
GRANT ALL ON TABLE "public"."service_contract" TO "service_role";



GRANT ALL ON TABLE "public"."service_contract_building" TO "anon";
GRANT ALL ON TABLE "public"."service_contract_building" TO "authenticated";
GRANT ALL ON TABLE "public"."service_contract_building" TO "service_role";



GRANT ALL ON TABLE "public"."service_visit" TO "anon";
GRANT ALL ON TABLE "public"."service_visit" TO "authenticated";
GRANT ALL ON TABLE "public"."service_visit" TO "service_role";



GRANT ALL ON TABLE "public"."staff_shift" TO "anon";
GRANT ALL ON TABLE "public"."staff_shift" TO "authenticated";
GRANT ALL ON TABLE "public"."staff_shift" TO "service_role";



GRANT ALL ON TABLE "public"."storage_assignment" TO "anon";
GRANT ALL ON TABLE "public"."storage_assignment" TO "authenticated";
GRANT ALL ON TABLE "public"."storage_assignment" TO "service_role";



GRANT ALL ON TABLE "public"."storage_assignment_field_view" TO "anon";
GRANT ALL ON TABLE "public"."storage_assignment_field_view" TO "authenticated";
GRANT ALL ON TABLE "public"."storage_assignment_field_view" TO "service_role";



GRANT ALL ON TABLE "public"."tenancy_record" TO "anon";
GRANT ALL ON TABLE "public"."tenancy_record" TO "authenticated";
GRANT ALL ON TABLE "public"."tenancy_record" TO "service_role";



GRANT ALL ON TABLE "public"."tenant" TO "anon";
GRANT ALL ON TABLE "public"."tenant" TO "authenticated";
GRANT ALL ON TABLE "public"."tenant" TO "service_role";



GRANT ALL ON TABLE "public"."tenant_equipment_loan" TO "anon";
GRANT ALL ON TABLE "public"."tenant_equipment_loan" TO "authenticated";
GRANT ALL ON TABLE "public"."tenant_equipment_loan" TO "service_role";



GRANT ALL ON TABLE "public"."triage_log" TO "anon";
GRANT ALL ON TABLE "public"."triage_log" TO "authenticated";
GRANT ALL ON TABLE "public"."triage_log" TO "service_role";



GRANT ALL ON SEQUENCE "public"."triage_log_log_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."triage_log_log_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."triage_log_log_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."unit" TO "anon";
GRANT ALL ON TABLE "public"."unit" TO "authenticated";
GRANT ALL ON TABLE "public"."unit" TO "service_role";



GRANT ALL ON TABLE "public"."unit_appliance" TO "anon";
GRANT ALL ON TABLE "public"."unit_appliance" TO "authenticated";
GRANT ALL ON TABLE "public"."unit_appliance" TO "service_role";



GRANT ALL ON TABLE "public"."unit_turnover" TO "anon";
GRANT ALL ON TABLE "public"."unit_turnover" TO "authenticated";
GRANT ALL ON TABLE "public"."unit_turnover" TO "service_role";



GRANT ALL ON TABLE "public"."unit_turnover_furniture_item" TO "anon";
GRANT ALL ON TABLE "public"."unit_turnover_furniture_item" TO "authenticated";
GRANT ALL ON TABLE "public"."unit_turnover_furniture_item" TO "service_role";



GRANT ALL ON TABLE "public"."unit_turnover_settlement" TO "anon";
GRANT ALL ON TABLE "public"."unit_turnover_settlement" TO "authenticated";
GRANT ALL ON TABLE "public"."unit_turnover_settlement" TO "service_role";



GRANT ALL ON TABLE "public"."vacant_unit_task" TO "anon";
GRANT ALL ON TABLE "public"."vacant_unit_task" TO "authenticated";
GRANT ALL ON TABLE "public"."vacant_unit_task" TO "service_role";



GRANT ALL ON TABLE "public"."vacant_unit_task_item" TO "anon";
GRANT ALL ON TABLE "public"."vacant_unit_task_item" TO "authenticated";
GRANT ALL ON TABLE "public"."vacant_unit_task_item" TO "service_role";



GRANT ALL ON TABLE "public"."vendor_category_exclusivity" TO "anon";
GRANT ALL ON TABLE "public"."vendor_category_exclusivity" TO "authenticated";
GRANT ALL ON TABLE "public"."vendor_category_exclusivity" TO "service_role";



GRANT ALL ON TABLE "public"."vendor_contact" TO "anon";
GRANT ALL ON TABLE "public"."vendor_contact" TO "authenticated";
GRANT ALL ON TABLE "public"."vendor_contact" TO "service_role";



GRANT ALL ON TABLE "public"."waste_collection_schedule" TO "anon";
GRANT ALL ON TABLE "public"."waste_collection_schedule" TO "authenticated";
GRANT ALL ON TABLE "public"."waste_collection_schedule" TO "service_role";



ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";


CREATE EVENT TRIGGER ensure_rls ON ddl_command_end
WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
EXECUTE FUNCTION public.rls_auto_enable();







