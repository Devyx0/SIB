-- Building geocode: store WGS84 coords from Nominatim (or equivalent) and a
-- status so failed / ambiguous Quebec addresses can be fixed by hand.

BEGIN;

ALTER TABLE public.building
    ADD COLUMN IF NOT EXISTS latitude double precision,
    ADD COLUMN IF NOT EXISTS longitude double precision,
    ADD COLUMN IF NOT EXISTS geocode_status text,
    ADD COLUMN IF NOT EXISTS geocoded_at timestamptz,
    ADD COLUMN IF NOT EXISTS geocode_query text;

ALTER TABLE public.building
    DROP CONSTRAINT IF EXISTS building_geocode_status_check;

ALTER TABLE public.building
    ADD CONSTRAINT building_geocode_status_check
    CHECK (
        geocode_status IS NULL
        OR geocode_status IN ('pending', 'ok', 'failed', 'skipped', 'needs_review')
    );

COMMENT ON COLUMN public.building.latitude IS
    'WGS84 latitude from geocoding (Nominatim).';
COMMENT ON COLUMN public.building.longitude IS
    'WGS84 longitude from geocoding (Nominatim).';
COMMENT ON COLUMN public.building.geocode_status IS
    'pending | ok | failed | skipped | needs_review';
COMMENT ON COLUMN public.building.geocoded_at IS
    'When latitude/longitude/geocode_status were last set.';
COMMENT ON COLUMN public.building.geocode_query IS
    'Query string sent to the geocoder (audit / re-runs).';

COMMIT;

-- ── Rollback ─────────────────────────────────────────────────────────────────
/*
BEGIN;
ALTER TABLE public.building DROP CONSTRAINT IF EXISTS building_geocode_status_check;
ALTER TABLE public.building
    DROP COLUMN IF EXISTS latitude,
    DROP COLUMN IF EXISTS longitude,
    DROP COLUMN IF EXISTS geocode_status,
    DROP COLUMN IF EXISTS geocoded_at,
    DROP COLUMN IF EXISTS geocode_query;
COMMIT;
*/
