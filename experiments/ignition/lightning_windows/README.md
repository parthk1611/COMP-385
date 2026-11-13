# Separate lightning-window ablations

Outcome: **24-hour lightning only is the numerical mean-AP winner**, improving
0.77% relative to coordinate HGB. The gain is small and driven by 2013; AP falls
in the other four years. Seven-day lightning alone lowers AP in every year.
This is a marginal development result, not a demonstrated significant upgrade.

This follow-up isolates the two CG-density windows from the
[combined-lightning experiment](../lightning/README.md). It adds no roads or other
source family and does not change HGB settings, labels, corrected weather,
missingness, coordinates, or the original frozen evaluation.

## Conditions

| Condition | Additional lightning inputs | Execution |
| --- | --- | --- |
| Coordinate HGB | None | Reuse verified predictions |
| Both windows | 24-hour and seven-day CG density | Reuse verified predictions |
| `24h_only` | 24-hour CG density only | Five new chronological fits |
| `7d_only` | Seven-day CG density only | Five new chronological fits |

The excluded lightning field is physically absent from each new model matrix,
not replaced by a constant or a placeholder. Each single-window model has
**39 raw predictors and 40 transformed inputs**, versus 38/39 for coordinate
HGB and 40/41 for the combined-lightning model. Original same-cell and
neighbourhood history at 30/365 days remain; the failed recent-history additions
are not used.

Both new conditions reuse the same two-column source cache
covering all 12,458,824 development rows. Selecting a column does not rebuild or
overwrite that cache. Every negative row and missing-weather row is retained.
No new source download or dependency is required beyond the previous lightning
experiment environment.

## Fixed protocol

- Train on expanding 2010-through-prior-year partitions; validate on 2012--2016.
- Every validation year contains all 1,779,832 cell-days at natural prevalence.
- HGB: 80 iterations, learning rate 0.1, L2 1, 15 maximum leaves, minimum leaf
  samples 100, seed 385, no class weighting or early stopping, two CPU threads.
- Primary: highest unweighted mean yearly AP across all four conditions.
  Exact ties use the predeclared order: coordinate baseline, both windows,
  24-hour only, seven-day only.
- Secondary metrics and daily-budget utility describe trade-offs; they do not
  replace the primary rule after results are observed.
- Ten new fits total. No further window search, parameter search, calibration,
  final-model promotion, or 2017--2019 feature construction/fitting/scoring.
- These development years have been reused for multiple investigations. A small
  winning difference is not an independent-test or significance result.

The source definitions remain unchanged: area-weighted native-grid detected CG
flash density, not exact strike counts inside the target squares. The trailing
windows contain eight or 56 fully completed three-hour intervals ending at
03:00 UTC, one hour before local midnight for the May--October study dates.
They are not exact previous-local-calendar-day totals. Unknown source coverage
is not zero; detector zeros do not certify sensor uptime. Historical publication
latency is unknown, so this remains a retrospective hindcast.

## Reproduction

Prerequisites: the corrected cache, coordinate and combined-lightning fold
predictions, and the two-column `features.npy` beside its scientific `audit.json`.
They are generated artifacts, not supplied in a fresh clone. Install the local
`requirements.txt` in the modelling environment.

```sh
python -m experiments.ignition.lightning_windows.experiment
```

This command runs both single-window conditions (ten fits) and writes the
four-way comparison. `--cache`, `--baseline`, `--combined`, `--features`, and
`--output` select explicit paths; `--features` may point to a freshly built
combined-lightning feature file. Feature definitions, complete development
shape, nonnegative-or-NaN values and cache-grid row alignment remain checked.
Reference metrics are recomputed from aligned fold predictions, not copied from
archived summaries. No original combined-run configuration or verification log
is required.

Outputs default to `artifacts/ignition_modeling/reruns/lightning_windows/`,
with separate condition directories. Existing output directories are rejected;
there is no resume/model replay, environment-equality or source-code hash gate.
Shared fixed-HGB fitting receives only the selected density after coordinates.
Owned temporary matrices are removed after fitting. Historical numerical
results below predate the refactor; no full-data reproduction is claimed.
Original features, archived results, saved pickles and the frozen evaluation
remain unchanged; there is no reserved-year construction, fitting or scoring.

## Results

| Condition | Mean yearly AP | Relative change vs coordinate HGB |
| --- | ---: | ---: |
| Coordinate HGB | 0.0069655251 | Reference |
| 24-hour lightning only | 0.0070194942 | +0.77% |
| Seven-day lightning only | 0.0065546845 | -5.90% |
| Both lightning windows | 0.0067628072 | -2.91% |

The predeclared selection rule chooses `24h_only`. Its small win should not be
described as a robust improvement: one year supplies the benefit, four worsen,
and these are repeatedly reused development folds. No model bundle or original
final evaluation is automatically replaced. If retaining a lightning feature
on this evidence, retain only the 24-hour window; do not claim a large gain.

| Validation year | Coordinate AP | 24-hour-only AP | Seven-day-only AP | Both-window AP |
| --- | ---: | ---: | ---: | ---: |
| 2012 | 0.01023845 | 0.00944543 | 0.00988717 | 0.00913086 |
| 2013 | 0.00904243 | 0.01053066 | 0.00783578 | 0.01086787 |
| 2014 | 0.00174955 | 0.00162603 | 0.00164744 | 0.00160872 |
| 2015 | 0.00451145 | 0.00439965 | 0.00434733 | 0.00426458 |
| 2016 | 0.00928574 | 0.00909570 | 0.00905570 | 0.00794201 |

| Condition | Mean yearly ROC-AUC | Mean yearly Brier | Mean yearly log loss |
| --- | ---: | ---: | ---: |
| Coordinate HGB | 0.87247731 | 0.00037887699 | 0.00289279732 |
| 24-hour only | 0.87334907 | 0.00037890321 | 0.00289151361 |
| Seven-day only | 0.87279647 | 0.00037888997 | 0.00289456168 |
| Both windows | 0.87249834 | 0.00037895444 | 0.00289509235 |

The 24-hour condition also improves mean ROC-AUC and log loss slightly, while
Brier worsens slightly. These do not establish meaningful operational value.
The result supports isolating predictors rather than assuming their joint
addition represents each individually. It does not identify why the longer
window performs worse; redundancy, smoothing and altered fitted splits remain
possible explanations, not proven causes.

## Daily-budget trade-offs

Rank the same 9,673 cells separately each day, select the top 97/194/484 cells,
and use immutable ascending `grid_id` ties without labels. Pooled recall uses
the same 3,384 positive cell-days across 920 dates:

| Daily budget | Coordinate recall | 24-hour-only recall | Seven-day-only recall | Both-window recall |
| --- | ---: | ---: | ---: | ---: |
| Top 1% | 12.20% | 12.44% | 12.41% | 12.26% |
| Top 2% | 18.59% | 19.00% | 19.21% | 19.00% |
| Top 5% | 31.91% | 31.89% | 32.03% | 32.12% |

There is no uniformly best condition at all budgets. These pooled fixed-budget
metrics answer a different question from unweighted mean yearly AP. Do not
switch the primary criterion after seeing the trade-off. Precision remains very
low, and no operating budget has been selected.

For 24-hour only, possible cutoff-tie allocations give pooled captured-positive
ranges 420--421, 643--643 and 1078--1079 at the three budgets; deterministic
selection gives 421, 643 and 1079. These tiny boundary differences do not change
the broad conclusion. Full year/weather-group counts, precision, false-alert
rates, and all four conditions' tie diagnostics are in
[daily_budget_results.json — supporting_results["daily_budget_results.json"]](results.json) and
[daily_budget_comparison.csv — tables["daily_budget_comparison.csv"]](results.json). Weather groups
stratify globally selected cells rather than reranking within groups.

## Verification and preservation

Three targeted tests passed: each model learns its selected density while
predictions remain exactly invariant to changes in the excluded field, and a
post-allocation fit failure removes only owned scratch files. Native weather/
history NaNs are retained. Discovery also cleanly skips the optional test module
when `h5py` is unavailable; see
optional_dependency_verification.json (historical verification summarized here; standalone log omitted).

A separate checker constructed the actual forty-column matrices independently:
36 corrected raw inputs, the censor flag, two cell centres, and exactly the
selected density. All **17,798,320 new-model validation probability values**
replayed exactly. This count is two conditions times five 2012--2016 validation
years, not scoring of the ten-year panel or reserved years.

The checker verified actual fitted parameters and class counts, all 20 metric
vectors across the four conditions, the selection rule, 216 aggregate daily-
budget/year/weather rows, old utility results, and unchanged shared-feature
bytes. All **62 unique protected original/prior files** retained their hashes.
See verification.json (historical verification summarized here; standalone log omitted).

The source cache's physical density, timing and missingness calculations were
already independently verified across all 12,458,824 development rows in
[the previous lightning study](../lightning/README.md). This study verifies
byte-identical reuse and one-column selection rather than rebuilding those
source files. Historical detector uptime/publication limitations remain; the
earlier combined-model quiet-period stress check is not a new sensitivity test
of these separately fitted models.

No roads, new source assets, additional tuning, reserved-year model evaluation,
or commits were included. The numerical winner remains development evidence
only; the original frozen model bundle is unchanged.

Historical completed-run resume checks also preserved the original artifacts.
Resume machinery and temporary checking scripts are no longer part of the
simplified runner.

## Archive layout

This report preserves the historical scientific account. `results.json` retains
all original primary fields, the original run configuration under
`recorded_configuration`, scientific JSON documents under `supporting_results`
(keyed by original filename), and CSV records under `tables` (original filenames;
all cells remain strings). Standalone execution-verification, resume, boundary,
and optional-dependency logs are omitted; the historical checks are summarized
above and were not rerun for this move.

Recorded source paths and fingerprints describe the original executed run and
predate relocation; they are not checksums of the current code. The simplified
runner uses fresh outputs rather than resume fingerprints. Generated prerequisites
remain outside this archive. Use the experiment-local `requirements.txt`; run
module commands from the repository root. The [original modelling guide](../../../docs/modeling/README.md)
retains the core dataset and frozen-evaluation context.
