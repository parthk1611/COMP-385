# Ontario Ignition Atlas: capstone implementation report

## Result

The project now includes a complete local historical ignition demonstration:
a reconstructed trained model, date-based prediction service, interactive
Ontario risk grid, selectable alert cutoffs, full-day exports and learning
materials. It supports all 184 dates from May 1 through October 31, 2019,
with 9,673 cells per date. This report supplements the original completed
model comparison in `docs/modeling/final_report.md`.

## Prediction problem and inputs

The target is at least one recorded wildfire ignition in an existing 10 km
Ontario Fire Region cell during one local calendar day. The original full
panel contains 17,798,320 rows across 2010–2019. The 36 approved inputs describe
calendar/solar conditions, static terrain, prior-day CWFIS weather/FWI and
strictly earlier ignition history. Dates, identifiers and outcome labels are
excluded from the model matrix. Native missing values and the explicit
history-censor indicator preserve distinct source-coverage states.

The corrected cache fixes the original station-selection and unsorted-date
join problems. Daily weather is based on t−1, and seven-day rainfall requires
all seven completed dates. Historical archive publication times remain unknown.

## Reconstruction and separation from the original experiment

The original saved model bytes were absent locally. We recovered the exact
audited CSV from the supplied gzip file, verified its checksum and the pinned
weather archive, then rebuilt the corrected cache with the existing builder.
An independent scan checked the complete daily grid, date ordering, label and
quality consistency, and all annual counts against the published audit.

Only the selected HGB configuration was refitted, on 12,458,824
rows from 2010–2016: 40 iterations, learning rate 0.1, 15 leaf nodes,
minimum leaf size 100, L2 regularisation 1.0, no class weighting, seed 385,
and no internal random early stopping. The recorded calibration decision
retains raw scores. The model and policy were frozen before 2019 evaluation.
Original training code and published experiment records were preserved.

| Measure | Original published 2019 | Reconstructed 2019 | Difference |
| --- | ---: | ---: | ---: |
| Average precision | 0.007274601012 | 0.007274601012 | 0 |
| ROC-AUC | 0.889195313548 | 0.889195313548 | 0 |
| Brier score | 0.000285651960 | 0.000285651960 | 0 |
| Log loss | 0.002305420989 | 0.002305420989 | 0 |

Reconstruction status: **PASS**. All eight frozen-cutoff
confusion tables also match. Reloaded predictions agree within absolute
tolerance 1e-14. Matching numerical results establish this reconstruction's
agreement with the reference evaluation; the model was not recovered as the
original byte-for-byte artifact.

The 2019 prevalence baseline is 0.000285982, compared with AP
0.007274601. ROC-AUC measures ranking and must
not be presented as the percentage of correct alerts.

## Prediction service and interface

A Python HTTP server binds to 127.0.0.1. It verifies model and cache
fingerprints, loads the trained pipeline once, and reads each requested day's
inputs from memory-mapped files. It explicitly reorders the daily cache rows
to match the map grid and caches recently requested days.

The browser uses plain JavaScript and a canvas. The map includes the actual
study grid and a simplified Ontario fire-region boundary in EPSG:3978. Its
fixed score colours come from 2018 cutoffs. Date controls, panning/zooming,
cell inspection, a keyboard-accessible ranked table, observed-ignition and
alert-only overlays, and full-precision CSV downloads support exploration.
Observed labels remain separate from model inputs. Missing weather and
censored fire history remain explicit in cell details.

The endpoints are `/api/metadata`, `/api/grid`, `/api/predictions`, `/api/cell`
and `/api/download`. Dates use America/Toronto local calendar dates, invalid
inputs receive clear errors, and missing numeric values use JSON null.

## Alert policy and its consequences

The demonstration policy maximises F2 among the eight existing cutoffs using
2018 validation counts only. F2 is `5 TP / (5 TP + 4 FN + FP)` and gives recall
more weight than precision. Its cutoff is **0.01502367973189238**
(1.5024% as a displayed probability). Scores equal to
the cutoff are included. Higher cutoffs win any exact F2 ties.

This policy is a learning default, not an operational optimum. On 2018 it
produced approximately 48.37 alerts per day, 1.44% precision and 10.24% recall.
The unchanged rule gives the following reconstructed 2019 results:

| Outcome | Cell-days |
| --- | ---: |
| Correct alerts | 15 |
| False alerts | 1,871 |
| Missed ignitions | 494 |
| Correct non-alerts | 1,777,452 |

Precision is 0.7953%, recall 2.9470%,
and alert volume 10.25 cells per day. These weak absolute
alert results remain visible alongside the improvement in ranking. Users may
compare other frozen cutoffs; their selections do not modify the fitted model
or the recorded default policy.

## Validation and reproduction

Compact source/model/cache fingerprints, numerical results and reconstruction
checks are in `reconstruction_evidence.json`. The large binary artifacts stay
under the ignored reconstruction/cache directories. Setup, launch commands
and API details are in `ignition_demo/README.md`. The small-fixture regression
suite and real-artifact checks verify policy arithmetic, date/schema handling,
cache alignment, score persistence, missingness and CSV precision.

Browser verification covers date changes and boundaries, 36-input inspection,
selection retention, cutoff changes, observed/alert-only overlays, zoom/reset,
ranking filters, downloads, invalid API dates and widths of 1440, 1024 and
390 pixels. The verification summary records the executed results separately.

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
