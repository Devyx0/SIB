# Repo structure — decisions

_Recorded 2026-10-13 after monorepo analysis. Update this file if a decision changes._

---

## Why the Python layout did not move

The proposed sketch had `packages/triage/` and `packages/ingestion/`. This was not applied for two reasons:

1. **`packages/` is a filesystem label, not a Python concept.** Moving `drive_pipeline/triage/` to `packages/triage/` breaks every absolute import in `backtest.py` (`from drive_pipeline.triage.*`) and requires adding `packages/` to `sys.path` via pyproject.toml. That is extra machinery for no runtime benefit.

2. **The right trigger is the API build, not the frontend.** When `apps/api/` is written, `triage` will be extracted as a proper installable package (its own `pyproject.toml`, installed as a workspace member). That work has a concrete reason to touch the import paths. Doing it now would mean touching ~30 import lines across 25+ files for a directory rename that helps no one today.

The frontend lives in `apps/web/`. The Python packages stay under `drive_pipeline/` until the API gives a real reason to move them.

---

## Why backtest.py is application code, not a test

`drive_pipeline/triage/backtest.py` is invoked manually with:

```
uv run python3 -m drive_pipeline.triage.backtest --full
```

It calls the real Anthropic API, reads 1,392 live DB rows, and costs approximately **$65 per full run** ($0.047/call × 1,392 calls). It is not a pytest test, has no fixtures, and must never be placed in a directory that a CI runner would discover automatically. It belongs with the triage library code, where it must be invoked deliberately.

The go/no-go gate for production is **A = 0, D = 0 across the full pool**. That gate is evaluated by running backtest manually after the client adjudication review returns and Gate 6 is fixed.

---

## Why the gate self-tests stay in `__main__` until pytest exists in CI

`drive_pipeline/triage/output_contract.py` contains 29 `chk()` calls under `if __name__ == "__main__"`. These are pure-Python assertions against the validation logic — zero cost, no API calls, run in milliseconds:

```
python3 drive_pipeline/triage/output_contract.py
```

They will move to `packages/triage/tests/test_output_contract.py` when pytest is added to CI. That is the trigger — not this restructuring. Adding pytest infrastructure before CI exists creates configuration debt with no payoff.

---

## Where credentials live and why

All three credential files stay at the **repo root**:

| File | Used by | How located |
|------|---------|-------------|
| `.env` | All Python code | `load_dotenv(Path(__file__).parent.parent.parent / ".env")` — relative from each script's depth |
| `credentials.json` | Google Drive OAuth (initial auth flow) | `ROOT / "credentials.json"` where `ROOT = Path(__file__).parent.parent.parent` |
| `token.json` | Google Drive API (refreshable token) | `ROOT / "token.json"` — same pattern |

`.env` is never committed (in `.gitignore`). `credentials.json` and `token.json` are Google OAuth artifacts — keep them at root so all ingestion scripts and the calendar parser find them via the same `ROOT` reference.

**Do not** move any of these into a subdirectory without auditing every `ROOT /` reference in `drive_pipeline/ingestion/`. There are approximately 15 scripts that compute `ROOT = Path(__file__).parent.parent.parent`.

---

## scripts/ — Fiches Techniques era tooling (removed)

The `scripts/` directory existed for the Fiches Techniques pipeline: downloading, translating, auditing, and maintaining the ~350 Excel technical sheets stored in Google Drive. That pipeline completed and was verified before 2026-10-13. The directory was removed entirely once all eight scripts were confirmed dead.

All eight files are recoverable from git history if ever needed.

**Pass 1 — 2026-10-13** (broken token path: `os.path.dirname(__file__) + "token.json"` resolved to `scripts/token.json`, which never existed):

| Script | What it did |
|--------|------------|
| `scripts/translate_labels.py` | Translated Fiches Techniques column A (field labels) French→English via Drive API |
| `scripts/translate_values.py` | Translated Fiches Techniques column B (values) via Anthropic API, wrote column C |
| `scripts/audit_flat.py` | Verified flat-labeled Fiches entries sat in the correct Drive folders |

**Pass 2 — 2026-10-13** (Fiches pipeline complete; no further folder reorganisation planned):

| Script | What it did |
|--------|------------|
| `scripts/dry_run_report.py` | Generated output file written by `translate_labels.py` — dry-run label translation diff |
| `scripts/value_dry_report.py` | Generated output file written by `translate_values.py` — per-cell translation stats and low-confidence flags |
| `scripts/build_inventory.py` | Downloaded all 350 Fiches xlsx from Drive, extracted column-A labels, wrote `columns_inventory.py` |
| `scripts/sample_layout.py` | Sampled Fiches xlsx row/column layout from Drive for one-time structural analysis |
| `scripts/swap_ancienne.py` | Swapped FR↔EN Drive file IDs in `links.py` for "01-Old Technical Sheets" entries; carried a CWD-relative `LINKS_FILE` path that required running from repo root |
