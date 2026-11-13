# Bounded randomized HGB search

Historical numerical results and tables below predate the orchestration refactor; they are preserved, not a claim of a new full-data reproduction. Historical verification conclusions remain evidence about that original run.

This experiment uses scikit-learn **`RandomizedSearchCV`**, not an exhaustive grid
or a custom substitute. It tests whether joint parameter combinations improve on
the existing coordinate/15-leaf development candidate. The search budget and
parameter ranges below were fixed before scoring any new configuration.

## Executed results

**Retain the existing coordinate/15-leaf baseline.** All 40 new fits completed.
None of the eight sampled configurations beat it in any development year.
Mean AP below is rounded; the [complete results](results.json) preserve precision.

| Configuration | Mean development AP | Relative change versus baseline |
| --- | ---: | ---: |
| Existing coordinate/15 baseline | 0.006965525 | — |
| C1 | 0.004299647 | -38.27% |
| C2 | 0.004565786 | -34.45% |
| C3 | 0.005322610 | -23.59% |
| C4: best sampled | 0.005827515 | -16.34% |
| C5 | 0.005827410 | -16.34% |
| C6 | 0.004519111 | -35.12% |
| C7 | 0.004361194 | -37.39% |
| C8 | 0.005254073 | -24.57% |

The best sampled configuration, C4, uses 160 iterations, learning rate 0.05,
L2 10, minimum leaf size 50 and maximum 15 leaves. Its deficit is not caused
by averaging a few wins against a bad year: it loses on AP in all five years.

| Validation year | Existing baseline AP | Best sampled C4 AP | Relative change |
| --- | ---: | ---: | ---: |
| 2012 | 0.010238445 | 0.009840821 | -3.88% |
| 2013 | 0.009042434 | 0.004108910 | -54.56% |
| 2014 | 0.001749552 | 0.001651641 | -5.60% |
| 2015 | 0.004511449 | 0.004285927 | -5.00% |
| 2016 | 0.009285745 | 0.009250278 | -0.38% |

The primary score matters: C4 improves mean ROC-AUC and log loss slightly,
despite worse AP and Brier. It therefore does not win the predeclared AP
comparison. Better broad discrimination or log loss is not interchangeable with
better precision–recall ranking in this rare-event task.

| Secondary metric | Existing baseline | Best sampled C4 |
| --- | ---: | ---: |
| Mean ROC-AUC (higher better) | 0.8724773144 | 0.8749577324 |
| Mean Brier (lower better) | 0.0003788770 | 0.0003789243 |
| Mean log loss (lower better) | 0.0028927973 | 0.0028889128 |

What we learned:

- The manual development choice survives this bounded randomized search.
  There is no new AP improvement to promote.
- Slower learning, different leaf budgets and/or stronger regularization did
  not help in these sampled combinations. Because multiple settings changed
  together, the experiment cannot isolate one parameter as the cause.
- Eight samples out of 162 do not establish global optimality or a feature
  performance ceiling. In particular, no learning-rate-0.1 combination was
  drawn; the control still provides that existing reference.
- The largest C4 AP loss is in 2013, but every other year also declines.
  We do not change the selection rule or draw more configurations after
  seeing the negative result.

Decision: stop this search at the approved budget and retain 80 iterations,
learning rate 0.1, L2 1, minimum leaf size 100 and maximum 15 leaves with
coordinates. This remains a development candidate, not a newly validated
held-out or operational model.

## Historical independent verification

- AP, ROC-AUC, Brier and log loss independently recomputed for **45 full
  prediction vectors**: 40 new candidate/fold vectors and five baseline controls.
- All **40 fitted models** checked for actual hyperparameters, seed, 39-column
  transformed schema, full chronological training counts and unweighted fitting.
- C4's saved model/preprocessor replayed all five full validation vectors within
  `1e-14`; labels, prediction/model hashes, score ranks and selection reproduced.
- Cache, grid and training-code fingerprints, plus all 11 protected previous
  report/result fingerprints, remained unchanged.
- Actual CLI resume reloaded 40 fitted checkpoints with **zero additional model
  fits**; all **123** configuration/result/CSV/model/prediction/metadata files
  remained byte-identical.
- An actual CLI attempt to use the coordinate baseline directory as search
  output was rejected before fitting, without changing protected outputs.
- No 2017--2019 model fitting/evaluation or final-model refit occurred.
  Nothing was committed.

Evidence: [predeclared configuration — recorded_configuration](results.json),
[complete results](results.json), [candidate CSV — tables["development_candidates.csv"]](results.json),
independent audit (historical verification summarized here; standalone log omitted), actual resume proof (historical verification summarized here; standalone log omitted),
and output-boundary proof (historical verification summarized here; standalone log omitted). Large fitted models and complete
prediction arrays remain ignored generated artifacts.

## Protocol

- Eight sampled configurations, five expanding chronological folds: **40 fits**.
- Validation years 2012--2016; each training partition starts in 2010 and ends
  before its validation year. Complete years/cell-days stay together.
- Fixed cell-centre coordinates, original weather/history/terrain/calendar inputs,
  native missingness, history-censor indicator, no class weighting or sampling.
- All validation rows retained at natural prevalence. Primary score is equally
  weighted mean year AP, with per-year AP and mean ROC-AUC/Brier/log loss retained.
- Search and estimator seed 385; one fit at a time, two threads per fit.
- `refit=False`, `return_train_score=False`, `error_score="raise"`. No calibration,
  operating-threshold selection, final-model fitting, or 2017--2019 evaluation.
- Compare the search winner against the existing baseline; an exact tie retains
  that baseline, then sample order. A search winner need not beat the baseline.

| Parameter | Allowed values |
| --- | --- |
| Learning rate | 0.03, 0.05, 0.1 |
| Iterations | 80, 160 |
| L2 regularization | 0.1, 1, 10 |
| Minimum samples per leaf | 50, 100, 200 |
| Maximum leaves per tree | 7, 15, 31 |

There are 162 combinations; only eight are sampled without replacement. The fixed
seed happens to sample no learning-rate-0.1 candidate, although the retained
baseline uses 0.1. We do not replace inconvenient samples after looking at them.
This is a small exploratory search, not comprehensive optimization.

## Sampled configurations

These identifiers follow `RandomizedSearchCV` sample order, not score order.
The control remains 80 iterations, learning rate 0.1, L2 1, minimum leaf size
100 and maximum 15 leaves.

| Candidate | Iterations | Learning rate | L2 | Minimum leaf size | Maximum leaves |
| --- | ---: | ---: | ---: | ---: | ---: |
| C1 | 80 | 0.03 | 0.1 | 50 | 7 |
| C2 | 80 | 0.05 | 10 | 100 | 7 |
| C3 | 80 | 0.05 | 1 | 50 | 7 |
| C4 | 160 | 0.05 | 10 | 50 | 15 |
| C5 | 160 | 0.05 | 10 | 100 | 15 |
| C6 | 80 | 0.05 | 0.1 | 100 | 31 |
| C7 | 80 | 0.05 | 0.1 | 50 | 7 |
| C8 | 160 | 0.05 | 10 | 100 | 7 |

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
python -m experiments.ignition.randomized.experiment
```

Default output: `artifacts/ignition_modeling/reruns/randomized/`. Use `--cache` and `--output` for explicit paths; `--help` lists the real input options without reading data. Choose a new output directory for each invocation. Archived results and the saved selected-model pickle are not overwritten. Results include full candidate/fold metrics and the original probability NPZ basenames. No reserved-year (2017--2019) fitting or evaluation occurs.

Shared `common.py` handles bounded disk-backed fitting, batched prediction and scientific input checks. Script hashes, environment-equality gates, protected-file inventories and checkpoint/model replay for resuming runs have been removed. Each invocation is fresh; existing output directories are rejected. Actual `RandomizedSearchCV` still executes exactly eight seeded draws with AP scoring; full-parameter directories avoid learning-rate filename collisions. Only row positions enter sklearn CV; these are not model predictors.
