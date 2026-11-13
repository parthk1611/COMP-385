# Complete local ignition HGB search

Historical numerical results and tables below predate the orchestration refactor; they are preserved, not a claim of a new full-data reproduction. Historical verification conclusions remain evidence about that original run.

This follow-up replaces the sparse broad draw with a complete local grid around
our existing coordinate/15-leaf candidate. It uses actual scikit-learn
`GridSearchCV` because coverage of every local pair is the purpose, not another
random sample. No prior experiment or held-out evaluation is overwritten.

## Executed results

**Retain the existing coordinate/15-leaf configuration.** Every point in the
predeclared grid was covered, but no new configuration improved mean AP.
Cells below contain mean AP over the five development years; the centre is the
retained baseline. Values are rounded; [results.json](results.json) retains precision.

| Learning rate / iterations | L2 = 0.5 | L2 = 1 | L2 = 2 |
| --- | ---: | ---: | ---: |
| 0.08 / 100 | 0.005741059 | 0.006367329 | 0.005855580 |
| 0.10 / 80 | 0.004985555 | **0.006965525** | 0.006019362 |
| 0.125 / 64 | 0.004133932 | 0.005342590 | 0.005661471 |

The best new configuration is learning rate 0.08, 100 iterations, L2 1,
15 maximum leaves and minimum leaf size 100. Its mean AP is **8.59% lower**;
only its 2015 AP exceeds the baseline.

| Validation year | Baseline AP | Best new AP | Relative change |
| --- | ---: | ---: | ---: |
| 2012 | 0.010238445 | 0.010143112 | -0.93% |
| 2013 | 0.009042434 | 0.006489030 | -28.24% |
| 2014 | 0.001749552 | 0.001621149 | -7.34% |
| 2015 | 0.004511449 | 0.004588637 | +1.71% |
| 2016 | 0.009285745 | 0.008994718 | -3.13% |

About 85.4% of this best-new configuration's net AP deficit comes from 2013.
That is a year-level score decomposition, not proof of a particular hotspot or
tree-split cause. Excluding 2013 descriptively, its other-four-year mean AP is
still 1.70% lower; the selection criterion itself continues to include all years.

The new setting improves all three secondary mean scores slightly:

| Metric | Baseline | Best new |
| --- | ---: | ---: |
| ROC-AUC (higher better) | 0.8724773144 | 0.8734953335 |
| Brier (lower better) | 0.0003788770 | 0.0003788494 |
| Log loss (lower better) | 0.0028927973 | 0.0028901998 |

Those small gains do not override the predeclared precision–recall objective.
“Best” here means highest mean AP, not simultaneously best on every metric.
The complete local coverage removes the sparse-draw explanation within this
particular neighborhood, but cannot establish global optimality. This is a sharp
local AP maximum on repeatedly used development folds, not independent evidence
of statistical significance or operational performance.

Decision: keep coordinates with 80 iterations, learning rate 0.1, L2 1,
15 maximum leaves and minimum leaf size 100. Stop at the agreed eight new
configurations. No final-model promotion, held-out evaluation or commits.

The independent audit verified all nine grid points, recomputed core metrics
for **45 prediction vectors**, checked all **40 fitted models**, replayed the
best new model's complete validation vectors for all five years within `1e-14`,
and verified unchanged cache/grid/code and 13 protected prior-output fingerprints.
The review and checks found no demonstrated fundamental training/label/split
failure; the checkpoint gaps below were latent validation weaknesses, not
evidence that historical results were wrong.

Evidence: [predeclared configuration — recorded_configuration](results.json),
[complete results](results.json), [candidate CSV — tables["development_candidates.csv"]](results.json),
and independent audit (historical verification summarized here; standalone log omitted).

An actual CLI resume revalidated complete checkpoint metrics and fitted-model
semantics, reloaded all 40 models with **zero additional fits**, and retained all
**123** configuration/result/CSV/model/prediction/metadata files byte-identically.
The protected-output CLI boundary also rejected the baseline directory before
fitting. See resume proof (historical verification summarized here; standalone log omitted) and
output-boundary proof (historical verification summarized here; standalone log omitted).

## Historical predeclared design

Cross these coupled learning-rate/iteration settings with L2 values **0.5, 1, 2**:

| Learning rate | Iterations | Learning rate × iterations |
| --- | ---: | ---: |
| 0.08 | 100 | 8 |
| 0.10 | 80 | 8 |
| 0.125 | 64 | 8 |

This makes nine total configurations, including the existing baseline
(0.1, 80 iterations, L2 1). Its verified five-fold predictions are reused; the
other eight require **40 new fits**. Maximum leaves stays 15, minimum leaf size
100, class weighting disabled, estimator seed 385, one fit at a time and two
threads per fit. The same coordinates, 36 original predictors and history-censor
flag produce 39 transformed columns. Missing weather/terrain stays missing.

The matched rate/iteration product is a rough budget control, not equivalent
boosting paths, guaranteed convergence or equal computation. It avoids spending
most of this small search on slower learning without compensating iterations.
The grid varies only that paired setting and regularization, rather than changing
capacity/minimum leaf size simultaneously. Every rate and L2 value receives full
coverage, including the existing best setting and both neighboring directions.

Five full-row expanding chronological folds train from 2010 and validate
2012--2016. Primary selection remains unweighted mean year AP; exact ties retain
the baseline, then grid order. Per-year AP and secondary ROC-AUC, Brier and log
loss remain visible. `refit=False`, `return_train_score=False`, `error_score="raise"`.
No 2017--2019 model fitting/evaluation, calibration, threshold selection or final
model refit occurs. No additional candidates are added after seeing scores.

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

Use the corrected full-row cache and the modeling dependencies in `requirements.txt`. Trusted saved baseline fold predictions are required (`--baseline`); their labels/probability ranges and available scientific metadata are checked, and full metrics are recomputed.

```sh
python -m experiments.ignition.local_search.experiment
```

Default output: `artifacts/ignition_modeling/reruns/local_search/`. Use `--cache` and `--output` for explicit paths; `--help` lists the real input options without reading data. Choose a new output directory for each invocation. Archived results and the saved selected-model pickle are not overwritten. Results include full candidate/fold metrics and the original probability NPZ basenames. No reserved-year (2017--2019) fitting or evaluation occurs.

Shared `common.py` handles bounded disk-backed fitting, batched prediction and scientific input checks. Script hashes, environment-equality gates, protected-file inventories and checkpoint/model replay for resuming runs have been removed. Each invocation is fresh; existing output directories are rejected. Actual `GridSearchCV` still fits the eight new grid points (40 fold fits), and trusted baseline predictions complete the nine-point comparison. Baseline-first ties and historical numerical tables remain unchanged. Only row positions enter sklearn CV; these are not model predictors.
