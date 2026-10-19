-- Refresh weather_threshold_band.source_text to the locked urgency map
-- (doc examples + top-level fill for −15…−5). Cut-points and suggested_tier unchanged.

UPDATE public.weather_threshold_band SET source_text =
  'Doc example: below -15 C -> critical, same-day (AJD). Draft cut-point.'
WHERE name = 'critical';

UPDATE public.weather_threshold_band SET source_text =
  'Gap fill: -15 to -5 C -> top-level urgency (AJD). Draft cut-point.'
WHERE name = 'emergency';

UPDATE public.weather_threshold_band SET source_text =
  'Doc example: -5 to +10 C -> 48h response -> ajd. Draft cut-point.'
WHERE name = 'priority';

UPDATE public.weather_threshold_band SET source_text =
  'Our call: t >= +10 C -> no weather floor (suggested_tier null). Draft cut-point.'
WHERE name = 'normal';
