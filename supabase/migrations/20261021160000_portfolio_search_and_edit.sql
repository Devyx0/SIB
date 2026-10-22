-- Portfolio search, filtered unit list, in-app editing of the hierarchy, and
-- the request history timeline.
--
-- 1. FK indexes the portfolio relies on. Every portfolio query resolves each
--    unit's current lease and its occupants; without these that is a
--    sequential scan of lease / tenancy_record per unit (~12 s for the
--    portfolio-wide unit list, ~6 s for the sector totals).
-- 2. Re-sync the identity sequences of the tables the app now inserts into.
--    The Drive ingestion scripts insert explicit ids (TF index, MAX+1) without
--    advancing the sequences, so the next app INSERT could collide.

BEGIN;

CREATE INDEX IF NOT EXISTS lease_unit_debut_idx
    ON public.lease (unit_id, debut_bail DESC);

CREATE INDEX IF NOT EXISTS tenancy_record_lease_idx
    ON public.tenancy_record (lease_id);

CREATE INDEX IF NOT EXISTS unit_building_idx
    ON public.unit (building_id);

CREATE INDEX IF NOT EXISTS building_project_idx
    ON public.building (project_id);

CREATE INDEX IF NOT EXISTS building_paint_spec_building_idx
    ON public.building_paint_spec (building_id);

CREATE INDEX IF NOT EXISTS building_document_building_idx
    ON public.building_document (building_id);

-- The request history timeline reads app edits (status changes) per request;
-- data_provenance is ~270k rows, almost all from ingestion.
CREATE INDEX IF NOT EXISTS data_provenance_app_target_idx
    ON public.data_provenance (target_table, target_pk)
    WHERE source_type = 'app';

SELECT setval(
    pg_get_serial_sequence('public.project', 'project_id'),
    COALESCE((SELECT MAX(project_id) FROM public.project), 0) + 1, false);
SELECT setval(
    pg_get_serial_sequence('public.building', 'building_id'),
    COALESCE((SELECT MAX(building_id) FROM public.building), 0) + 1, false);
SELECT setval(
    pg_get_serial_sequence('public.unit', 'unit_id'),
    COALESCE((SELECT MAX(unit_id) FROM public.unit), 0) + 1, false);
SELECT setval(
    pg_get_serial_sequence('public.building_paint_spec', 'paint_spec_id'),
    COALESCE((SELECT MAX(paint_spec_id) FROM public.building_paint_spec), 0) + 1, false);
SELECT setval(
    pg_get_serial_sequence('public.building_document', 'document_id'),
    COALESCE((SELECT MAX(document_id) FROM public.building_document), 0) + 1, false);
SELECT setval(
    pg_get_serial_sequence('public.data_provenance', 'provenance_id'),
    COALESCE((SELECT MAX(provenance_id) FROM public.data_provenance), 0) + 1, false);

COMMIT;
