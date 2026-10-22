-- Replace letter-code urgency (AJD / ajd / none) with plain sheet levels
-- from Générale!E (Niveau d'urgence): URGENT / Intermédiaire / Faible.
-- Calendar title prefix constraints no longer apply.

BEGIN;

-- Drop the enum cast: convert column to text with mapped values.
ALTER TABLE public.maintenance_request
    ALTER COLUMN urgency_tier DROP DEFAULT;

ALTER TABLE public.maintenance_request
    ALTER COLUMN urgency_tier TYPE text
    USING (
        CASE urgency_tier::text
            WHEN 'AJD'  THEN 'URGENT'
            WHEN 'ajd'  THEN 'Intermédiaire'
            WHEN 'none' THEN NULL
            ELSE NULL
        END
    );

ALTER TABLE public.maintenance_request
    ADD CONSTRAINT urgency_tier_check
    CHECK (
        urgency_tier IS NULL
        OR urgency_tier IN ('URGENT', 'Intermédiaire', 'Faible')
    );

DROP TYPE IF EXISTS public.urgency_tier;

COMMENT ON COLUMN public.maintenance_request.urgency_tier IS
    'Plain urgency from sheet Niveau d''urgence: URGENT | Intermédiaire | Faible | NULL.';

-- Weather bands suggested the old letter codes.
UPDATE public.weather_threshold_band
SET suggested_tier = 'URGENT',
    source_text = replace(source_text, 'AJD', 'URGENT')
WHERE suggested_tier = 'AJD';

UPDATE public.weather_threshold_band
SET suggested_tier = 'Intermédiaire',
    source_text = replace(replace(source_text, 'ajd', 'Intermédiaire'), 'AJD', 'URGENT')
WHERE suggested_tier = 'ajd';

COMMIT;
