-- Weather escalation (SoW 3.4) — staleness guard.
-- Record the call's urgency tier at the moment the forecast was evaluated, so the
-- UI can hide a suggestion once urgency changes and the accept endpoint can 409 a
-- stale suggestion (« Suggestion périmée — revérifiez la météo »).
-- Nullable; existing weather_evaluation rows stay valid (NULL).

BEGIN;

ALTER TABLE public.weather_evaluation
    ADD COLUMN current_tier_at_eval text;

COMMIT;

/*
═══════════════════════════════════════════════════════════════════════════════
ROLLBACK (run manually in psql if this migration must be reverted)
═══════════════════════════════════════════════════════════════════════════════
BEGIN;
ALTER TABLE public.weather_evaluation DROP COLUMN IF EXISTS current_tier_at_eval;
COMMIT;
*/
