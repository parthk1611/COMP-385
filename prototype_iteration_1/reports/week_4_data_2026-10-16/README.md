# Week 4 — completed local development package

Completed October 16, 2026. The requested corrected-weather comparison, provincial selected-source preparation/join, and live HRDPS research adapter have executed locally. **110 tests pass.** This completes the implemented Week 4 data-preparation scope; it does not establish operational forecasting or complete Week 5 acceptance.

## Results

| Work | Measured result | Evidence |
| --- | --- | --- |
| Historical weather correction | 14,238,656 unchanged 2010–2017 development rows; weather missingness 54.0506% → 11.4542% | [Original build details](increment_notes.md), [join audit](weather_feature_join_audit.json) |
| Fair model refits | Four candidates × two protocols × two grid scenarios; 16 new saved bundles, save/load parity | [Comparison and limits](model_comparison_update.md) |
| Provincial weather | 11 pinned Jan–Nov 2025 ERA5 files; 8,016 hours; 3,222,432 daily rows across 9,648 cells; 2,351,184 valid research FWI rows | [Weather audit](provincial_weather_build_audit.json) |
| Selected landscapes | FBP 2024 native area-weighted class fractions; SCANFI v1.2/2020 and MRDEM sample estimates for 9,648 cells | [Native static audit](native_static_build_audit.json), [sampled forest/terrain audit](provincial_static_build_audit.json) |
| Selected 2025 ignition panel | 1,775,232 rows, May–October; 600 positive cell-days from 624 retained recorded starts; 1,773,024 valid research FWI rows | [Panel audit](selected_2025_panel_audit.json), [source adjudication](selected_2025_fire_adjudication.csv) |
| Live HRDPS research integration | Actual October 16 00 UTC run, 144 downloaded GRIB files including prior-run rain; 231,552 hourly rows; next six hours covered at retrieval | [Live audit](hrdps_live_integration_audit.json) |
| Stateful forecast FWI | 8,526 valid research updates/checkpoint cells; 1,122 cells retain incomplete-weather status | [Live audit](hrdps_live_integration_audit.json) |
| Software and integrity | 110 passing tests; original four evaluation files and eight Week 3 bundles unchanged; 16 new bundle hashes verified | [Test output](unit_tests_final.txt), [completion integrity](completion_integrity.json) |

LightGBM now leads pooled temporal development average precision: **0.00599798**, versus histogram boosting **0.00548892** and historical rate **0.00036773**. At the illustrative 1% daily alert budget, LightGBM recalls 9.778% of positives with 0.359% precision; inner spatial recall is only 0.641%. Histogram boosting's temporal AP falls after the correction. These results support a provisional development choice, not a reliable deployed alert system. The current-boundary sensitivity has a different eligible population. Full results, paired sampling hashes and year-level metrics remain separate from the immutable v1 benchmark.

## Workflow

```text
Historical NFDB/CDEM/CWFIS benchmark (2010–2019)
    -> corrected prior-day station weather (development 2010–2017 only)
    -> fixed selectors / train-only preprocessing
    -> four candidate refits + current-boundary sensitivity
    -> saved research models -> Week 5 calibration / final evaluation

Selected modern-source study (separate data contract)
    FBP2024 native fractions + SCANFI2020/MRDEM sample estimates
                           + ERA5-Land2025 noon/rain/research FWI
                           + provincial recorded-start dates
    -> 9,648 independent current-boundary 10 km cells
    -> 1,775,232 dated rows + null/coverage flags + predictor allowlist
    -> own future evaluation design required before model fitting

Live HRDPS research path
    -> discover completed available run -> hash/cache GRIBs
    -> rotate wind / decode accumulated rain / sample grid centres
    -> exact standard-noon weather + previous state
    -> research FWI + versioned untrusted checkpoint
    -> future source-compatibility/observed-state validation gate

Separate capability: 90 m spread simulation -> corrected replay / map
```

## Source and feature decisions

The seven-source scope is retained. Ontario points supply labels; Ontario areas and VIIRS remain separate validation sources. They are not added as ignition predictors. HRDPS supplies forecast weather; ERA5 supplies retrospective weather. The selected modern panel is not backfilled into 2010–2019 or passed to historical CWFIS-trained models.

The independent current-boundary grid has 9,648 cells; the v1 benchmark retains 9,673. The missing old pinned geometry prevents exact historical-mask recovery. Current eligibility is metadata, never a predictor. The selected panel preserves provider calendar dates from epoch encoding, not inferred exact ignition times. Of 649 source 2025 instances, 624 are retained and 25 explicitly excluded: 14 outside season, five outside IFR type, three year/date conflicts and three outside the grid. Repeated fire identifiers are not automatically duplicates; unique source OBJECTIDs identify retained instances. A negative label means no IFR start recorded in this source/date/cell.

Fuel proportions were refined after a deterministic sample check found appreciable differences between 100-point samples and native-pixel counts. Final FBP shares use exact pixel/cell intersection areas within each cell's nominal source tile. Uncovered boundary strips/nodata remain in coverage metadata; six cells have zero support and null shares. Every raw code is preserved categorically; fractions are normalized over valid support. Forest and terrain remain **100 deterministic 1 km strata-centre estimates**, not full native-area means. SCANFI closure is conditional on valid closure AND species composition. Conifer share is canopy-weighted after within-pixel composition normalization; zero-canopy cells retain undefined conifer fractions. MRDEM's source EPSG:3979 is transformed explicitly, and the slope statistic is a coarse 1 km sample gradient, not native 30 m slope. See the [feature dictionary and architecture decisions](feature_dictionary_and_decisions.md).

ERA5 uses per-cell local standard noon, timezone database 2026e, reset-aware accumulated rain, and an explicit April 1 research startup (FFMC 85/DMC 6/DC 15). Missing updates invalidate subsequent state rather than becoming zero rainfall. These seeds are not observed or overwintered conditions; agreement with the existing scalar implementation is software consistency, not independent canonical/field validation. Weather for ignition date D comes from the previous standard-noon day, and seven-day rain requires seven complete values. All joined observation instants precede the declared midnight Toronto issue time. Retrospective availability cannot be reconstructed from these archives.

The live adapter discovers candidate cycles and verifies required downloads. At the measured discovery, 06 UTC was unavailable and 00 UTC was selected; that trace is preserved in `hrdps_before_checkpoint_audit.json`. The final stateful execution reuses the verified 00 UTC raw files. Its conservative availability time is after complete retrieval. HRDPS's grid-relative wind is rotated using actual GRIB metadata and geodesic grid north; cumulative precipitation is differenced only across matching accumulation starts. Missing/negative-invalid increments remain unknown. The adapter follows [ECCC's HRDPS data layout](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/) and interprets wind orientation through the [GRIB2 component flag table](https://codes.ecmwf.int/grib/format/grib2/ctables/3/3/).

FWI seeds must match the exact previous standard-noon state, have known pre-issue availability, finite valid codes and provenance. Explicit research mode permits startup constants or an untrusted research checkpoint. Forecast-derived checkpoints always remain `trusted=false`; they do not become observed state through reuse. Default operation cannot manufacture trusted state. A future observed-state bridge, ERA5/HRDPS model compatibility and meteorological validation remain acceptance gates.

## Local outputs

All paths below are relative to `/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/`.

| Artifact | Path |
| --- | --- |
| Corrected historical features | `data/processed/ignition_weather_v2_development/` |
| New model bundles | `data/processed/ignition_models_week3_v1/comparison_weather_v2/` and `comparison_weather_v2_boundary/` (historical parent-directory name retained) |
| Provincial daily weather | `data/processed/selected_provincial_2025/` |
| Final selected static features | `data/processed/selected_provincial_static_native_2025/` |
| Selected 2025 cell-day panel and contract | `data/processed/selected_2025_ignition_panel/` |
| Live research weather, FWI and state | `data/processed/hrdps_live_research_2026-10-16_stateful/` |
| Full selected SCANFI national source copies | `data/raw/scanfi_v1_2_national/` (11 pinned files; hashes in completion integrity) |

## Reproduction and verification

The `.venv`, pinned raw inputs and source snapshots are retained locally. `completion_environment.lock.txt` records the environment. From CAPSTONE, the fresh-workspace dependency order is:

```sh
.venv/bin/python -m scripts.prepare_provincial_weather
.venv/bin/python -m scripts.prepare_provincial_static
.venv/bin/python -m scripts.refine_provincial_fuel
.venv/bin/python -m scripts.build_selected_2025_panel
.venv/bin/python -m scripts.hrdps_live_weather --research-startup --output-dir data/processed/hrdps_research_new_run
.venv/bin/python -m pytest tests team_repository/tests team_repository/capability_2_fire_spread/tests -q
```

The first four default datasets already exist and refuse overwrite. These commands document fresh-workspace reproduction, not instructions to overwrite them. Repeating with alternate roots requires explicitly matching downstream module paths; only each script's output path is configurable. HRDPS output must use an unused name, current completed forecast files must still be available, and weather availability/state can cause explicit failure. `--seed-path` accepts a checkpoint only for its matching next standard-noon update; research checkpoints require research mode.

The comparison CLI accepts `--data-dir`, `--contract-path`, `--output-dir` and optional `--boundary-only`. Its full frozen settings, hashes, selectors and fitted-sample provenance are in each comparison directory. Original calibration/final-test Parquet contents remain unopened by these pipelines; hash-only integrity checks were performed. Earlier broad 2019 EDA exposure remains disclosed, so the holdout is not claimed pristine.

Review used an implementer pass, focused regression tests and automated code-quality scans. Long orchestration functions/complexity remain maintenance debt; independent review or scientific sign-off is not claimed. Full raw datasets and large prediction Parquets stay local outside the compact completion ZIP. The original increment ZIP remains an earlier snapshot. The completion manifest inventories the new package and local dataset manifests.

## Week 5 acceptance work

Calibrate the selected historical development model under a frozen corrected-source policy, then perform reserved final evaluation and explanations/map integration. The selected 2025 panel is intentionally `training_ready=false`: it requires its own frozen evaluation design and enough independent data before fitting. Validate forecast-source compatibility and trusted observed FWI state before live ignition inference. Restore missing raw spread windows for a corrected full replay and integrate the separately evaluated capabilities. Native Microsoft Project verification remains deferred by the user. No Git merge/push, submission, operational acceptance or independent team/professor approval is claimed.
