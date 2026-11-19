# Learn the ignition demo

The system answers a specific question: **Will this existing 10 km grid cell
have at least one recorded wildfire ignition during this local calendar day?**
Each score belongs to one cell and one day. The model does not simulate fire
spread, and it does not take the eventual fire size or perimeter as inputs.

## 1. Understand the saved model

Training learns a rule from labelled historical examples. Prediction applies
that learned rule to the required inputs. A saved model lets us reuse the rule
without repeating training whenever someone changes the date in the app.

The current retained model is coordinate HGB from experiment 2, trained
through the main pipeline: **80 iterations and 39 inputs**, seed 385,
12,458,824 training rows from 2010–2016, learning rate 0.1, L2 1.0,
15 leaves and minimum leaf size 100. There is no class weighting,
early stopping or calibration.

The ordered inputs are the original 36 fields, the persisted history-censor
flag, then cell-centre easting/northing. The only feature list is
`data/metadata/ignition_feature_selection_v1.json`. HGB preprocessing
preserves all 39 fields and native NaNs; it does not add a 40th input.

`scripts/ignition_demo/reconstruct.py` delegates to panel validation, the
corrected-cache builder and `scripts/ignition_modeling/run.py`.
The main runner fits 2010–2016, saves a joblib bundle, checks reload agreement
and optionally compares every development prediction with the experiment
pickle. It records metadata rather than rerunning the old final-test protocol.

**Try it:** Open `artifacts/ignition_modeling/retained_coordinate_hgb/training.json`.
Find `n_rows`, `n_features_raw`, `n_features_transformed` and `n_iter`.
Explain why both widths are 39 and why changing the replay date does not fit
another model.

## 2. Trace a request

Changing the date triggers `loadDay` in `ignition_demo/web/app.js`. The browser
requests `/api/predictions?date=2019-07-01`. The Python handler validates the
date, reads its rows, orders them to match the map grid, and runs the saved
pipeline. JSON carries the results back to the browser. A small in-memory
cache avoids repeatedly scoring a recently viewed date.

`DemoStore._day` in `scripts/ignition_demo/server.py` is the main bridge between
data and model. It reads exactly the approved feature order. Dates, IDs and
labels are not in that numerical matrix. The date selects the rows; it does
not become an extra model input.

**Try it:** While the server is running, open
<http://127.0.0.1:8766/api/predictions?date=2019-07-01>. Find the date, a score,
and the `weather_missing` array. Try an unsupported date and read the error.

## 3. Read the map correctly

Each square is one frozen 10 km cell in Canada Atlas Lambert coordinates.
The service supplies cell origins and their grid footprint, not an official
sector boundary. The pinned Ontario boundary asset is unavailable; a
checksum-mismatched substitute must not be used. Panning/zooming affects only
the view, not the data or model.

Fixed illustrative cutoffs define colours consistently across dates. A darker
cell has a larger model score, which can still be a small probability.
White cell outlines indicate alerts at the selected cutoff.
Black circles, when enabled, show recorded ignitions. A diagonal mark at close
zoom indicates missing weather. The table provides a keyboard-accessible way
to select cells without clicking the canvas.

The inspector shows the actual prior-day weather and other inputs. These are
context, not explanations proving that a particular input caused a prediction.
Missing prior fire history means no earlier observed same-cell event in the
available record. It is censored history rather than zero days since a fire.

**Try it:** Select the top-ranked cell. Read its percentage score and weather
coverage. Change to the next day and inspect that same cell. Describe which
inputs changed and which terrain inputs stayed constant.

## 4. Separate scores from alert decisions

A score is continuous. A threshold turns it into a decision: flag the cell if
its score is **greater than or equal to** the cutoff. Lowering the cutoff
usually catches more recorded ignitions and creates more false alerts.

| Count | Meaning |
| --- | --- |
| True positive | A flagged cell-day with a recorded ignition |
| False positive | A flagged cell-day without a recorded ignition |
| False negative | An unflagged cell-day with a recorded ignition |
| True negative | An unflagged cell-day without a recorded ignition |

Precision = true positives / all alerts. Recall = true positives / all
recorded ignition cell-days. An undefined denominator is shown as unknown.

The current app does not select cutoffs by F2 or reuse the old model's 2018
threshold policy. Its eight cutoffs are illustrative; the default **0.001**
is displayed as **0.1%**. It was not chosen using replay-year labels.

Counts refer only to the displayed day. The old 40-iteration model's 2019
AP, ROC-AUC and confusion counts are not results for this model. No new global
reserved-year evaluation is displayed. High accuracy on a rare target can
still mean missing nearly every ignition; ranking and calibration need
separate chronological/spatial evaluation.

**Try it:** Record one day's correct alerts, false alerts and missed ignitions.
Choose a lower cutoff and explain the changes. Explain why choosing a policy
using the displayed day's labels would not establish future-day performance.

## 5. Verify and explain your implementation

The full rebuild validated 17,798,320 rows across 1,840 dates. The v3 corrected
cache keeps the ordered 39 columns, full daily grid, labels, weather quality
and native history censoring. Old 36-column caches are rejected.

The current model export records clean commit
`1cff710d4ea388acfeefa72cdbd7bd17696db61d` and `working_tree_dirty: false`.
All 12,458,824 development predictions match the experiment pickle
bit-for-bit, with maximum difference 0.0; the 1,024-row reload check also
matches exactly. This is reproducibility evidence, not a new test score.

Tests cover independent fixtures and real artifacts. API checks compare
served scores with the main joblib model, preserving grid order, missing
values and full-precision CSV output. The updated browser verifier exercises
the 39-input inspector and responsive interaction flow.

**Try it:** Read `model_metadata.json` and `verification.json` in the retained
export directory. Distinguish the model's clean training commit from later
documentation edits. Explain why equal development predictions do not prove
performance on unseen years or geography.

## How to discuss future work

Live forecasting would need issue-time-available data, a current feature
pipeline, appropriate retraining and temporal/spatial validation, monitoring,
and an alert policy informed by real capacity and costs. Modern historical
archive downloads do not establish what was available on each historical date.
The frozen grid also has event-informed edge selection. Keep these limits
attached to any claim about the results.
