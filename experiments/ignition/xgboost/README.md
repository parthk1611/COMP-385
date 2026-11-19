# Fixed CPU XGBoost ignition benchmark

One XGBoost configuration is compared with the existing coordinate HGB on the
same corrected-weather cache, raw predictor information and five chronological
development folds. The neural-network experiment is **not pursued**. This is a
bounded alternative-implementation benchmark, not a parameter search or a claim
that XGBoost is fundamentally superior.

## Executed results

**Retain coordinate HGB under the predeclared mean-AP criterion.** Five full-data
XGBoost fits completed; the complete benchmark CLI took 268.54 seconds
(approximately 4.5 minutes), excluding implementation and verification work.

| Model | Mean AP | Mean ROC-AUC | Mean Brier | Mean log loss |
| --- | ---: | ---: | ---: | ---: |
| Coordinate HGB | **0.006965525** | 0.872477314 | 0.000378877 | 0.002892797 |
| Fixed coordinate XGBoost | 0.005921247 | 0.876461446 | 0.000378983 | 0.002884807 |

XGBoost's mean AP is **14.99% lower**. It improves 2015 only, not four of the five
development years. Better mean ROC-AUC and log loss do not override the agreed
precision–recall objective; mean Brier is slightly worse.

| Validation year | HGB AP | XGBoost AP | Relative AP change |
| --- | ---: | ---: | ---: |
| 2012 | 0.010238445 | 0.009071815 | -11.39% |
| 2013 | 0.009042434 | 0.006884990 | -23.86% |
| 2014 | 0.001749552 | 0.001718555 | -1.77% |
| 2015 | 0.004511449 | 0.005087557 | +12.77% |
| 2016 | 0.009285745 | 0.006843319 | -26.30% |

Decision: keep the existing HGB as the primary development candidate. This
benchmark rejects this **one fixed XGBoost configuration**, not the entire model
family or every possible tuning choice. HGB has received substantially more
tuning. We do not add a search or claim fundamental superiority after this result.
The neural-network experiment remains dropped.

## Historical independent verification

Before this refactor, the independent audit recomputed all ten prediction metric
vectors, replayed native and bundled models exactly, and checked native settings,
training-only prevalence, complete quantile passes and tree limits. Historical
resume and output-boundary checks passed. These conclusions predate this refactor;
no full-data rerun is claimed here.

## Predeclared settings

| Setting | Value |
| --- | --- |
| Implementation | `xgboost-cpu==3.4.1`, CPU `hist` |
| Objective | Unweighted `binary:logistic` |
| Trees / learning rate | 160 / 0.05 |
| Maximum depth / leaves | 4 / 15, loss-guided growth |
| Minimum child Hessian weight | 0.1 |
| L2 / L1 regularization | 1 / 0 |
| Histogram bins | 255 |
| Row / feature fraction per tree | 0.8 / 0.8 |
| Positive-class multiplier | 1 |
| Initial probability | Current training positive prevalence |
| Seed / CPU threads | 385 / 2 |

The 160 × 0.05 rate/iteration product matches HGB's 80 × 0.1 approximately as a
budget control; it does not equate training paths, convergence, tree complexity
or computation. XGBoost's child-Hessian threshold is not the same parameter as
HGB's minimum sample count. These are reasonable fixed settings, not a globally
optimized XGBoost configuration.

All training rows remain in the dataset and quantile construction. XGBoost then
uniformly samples 80% of eligible rows per tree; this is ordinary internal tree
sampling, **not negative-class undersampling or deleting missing-weather rows**.
Feature sampling is also per tree. Every validation cell-day is retained at its
natural prevalence. No class balancing or validation weights are introduced.

## Time contract and bounded-memory input

Training starts in 2010 and ends before each complete validation year in
2012--2016. There are five new full-data fits, no early stopping, and no use of
2017--2019 for fitting, calibration, thresholds or evaluation. No final-model
refit, deployment promotion or commits occur.

The same 36 raw features, explicit history-censor indicator and two static
EPSG:3978 cell-centre coordinates produce 39 transformed fields. NaNs remain
NaNs. No fitted scaling, imputation, new feature family or new source asset is
added. Cell coordinates are square centres, not incident-point locations.

A public XGBoost `DataIter` replays training rows in batches of at most 50,000.
`QuantileDMatrix` constructs compressed histogram data **from training only**;
no global float feature matrix is materialized. Native XGBoost numeric input is
float32. Prediction uses chunked `inplace_predict` on validation features, so
there is no validation-side quantile fitting. The existing HGB preprocessing
and source cache remain unchanged.

Selection uses the same external scikit-learn average precision implementation
as previous experiments, independently audited—not XGBoost's differently defined
native `aucpr`. Mean year AP is primary; per-year AP, mean ROC-AUC, Brier and log
loss remain visible. The existing HGB is retained on an exact tie. The training
`eval_metric=logloss` does not select a checkpoint: all 160 rounds run without a
validation evaluation set.

## Current execution and environment

Use the experiment-local `requirements.txt` (including `xgboost-cpu==3.4.1`),
the corrected cache, frozen grid and existing coordinate-HGB prediction vectors.
Run from the repository root:

```sh
python -m pip install -r experiments/ignition/xgboost/requirements.txt
python -m experiments.ignition.xgboost.experiment
```

Default output: `artifacts/ignition_modeling/reruns/xgboost/`.
`--cache` and `--output` select explicit paths. A new output directory is required;
existing directories and archived/frozen destinations are rejected. The runner
writes predictions and full per-year metrics without overwriting historical results.
It recomputes HGB baseline metrics from aligned saved vectors and always performs
five fresh XGBoost fits; it does not load or save model checkpoints/native exports.
Source/package-equality gates and memory-monitor threads are removed. CPU hist
parameters, all-row training quantiles and bounded validation prediction are unchanged.
No reserved-year work or final-model replacement occurs.

These reused development folds do not establish statistical significance,
independent confirmation, unseen-geography generalization or operational forecast
performance. Historical per-record availability times remain unknown.

## Historical regression verification

The original suite completed 55 tests, including five XGBoost tests. Constructor
validation was placed after native iterator initialization to avoid unraisable
cleanup errors; that ordering remains. Checks covered complete multi-batch
alignment, NaNs/history flags, signal learning, batch-independent predictions,
training-prevalence initialization, read-only inference and persistence replay.
Those historical checks are not a new verification claim for this refactor.

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
