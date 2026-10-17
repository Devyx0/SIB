-- Migration 0005: Gravity Forms intake columns
-- Adds two nullable columns to maintenance_request for form-sourced calls.
-- Existing rows are unaffected (both default to NULL).
--
-- attachment_url      — single photo URL submitted via GF; not downloaded, stored as text.
-- created_by_wp_user_id — WordPress integer user ID of the staff submitter (blank = tenant).
-- raw_caller_body     — original caller-provided JSON preserved before triage overwrites.
--
-- unaccent: required by board search (repository.py get_board_list) for accent-insensitive
-- ILIKE on asnu, raw_title, adresse, web_building_name, nom_employe.

CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA public;

BEGIN;

ALTER TABLE public.maintenance_request
    ADD COLUMN IF NOT EXISTS attachment_url        text,
    ADD COLUMN IF NOT EXISTS created_by_wp_user_id integer,
    ADD COLUMN IF NOT EXISTS raw_caller_body       jsonb;

COMMIT;

/*
ROLLBACK:
BEGIN;
ALTER TABLE public.maintenance_request
    DROP COLUMN IF EXISTS raw_caller_body,
    DROP COLUMN IF EXISTS created_by_wp_user_id,
    DROP COLUMN IF EXISTS attachment_url;
COMMIT;
*/
