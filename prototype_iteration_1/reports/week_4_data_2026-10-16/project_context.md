# Ontario Wildfire Prediction — Project Context

## Current Week 4 completion — October 16, 2026

The [completed local Week 4 package](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_4_data_2026-10-16/README.md) adds corrected historical-weather refits (16 new bundles across four candidates/two protocols/two grid scenarios), the selected 2025 provincial panel and executed HRDPS research weather/FWI integration. LightGBM leads pooled v2 temporal AP at 0.00599798; spatial transfer and absolute alert precision remain weak. The original v1 results, four evaluation partitions and eight model bundles are unchanged. Calibration/final-test Parquet content remains unopened by these pipelines; earlier 2019 EDA exposure is disclosed.

The separate selected panel contains 1,775,232 May–October 2025 cell-days over 9,648 independent current-boundary 10 km cells, 600 positive cell-days from 624 retained source instances, native FBP2024 area-weighted categorical shares, SCANFI v1.2/2020 and MRDEM 100-point estimates, and prior-standard-noon ERA5 weather/research FWI. Twenty-five source instances are explicitly excluded. Six fuel cells and twelve weather cells lack support; nulls remain. Closure is conditional on joint species validity; terrain slope is a coarse 1 km sample gradient. This one-year fixed-landscape panel requires its own evaluation design (`training_ready=false`), and is not backfilled into the historical benchmark.

The actual HRDPS October 16 00 UTC run supplies 231,552 hourly records, with six future hours covered at retrieval. The stateful research FWI output/checkpoint has 8,526 valid cells and 1,122 incomplete-weather cells. Forecast-derived checkpoint states always remain untrusted. Available-run selection, rotated wind, accumulated-rain decoding, seed date/noon/availability and provenance guards are implemented. No CWFIS model was applied to incompatible forecast features; observed/overwintered FWI state and live source compatibility remain Week 5 acceptance gates.

All 110 combined tests pass. Week 4 local development is complete, with updated source/feature decisions and compact reproducible evidence. Week 5 still requires frozen calibration/final evaluation, explanations/map, selected-panel evaluation/live compatibility and corrected spread replay. Independent reviewer/professor approval and operational acceptance are not claimed. The 10 km ignition / separate 90 m spread and seven-source scope remain fixed. Earlier dated sections below are historical snapshots.

## Current Week 3 update - October 16, 2026

The [Week 3 design package](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_3_design_2026-10-15/README.md) completes local technical design, component diagrams/contracts, requirements traceability, six architecture decisions and restricted spread review. Four ignition candidates are fitted under common temporal/inner-geographic development protocols. Histogram boosting is the provisional pooled temporal AP candidate (0.005764 versus historical-rate 0.000368), but geographic transfer and absolute alert precision remain weak. The models are uncalibrated research artifacts; 2018 calibration and 2019 final-test content remain unopened by the pipeline. Source station/mask limitations are retained and disclosed.

Scoped spread barrier/corner/empty-active defects are fixed, repair defaults off and reconstruction drivers declare their mode/revision. Archived scores/viewer still describe old code; missing raw landscape windows prevent corrected full replay. The complete suite passes 71 tests. No independent reviewer sign-off, live adapter, calibrated final model, SHAP/map, Git merge/push or operational acceptance is claimed. Full selected-source preparation remains Week 4 and prototype integration remains Week 5. The dated historical sections below remain snapshots; this update supersedes their no-model/no-fix status.


## Project

- Course: COMP 385 AI Capstone
- Project: Ontario Wildfire Prediction
- Start date: September 28, 2026
- Study area: Ontario, with particular attention to northern Ontario and the provincial fire region

## Objective

Build an explainable research system for daily wildfire ignition risk in **10 km Ontario grid cells**, selected by the user on October 14, 2026. The first historical benchmark retains the repository's local-calendar-day target and 2010–2019 Fire Region panel. An operational rolling-next-24-hour claim remains later work; date-only labels and retrospective archives do not establish it. The seven-source development scope remains recorded below, while the implemented historical baseline uses NFDB, CDEM and CWFIS. Fire-spread simulation is a separate capability with an implemented historical prototype and requested 1-, 3-, and 6-hour outputs whose validation remains limited.

The primary output will be a daily risk map. Each grid cell will receive:

- an ignition probability from 0 to 100%;
- a risk category such as low, moderate, high, or extreme;
- the main factors contributing to the prediction;
- a confidence or uncertainty indicator.

## Primary AI Model

Four candidate families are fitted and saved: historical fire rate, logistic regression, histogram gradient boosting and LightGBM. LightGBM is provisional under corrected-weather pooled temporal development AP; histogram boosting led the earlier v1 experiment. These are uncalibrated research models with explicit source contracts and weak spatial transfer; final evaluation and operational acceptance remain open.

### Unit of analysis

One row represents one **10 km** Ontario grid cell on one local calendar day. The existing repository benchmark has 9,673 cells and 1,840 May–October dates across 2010–2019, with a 00:00 America/Toronto issue time. The older 2.5 km Thunder Bay pilot is retained as experimental reference. HRDPS's nominal 2.5 km weather resolution is an input resolution, not the selected prediction-cell size; any future 10 km aggregation needs an explicit variable/unit/time contract.

### Target (`y`)

`y` is the historical outcome the model must learn to predict:

```text
ignition = 1  if at least one selected fire start is recorded in the cell on the target local date
ignition = 0  if none is recorded in the selected archive for that cell and date
```

### Features (`X`)

The active historical baseline uses calendar/solar, CDEM terrain, prior-day CWFIS weather/FWI and past-only NFDB ignition history with quality flags. Its 48-column contract is in the local repository. The following landscape/weather families describe the selected-source development scope; they are not all present in that baseline and require eligible vintages and pre-issue inputs:

- temperature, relative humidity, wind, and precipitation;
- FWI, FFMC, DMC, DC, ISI, and BUI;
- dominant fuel category and fuel-group shares, retaining water separately;
- canopy closure, percent conifer, and optional canopy height;
- elevation, slope, and aspect;
- month, day of year, days since rain, recent rainfall totals, and lagged weather.

Fire cause, final size, out date, and final perimeter are outcome/filtering/evaluation fields, not contemporaneous ignition predictors. FIRMS VIIRS is reserved for spread validation. Do not use the fire-record `FIRE_WEATHER_INDEX` or `FIRE_RESPONSE_OBJ_CODE` as ignition predictors; independently computed pre-cutoff FWI is permitted.

Example:

```python
X = data[feature_columns]  # Explicit reviewed predictor list; exclude label metadata.
y = data["ignition"]

model.fit(X, y)
```

## Model Evaluation

Wildfire starts are rare, so ordinary accuracy is not sufficient. Evaluate the model using:

- precision-recall area under the curve;
- recall of actual fires;
- precision of high-risk alerts;
- false alarms per 1,000 grid cells;
- probability calibration;
- performance by year, region, cause, and fire size.

Training and validation must be separated by both time and geography. Do not randomly mix neighbouring cells or records from the same fire between training and test sets. Reserve the latest complete fire year for final testing and use only information that would have been available at prediction time.

Use class weighting or controlled negative sampling to address the large imbalance between fire and non-fire examples. Use SHAP values to explain individual predictions and global feature importance.

## Spread capability

The repository now contains a separate 90 m Canadian-FBP-inspired simulator, historical spread dataset, EDA, saved replay scores and static viewer. Choosing 10 km for ignition does not change the spread grid. The all-branch review found a one-cell water-barrier crossing defect and final-perimeter-assisted fuel reconstruction; fixes and outcome-independent evaluation remain open. The saved overall replay scores do not beat even growth. Historical observations do not establish 1-/3-hour forecast accuracy, and live HRDPS integration remains unimplemented. See the [repository review](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/repository_review_2026-10-14/README.md).

## Team-selected data sources — 2026-10-09

The team uses these seven source groups; the Ontario point and area layers count as one source:

1. Ontario Fire Disturbance Point + Fire Disturbance Area: ignition labels, cause/filtering fields, location quality, and final outcomes for evaluation.
2. NASA FIRMS VIIRS 375 m: timestamped hotspot observations for spread validation only.
3. ERA5-Land hourly: historical temperature, dewpoint, wind components, and precipitation; derive RH, wind, rainfall summaries, and FWI codes.
4. HRDPS 2.5 km: live surface weather and wind; derive compatible model features and forecast FWI from maintained moisture-code state.
5. FBP Fuel Types 2024, 30 m: categorical fuel inputs for classification and simulation.
6. SCANFI, 2020 reference, using the team's linked product: canopy closure, percent conifer, and optional height.
7. MRDEM 30 m DTM: elevation, derived slope, and circular aspect.

The detailed field contract, exclusions, source links, and unresolved checks are in [the data dictionary](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/data_dictionary.md#team-source-contract--2026-10-09). This list replaces the earlier 18-source research wishlist. Separate lightning, road/access, and FWI datasets are outside this selected scope. Existing extra downloads remain historical EDA material.

For every dataset, record:

- provider and official source URL;
- licence and attribution requirements;
- years covered and latest update;
- spatial and temporal resolution;
- file format and coordinate reference system;
- important fields and units;
- missing-data and quality limitations;
- approximate download size;
- acquisition method and required credentials;
- how the dataset will be aligned to the modelling grid.

## Data Engineering Requirements

- Preserve original downloads in a read-only raw-data layer.
- Store source metadata and checksums with every download.
- Convert dates to UTC while retaining the original timezone information.
- Use a consistent Ontario modelling grid and coordinate reference system.
- Keep fire ignition points separate from final fire perimeters.
- Link datasets only through verified identifiers or documented spatial-temporal matching rules.
- Record missing weather values and satellite observation gaps explicitly.
- Avoid treating FIRMS hotspots as confirmed ignition points without validation.
- Maintain FWI moisture-code history, initialization, fire-season rules, and the chosen algorithm version. Use noon local standard time and noon-to-noon precipitation; do not use same-day observed noon weather before a morning prediction cutoff.
- Bridge the historical/live weather availability gap explicitly. Validate ERA5-Land-to-HRDPS feature consistency, forecast issue times, precipitation accumulation conventions, and retained forecast history before live deployment.

## Initial Deliverables

1. Dataset inventory and data dictionary for the seven selected source groups.
2. Reproducible download scripts for public APIs and archives.
3. Ontario fire-point profile containing annual counts and field completeness.
4. A modelling table with one row per grid-cell day.
5. An evaluated ignition baseline and agreed boosting candidate; LightGBM remains one candidate.
6. A spatial and temporal validation report.
7. An interactive Ontario risk map with SHAP explanations.
8. A separately evaluated 1-, 3-, and 6-hour spread simulator with observation-coverage limits reported.

## Current Status — October 14, 2026

The active ignition grid is **10 km**. The first benchmark follows the established historical repository contract; the seven-source development scope is not silently substituted into earlier years.

The repository is stored permanently at [team_repository](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/team_repository), on local branch `codex/week-one-plan`, with all eight remote branches available. No remote branches were merged or pushed. The [Week 1 development plan](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/team_repository/docs/week_1_development_plan.md) records the working contract and iterative increments. It completes Week 1 technical planning, not later architecture, data or model work.

The original static EDA and 30,816-cell-day Thunder Bay pilot remain preserved. All 11 local CDS ERA5-Land files exist and matched their saved checksums during the October 14 review; older no-download statements are stale. Local weather/FWI joins are still incomplete. The repository historical ignition feature pipeline and separate spread capability are implemented, but the full generated ignition feature file/raw replay inputs are not included by a normal clone. The all-branch review documents 26 passing unit tests, 18 spread structural checks followed by an incomplete source sanity check due to an absent ignored raw file, recomputed saved replay scores, and outstanding correctness/design issues.

Next work: historical input/coverage and label-grid review, explicit temporal/spatial evaluation design, formal software-architecture review before implementation changes, ignition baselines, spread corrections/re-evaluation, then historical map integration and a separately validated live-weather bridge. Use the [development checklist](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_1_to_5_checklist.md) for current status.

## Research review — October 14, 2026

The user's “Ten papers form one pipeline” slide has eleven entries: seven journal papers, one main-conference paper, one workshop paper, one government technical report, and the generic output “burn-probability maps.” Several entries describe both a paper and a tool/dataset. C2FK's developer-linked journal article is from 2026. The earlier one-paper count was incomplete for this research list.

The [local research and tool review](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/research_review_2026-10-14/README.md) now provides two original peer-reviewed studies (Cell2Fire 2021 and Kim 2025), synthesis, comparison with our project, additional ignition/benchmark research, references and future tool assessments. Seven accessible paper PDFs and pinned tool documentation/source snapshots are stored alongside it. The Week 2 minimum literature-review item is complete locally. Full publisher HTML for DPV and C2FK has now been read through Centennial Library; methods, numerical results, validation limits and future uses are documented. DPV HTML is archived locally; no local C2FK publisher PDF is claimed. The extended slide review is complete, with burn-probability maps resolved as a method/output supported by the identified papers. Prometheus report sections were read in the browser, but its PDF was not archived locally.

Research does not change the 10 km ignition decision, the separate 90 m spread grid or the selected seven-source scope. Simulator agreement and final-scar calibration are not independent forecast validation. PyTorchFire requires an Ontario input adapter and real observation-target trainer logic; inspected BaseTrainer methods are templates. JaxWildfire's public repository does not yet contain simulator code. WildfireSpreadTS developer notes document a loader fix and an unresolved angle-encoding issue. No external engine was installed, benchmarked or integrated by this review; those trials and architecture acceptance remain open.

## Week 2 continuation — October 15, 2026

The [Week 2 package](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_2_development_2026-10-15/README.md) adds SRS v1 (16 functional/12 non-functional requirements), an ASCII use-case diagram and four detailed AI use cases. These are documented acceptance targets; they do not establish implemented or tested app behaviour.

Fresh data audits cover all 11 CDS NetCDF files (8,016 continuous unique hours across January–November 2025, five variables, no missing pilot samples), selected SCANFI v1.2/2020 composition, fuel/terrain samples, 65,655 provincial point records and 300,601 processed matched VIIRS detections. Five public HRDPS surface files for one run/lead were downloaded, hashed and decoded; this is a late-retrieved sample, not an available-at-issue forecast replay or a live adapter. The full provincial point/area files, 20 VIIRS sensor-years and pinned CWFIS archive have since been restored locally. Fire matching yields 8,107 unique date/cell correspondences plus two flagged conflicts among 8,109 retained NFDB rows. The unchanged 17,798,320-row label panel and 48-column v1 feature panel were rebuilt; 52.482010% weather missingness and zero prior-day observation violations were reproduced. This is reproduction, not a fix of the station-candidate/mask issues. The selected ERA5 pilot rain/RH/wind/FWI converter is now implemented and tested: 18,704 daily weather records, including 13,664 valid FWI records under an explicit April 1 research startup and fixed UTC-5 noon. No ignition join, operational state or province-wide preparation is claimed. Full eligible enrichment remains unfinished under Week 4.

Local evaluation selectors are frozen: training 2010–2015, validation 2016–2017, calibration 2018 and final test 2019. An independent hash-based 100 km block experiment reserves 1,387 test cells, 7,767 development cells and 519 buffer cells with a 20 km minimum centre separation. Strict spatial fitting omits fire_history_* predictors. Existing descriptive EDA included 2019, so it is not described as a pristine holdout. The reconstructed full v1 panel has now been physically exported into training (10,678,992 rows), validation (3,559,664), calibration (1,779,832) and final-test (1,779,832) Parquet files, each carrying the frozen spatial role. Final-test output is read-only, and source/selector/output hashes plus explicit 36/31-predictor candidate lists are recorded. No training pipeline has yet enforced those rules or fitted a model.

A provisional 21-task CSV/XML development schedule includes two AI iterations and overlapping app/spread work. The user requested completion without focusing on dates, so calendar placeholders are not a blocker. Native Microsoft Project verification is explicitly deferred by the user; no official deadline is inferred. Week 2 development research, EDA/source decisions, requirements/use cases, schedule preparation and physical evaluation reservation are complete locally. The broad unfinished source-integration row is retained under Week 4, matching the course data-preparation milestone; it was not marked done. A new bounded weather converter and ten tests were added locally, with 53 combined tests passing. No simulator fix, Git merge/push or model training occurred.

Coverage follow-up: 145 existing FBP2024 and 145 MRDEM tiles cover all 9,673 grid centres, with 9,654 valid fuel and 9,673 valid terrain centre probes; these are not whole-cell aggregates. January 2025 provincial ERA5 is downloaded/profiled: 744 hourly steps, 166 x 221 source points, all five variables. All model centres lie inside the box, but 12 are masked at the first-hour temperature probe. Additional months are not counted until locally manifested. Selected SCANFI remains v1.2/2020; broader v2/2025 material was not substituted.
