# Ontario Wildfire Prediction: architecture and EDA

## Current Week 4 completion — October 16, 2026

The [completed local Week 4 package](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_4_data_2026-10-16/README.md) adds corrected historical-weather refits (16 new bundles across four candidates/two protocols/two grid scenarios), the selected 2025 provincial panel and executed HRDPS research weather/FWI integration. LightGBM leads pooled v2 temporal AP at 0.00599798; spatial transfer and absolute alert precision remain weak. The original v1 results, four evaluation partitions and eight model bundles are unchanged. Calibration/final-test Parquet content remains unopened by these pipelines; earlier 2019 EDA exposure is disclosed.

The separate selected panel contains 1,775,232 May–October 2025 cell-days over 9,648 independent current-boundary 10 km cells, 600 positive cell-days from 624 retained source instances, native FBP2024 area-weighted categorical shares, SCANFI v1.2/2020 and MRDEM 100-point estimates, and prior-standard-noon ERA5 weather/research FWI. Twenty-five source instances are explicitly excluded. Six fuel cells and twelve weather cells lack support; nulls remain. Closure is conditional on joint species validity; terrain slope is a coarse 1 km sample gradient. This one-year fixed-landscape panel requires its own evaluation design (`training_ready=false`), and is not backfilled into the historical benchmark.

The actual HRDPS October 16 00 UTC run supplies 231,552 hourly records, with six future hours covered at retrieval. The stateful research FWI output/checkpoint has 8,526 valid cells and 1,122 incomplete-weather cells. Forecast-derived checkpoint states always remain untrusted. Available-run selection, rotated wind, accumulated-rain decoding, seed date/noon/availability and provenance guards are implemented. No CWFIS model was applied to incompatible forecast features; observed/overwintered FWI state and live source compatibility remain Week 5 acceptance gates.

All 110 combined tests pass. Week 4 local development is complete, with updated source/feature decisions and compact reproducible evidence. Week 5 still requires frozen calibration/final evaluation, explanations/map, selected-panel evaluation/live compatibility and corrected spread replay. Independent reviewer/professor approval and operational acceptance are not claimed. The 10 km ignition / separate 90 m spread and seven-source scope remain fixed. Earlier dated sections below are historical snapshots.

## Current Week 3 update - October 16, 2026

The [Week 3 design package](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_3_design_2026-10-15/README.md) completes local technical design, component diagrams/contracts, requirements traceability, six architecture decisions and restricted spread review. Four ignition candidates are fitted under common temporal/inner-geographic development protocols. Histogram boosting is the provisional pooled temporal AP candidate (0.005764 versus historical-rate 0.000368), but geographic transfer and absolute alert precision remain weak. The models are uncalibrated research artifacts; 2018 calibration and 2019 final-test content remain unopened by the pipeline. Source station/mask limitations are retained and disclosed.

Scoped spread barrier/corner/empty-active defects are fixed, repair defaults off and reconstruction drivers declare their mode/revision. Archived scores/viewer still describe old code; missing raw landscape windows prevent corrected full replay. The complete suite passes 71 tests. No independent reviewer sign-off, live adapter, calibrated final model, SHAP/map, Git merge/push or operational acceptance is claimed. Full selected-source preparation remains Week 4 and prototype integration remains Week 5. The dated historical sections below remain snapshots; this update supersedes their no-model/no-fix status.


## Week 2 specification update — October 15, 2026

The [Week 2 package](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_2_development_2026-10-15/README.md) now supplies measurable requirements, AI use cases, module/requirement traceability, bounded source audits and frozen evaluation selectors. Formal architecture review and implementation remain separate open milestones. Dates remain provisional at the user's request; the dependency plan is prepared and native Microsoft Project verification is deferred by the user. The extended DPV/C2FK review and Week2 data investigation are complete; full selected-source integration remains Week4 work. The selected grids and historical/source contracts below remain unchanged.

## Active development decision — October 14, 2026

The user selected **10 km cells for ignition modelling**. The permanent local repository is [team_repository](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/team_repository); its [Week 1 plan](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/team_repository/docs/week_1_development_plan.md) defines the initial historical contract and incremental delivery process. All eight remote branches are available locally. Earlier 2.5 km pilot outputs are retained as reference, not the current ignition grid.

The first benchmark retains the existing 2010–2019 Ontario Fire Region local-calendar-day label universe, NFDB/CDEM/CWFIS provenance and explicit hindcast limits. The selected seven-source enrichment/live design is a separate integration task, not an automatic replacement for historical inputs. The existing spread simulator uses its separate 90 m grid. Shared interfaces, source compatibility, label-independent grid eligibility, weather coverage and outcome-independent spread evaluation still require the formal architecture-review milestone.

The [all-branch review](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/repository_review_2026-10-14/README.md) and [development checklist](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/week_1_to_5_checklist.md) supersede older progress summaries below. Week 1 documentation is complete; no ignition training, simulator fixes or later-week acceptance is claimed.

The assigned static datasets have been downloaded and profiled in the Centennial CAPSTONE folder. The measured Ontario-wide findings, candidate features, next steps, and system Mermaid diagram are in [the Ontario static EDA report](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/ontario_static_eda.md). The seven-role hierarchy is in [the IT department plan](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/it_department.md).

The local sources are FBP Fuel Types 2024 and 2026, SCANFI v2 2025, MRDEM 30 m, the historical Ontario Fire Management Zone layer, and a separate northwestern Ontario Fire Response Plan Area layer. No official public FBP 2025 raster was located on 2026-10-02. The 2025 vintage is recorded as unavailable, not substituted.

The original EDA covers static predictors. A [Thunder Bay ignition-data pilot](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/ignition_pilot.md) now joins selected static features to 30,816 calendar-day rows in April–October 2025, with one in-grid recorded fire start. Eleven pilot ERA5-Land files are downloaded. A tested local converter now derives rain/RH/wind/research FWI, with fixed standard noon, explicit startup and missing-state invalidation; ignition joins and province-scale/live integration remain unimplemented. No ignition model has been trained. The repository separately contains historical weather/FWI processing and a spread simulator, as described in the current decision above. Live sub-agents have not been launched; the hierarchy is a design for their collaboration.

The team's selected scope is seven source groups: Ontario Fire Disturbance Point + Area, FIRMS VIIRS, ERA5-Land, HRDPS, FBP 2024, SCANFI 2020, and MRDEM. The [source contract](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/data_dictionary.md#team-source-contract--2026-10-09) separates ignition inputs, live weather, and spread-validation data. Previously downloaded FBP 2026 and SCANFI v2/2025 remain EDA material rather than automatic replacements for selected products.

## Earlier pilot workflow — 2026-10-09 (historical reference)

1. Confirm the ignition prediction unit, historical period, daily cutoff, and spread initialization/horizons.
2. Review software architecture: stakeholders, components/interfaces, alternatives, decision records, feasibility, risks, and maintainability. Existing diagrams are drafted; formal review and prototype validation are pending.
3. Acquire and validate fire-start labels.
4. Acquire ERA5-Land and validation-only VIIRS; establish HRDPS ingestion and a versioned registry for the seven source groups.
5. Derive RH, wind, rainfall summaries, and stateful FWI; complete the version-aware feature builder and cell-day modelling table.
6. Create spatial/temporal holdouts and reusable preprocessing pipelines.
7. Train baselines and LightGBM, evaluate, calibrate, and explain predictions.
8. Build and evaluate the spread simulator using historical weather and matched VIIRS/final-perimeter observations; report unavailable 1-/3-/6-hour validation windows.
9. Build HRDPS-driven scoring, spread outputs, and the map. Resolve the recent-weather/FWI-state bridge and historical-to-forecast feature consistency; review architecture and prototype quality after each sprint.

The architecture-review checklist and detailed sequence are maintained in [the Ontario static EDA report](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/ontario_static_eda.md#system-architecture). Architecture review is an explicit Module 4 task; the diagrams describe the intended system and do not establish that operational software exists.

## Historical course checklist — Weeks 3–5 (October 9 snapshot)

These requirements come from the course summaries supplied by the user. For each week, review the online content and key terms, attend the professor discussion/meeting, and update the technical report. Content review, meeting attendance, professor feedback, and submission are unverified; LMS “started” counts do not establish completion.

| Week | Required technical-report content and project work | Current local status |
| --- | --- | --- |
| 3: AI capability design | Explain how ignition prediction and spread simulation address the problem. Document inputs, outputs, model/simulator approach, requirement links, evaluation criteria, constraints, and design rationale. | Design material is drafted in project notes and diagrams. Formal report integration and professor review remain unverified. |
| 4: Data preparation, frameworks, architecture | Document the seven-source data contract, cleaning/missing-value rules, engineered features, preprocessing pipelines, framework comparison, component interfaces, architectural alternatives, and significant decisions. | Static EDA and pilot features exist. Dated data preparation, RH/FWI implementation, framework comparison, and formal architecture review remain pending. |
| 5: Code, prototype, module testing | Implement a small end-to-end prototype, test individual modules during development, run an integration demonstration, and add code/prototype evidence, test results, defects, and limitations to the report. | The Thunder Bay daily label/static builder and ERA5-Land request preparation are implemented. Dated data and acquisition evidence exist; module/output tests cover key label rules and versions. Weather processing, trained predictor, spread simulator, and the end-to-end prediction demonstration remain pending. |

Module testing runs alongside workflow steps 3–9, not only after the system is assembled. Start the Week 5 prototype with a small region and eligible historical period; demonstrate real labels → features → baseline prediction → map output. Track spread simulation as a separate prototype path with its own observation-coverage limits. Full live deployment is a later milestone.

The detailed [weekly deliverables and module-test checklist](/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/ontario_static_eda.md#course-deliverables--weeks-35) identify what evidence to add to the technical report. Record each professor meeting's date, feedback, and resulting actions when available. No course item has been marked complete in the LMS by this documentation update.
