# System requirements specification v1

Prepared October 15, 2026 from the documented project scope, supplied COMP 385 requirements, repository contracts and research review. These are requirements and acceptance criteria, not implemented features or measured performance. This development specification omits team administration and stakeholder-register tasks as requested.

## Purpose and boundaries

Support an analyst exploring Ontario wildfire risk through two separate capabilities:

1. Daily probability of at least one recorded new start in an existing **10 km** Ontario Fire Region cell.
2. Progression of an **existing fire**, using the separate **90 m** spread prototype.

The first demonstrable product is historical analysis. Live HRDPS scoring is a later increment. The active historical ignition contract is May–October 2010–2019, issue time 00:00 America/Toronto, keyed by `(grid_id, ignition_date)`. The initial feature baseline uses NFDB, CDEM and CWFIS. The selected seven-source development scope remains documented separately; neither modern landscape layers nor US benchmark datasets silently replace baseline sources.

An analyst can choose a date/area, inspect a cell and its explanation, initialize a fire simulation, inspect historical replay comparisons and export results. An operator can build versioned inputs, train/evaluate candidates and load the selected model. These actor descriptions identify software actions without adding an administrative stakeholder register.

## Functional requirements

Priority meanings: **M1** = required for historical prototype; **M2** = required for later live increment; **L** = later research option. Acceptance checks below are future verification work.

| ID | Priority | User-visible requirement | Acceptance evidence |
| --- | --- | --- | --- |
| FR-01 | M1 | Select a supported historical date and study area. | A valid May–October date in the pinned period selects the correct existing grid; an unsupported date/area receives a specific message. No cell-size change is inferred from weather resolution. |
| FR-02 | M1 | Request ignition-risk scores for selected eligible 10 km cells. | Output has one unique cell/date key, probability in [0,1], model/data versions and issue time. An unavailable model produces an explicit failure rather than fabricated scores. |
| FR-03 | M1 | Display scores on a map and inspect a cell. | Polygon geometry matches EPSG:3978 source cells; display coordinates are transformed for the map. Legend explains probability and missing output. Any risk categories use recorded validation-derived thresholds. |
| FR-04 | M1 | Explain a selected cell's prediction. | Show the model-specific explanation method, contributing features, feature values/units and missing-data flags. If explanations have not been generated, show that state. Contributions are not described as causal effects. |
| FR-05 | M1 | Inspect provenance and quality. | The analyst can see source versions, feature contract, observation/issue timestamps, coverage flags and historical/live mode. Missing weather is distinct from zero temperature, rain or wind. |
| FR-06 | M1 | Export selected ignition outputs. | CSV/GeoJSON exports retain keys, probabilities, geometry/CRS where relevant, issue time, model/data versions, quality flags and threshold version. Exported key/value counts agree with the selected map output. |
| FR-07 | M1 | Start a spread simulation from an existing fire state. | Accept a supported incident or validated coordinates/initial fire mask and start time. Reject empty/outside/non-burnable initial states and unsupported source combinations. Final future perimeters cannot initialize a forecast. |
| FR-08 | M1 | Inspect 1-, 3- and 6-hour simulated progression. | Return time-labelled outputs only for completed simulation horizons. State separately whether each horizon has suitable validation observations. Computation is not evidence of forecast accuracy. The spread grid remains separate from 10 km ignition cells. |
| FR-09 | M1 | Compare a historical replay with observations and a simple baseline. | Align incident, observation time, target definition and spatial scoring support. Show reached/missed cells and recall/IoU or other explicitly defined measures. Missing satellite detections remain unknown, not confirmed unburned ground. |
| FR-10 | M1 | Distinguish reconstruction from prediction. | A run using final-perimeter-assisted fuel repair is labelled retrospective reconstruction and excluded from outcome-independent forecast results. A fixed modern-fuel scenario is labelled with that vintage. |
| FR-11 | M1 | Build and inspect a reproducible dataset. | The operator receives source paths/URLs, hashes, record counts, schemas, units, time rules and exclusions. Invalid keys/types fail a build or produce a named quarantine report. Raw inputs are preserved. |
| FR-12 | M1 | Compare ignition candidates on reserved evaluation partitions. | Training, validation, calibration and final-test selectors are recorded. Report historical-rate/interpretable baseline and agreed boosting candidate on a common evaluation contract; model choice is supported by measured results. |
| FR-13 | M1 | Save and reload an evaluated model for scoring. | Bundle model, predictor order, fitted preprocessing, calibration, threshold definitions, dependency versions and source/feature contract. Reloaded output agrees with saved-model output within the documented numeric tolerance. |
| FR-14 | M2 | Select a genuinely available HRDPS run for live scoring/simulation. | Run time, valid time, lead and retrieval/availability evidence are retained. All requested horizons are covered; missing required weather causes a visible incomplete-input state. Run time alone is not treated as availability. |
| FR-15 | M2 | Maintain compatible recent-weather/FWI state. | Required rain history and moisture-code state exist with startup, timezone, algorithm/version and reset rules. A six-hour weather slice cannot stand in for seasonal state or seven-day history. |
| FR-16 | L | Display spread ensemble uncertainty or treatment priorities. | Only after a documented ensemble/DPV method and held-out evaluation exist; otherwise show unavailable. A burn-frequency map is not relabelled as new-ignition probability. |

## Non-functional requirements

Performance figures are initial engineering targets for a declared reference machine, not results, staffing commitments or fixed course rubrics. Record actual hardware, dataset size, warm/cold state and measured distribution when testing.

| ID | Quality requirement | Measurable acceptance rule |
| --- | --- | --- |
| NFR-01 | Data and time integrity | Zero duplicate output cell/date keys. All observed dynamic ignition inputs precede the local issue day; any known availability later than issue is rejected in forecast mode. Unknown historical availability is retained and labelled hindcast. |
| NFR-02 | Geographic and unit consistency | Every exchanged raster/table declares CRS, resolution, spatial support and units. Fuel codes use categorical resampling. Wind direction/bearing and slope conversions pass explicit north/east and unit reference cases before integration. |
| NFR-03 | Reproducibility | Each reported experiment has code/source revision, input hashes, selectors, seed, predictor list, environment and output hash. Deterministic repeated scores differ by no more than 1e-6 absolute probability on identical inputs; stochastic runs record seed and ensemble size. |
| NFR-04 | Honest scientific evaluation | Preserve natural held-out prevalence; fit learned preprocessing only on permitted training data. Report average precision (AP), precision, recall, false-positive alerts per 1,000 eligible cell-days and a calibration measure such as Brier score. Name the metric implementation; AP and trapezoidal PR-AUC are not silently interchanged. |
| NFR-05 | Baseline comparison | No accuracy percentage or superiority claim is required in advance. The report must compare the candidate with the baseline on identical targets and disclose failures, undefined metrics and coverage. Retain the simpler method if an improvement is unsupported. |
| NFR-06 | Interface response | For precomputed results up to 9,673 cells on the reference machine, target p95 initial map/data response <=5 seconds across 20 requests and cell-details response <=2 seconds. Cold data rebuild/download time is measured separately. |
| NFR-07 | Spread responsiveness | For a declared window <=100,000 cells and +6-hour simulation, initial target p95 <=60 seconds over 20 cases on the reference machine. Exceeding it triggers a performance review; no false completed response is returned. |
| NFR-08 | Failure visibility | All attempted requests end in success, failure or a stated incomplete-input state. Missing model, timeout, missing weather and unsupported fuel each have a distinct visible outcome; failed output is never shown as low risk. |
| NFR-09 | Usability | A first-time tester can complete UC-01 and inspect a cell without editing code. Map legend, units, selected dates, mode and missing-output state remain visible; status is understandable without colour alone. Record task success and obstacles. |
| NFR-10 | Access and provenance | Use documented public-source terms/attribution, retain source credits in maps/exports and keep credentials outside Git and exported results. No personal-data collection is required for the prototype. |
| NFR-11 | Maintainability | Separate acquisition, transformations, fitting, scoring, simulation and display. Each module has a documented input/output contract and appropriate module/integration checks. Passing software tests does not replace scientific evaluation. |
| NFR-12 | Portability and resource limits | Provide one reproducible environment/build procedure for the local historical demo. Record peak memory, storage and runtime of the full-panel build; do not assume the 17.8-million-row table fits in memory or that this Mac has an NVIDIA GPU. |

## Acceptance and traceability

| User action | Functional requirements | Quality requirements | Main components | Current implementation evidence |
| --- | --- | --- | --- | --- |
| UC-01: predict daily risk | FR-01–03, FR-05 | NFR-01–06, 08–09 | grid/date selector, feature builder, saved-model scorer, map | Historical feature-building code exists; fitted ignition model/map remains absent. |
| UC-02: explain a cell | FR-04–06, FR-13 | NFR-03, 08–10 | scorer, explanation service, cell details/export | Defined requirement; no fitted explanation output claimed. |
| UC-03: simulate a fire | FR-07–08, FR-10 | NFR-01–03, 07–09 | incident/input adapter, spread engine, viewer | 90 m simulator/viewer exists; reproduced barrier defect and outcome-input issue remain. |
| UC-04: compare replay | FR-09–10, FR-12 | NFR-03–05, 08 | replay selector, common scorer, observations | Saved historical replay exists; revised outcome-independent evaluation remains. |
| Build/train/load | FR-11–13 | NFR-01–05, 10–12 | acquisition/QA, selectors, training, registry | Source registries/code exist; selectors now reserved; fitted model absent. |
| Live increment | FR-14–15 | NFR-01–03, 08, 10–12 | HRDPS adapter, weather/FWI state | A one-run/one-lead sample is decoded; ingestion/state/model compatibility are unimplemented. |

Architecture review must examine these contracts, alternatives, feasibility, failure paths and source mismatches **before implementation changes**. This specification does not declare that milestone complete.

## Explicit unresolved decisions

- Calendar dates remain provisional at the user's request; the dependency/duration plan can be used immediately. Native Microsoft Project import remains unverified.
- Final boosting framework: compare the documented candidates; no new selection is made here.
- Risk-category thresholds and uncertainty method: select and document using development/calibration data, not final-test outcomes.
- Label-independent study mask and historical source limitations: retain baseline reproducibility and perform a separately versioned sensitivity evaluation.
- Missing data acquisition, historical weather coverage/station selection and fire-date reconciliation: see the data audit. Requirements do not make these inputs complete.

Sources: [project context](/Users/parthkevadiya/Documents/ChatGPT/AI%20CAPSTONE/context.md), [Week 1 contract](../../team_repository/docs/week_1_development_plan.md), [source dictionary](../data_dictionary.md), [all-branch review](../repository_review_2026-10-14/README.md), [research review](../research_review_2026-10-14/README.md). All acceptance checks are prospective unless an evidence statement explicitly says otherwise.
