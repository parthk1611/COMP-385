# Recent neighbourhood ignition-history experiment

Decision: retain the existing coordinate-HGB candidate. Adding two short-window
history predictors reduced mean development AP by 9.18%, with AP lower in all
five validation years. This is a negative feature experiment, not a change to
the selected model, v1 panel, corrected cache, or original final evaluation.

## Features and rationale

The coordinate model already contains same-cell and 3x3-neighbourhood history
for 30 and 365 days, plus days since an earlier same-cell event. Those features
were not removed. This experiment adds only:

| Predictor | Meaning |
| --- | --- |
| `fire_history_neighborhood_1d` | Individual selected source ignitions dated yesterday in the existing 3x3 neighbourhood, including the target cell |
| `fire_history_neighborhood_7d` | Individual selected source ignitions dated t-7 through t-1 inclusive in that same neighbourhood |

A neighbourhood is defined by +/-10 km in each projected axis, including diagonal
cells and the target cell; cells absent from the frozen dimension are not added.
Multiple source ignition records in one cell-day each contribute, as in the
existing history features. They are not collapsed to the binary target.

The hypothesis was that recent local clusters contain information diluted by
30-day aggregation. These are past ignition indicators, not fire-front or spread
features. The result does not support retaining this two-feature addition in the
fixed model. It does not establish that every possible history feature or model
configuration would fail.

No new external data were downloaded. Fuel composition and land cover are **not**
current model predictors: CDEM elevation, slope, aspect, and ruggedness are
terrain-only. The registry lists land-cover/fuel enrichment as deferred because
appropriate historical assets and availability metadata are not supplied.

## Timing and source limitations

The original `FireHistory` state machine is reused with two additional windows.
Events enter only when their source date is strictly before the local target
date. The one-day window contains t-1 only; seven days includes t-7 and excludes
t. Validation histories may use completed earlier validation dates, consistent
with the existing sequential issue-day contract, but never same-/future-day
records. No fitted transformation sees validation outcomes.

The selected event history begins in 2010 and covers the selected fire-season
records. Counts describe that available subset, not a complete year-round or
pre-2010 fire catalogue. No absent pre-2010 or off-season observations are
fabricated. NFDB historical discovery/report availability timestamps are unknown;
recent historical ignition dates cannot be claimed to have been operationally
available at the historical issue time. This remains a retrospective hindcast.

Experimental version: `ignition-weather-v2-cell-centres-recent-neighborhood-v1`.
The separately recorded [feature manifest — supporting_results["feature_manifest.json"]](results.json) has **40 raw
predictors and 41 transformed inputs**. Original predictors, coordinates, native
NaNs, source-quality fields, and the history-censoring indicator are retained.
The 2017--2019 feature rows are not constructed or scored by this experiment.

## Fixed comparison

Five expanding chronological folds validate on 2012--2016, with every row and
natural class prevalence retained. The baseline reuses verified coordinate-HGB
predictions; only five new models are fitted. Both variants use 80 iterations,
learning rate 0.1, L2 1, maximum leaves 15, minimum leaf samples 100, no class
weighting, no early stopping, and seed 385. No new parameter search, calibration,
reserved-year evaluation, or commit is performed.

The selection criterion remains unweighted mean yearly AP; exact ties retain the
baseline. These are reused development years, so this is not a new blind test or
statistical significance result.

| Metric | Coordinate HGB | Coordinates + recent history |
| --- | ---: | ---: |
| Mean yearly AP | 0.0069655251 | 0.0063260005 |
| Mean yearly ROC-AUC | 0.87247731 | 0.87397112 |
| Mean yearly Brier score | 0.00037887699 | 0.00037903135 |
| Mean yearly log loss | 0.00289279732 | 0.00289390382 |

ROC-AUC improved slightly, but the primary criterion worsened, as did Brier and
log loss. A small ROC-AUC gain is not grounds to change the predeclared AP rule.

| Validation year | Coordinate AP | AP with recent history |
| --- | ---: | ---: |
| 2012 | 0.01023845 | 0.00979106 |
| 2013 | 0.00904243 | 0.00814369 |
| 2014 | 0.00174955 | 0.00141977 |
| 2015 | 0.00451145 | 0.00430983 |
| 2016 | 0.00928574 | 0.00796566 |

The experiment shows a degradation, not its cause. Redundant or noisy history
and altered tree splits are possibilities, not established explanations. No
additional model-capacity changes were made to chase this result.

## Fixed daily-budget trade-offs

Reuse the same daily ranking rule as the previous utility analysis: select
exactly 97, 194, or 484 of 9,673 cells per day, with label-blind ascending
`grid_id` cutoff ties. Rank globally before weather stratification, and include
all 920 validation dates. Pooled recall uses all 3,384 positive cell-days.

| Daily budget | Coordinate recall | Recent-history recall | Coordinate precision | Recent-history precision |
| --- | ---: | ---: | ---: | ---: |
| Top 1% | 12.20% | 12.06% | 0.463% | 0.457% |
| Top 2% | 18.59% | 19.00% | 0.352% | 0.360% |
| Top 5% | 31.91% | 33.51% | 0.243% | 0.255% |

The secondary result is mixed, not uniformly worse: larger review budgets
capture more positive cell-days, while the tightest budget captures fewer.
These are descriptive development results, not significant gains established
on a new test set. Mean yearly AP measures a different ranking question from
pooled recall at a fixed daily budget. Do not switch the selection criterion
after seeing this trade-off; the predeclared mean-AP rule retains the baseline.

At the new model's cutoff ties, attainable pooled true-positive counts are
identical to the deterministic counts at all three budgets. These utility
results are not caused by label-aware tie resolution. Full year/weather-group
counts and false-alert rates are in
[daily_budget_comparison.csv — tables["daily_budget_comparison.csv"]](results.json) and
[daily_budget_results.json — supporting_results["daily_budget_results.json"]](results.json).

## Historical verification

The original run reconstructed all five existing histories and labels over
12,458,824 development rows: 62,294,120 history values, 5,530 event records and
5,290 positive cell-days matched. New one-/seven-day counts reached maxima 12
and 18. An independent dense-calendar check matched all existing and new history
values and replayed 8,899,160 validation probabilities exactly. Metrics and daily
budget results were independently checked; historical resume/output-boundary
checks also passed. Four targeted tests covered record multiplicity, neighbourhood
membership, time-window expiry, native missingness and scratch cleanup.

These findings predate simplification; no full-data rerun is claimed here. The
current builder no longer recomputes existing history columns solely to prove the
cache again. It retains the original event-state timing, row/grid alignment and
event-source label checks. Historical publication availability remains unknown.

## Current execution

Install the experiment-local `requirements.txt` and provide the corrected cache,
frozen grid/event sources and existing coordinate-HGB prediction vectors. Run
from the repository root:

```sh
python -m experiments.ignition.recent_history.experiment
```

Default output: `artifacts/ignition_modeling/reruns/recent_history/`.
`--cache`, `--baseline` and `--output` select explicit paths. Output must be a new
directory; existing directories and archived/frozen destinations are rejected.
Baseline metrics are recomputed from aligned saved vectors. New predictions and
full per-year metrics do not overwrite historical results.

Only development history rows are built. Training uses the shared coordinate-HGB
helper with the same temporary 41-column disk matrix, removed after each fit.
All event records, own-cell/diagonal inclusion and strictly pre-issue one-/seven-day
windows are unchanged. Five fresh fits replace checkpoint replay; source/package
fingerprints and memory-monitor threads are removed. No 2017--2019 feature
construction, fitting or scoring and no final-model replacement occurs.

The selected candidate remains coordinate HGB without these two added features.

## Archive layout

This report preserves the historical scientific account. `results.json` retains
all original primary fields, the original run configuration under
`recorded_configuration`, scientific JSON documents under `supporting_results`
(keyed by original filename), and CSV records under `tables` (original filenames;
all cells remain strings). Standalone execution-verification, resume, boundary,
and optional-dependency logs are omitted; the historical checks are summarized
above and were not rerun for this move.

Recorded source paths and fingerprints describe the original executed run and
predate relocation; they are not checksums of the relocated code. The current runner has been simplified; the archived findings and numerical
results predate that refactor. Generated prerequisites remain outside this archive. Use the experiment-local `requirements.txt`; run
module commands from the repository root. The [original modelling guide](../../../docs/modeling/README.md)
retains the core dataset and frozen-evaluation context.
