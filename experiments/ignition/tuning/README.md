# Development-only HGB tuning

Historical numerical results and tables below predate the orchestration refactor; they are preserved, not a claim of a new full-data reproduction. Historical verification conclusions remain evidence about that original run.

This follow-up changes only histogram gradient boosting hyperparameters. It does
not change the 36 source predictors, labels, grid, missingness handling, or
chronological folds, and it does not replace the original frozen model or its
2019 test results. This remains a retrospective ignition hindcast, not an
operational forecast or a fire-spread model.

## Development results

The original 40-iteration baseline reproduced its recorded AP **exactly in every
development year**. Increasing to 80 iterations improved mean AP by **6.45%** and
improved four of five years; 160 iterations performed worse than 80. The iteration
stage therefore selected 80, rather than assuming that more trees always help.

| Configuration | Mean AP | Mean ROC-AUC | Mean Brier | Mean log loss |
| --- | ---: | ---: | ---: | ---: |
| 40 iterations (baseline) | 0.00644950 | 0.867833 | 0.00037914 | 0.00291759 |
| 80 iterations | 0.00686547 | 0.869674 | 0.00037901 | 0.00290791 |
| 160 iterations | 0.00659376 | 0.868612 | 0.00037908 | 0.00291129 |
| 80 iterations; L2 0.1 | 0.00388566 | 0.865221 | 0.00040370 | 0.00304711 |
| 80 iterations; L2 0 | 0.00240674 | 0.835628 | 0.00106819 | 0.01390174 |
| 80 iterations; 31 leaves | 0.00619101 | 0.867979 | 0.00037944 | 0.00292401 |
| 80 iterations; minimum leaf size 30 | 0.00623901 | 0.870057 | 0.00037915 | 0.00290862 |

Reducing L2 worsened AP in **all five years** at both tested values. The search
therefore retained L2 1. Weaker regularization was a plausible hypothesis, but
the actual results reject it for these configurations; removing L2 also worsened
probability errors substantially.

Neither capacity change improved mean AP. Minimum leaf size 30 slightly improved
mean ROC-AUC, but worsened the predeclared primary ranking metric; it was not
selected. All rows use learning rate 0.1 and no class weighting. Unless stated
otherwise, L2 is 1, maximum leaves 15, and minimum leaf size 100.

**Selected development configuration:** 80 iterations, L2 1, 15 maximum leaves,
100 minimum samples per leaf, learning rate 0.1, no class weighting.

| Validation year | Original 40-iteration AP | Selected 80-iteration AP | Relative change |
| --- | ---: | ---: | ---: |
| 2012 | 0.00831164 | 0.00889350 | +7.00% |
| 2013 | 0.01119227 | 0.01152891 | +3.01% |
| 2014 | 0.00143027 | 0.00139021 | -2.80% |
| 2015 | 0.00376731 | 0.00384518 | +2.07% |
| 2016 | 0.00754599 | 0.00866953 | +14.89% |

The result is a **modest development improvement, not a breakthrough**. Probability
metric improvements are small, one development year worsens, and no statistical
significance test or new held-out evaluation was performed. The experiments do
not establish that a fundamental training bug caused the original performance.
They also do not remove the existing retrospective-availability, frozen-grid,
target-scope, history-censoring, or false-alert limitations. AP is a ranking
measure, not the percentage of alerts that are correct.

## Experiment protocol

Each stage selects the highest unweighted mean average precision (AP) over the
five expanding development folds: train from 2010 through the preceding year,
then validate on 2012, 2013, 2014, 2015, or 2016. Every validation year retains all
1,779,832 cell-days at natural prevalence. Exact ties retain candidate order,
with the unchanged configuration listed first.

| Stage | Changes | Held fixed |
| --- | --- | --- |
| Iterations | 40, 80, 160 | Unweighted; learning rate 0.1; 15 leaves; minimum leaf size 100; L2 1 |
| L2 | 1, 0.1, 0 | Selected iterations; all other parameters unchanged |
| Capacity | Baseline versus 31 leaves, or minimum leaf size 30, separately | Selected iterations and L2; no joint leaf/minimum-size change |

Iteration prefixes share one 160-iteration fit per fold. The prefix probabilities
are regression-tested against a separately fitted shorter model. This gives 35
candidate/fold evaluations from 25 fits. It is a small sequential search, not
an exhaustive joint optimization. Every fit uses all training rows, seed 385,
two threads, native NaNs, the history-censor indicator, and no random internal
early stopping or resampling.

The runner never fits or evaluates 2017--2019. No calibrator, operating threshold,
new final-test score, or deployment-model refit is produced by these experiments.

## Rebuilt data and provenance

The missing large artifacts were reconstructed using the committed frozen grid,
selected events, terrain summary, and checksum-pinned CWFIS archive. No new
spatial-source vintage or feature family was introduced.

The rebuilt original CSV exactly matches the historically audited input:

- Bytes: **6,542,580,992**.
- SHA-256: `8791c96e460e6294791bbbf1ad0d6aad68e31a98be28dbcc6060463f94ccfc9d`.
- Universe: **17,798,320 rows**, **9,673 cells**, **1,840 dates**, **7,785 positive cell-days**.
- Corrected cache: `ignition-v1-weather-asof-global-date-v2`.

Exact byte identity means the original 277 source-data checks remain applicable;
that original scan was not rerun merely to reconfirm identical bytes. The
corrected cache was freshly audited over every row, including label/grid
alignment, physical/null/quality constraints, independently reconstructed
seven-day rainfall across 1,780 dates, and 12 representative raw-station joins.

Compact reconstruction and fresh-cache evidence is in
[`results.json` → `supporting_results["rebuild_audit.json"]` — supporting_results["rebuild_audit.json"]](results.json). Source archives, full panels, numerical
cache, scratch matrices and prediction vectors remain ignored generated files.

All eight shared training-module fingerprints and all shared pinned package
versions match the original executed run. The cache-manifest hash differs only
because the new manifest omits two original post-audit annotations and uses LF
rather than Windows CRLF: restoring those annotations and CRLF **in memory**
reproduces the original manifest hash exactly. The actual cache and recorded
tuning configuration were not rewritten. See
[`results.json` → `supporting_results["reconstruction_equivalence.json"]` — supporting_results["reconstruction_equivalence.json"]](results.json).

## Archive layout

This report preserves the historical scientific account. `results.json` retains
all original primary fields, the original run configuration under
`recorded_configuration`, scientific JSON documents under `supporting_results`
(keyed by original filename), and CSV records under `tables` (original filenames;
all cells remain strings). Standalone execution-verification, resume, boundary,
and optional-dependency logs are omitted; the historical checks are summarized
above and were not rerun for this move.

Recorded source paths and fingerprints describe the original executed run and
predate relocation/refactoring; they are not checksums of the current code.
Current runners do not use them as resume gates. Generated prerequisites
remain outside this archive. Use the experiment-local `requirements.txt`; run
module commands from the repository root. The [original modelling guide](../../../docs/modeling/README.md)
retains the core dataset and frozen-evaluation context.

## Current reproduction

Use the corrected full-row cache and the modeling dependencies in `requirements.txt`.

```sh
python -m experiments.ignition.tuning.experiment
```

Default output: `artifacts/ignition_modeling/reruns/tuning/`. Use `--cache` and `--output` for explicit paths; `--help` lists the real input options without reading data. Choose a new output directory for each invocation. Archived results and the saved selected-model pickle are not overwritten. Results include full candidate/fold metrics and the original probability NPZ basenames. No reserved-year (2017--2019) fitting or evaluation occurs.

Shared `common.py` handles bounded disk-backed fitting, batched prediction and scientific input checks. Script hashes, environment-equality gates, protected-file inventories and checkpoint/model replay for resuming runs have been removed. Each invocation is fresh; existing output directories are rejected. The 40/80/160 stage still scores actual prefixes of one 160-iteration fit per fold; later stages reuse already-computed candidate results within that invocation.
