# Weather-triggered escalation (SoW 3.4) — research + plan

**Status: DRAFT (pending Charles Bergeron). STEP 2 (button + tables) + STEP 3 (triage
auto-escalation) built locally; feature off by default; never committed, never deployed.**
Every rule below is a *provisional default* stored as data (not code), marked `draft`, with
its source here. The client has **not** confirmed any threshold. See "STEP 2" / "STEP 3"
notes below for how the approved plan changed.

**Source of the thresholds:** client doc `Francois Notes Maintenance` (Drive `1gFlEa4Bi…`),
section *"Notes Claude Latchel" §2.3 — « La vérification météo »*, draft table labelled
**« Ébauche à valider avec Charles Bergeron »** (draft to validate with Charles Bergeron).
Summarised in `docs/francois-milestone1-reference.md` §4. The table is AI-written research
pasted by François, **not** François's own words and **not** a client decision.

---

## What it does

When the feature is enabled (`WEATHER_ESCALATION_ENABLED`), triage may automatically escalate
urgency for **no-heat** calls:

1. The triage model sets `heating_failure: true | false | null` (null = unsure — never guess).
2. After the output gate accepts, if the flag is **true**, the app evaluates weather for the
   building (Québec / Lévis), maps the lowest 24 h forecast temp to a draft band, and — if the
   band's suggested tier ranks **higher** than the model's `urgency_tier` — floors urgency up
   before write, and appends one French line to `other_notes` citing the forecast, band, and
   **art. 1864–1865 C.c.Q.** Raise only (see locked urgency map under Seed bands).
3. Weather failures never block triage (B10); the evaluation row still records
   `source_failed` / `location_unknown`.

The detail panel shows a **read-only** summary of the latest evaluation (band, min temp,
astreinte badge when critical, ECCC licence credit). The **« Vérifier la météo »** button and
keyword hint are removed. `POST /requests/{id}/weather-check` remains for manual re-check.

---

## A. Research findings

### A1. Weather data source — recommend Environment Canada (MSC), CityPage Weather XML

Verified against a **live** file on 2026-10-19 (Québec, `s0000620`).

| Question | Finding | Source |
|---|---|---|
| Free? | **Yes.** Public open data, no cost. | ECCC Data Server End-use Licence (below) |
| API key? | **No key.** Plain HTTPS GET. | datamart is anonymous HTTP |
| Licence / attribution | **ECCC Data Services End-use Licence v2.1.1** (not OGL-Canada). "Royalty-free, perpetual, non-exclusive licence … including for commercial purposes." Required credit: **« Contains information licenced under the Data Server End-use Licence of Environment and Climate Change Canada. »** (or "Data Source: Environment and Climate Change Canada"). | https://eccc-msc.github.io/open-data/licence/readme_en/ |
| Hourly 24 h forecast? | **Yes — exactly 24 `<hourlyForecast>` entries**, each with `<temperature>`. The *lowest forecast temp in the next 24 h* is `min()` over these. Live sample min = 3 °C. | live `s0000620_en.xml`, element `hourlyForecastGroup` |
| Current temp? | **Yes** — `currentConditions/temperature` (live sample 5.2 °C). | same file |
| Wind chill? | Element `windChill` exists in both `currentConditions` and each `hourlyForecast`; **ECCC only populates it when cold enough to matter** — empty in today's mild sample, present in winter. Store it when present, else NULL. | same file |
| Update frequency | "updated hourly at a minimum" (more often for warnings). | https://eccc-msc.github.io/open-data/msc-data/citypage-weather/readme_citypageweather-datamart_en/ |
| Rate limits | MSC Open Data Service Usage Policy (fair-use; no published hard quota). Our cache (≤1 fetch/location/hour) keeps us well inside it. | https://eccc-msc.github.io/open-data/usage-policy/readme_en/ |

**Access path (2026 datamart layout).** The old stable `…/citypage_weather/xml/QC/s0000620_e.xml`
path now **404s**. Current layout:
`https://dd.weather.gc.ca/today/citypage_weather/QC/<HH>/<timestamp>_MSC_CitypageWeather_<siteCode>_en.xml`
(`_fr.xml` for French). Filenames are timestamped, so a consumer lists the current hour's
directory, filters for the site code, and takes the newest file (fall back to the previous
hour near the top of the hour). Site codes come from
`https://collaboration.cmc.ec.gc.ca/cmc/cmos/public_doc/msc-data/citypage-weather/site_list_en.geojson`.

**Site codes (verified in the geojson):** Québec = **`s0000620`** (46.82, −71.22), Lévis = **`s0000416`** (46.80, −71.18). Both cities have their own distinct feed.

> GeoMet-Weather OGC API (also free, also MSC) is an alternative access method if the
> timestamped-filename listing proves annoying. Not required; CityPage XML is sufficient and
> verified. No paid source was evaluated (per ticket).

### A2. Québec vs Lévis from the current schema

Location lives on `building`: `sib_territory` (= `sector.territoire`), `municipality`, and `ville`.
There is **no** `is_levis`/`city_weather` column; it must be derived. (180 buildings total.)

```sql
-- Recommended rule: layered — municipality, then sib_territory, then ville.
SELECT CASE
         WHEN building.municipality ILIKE 'Levis' OR building.sib_territory ILIKE 'Levis%'
              OR building.ville ILIKE 'L_vis'                        THEN 'levis'   -- s0000416
         WHEN building.municipality IS NOT NULL AND btrim(building.municipality) <> '' THEN 'quebec'  -- s0000620
         WHEN building.sib_territory IS NOT NULL AND btrim(building.sib_territory) <> '' THEN 'quebec'
         WHEN building.ville IS NOT NULL AND btrim(building.ville) <> ''             THEN 'quebec'
         ELSE 'unknown'   -- no check; panel shows "Emplacement inconnu"
       END
FROM building;
```

Counts on the dev DB (2026-10-19):

| Signal | Lévis | Québec | Undetermined |
|---|---|---|---|
| `sib_territory` prefix alone | 36 | 136 | **8** |
| `municipality` alone | 36 | 143 | **1** |
| **Layered (recommended)** | **36** | **143** | **1** |

`sib_territory` and `municipality` **agree with zero conflicts** (36/36 Lévis, 136/136 Québec).
The layered rule resolves all but **one** building today. L'Ancienne-Lorette (2) and
Saint-Augustin-de-Desmaures (1) are in the Québec City agglomeration → Québec weather point.

**Buildings that can't be determined from `sib_territory` alone (8):** ids
33, 34, 35, 36, 37, 38, 39 (all `municipality='Quebec'`, so recovered → Québec) and
**120** (`ville='Québec'`, `municipality` blank, `sib_territory` blank — recovered by `ville`).
If all three are blank on a future row → `unknown`, **never guess**.

### A3. Detecting "no heat" calls — recommend (a) a triage flag, keyword as interim only

Three options compared on the dev DB (search over `problem_summary + problems + raw_title +
triage_summary`, 11,046 rows spanning `start_date` **2026-03-02 → 2026-10-28** — about 8 months,
mostly warm season, **no winter**):

**(a) Add a nullable `heating_failure` boolean to the triage output — RECOMMENDED.**
- Triage prompt: add one line to `backend/triage/output_contract.py::OUTPUT_SCHEMA`
  (`"heating_failure": "bool | null"`) and one instruction to `backend/triage/system_prompt.py`
  ("true only when the tenant reports no/insufficient heat; null if unclear"). The model already
  reads the full problem text and already classes « panne de chauffage » as AJD, so this reuses
  comprehension it already has. **NULL when unsure** satisfies "never guess."
- Cost: one extra boolean in the output ≈ negligible per-call tokens. The real cost is **one-time
  re-validation**: the output-contract self-tests and the **full backtest (~$65/run, go/no-go gate
  A=0 D=0)** must be re-run because the prompt changed. (`docs/repo-structure.md`.)
- 3.3 feedback snapshot: `backend/modules/feedback/repository.py::get_triage_snapshot()` is an
  explicit 6-column SELECT, so adding a triage field does **not** change existing snapshots unless
  we choose to add it. Low blast radius; optional to surface in the snapshot.

**(b) Keyword match on the raw problem text — INTERIM FALLBACK ONLY.** Proposed French keywords
(failure-explicit): `pas de chauffage`, `sans chauffage`, `aucun/plus/manque de chauffage`,
`panne de chauffage`, `chauffage {ne fonctionne|défectueux|brisé|hors service|en panne}`,
`pas/manque de chaleur`, `no heat`.
- Focused match = **30 / 11,046**. Broad "any heating term" (adds `thermopompe`, `fournaise`,
  `calorifère`, `plinthe`, `radiateur`, `chaleur`) = **409** and visibly noisy.
- The 11,046 rows span `start_date` **2026-03-02 → 2026-10-28** (about 8 months, mostly warm
  season, no winter). Focused matches = **30**: **14 dated in 2026**, **16 with no `start_date`**.
- **Winter volume is unknown from this data** — the dataset contains no December–February rows,
  which is exactly when a no-heat weather escalation would matter most.
- Even the focused set has **~20-30 % false hits**: e.g. *"chauffage piscine défectueux"* (pool),
  *"thermostat bloqué à 30 °C"* (stuck **hot**), *"chauffage non démarré (mode été)"*, *"chauffage
  central"* (routine). And it **misses** phrasings the model would catch.
- `category_raw` is **empty (0 / 11,046 rows)** — there is no existing category column to lean on.
- 20 sample titles are in the "Research appendix" at the bottom so the client can judge false hits.

**(c) Coordinator toggle only.** Zero AI cost/complexity, but manual and easy to forget — though
the coordinator is already in the loop because no-heat is already AJD.

**Recommendation:** (a) as the authoritative signal; (b) keyword match as a *zero-cost interim*
that only decides whether to **show the "Vérifier la météo" affordance** (never to change urgency);
(c) the manual button is always available as override. `heating_failure` NULL ⇒ no automatic check.

---

## B. Plan — provisional defaults (all overridable later)

> **Design note (open question for Charles):** triage **already** sets every heating/hot-water
> failure to **AJD** regardless of temperature (`docs/francois-milestone1-reference.md` §4.2;
> guide §9). The stored `urgency_tier` enum has only `AJD / ajd / none`. STEP 2 therefore makes
> suggestions **bidirectional** (approved change): a band tier higher than current → « Hausse
> suggérée »; lower → « Baisse possible » (neutral); equal → context only. Accepting either goes
> through the justification modal. **Open question: may weather *lower* urgency at all?** Lowering
> is shown as a non-alarming option, never auto-applied, pending Charles.
>
> ### STEP 2 — what was built (button era; superseded in STEP 3 for detection)
> - Tables, MSC fetch, bands, cache, `/me` flag, manual `POST …/weather-check`, licence credit.
> - Originally button-only with a keyword hint; see STEP 3 for the current design.
>
> ### STEP 3 — triage auto-escalation (approved 2026-10-19)
> - **Model flag** `heating_failure: bool | null` in triage output + one system-prompt line
>   (true only for dwelling heat failure; cite art. 1864–1865 C.c.Q.). **No backtest re-run.**
> - **`evaluate(conn, request_id, evaluated_by=None)`** extracted; endpoint is a thin wrapper;
>   system evaluations use `evaluated_by=NULL`.
> - **`apply_triage_escalation`** after gate accept: raise-only floor + French `other_notes` line;
>   try/except so weather never blocks triage.
> - **UI read-only**: `RequestDetail.weather_evaluation` (latest row); no button, no keyword hint,
>   no accept/suggest flows. Manual endpoint kept.
> - Keyword matcher `backend/modules/weather/keywords.py` **deleted**.
> - Tests: `tests/backend/test_weather.py` (escalation + detail), output-contract self-check,
>   `WeatherPanel.test.tsx` rewritten as read-only.

| # | Default | Source / our choice | Open question |
|---|---|---|---|
| B1 | Feature setting `weather_escalation_enabled`, **default off**. Our choice: an **env var** (`WEATHER_ESCALATION_ENABLED=false`) read by `backend/core/config.py` and surfaced to the UI via `/me` (no DB settings table exists). | Our choice (ticket says "feature setting, default off") | Does the client want a coordinator-editable toggle in the UI? That needs a 1-row DB setting instead of an env var. |
| B2 | `weather_threshold_band` settings table, seeded with 4 draft bands (below). `status='draft'`, `source_text` carries the provenance. | Cut-points from S5 §2.3 examples (−15 / −5…+10). Urgency map locked (below). | Cut-points still draft pending Charles; urgency map is locked from known examples. |
| B3 | Temperature used = **lowest forecast temp in the next 24 h** (min over the 24 hourly entries). Also store `current_temp` and `wind_chill` when present. | S5 §2.3 ("24 h"); mechanics our choice | Should wind chill (not raw temp) drive the band when it's colder? S5 mentions wind chill rhetorically but the table is in °C air temp. |
| B4 | Detection is the triage **`heating_failure`** flag (STEP 3). Keyword hint removed. No backtest re-run. Manual `POST …/weather-check` still available. | Approved STEP 3 | — |
| B5 | Location = Québec or Lévis from the building (A2). Unknown ⇒ no check; panel shows **« Emplacement inconnu »**. | Our choice (per schema) | Which buildings are genuinely out-of-area vs just missing data? |
| B6 | **Bidirectional** (approved change): higher → « Hausse suggérée »; lower → « Baisse possible » (neutral/grey); equal → context only. Never writes urgency directly — accepting either runs through `JustificationModal` → `POST /api/v1/requests/{id}/urgency` (`SetUrgencyBody` + `current_*` stale checks). | Approved change; reuses `action_set_urgency` | May weather *lower* urgency at all? (shown as a non-alarming option, pending Charles) |
| B7 | Critical band shows an **« astreinte / garde »** badge. **No** SMS / email / call sent. | Ticket (3.7 after-hours is separate) | Wiring the badge to a real on-call roster is 3.7, out of scope here. |
| B8 | **Primary:** auto at triage when `heating_failure is true`. **Secondary:** manual `POST …/weather-check` (coord/dir → 403 otherwise). UI is read-only (no button). | Approved STEP 3 | — |
| B9 | **Cache ≤ 1 fetch / location / hour.** Store each forecast snapshot (location, site_code, fetched_at, source, source_url, current/windchill/min-24h, raw). Link each call evaluation to its snapshot. Provenance on accept (approved change): `data_provenance.source_type = 'app'` (existing value — **no** new `'weather'` value); `decision_justification_log.after_value` jsonb carries `{evaluation_id, band, min_forecast_temp_24h_c, source_url}`. | Approved change | — |
| B10 | **Failure-safe:** if the source is down, triage/call is unaffected; the evaluation row records `status='source_failed'`; panel says « La vérification météo a échoué ». Never blocks triage. | Ticket | — |
| B11 | Migration `20261019120000_weather_escalation.sql` **applied to local dev + `sib_test` only** (via psql, no `db reset`; `supabase db diff --local` → no schema changes). RLS **enabled** on all three tables (matching `triage_notes_feedback`). Never pushed. | Ticket | — |
| B12 | Tests in `sib_test` only, **weather API always mocked, no network** (monkeypatch the fetcher, as the codebase mocks via `monkeypatch`/`MagicMock`). | Ticket | — |
| B13 | This document. | Ticket | — |

### Seed bands (draft cut-points; urgency map locked)

`below −15 → critical`, `−15 to −5 → emergency`, `−5 to +10 → priority`, `above +10 → normal`.
Maps onto the existing `urgency_tier` enum `AJD` / `ajd` / null (raise-only at triage):

| Band | Temp range (°C, lowest-24 h) | Suggested tier | Critical badge | Provenance |
|---|---|---|---|---|
| critical | `t < −15` | `AJD` | **yes** (astreinte) | Doc example: below −15°C → critical, same-day |
| emergency | `−15 ≤ t < −5` | `AJD` | no | Gap fill: top-level urgency (`AJD`) |
| priority | `−5 ≤ t < +10` | `ajd` | no | Doc example: −5°C to +10°C → 48h response → `ajd` |
| normal | `t ≥ +10` | `none` (no change) | no | Our call: no weather floor when mild |

> **Boundary rule** (tests assert): inclusive lower bound, exclusive upper. Exactly −15 →
> emergency, exactly −5 → priority, exactly +10 → normal. Direction compare:
> `none/null < ajd < AJD` (suggested > current → higher; < → lower; = → equal).

---

## Schema (migration `20261019120000_weather_escalation.sql` — applied to local dev + sib_test)

Three new tables, all RLS-enabled. **No** triage/`heating_failure` column (detection is
button-only). No changes to existing tables; `SetUrgencyBody` gained an optional
`weather_evaluation_id`, and `RequestDetail` an advisory `heating_keyword_hint` boolean.

1. **`weather_threshold_band`** — `band_id` PK, `name`, `temp_min_c` null, `temp_max_c` null,
   `suggested_tier` text null (`AJD`/`ajd`/null), `is_critical` bool, `status` default `'draft'`,
   `source_text`, `sort_order`. Seed the 4 rows above.
2. **`weather_forecast_snapshot`** — `snapshot_id` PK, `location` (`quebec`/`levis`), `site_code`,
   `fetched_at`, `source` (`'msc_citypage'`), `source_url`, `current_temp_c` null,
   `wind_chill_c` null, `min_forecast_temp_24h_c` null, `raw` jsonb. Cache = "reuse newest row for
   location where `fetched_at > now() - 1 hour`, else fetch+insert."
3. **`weather_evaluation`** — `evaluation_id` PK, `request_id` FK, `snapshot_id` FK null,
   `location` null, `band_name` null, `min_forecast_temp_24h_c` null, `suggested_tier` null,
   `is_critical` bool, `evaluated_by` FK, `evaluated_at`, `status`
   (`ok`/`location_unknown`/`source_failed` — `feature_off` was dropped). The panel renders from
   the returned evaluation.
4. **Provenance on accept:** `data_provenance.source_type = 'app'` (existing value, written by the
   shared `write_provenance`); `decision_justification_log.after_value` jsonb carries
   `{evaluation_id, band, min_forecast_temp_24h_c, source_url}`. No `heating_failure` column.

## Tests (sib_test, weather fetcher always mocked, no network) — written in STEP 2

`tests/backend/test_weather.py` (29) + `apps/web/src/tests/WeatherPanel.test.tsx` (10):
band boundaries at exact **−15 / −5 / +10**; higher / lower / equal suggestion; unknown location;
source failure (does not block, no snapshot written); cache reuse (no 2nd fetch within the hour);
feature off → 404 and nothing written; 403 for technician/contractor; accept → justification
`after_value` + `source_type='app'` provenance; stale-check 409; keyword hint shown/hidden;
licence text present; frontend panel states (higher/lower/equal, astreinte badge, emplacement
inconnu, check-failed, feature-off-hidden); RLS enabled on all three tables.

---

## Consolidated open questions for Charles / François

1. **May weather *lower* urgency at all?** Built as a non-alarming « Baisse possible » option that
   is never auto-applied — but given no-heat is already AJD, confirm lowering is wanted at all.
2. Confirm the four cut-points (−15 / −5 / +10) and the boundary convention (inclusive lower bound).
   Urgency map for those bands is **locked** (critical/emergency → `AJD`, priority → `ajd`,
   normal → none); only the numeric thresholds remain draft.
3. Wind chill vs air temperature as the band driver (wind chill is stored, not used).
4. Coordinator-editable enable toggle (DB setting) vs ops-only env var (`WEATHER_ESCALATION_ENABLED`).
5. The "astreinte / garde" badge: does it need to read a real on-call roster (that is 3.7, out of scope)?
6. Pipe-freezing (<−20 °C), snow accumulation, and AC-in-heatwave variants are mentioned in S5 §2.3
   with **no thresholds** — out of scope for 3.4 unless the client provides them.

---

## Research appendix — sample "no heat" titles (focused keyword match, dev DB, no personal data)

`problem_summary` only (no address, no names). These show why keyword matching is noisy — the client
can judge the false hits:

```
Fuite gym, chauffage piscine défectueux, zone bien-être sale      ← pool heating (false hit)
Thermostat électrique chambre à coucher (bloqué à 30°C)           ← stuck HOT (false hit)
Chauffage central                                                  ← routine? ambiguous
DOUBLON POTENTIEL — Chauffage non démarré / Porte: froid entre
Chauffage hors service (menace TAL)                                ← genuine no-heat
Panne de chauffage — thermostats inopérants                        ← genuine no-heat
Pas de chauffage                                                   ← genuine no-heat
Chauffage en panne — suivi demandé                                 ← genuine no-heat
Pas de chauffage / Climatiseur portatif SIB à récupérer
2 calorifères HS                                                   ← genuine (heaters dead)
Thermostat                                                         ← ambiguous
Chauffage non démarré (mode été) / Plafonnier couloir
Doublon  Douche / Cuisinière / Chauffage / Robinet cuisine / Ampoules   ← "chauffage" in a list
Fuite robinet cuisine / Détecteur fumée / Chauffage                ← "chauffage" in a list
```
Focused match volume: **30 rows** (dev dataset `start_date` 2026-03-02 → 2026-10-28; 14 dated
in 2026, 16 with no `start_date`). Broad "any heating term": 409 (very noisy).
