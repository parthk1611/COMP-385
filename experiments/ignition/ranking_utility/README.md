# Coordinate-HGB daily ranking utility

Status: completed and independently reconstructed. Development analysis only;
no new fits, calibration, 2017--2019 scoring, or commits.

## Question and scope

Does the selected coordinate-HGB concentrate recorded ignition cell-days into
small daily review budgets? This evaluates ranking utility, not whether a
particular alert is likely to become a fire, and not fire spread.

Reuse the five saved, expanding-window validation prediction vectors for
2012--2016: 920 local issue dates, 8,899,160 cell-days, and 3,384 positive
cell-days. These are the same development years used for model/feature selection;
the results are not a new independent test and may be selection-optimistic.
The corrected weather cache, labels, missingness, and grid are unchanged.

The fixed development candidate has two static EPSG:3978 cell-centre predictors,
80 HGB iterations, learning rate 0.1, L2 1, 15 maximum leaves, minimum leaf size
100, no class weighting, and seed 385. This report fixes its specification for
analysis; it does not replace the original probability bundle or original
final-study freeze.

## Daily policy and definitions

For each local date, rank all 9,673 cells by predicted score. Select exactly
`ceil(budget_percent * 9673 / 100)` cells: 97, 194, or 484. Break equal scores by
ascending immutable `grid_id`, without consulting labels. Grid IDs resolve ties
only; they are not additional fitted features.

- Precision: positive selected cell-days / selected cell-days.
- Recall: positive selected cell-days / all positive cell-days.
- False alerts: selected cell-days without a recorded ignition. This is a label
  definition, not evidence about operational warning outcomes or unrecorded fires.
- Daily rates include every issue date, including zero-event dates.
- Random comparator: select the same number uniformly from all cells separately
  each day; expected positives are `k * daily_positives / 9673`.
- Pooled recall weights years by their positive counts; it is not mean-year recall.
- Each positive is a cell-day with at least one ignition, not a count of incidents.

The daily cutoff uses scores only. It is not a calibrated probability threshold
and does not require a new calibration fit.

## Pooled 2012--2016 results

| Daily budget | Cells/day | Captured positive cell-days | Recall | Precision | False alerts/day | Recall lift over random |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Top 1% | 97 | 413 / 3,384 | 12.20% | 0.463% | 96.55 | 12.17x |
| Top 2% | 194 | 629 / 3,384 | 18.59% | 0.352% | 193.32 | 9.27x |
| Top 5% | 484 | 1,080 / 3,384 | 31.91% | 0.243% | 482.83 | 6.38x |

There is meaningful concentration relative to random allocation, but very low
absolute precision. Even the largest budget misses 68.09% of positive cell-days.
This supports investigating prioritization; it does not establish acceptable
operational cost, accurate individual alerts, or incremental value over a strong
historical/spatial baseline. No budget is selected as an operating policy.

## Year consistency

| Validation year | Positive cell-days | Recall at 1% | Recall at 2% | Recall at 5% |
| --- | ---: | ---: | ---: | ---: |
| 2012 | 1,407 | 11.51% | 19.12% | 32.76% |
| 2013 | 527 | 10.44% | 14.42% | 24.48% |
| 2014 | 293 | 13.65% | 19.45% | 32.76% |
| 2015 | 584 | 15.07% | 21.92% | 35.79% |
| 2016 | 573 | 11.87% | 17.28% | 32.29% |

All years beat random selection at every budget. 2013 is weakest on these recall
measures; 2015 is strongest. A weak yearly AP does not imply equally weak daily
recall: AP and fixed daily review budgets measure different ranking questions.
These descriptive comparisons do not supply statistical significance or causal
explanations for year differences.

## Weather coverage

First apply the global daily ranking, then stratify those same selected cells by
`cwfis_missing`. Never independently rerank within each weather group.
"Covered" means this flag is zero, not that every weather/FWI field is complete.

| Weather group | Positive cell-days | Recall at 1% | Recall at 2% | Recall at 5% | Precision at 1% |
| --- | ---: | ---: | ---: | ---: | ---: |
| Covered | 3,357 | 12.27% | 18.71% | 32.11% | 0.468% |
| Missing | 27 | 3.70% | 3.70% | 7.41% | 0.080% |

Missing-weather rows account for 533,059 cell-days, approximately 6% of this
validation universe. Only one of their 27 positive cell-days is captured at the
1% and 2% budgets, and two at 5%. This is a weak-coverage subgroup, but too small
for a stable performance conclusion. Its lower observed prevalence and different
selected allocation also prevent attributing the difference to missing weather
alone. Retain these rows and flags; do not hide the subgroup through deletion or
zero filling. Complete per-year/group counts and false-alert rates are in
[budget_metrics.csv — tables["budget_metrics.csv"]](results.json).

## Tie sensitivity and verification

There are 61, 58, and 71 dates with ambiguous cutoff ties at the three budgets.
Allowing every possible label allocation within each boundary tie changes pooled
captured positives only from 413 to 414, 629 to 630, and 1,080 to 1,081,
respectively. The result is not driven by the chosen ID tie-break.

The primary calculation used a full score/ID lexicographic sort. A separate
checker reconstructed every selection using `numpy.partition` for the threshold
and Python ID sorting only at ties. It verified all 2,760 daily selections by
exact selected-grid SHA-256, all 54 aggregate rows, weather partitions, rates,
random expectations, attainable tie bounds, and CSV/JSON agreement. Cache and
prediction fingerprints matched; 20 protected prior artifacts remained unchanged.
See verification.json (historical verification summarized here; standalone log omitted).

No permanent training code was changed. Historical verification predates the
entry-point simplification; its logs and fingerprints are not runtime inputs.

## Final-evaluation decision

Stop development hyperparameter searches and retain coordinate-HGB as the
preferred development candidate. This analysis does not authorize or execute a
final refit, calibration, or new reserved-year scoring.

[The recorded proposal — supporting_results["candidate_and_final_evaluation_proposal.json"]](results.json), if
separately approved, is one 2010--2016 base fit, 2017 calibration fitting, 2018
calibration/policy selection, then a 2019 retrospective evaluation. Specify the
calibration alternatives and policy criterion before executing that stage; do
not choose a budget here without an application capacity/cost rationale.

Important: the original study already evaluated 2019, as recorded in
[the original freeze](../../../docs/modeling/final_freeze.json) and
[the original report](../../../docs/modeling/final_report.md). A new coordinate-model evaluation there
must not be described as a fresh blind test. This remains a retrospective,
archive-based hindcast, conditional on the study's frozen grid universe; it is
not validated operational forecasting or province-wide deployment evidence.

If one additional small investigation is wanted before reporting, compare these
same budgets with a training-only historical spatial baseline. Random selection
is a weak comparator. That comparison was not performed here.

## Archive layout

This report preserves the historical scientific account. `results.json` retains
all original primary fields, the original run configuration under
`recorded_configuration`, scientific JSON documents under `supporting_results`
(keyed by original filename), and CSV records under `tables` (original filenames;
all cells remain strings). Standalone execution-verification, resume, boundary,
and optional-dependency logs are omitted; the historical checks are summarized
above and were not rerun for this move.

## Recomputing the analysis

From the repository root, with this folder's requirements installed:

```sh
python -m experiments.ignition.ranking_utility.experiment --help
python -m experiments.ignition.ranking_utility.experiment \
  --cache data/interim/ignition_modeling_cache \
  --predictions artifacts/ignition_modeling/hgb_coordinates \
  --output artifacts/ignition_modeling/reruns/ranking_utility
```

Requires the existing corrected cache, frozen grid CSV, and five original
`fold_<year>_iter_80_l2_1p0_leaves_15_min_100.npz` prediction files.
Labels, probabilities, dates, and full daily grid alignment are checked. Metrics
are recomputed from saved predictions, not copied from this report. Importing
or requesting help does not load data or run the analysis. The output directory
must be new; archived results and saved models are never overwritten. Outputs
are configuration/results JSON and daily/aggregate CSV, without protected-file
snapshots, resume inputs, or generated final-evaluation proposals. No fitting,
native rebuilds, or reserved-year scoring occurs. The historical numerical
report above predates this runtime refactor and has not been rerun here.

The [original modelling guide](../../../docs/modeling/README.md) retains the
core dataset and frozen-evaluation context.
