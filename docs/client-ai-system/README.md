# Client AI System — Orientation

This folder contains the operating files for a **separate, independently-built Claude-based maintenance-call triage agent** that runs in production against the client's Google Calendar. This system was built and is operated by the client. It is **entirely distinct from anything in this repository** — we are not building it, maintaining it, or deploying it. It is documented here because several of its data sources overlap with ours, and understanding those overlaps is necessary for our ingestion work.

---

## Files in this folder

| File | What it is |
|------|-----------|
| `SKILL.md` | The triage agent's own skill definition — its full operating instructions (~527 lines). This is the executable spec that another Claude instance reads at runtime. **Do not translate, reformat, or alter it.** |
| `guide-coordonnateur-maintenance-v4_39.md` | A detailed human-facing rules guide (~958 lines) that the skill references. Also a live production document. **Do not alter.** |
| `exemple-complet.md` | A worked example of the structured note format the agent writes into Calendar events. Reference only. |
| `secteurs-et-equipe.md` | A sector/color/employee/vendor reference table used during triage. Reference only. |

All four files were copied verbatim. They must remain byte-for-byte identical to their source — any in-place translation or reformatting would break the running system that reads them.

---

## Key cross-references with OUR project

### RRIA ("Rent Roll IA")

Described in SKILL.md section 6 and referenced throughout. This is an AI-maintained occupant lookup, stored in a folder called "Rent roll (IA)" in the maintenance@ Google Drive, **regenerated nightly around 4 AM**. Split into per-project files (one file per project, with overflow blocks suffixed `(2)`, `(3)` beyond 90 occupants). Explicitly contains **no financial data**.

The RRIA master index file is: `1AFE019j2gt_AqfI2PQgAsD9GixfCvXV56d7LEH0GMSw` (SKILL.md section 4.3).

**Relationship to our Master Rent Roll**: the RRIA is likely **derived from** but **distinct from** the "Master Rent Roll.xlsx" (Drive ID `1wfGj7Bjzb08AyaOk5zzlnsvqzAcfPA66`) we used in the Phase 0 crosswalk. Our MRR has financial data; the RRIA explicitly does not. Whether they share the same underlying tenant data, and whether the RRIA was generated from our MRR or from a separate source, is **unconfirmed — needs verification** before treating the two as equivalent.

---

### "Fiches techniques (IA)" folder

SKILL.md section Sources states: *"Hors projet : dossier 'Fiches techniques (IA)' de Mon Drive de maintenance@."* The triage agent reads these for building technical context during call handling.

**Critical finding from the cross-check**: The `Table_Fondamentale` (see `drive_pipeline/table_fondamentale/`) contains Google Sheets links to FT files (`/spreadsheets/d/...` URLs). **None of these 177 Sheets IDs match any Drive file ID in our `drive_pipeline/fiches_techniques/links.py`** — checked exhaustively against all Drive IDs and all link-embedded IDs in our links file.

This means the "Fiches techniques (IA)" folder that the triage agent uses is **a different set of files** than the `.xlsx` files we have been translating in this project. These are native Google Sheets (not uploaded `.xlsx` files), stored in the maintenance@ Drive, not the same Drive folder our links.py points to.

**What this means for our work**: our entire translated FT pipeline (`drive_pipeline/fiches_techniques/`) has been working with a different copy of the FT data than the one the production AI system uses. The Table Fondamentale's links are the authoritative production FT references. **This needs a decision**: do we continue with our existing .xlsx pipeline, switch to the Sheets-native files the triage agent uses, or reconcile them?

---

### "Tableau vivant" / Tableau des Appels de Service (IA)

Described in SKILL.md section 4.7. Sheet ID: `1VLLHbK0euh-6utsGhI5XZSxmFdxQM4xrj9Ns69_OjAQ`. Tab name: "Appels". Described as a 15-minute-regenerated cache of live Calendar events, covering ~6 months. **Never a source of truth** — the agent uses it only to identify candidates, never to derive links or authoritative data.

**Working hypothesis that needs confirmation**: our already-translated `work/dryrun_maintenance/Service Call Log (IA).xlsx` (File 10 from the maintenance translation batch) appears to be a snapshot/export of this live sheet. Evidence:

- Sheet tab name matches: `"Appels"` ✓
- Column Y is "Project" / "Projet" ✓ (SKILL.md explicitly says "filtrer par la colonne Projet (colonne Y)")
- "Last Calendar Update" = "Dernière modif agenda" ✓ (SKILL.md's staleness check column)
- "Event Link" = "Lien événement" ✓

This is **high-confidence but unconfirmed** — we are seeing a translated version of File 10's headers, not the original French. The original French headers need to be checked against the live sheet to confirm they are an exact match. Do not treat this as confirmed until then.

---

### Fichier des numéros uniques d'unité (~4,310 units)

Mentioned in SKILL.md section Sources: *"Fichier des numéros uniques d'unité (~4310 unités) : jumeler l'adresse libre du Gravity au numéro officiel."* This is a lookup file that maps free-text Gravity (ticketing system) addresses to official unit numbers.

**This file exists and is actively used by the triage agent.** An earlier assumption in this project held that no such comprehensive unit-number file existed. That assumption was incorrect. We have not yet located this file in the Drive, and it has no Drive ID recorded anywhere in our pipeline. It should be found and evaluated as a potential ingestion source for unit-number normalization.

---

## What NOT to do with these files

- Do not translate SKILL.md or the guide in place — any translation is a separate deliverable
- Do not use these files as ingestion sources for our Supabase schema (they are instruction/reference documents, not business data)
- Do not assume the RRIA and our Master Rent Roll are interchangeable without verification
- Do not assume the TF Sheets FT links point to the same files as our links.py — they don't
