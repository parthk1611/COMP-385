# Ontario Wildfire Prediction — Weeks 1–5 development checklist

Reviewed: October 16, 2026. Development tasks only, based on the supplied course pages and current local project files. Week 1/2 group Module 1/2 activities; Weeks 3–5 follow the previously supplied weekly guidance. Week labels organize the work rather than establish deadlines.

Updated against all eight repository branches: [repository review and file-by-file cross-reference](repository_review_2026-10-14/README.md). The user has now selected **10 km ignition cells**. The [Week 1 development plan](../team_repository/docs/week_1_development_plan.md) records the initial historical benchmark and local process. The earlier 2.5 km pilot remains preserved as reference. The seven-source scope has not been silently substituted into the historical baseline.

## Status key

- `[x] DONE`: a local artifact or implemented output supports the item.
- `[ ] PARTIAL`: some work exists; the item is not complete.
- `[ ] NEXT`: required work remains.
- `[ ] VERIFY`: completion cannot be established from the inspected files.
- `[ ] DEFERRED BY USER`: deliberately set aside, without claiming completion.

“Partial” describes the state of the work, not a process running in the background.

## Overview

| Week | Main purpose | Current position |
| --- | --- | --- |
| 1 | Define the problem, scope and development approach | Complete locally: 10 km decision, initial historical contract, workflow, iterative increments and persistent repository are documented. |
| 2 | Research, inspect data, plan and specify requirements | Development deliverables complete locally, including extended DPV/C2FK full-text review. Microsoft Project verification is deferred by the user. Week 4 now adds the executed provincial preparation and live research adapter; operational acceptance remains separate. |
| 3 | Design the AI capability | Complete locally: four fitted candidates across temporal/inner-spatial development validation, component diagrams, schemas, traceability, six ADRs and restricted spread review. No operational acceptance. |
| 4 | Prepare data and review architecture | Local development scope complete: corrected-weather refits, native-fuel/forest/terrain and ERA5 provincial join, source adjudication, live HRDPS research FWI/checkpoints and architecture records. Operational readiness is not claimed. |
| 5 | Code, test and demonstrate a prototype | 110 tests pass; corrected-weather development candidates and research adapters exist. Calibration, final evaluation, explanations/map, source-compatible live ignition inference and corrected spread replay remain. |

## Week 1 — Define the development scope

- [x] DONE — Document the development problem and separate daily ignition-risk and 1-/3-/6-hour spread capabilities. The first ignition benchmark uses calendar-day recorded starts; operational rolling-24-hour validation is later work.
- [x] DONE — Describe the proposed input/output workflow in project notes.
- [x] DONE — Document the iterative/incremental process, two AI iterations, overlapping application work and explicit software-architecture review milestone in the [Week 1 plan](../team_repository/docs/week_1_development_plan.md).
- [x] DONE — Record the user-selected 10 km grid and the initial historical contract: existing Ontario Fire Region panel, 2010–2019 fire seasons, midnight America/Toronto issue time, recorded calendar-day target and NFDB/CDEM/CWFIS baseline provenance.
- [x] DONE — Store a permanent local repository checkout with all eight remote branches available, independently of the temporary review mirror.
- [x] DONE — Verify source-controlled project code in [COMP-385](https://github.com/parthk1611/COMP-385). All eight remote branches were inventoried and fetched locally; no remote branches were merged or pushed. The local planning branch holds the Week 1 documentation.

Week 1 development documentation is complete locally. Later source compatibility, architecture review, model training and code fixes remain open below; Week 2 requirements and bounded audits now have local artifacts.

## Week 2 — Research, data, requirements and plan

- [x] DONE — Document the seven-source contract: Ontario fire points/areas, VIIRS, ERA5-Land, HRDPS, FBP 2024, selected SCANFI 2020 and MRDEM.
- [x] DONE — Produce static-data EDA, plots, a data dictionary and the original 432-cell feature pilot.
- [x] DONE — Complete the Week 2 source investigation and representative-data EDA for all seven groups, with units/time/CRS, missingness, distributions, source suitability, measured storage and remaining acquisition coverage recorded in the [audit](week_2_development_2026-10-15/data_readiness.md). Full provincial point/area files and 20 raw VIIRS sensor-years are restored with exact pinned hashes. All 11 CDS pilot files, selected SCANFI, fuel/terrain samples and five HRDPS sample files have bounded profiles.
- [x] DONE — Restore the pinned CWFIS archive and reconstruct the existing 17,798,320-row label panel, then rerun the unmodified full 48-column feature builder locally. The [fresh audit](week_2_development_2026-10-15/historical_feature_rebuild_audit.json) reproduces v1 coverage and reports zero prior-day weather-date violations; known station-selection/mask limitations remain open.
- [x] DONE — Cross-reference retained NFDB events with provincial points/areas and record source decisions. All 8,109 NFDB rows have identifier/year candidates; 8,107 have a unique matching date/cell and two remain explicitly flagged. Preserve the baseline rather than silently replacing labels. Raw geometry/date/identity issues and the changed boundary format are documented in the [decision handoff](week_2_development_2026-10-15/data_decisions.md).
- [x] DONE — Verify repository ignition EDA artifacts and the 65,655-row Ontario point EDA/column-cleaning output. The earlier full-panel EDA scan remains recorded evidence. A fresh normalized provincial point audit now preserves date/identity quality flags; it is not a replacement label release.
- [x] DONE — Complete the local literature-review attachment using two original peer-reviewed studies (Cell2Fire 2021 and Kim 2025), synthesis and explicit comparison with our project, with additional ignition/benchmark research and references. See the [research and tool review](research_review_2026-10-14/README.md). Eight journal/main-conference papers, one workshop paper and one technical report are identified across the slide; seven accessible paper PDFs are saved locally. This does not claim all texts were fully accessible or results reproduced.
- [x] DONE — Complete the extended slide review: DPV and C2FK full publisher HTML was accessed through Centennial Library and methods, numerical results and limits critically reviewed. The [review](research_review_2026-10-14/README.md) records future uses and separates reported simulator comparisons from field validation. “Burn-probability maps” is resolved as a method/output supported by Cell2Fire and C2FK §2.6, not an invented extra paper.
- [x] DONE — Prepare a [21-task dated schedule](week_2_development_2026-10-15/development_schedule.md) with CSV and XML import files, dependencies, two AI iterations and overlapping application work. The dependency/duration plan and XML consistency checks are complete. Dates remain provisional by user request; December 16 is not a claimed course deadline.
- [ ] DEFERRED BY USER — Native Microsoft Project import/use verification is set aside. The XML/CSV plan is prepared; no native application verification is claimed.
- [x] DONE — Document the [ASCII use-case diagram and four detailed AI templates](week_2_development_2026-10-15/use_cases.md), with actors, goals, triggers, actor/system steps, exceptions, priority, channel and requirement links. This completes the documentation, not its implementation.
- [x] DONE — Document [SRS v1](week_2_development_2026-10-15/system_requirements.md): 16 functional and 12 measurable non-functional requirements, priorities, acceptance criteria and traceability. Performance targets are proposed engineering criteria, not tested outcomes.
- [x] DONE — Freeze [temporal/geographic evaluation selectors](week_2_development_2026-10-15/evaluation_plan.md) and source/selector hashes before new training. Dates reserve 2010–2015 training, 2016–2017 validation, 2018 calibration and 2019 final testing; the separate spatial experiment reserves 1,387 cells, 7,767 development cells and 519 buffer cells. Earlier 2019 EDA exposure is disclosed. Four full-panel temporal Parquet partitions are now materialized with spatial roles, metadata checks and hashes. Final-test data is isolated/read-only. The explicit 36/31-predictor candidate allowlists exclude labels and metadata. Week 3 now enforces those rules in a fitted development comparison; Week 4 now adds the separately contracted selected-source research integration below.

Week 2 development deliverables are complete locally: source investigation/EDA, source-quality decisions, literature review, requirements/use cases, development dependencies and evaluation reservation. Microsoft Project verification is deferred by explicit user instruction. The previous checklist mixed final training/live readiness into Week 2. Week 4 now completes the transformation/join and research forecast-adapter implementation; its unmet model/operational acceptance criteria remain explicitly listed under Week 5.

## Week 3 — Design the AI capability

- [x] DONE — Explain predictive analytics and distinguish 10 km ignition classification from 90 m incident spread. Identify external data, frameworks and the absence of LLM/paid AI API dependencies in the [technical design](week_3_design_2026-10-15/technical_design.md).
- [x] DONE — Provide separate ASCII training, daily scoring and spread workflows, component interactions and implemented/materialized/planned module states.
- [x] DONE — Reconcile LightGBM with historical-rate, logistic and histogram-boosting candidates. Fit all four on a common weighted sample under temporal and inner blocked-geographic protocols; evaluate full natural-prevalence validation. Report costs, settings, missingness, per-year results, alert performance and limits in the [experiment report](week_3_design_2026-10-15/experiment_report.md). Histogram boosting is provisional for temporal research only; geographic/operational promotion is unsupported.
- [x] DONE — Map the slide's research/tools to present methods and optional future work in the [research review](research_review_2026-10-14/README.md#tool-assessment-and-future-integration). No external engine integration or transferred validation claim.
- [x] DONE — Complete the [critical spread design review](week_3_design_2026-10-15/spread_design_review.md): distinguish FBP-inspired subset and graph propagation from canonical tools; expose weather/domain/outcome assistance. Restricted reconstruction is accepted; operational forecasting is rejected. Barrier, corner and empty-active defects are fixed with regression evidence. Corrected full replay remains Week 5 validation work because raw windows are missing.
- [x] DONE — Define five exchanged JSON contracts, fixtures, timestamp/unit/failure rules and FR-01–16/NFR-01–12 design links. Four interface tests pass; schemas are design artifacts, not deployed endpoints.
- [x] DONE — Finalize evaluation isolation, source/selector/config/model hashes, dependency lock, seed, sampling, overwrite guards and repeatability/save-load evidence. Calibration/final-test content stays unopened by fitting/scoring.
- [x] DONE — Record six [architecture decisions](week_3_design_2026-10-15/decisions.md), pre-implementation constraints, alternatives, version/review rules and limitations. Align the report and modules; package the PDF, editable documents and source evidence in the [Week 3 package](week_3_design_2026-10-15/README.md).

Week 3 technical design and bounded development experiments are complete locally. Independent team/professor sign-off, operational validation and later application implementation are not claimed. [Validation review](week_3_design_2026-10-15/validation_review.md) records 71 passing tests and retained maintainability/scientific limits.

## Week 4 — Prepare data, select tools and review software architecture

- [x] DONE — Preserve the original Thunder Bay selected-static/weather pilot and its dated source/quality evidence as a small reference experiment.
- [x] DONE — Verify and transform all 11 pinned provincial Jan–Nov 2025 ERA5-Land files. The executed converter produces 3,222,432 daily records across 9,648 cells, with standard-noon mapping, reset-aware rain, RH/wind, explicit research FWI startup and missing-state invalidation. [Audit](week_4_data_2026-10-16/provincial_weather_build_audit.json).
- [x] DONE — Build corrected historical weather and strict development joins for 14,238,656 unchanged 2010–2017 keys/labels. Missingness falls from 54.0506% to 11.4542%; 100/200/300 km coverage sensitivity and the fixed 200 km development method are recorded.
- [x] DONE — Construct the outcome-independent current-boundary 9,648-cell scenario, record its intersection with v1 and keep eligibility out of predictors. The original geometry remains unavailable; no exact historical-mask recovery is claimed.
- [x] DONE — Refit all four candidates under temporal and inner spatial protocols on corrected weather and on the current-boundary scenario: 16 saved bundles with parity/hashes. Accept corrected v2 for development; retain v1 and the boundary sensitivity separately. LightGBM leads pooled temporal v2 AP, with weak absolute precision/spatial transfer. Radius model optimality is not claimed. [Comparison](week_4_data_2026-10-16/model_comparison_update.md).
- [x] DONE — Acquire/cache the exact selected 11 national SCANFI v1.2/2020 files with identity and hashes, transform their custom CRS explicitly, and build forest features plus MRDEM terrain estimates at 100 deterministic strata centres per cell. Closure is conditional on joint composition validity; slope is a coarse 1 km estimate.
- [x] DONE — Refine FBP 2024 to native-pixel intersection-area categorical shares after sample QA showed discrepancies. Preserve every raw code, partial source support and six unsupported-cell nulls. Final fuel shares are not the earlier coarse estimates. [Audit](week_4_data_2026-10-16/native_static_build_audit.json).
- [x] DONE — Adjudicate 649 provincial 2025 start instances using unique OBJECTIDs, provider calendar dates, IFR type, season and fixed grid: retain 624 records and explicitly exclude 25. Do not silently replace NFDB benchmark labels. [Ledger](week_4_data_2026-10-16/selected_2025_fire_adjudication.csv).
- [x] DONE — Join selected provincial weather/landscapes/labels into 1,775,232 cell-days, with 600 positive cell-days, 1,773,024 valid research FWI rows, null/coverage flags and a frozen predictor allowlist. All weather instants precede issue time. Areas/VIIRS are validation only; no fire outcomes enter predictors. The one-year selected panel has no trained model/evaluation acceptance yet. [Audit](week_4_data_2026-10-16/selected_2025_panel_audit.json).
- [x] DONE — Implement and execute the live HRDPS research adapter: completed-run discovery, actual download/hash validation, rotated wind, interval-aware accumulated rain and conservative availability. The final measured run has 231,552 hourly rows and six future hours covered at retrieval.
- [x] DONE — Implement exact-date/noon/availability/provenance FWI seed checks and reusable forecast-state checkpoints. The actual run yields 8,526 valid research updates and 1,122 incomplete-weather cells. Forecast-derived checkpoints remain untrusted; no observed/overwintered operational state is claimed. [Audit](week_4_data_2026-10-16/hrdps_live_integration_audit.json).
- [x] DONE — Preserve training-only imputation/scaling, native tree missingness, explicit categorical shares, separate historical/modern/live source contracts and reserved-role guards. Never apply CWFIS models automatically to ERA5/HRDPS features.
- [x] DONE — Complete framework/tool comparison and actual sklearn/LightGBM compatibility experiments. External spread engines remain optional research alternatives, not required integrations; no unperformed runtime trial is claimed.
- [x] DONE — Complete architecture review/documentation, including the Week 3 pre-implementation decisions, Week 4 original review and measured revised-source decisions, feature dictionary, failure rules and next acceptance gates. Independent review/professor feedback remain unverified.
- [x] DONE — Run the full combined suite: **110 passed**; verify original four partitions/eight models unchanged and all 16 new model hashes. Package code, tests, audits, contracts, source snapshots and environment. [Completion package](week_4_data_2026-10-16/README.md).

Week 4 local data-preparation and research-integration development is complete. This does **not** turn research state or a one-year panel into an operational forecasting system. The earlier broad “full selected-source training/live readiness” item mixed preparation with application/scientific acceptance; its implemented transformations are checked above, while its unmet acceptance criteria are explicitly retained under Week 5 below. The selected panel remains `training_ready=false` pending its own evaluation protocol. No raw source was silently substituted into the historical benchmark.

## Week 5 — Code, test and demonstrate

- [x] DONE — Implement static-data acquisition/analysis, dated-label/static-feature construction and ERA5 request/download scripts.
- [x] DONE — Rerun the combined local and repository suites: **110 tests passed**, including weather, source/label joins, native categorical areas, forecast seed/checkpoint guards, model contracts, interfaces and spread regressions. Module tests do not establish scientific/application acceptance. [Output](week_4_data_2026-10-16/unit_tests_final.txt).
- [x] DONE — Historical and selected-source preparation modules, corrected-weather development comparisons and the live HRDPS research weather/FWI adapter are implemented and tested. Their distinct source/timing contracts remain enforced.
- [x] DONE — Fit historical-rate, logistic, histogram and LightGBM candidates on the fixed v1 training sample, with common temporal/inner blocked validation and saved bundles. These are uncalibrated development models; the executed Week 4 source/mask revision now has its separate development experiment.
- [ ] PARTIAL — Development AP, ROC-AUC, recall, precision, false alerts, Brier/log loss and year-level results are measured. Fit calibration, perform frozen final evaluation and add model explanations before prototype acceptance.
- [ ] PARTIAL — Eight original and sixteen new development bundles pass save/load parity; validation scoring is recorded separately. A calibrated selected model, keyed app scoring and simple historical risk map remain unfinished.
- [x] DONE — Verify the implemented historical spread simulator, saved replay results and static viewer. Holdout aggregates were recomputed from 150 steps across 22 fires.
- [ ] PARTIAL — Water/diagonal barriers and empty active masks are fixed and regression-tested; repair defaults off, reconstruction mode is explicit and outputs are revision-separated. Restore missing raw landscape windows and rerun corrected real-fire replay. Archived v1 overall skill does not beat even growth; no 1-/3-hour validation exists.
- [ ] PARTIAL — Run integrated historical prediction/map and spread checks. After restoring the exact pinned raw area source, the full dataset validator completed all 18 structural checks and its source sanity summaries. The current 27-test spread run passes. Full replay rebuilding, ignition map integration and live integration remain unverified.
- [x] DONE — Record a branch/file development review and concrete findings.
- [ ] PARTIAL — Implemented scoped spread fixes and a guarded model-comparison pipeline; 110 combined tests pass. Independent review, corrected full replay and integrated prototype verification remain open.

- [ ] NEXT — Freeze the selected 2025 panel's own evaluation protocol before fitting a compatible model; acquire additional independent data if its one-year support is insufficient. Its construction does not constitute an evaluated model.
- [ ] NEXT — Validate ERA5/HRDPS feature-source compatibility and an observed/overwintered FWI state bridge before live ignition inference. Research checkpoints and startup constants cannot satisfy this operational gate.

The HRDPS weather/FWI research adapter is executed; calibrated live ignition scoring and full application integration remain open. A historical prototype can precede live deployment. Keep spread as a separate evaluated capability.

## Immediate order of work

```text
Completed: 10 km contract -> research / SRS / frozen selectors
    -> architecture -> corrected historical weather + model comparisons
    -> provincial selected-source join + live research weather/FWI adapter
                                  |
                                  v
Week 5: freeze calibration/alert choices -> calibrate -> final evaluation
    -> explanations / keyed scoring / historical map -> integrated demo

Parallel acceptance gates:
  selected 2025 panel -> own frozen evaluation -> compatible model
  live weather -> trusted observed state + source parity -> live ignition
  spread fixes -> restore raw windows -> corrected replay -> viewer
```

## Evidence and boundaries

- [Project context](</Users/parthkevadiya/Documents/ChatGPT/AI CAPSTONE/context.md>) and [architecture notes](</Users/parthkevadiya/Documents/ChatGPT/AI CAPSTONE/architecture.md>): scope, design and existing course mapping.
- [Static EDA](ontario_static_eda.md), [data dictionary](data_dictionary.md), [pilot report](ignition_pilot.md), [pilot summary](../data/processed/ignition_pilot_summary.json), scripts and tests: local technical evidence.
- [ERA5 download manifest](../data/raw/ignition_pilot/era5/download_manifest.json): all 11 listed files exist and match their checksums.
- Older reports and the pilot summary still say no weather was downloaded. That acquisition claim is stale; their weather-feature/FWI status is also partly superseded by the new converter; their missing-model/full-join claims are also superseded by the separate historical experiments and provincial panel.
- The original pilot remains a small reference. A complete selected 2025 provincial join now exists separately, with `training_ready=false` because its own evaluation design/model acceptance is unfinished. Historical v1/v2 development models use different contracts.
- [All-branch review](repository_review_2026-10-14/README.md) supersedes earlier claims that the team has no spread simulator or no historical ignition feature pipeline. Those claims described the local pilot only.
- [Research and tool review](research_review_2026-10-14/README.md) supersedes the earlier global research count of one. It contains the two-paper synthesis, all eleven slide entries, reference links, seven local paper PDFs, tool source snapshots and full-text access provenance and explicit unperformed runtime trials.
- [October 15 Week 2 package](week_2_development_2026-10-15/README.md) adds fresh measured audits, HRDPS sample provenance, requirements/use cases, frozen evaluation selectors and the provisional schedule. Fresh source restorations and validation are now linked there. The extended DPV/C2FK full-text review and tested pilot weather derivations are now added. That historical Week 2 snapshot did not contain fitted models or simulator fixes; Week 3 now adds them. Native Project import remains deferred; Week 4 adds executed selected-source and research forecast integration.
- Checked items reflect the inspected technical evidence; no overall completion percentage is inferred.

- [October 16 Week 4 completion](week_4_data_2026-10-16/README.md): corrected-weather refits, provincial weather/native fuel/forest/terrain/label join, live HRDPS research adapter/checkpoints, 110 tests and integrity evidence. Original benchmark artifacts remain unchanged. Model improvements are mixed; operational acceptance is still open.
