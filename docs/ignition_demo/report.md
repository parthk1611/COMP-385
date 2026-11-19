# Ontario Ignition Atlas: capstone implementation report

## Result

The project includes a local historical ignition demonstration using the
retained **80-iteration coordinate HGB with 39 persisted inputs**. It provides
date-based predictions, a frozen-grid map, illustrative score cutoffs,
full-day CSV exports and learning materials. The replay supports all 184
dates from May 1 through October 31, 2019, with 9,673 cells per date.
The earlier 40-iteration comparison in `docs/modeling/final_report.md` is
historical evidence, not a performance evaluation of this retained model.

## Prediction problem and inputs

The target is at least one recorded wildfire ignition in an existing 10 km
Ontario Fire Region cell during one local calendar day. The rebuilt panel
contains 17,798,320 rows across 2010–2019 and 51 columns. Its only authoritative
predictor list is `data/metadata/ignition_feature_selection_v1.json`.
The ordered 39 inputs contain the original 36 calendar/terrain/weather/history
fields, `fire_history_days_since_same_cell__censored`, and the two static
EPSG:3978 cell-centre coordinates. Dates, IDs, source metadata and labels are
excluded. HGB preserves native NaNs and adds no duplicate flag or coordinates.

The corrected cache fixes the original station-selection and unsorted-date
join problems. Daily weather is based on t−1, and seven-day rainfall requires
all seven completed dates. Historical archive publication times remain unknown.

## Main-pipeline model and clean provenance

The main pipeline rebuilds the panel, validates it and writes all 39 inputs
to cache version `ignition-v1-weather-asof-global-date-coordinates-v3`.
All rows and labels remain, including missing-weather and censored-history
states. The model is fitted on all **12,458,824 rows from 2010–2016**:
80 iterations, learning rate 0.1, 15 leaves, minimum leaf size 100, L2 1.0,
seed 385, no class weighting, no early stopping and no calibration.

`scripts/ignition_modeling/run.py` exports `selected_system.joblib`,
`model_metadata.json`, `training.json` and `verification.json` under
`artifacts/ignition_modeling/retained_coordinate_hgb/`.
`scripts/ignition_demo/reconstruct.py` delegates to that same pipeline.

The current export was recreated from clean commit
`1cff710d4ea388acfeefa72cdbd7bd17696db61d`; its metadata records
`working_tree_dirty: false`, ordered features, settings, training scope,
cache version, package versions and source/model/cache checksums.
The model SHA-256 is
`5dd1c909a9d0ea4903567ee66f4831d9e687e62156b6288812888ec3e830cb89`.

Every development prediction matches the verified experiment pickle
bit-for-bit: **12,458,824 compared, zero differences, maximum absolute
difference 0.0**. The 1,024-row joblib reload probe also has zero difference.
This establishes reproducibility, not held-out predictive performance.
No 2017–2019 fitting, calibration, threshold tuning or global scoring was
performed. Old published 2019 metrics and F2 policy results must not be
attributed to this model; `reconstruction_evidence.json` preserves the
earlier 40-iteration reconstruction as historical evidence only.

## Prediction service and interface

A Python HTTP server binds to 127.0.0.1. It verifies model and cache
fingerprints, loads the trained pipeline once, and reads each requested day's
inputs from memory-mapped files. It explicitly reorders the daily cache rows
to match the map grid and caches recently requested days.

The browser uses plain JavaScript and a canvas to show the frozen 10 km grid
footprint in EPSG:3978, not a simplified official sector boundary. The pinned
Ontario boundary asset is unavailable; no checksum-mismatched substitute is
used. Fixed illustrative score colours are shared across dates. Date controls,
panning/zooming, 39-input cell inspection, accessible rankings, overlays and
full-precision CSV downloads support exploration.
Observed labels remain separate from model inputs. Missing weather and
censored fire history remain explicit in cell details.

The endpoints are `/api/metadata`, `/api/grid`, `/api/predictions`, `/api/cell`
and `/api/download`. Dates use America/Toronto local calendar dates, invalid
inputs receive clear errors, and missing numeric values use JSON null.

## Alert policy and its consequences

The eight probability cutoffs are illustrative and were not selected using
2018 or 2019 labels. The default is **0.001**, displayed as **0.1%**.
Comparisons are inclusive: scores equal to the cutoff are flagged.
This is not an operational optimum or a validated response policy.

The app reports true/false positives and negatives, precision, recall and alert
counts only for the displayed day. Undefined ratios remain unknown. Lowering
the cutoff can increase alerts and recall while increasing false alerts.
Selecting a cutoff changes the view, not the fitted model. The interface
explicitly states that global reserved-year evaluation was not recomputed.

## Validation and reproduction

The clean export's `model_metadata.json` and `verification.json` provide the
current provenance and numerical comparison. Large binaries and caches stay
ignored. `ignition_demo/README.md` documents setup, launch and API contracts;
`verification.md` records the executed checks and clean commit.

The updated `ignition_demo/verify_browser.js` passed against the clean export:
80-iteration/39-input metadata, all 39 inspector fields, illustrative cutoffs,
date stepping/boundaries, retained cell selection, overlays, zoom/reset,
ranking filters, CSV download and invalid-date handling. The July 2 download
contained 9,673 unique cells. Widths of 1440, 1024 and 390 pixels had no
page overflow, and no page errors occurred. Desktop/mobile screenshots were
visually inspected. Browser evidence is in `output/playwright/verification.json`.

## Limits and future development

This remains a retrospective hindcast on a frozen grid whose edge selection
uses study-period events. Archive publication and revision times are unknown.
Terrain is a retrospective static approximation, history starts in 2010,
spatial generalisation and date-dependent uncertainty remain untested, and
false alerts dominate at the demonstrated cutoffs. The interface cannot
establish current conditions or provide emergency guidance.

Live forecasting would require an issue-time-available current data pipeline,
an appropriate current grid and model evaluation, temporal and spatial
validation, monitoring of coverage and score drift, and an alert policy tied
to actual response capacity and error costs. Fire spread is a separate
prediction problem and does not supply ignition predictors.
