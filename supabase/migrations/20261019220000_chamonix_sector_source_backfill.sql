-- 1175 Chamonix is Québec-Est (sector_id 4), not Inconnu (7).
-- Also backfill source_calendar from sector for pre-auto-route rows.

UPDATE building
SET sector_id = 4
WHERE adresse ILIKE '%Chamonix%'
  AND sector_id = 7;

UPDATE maintenance_request mr
SET sector_id = b.sector_id
FROM building b
WHERE mr.building_id = b.building_id
  AND b.adresse ILIKE '%Chamonix%'
  AND (mr.sector_id IS DISTINCT FROM b.sector_id);

UPDATE maintenance_request mr
SET source_calendar = CASE
  WHEN COALESCE(s.color_code, '') = '6' THEN 'st_maj'
  WHEN lower(unaccent(COALESCE(s.territoire, ''))) ~ 'levis|rive.?sud|charny'
    THEN 'st_maj'
  ELSE 'main'
END
FROM sector s
WHERE s.sector_id = mr.sector_id
  AND mr.source_calendar IS NULL;
