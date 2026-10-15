-- Extend data_provenance for app-initiated edits.
-- Both columns nullable; existing ingestion rows stay valid (NULL in both).
-- App edits write: employee_id = acting user, previous_value = old text,
--   ingested_value = new text, raw_value = new as entered, source_type = 'app'.
ALTER TABLE data_provenance
    ADD COLUMN employee_id    integer REFERENCES employee(employee_id),
    ADD COLUMN previous_value text;
