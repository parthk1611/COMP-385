# Learn the ignition demo

The system answers a specific question: **Will this existing 10 km grid cell
have at least one recorded wildfire ignition during this local calendar day?**
Each score belongs to one cell and one day. The model does not simulate fire
spread, and it does not take the eventual fire size or perimeter as inputs.

## 1. Understand the saved model

Training learns a rule from labelled historical examples. Prediction applies
that learned rule to the required inputs. A saved model lets us reuse the rule
without repeating training whenever someone changes the date in the app.

The original experiment compared logistic regression and histogram gradient
boosting across five chronological development folds. The selected boosting
model has 40 iterations. This demo reconstructs that selected model using all
12,458,824 training rows from 2010–2016 and seed 385. It adds one explicit
history-censor indicator to the 36 source features, giving 37 transformed
features. Missing numerical values remain missing for the boosting model.

Reconstruction happens in `scripts/ignition_demo/reconstruct.py`. Read its
`reconstruct` function in this order: prepare cache, verify cache, train,
save/reload, freeze, evaluate. The freeze records what existed before test
evaluation. The original experiment's records remain the reference.

**Try it:** Open the reconstruction's `training.json`. Locate `n_rows`,
`n_features_raw`, `n_features_transformed` and `n_iter`. Explain why 36 inputs
become 37 features and why changing the map date does not train another model.

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

Each square is one 10 km cell in Canada Atlas Lambert coordinates. The service
supplies the cell origins and a simplified study boundary. The browser draws
them on a canvas. Panning and zooming change only the view.

The colour boundaries come from fixed 2018 score cutoffs and stay identical
across dates. A darker cell has a larger model score, which can still be a
small probability. White cell outlines indicate alerts at the selected cutoff.
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

Precision = true positives / all alerts. Recall = true positives / all recorded
ignition cell-days. F2 = `5 TP / (5 TP + 4 FN + FP)`. It favours recall more
heavily than precision. We maximise it only among the eight pre-existing
cutoffs using 2018 validation data. The result is approximately 0.015024, or
**1.5024%** when displayed as a probability percentage.

For 2019, this default flags 1,886 cell-days: 15 correct alerts and 1,871 false
alerts. It misses 494 of the 509 positive cell-days. These counts explain why
the app exposes the full tradeoff rather than implying reliable alerts.

The final test has 1,779,832 rows but only 509 positives. Always predicting
"no ignition" would have very high accuracy while catching no ignitions.
ROC-AUC of 0.8892 describes ranking, not 88.92% alert correctness. Average
precision of 0.007275 exceeds the prevalence baseline of 0.000286, while
absolute precision remains low.

**Try it:** Record the default's correct alerts, false alerts and missed
ignitions for a day. Choose a lower cutoff. Explain the changes. Then compare
the 2018 validation row with the 2019 test row. Why would selecting the best
2019 cutoff make the reported test evaluation less trustworthy?

## 5. Verify and explain your implementation

The reconstruction checks all 1,840 dates and 17,798,320 rows. It verifies
daily grid permutations, labels, missing-weather states, rainfall coverage and
annual totals. The model's four aggregate 2019 metrics and all eight confusion
tables match the published experiment. Model reload predictions agree within
an absolute tolerance of 1e-14. The model was rebuilt rather than recovered
byte-for-byte from the original machine.

The new tests cover both small independent fixtures and the real artifacts.
The latter compare served first/middle/last-season days against saved frozen
prediction vectors, including grid ordering and full-precision CSV output.

**Try it:** Run the test suite. Choose one policy test and explain its expected
answer by hand. Then use the demo script to give a three-minute walkthrough.

## How to discuss future work

Live forecasting would need issue-time-available data, a current feature
pipeline, appropriate retraining and temporal/spatial validation, monitoring,
and an alert policy informed by real capacity and costs. Modern historical
archive downloads do not establish what was available on each historical date.
The frozen grid also has event-informed edge selection. Keep these limits
attached to any claim about the results.
