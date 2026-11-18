# History-seeded Bayesian coordinate-HGB optimization

Completed: all 16 new configurations and 80 chronological fits. **B9 is the
numerical winner, improving mean yearly AP by 1.28% relative to the retained
coordinate baseline.** It improves three years and worsens two; this is a small
development gain, not an established generalization improvement.

## Question

Can a sequential, history-informed hyperparameter search improve the retained
coordinate-HGB's mean development average precision (AP)? This is a new
retrospective ignition experiment, not a replacement for prior experiments or
an operational forecast evaluation.

## Predeclared protocol

- Optuna 4.6.0 multivariate Tree-structured Parzen Estimator (TPE), maximizing
  unweighted mean yearly AP. TPE is a Bayesian-optimization approach; it models
  promising and unpromising hyperparameter regions rather than fitting a
  Gaussian-process response surface.
- Seed 385 for sampler and HGB; 16 new configurations, five complete expanding
  chronological folds per configuration: **80 new fits**. No pruning or early
  stopping. One fit at a time, two CPU threads.
- Training starts in 2010 and ends before validation years 2012--2016. Every
  validation year retains 1,779,832 rows, including negatives and missing weather.
- Same corrected-weather inputs and static EPSG:3978 cell-centre coordinates:
  38 raw predictors, 39 transformed inputs including the history censor flag.
  Existing 30/365-day history remains. No lightning or new short-window history.
- Seed observations: retained coordinate-HGB plus the eight randomized and eight
  local-search configurations. Their fold APs are recomputed from saved,
  label-aligned predictions. Historical cache manifest, folds and raw predictor
  schema must match. Fitted model weights are not used to initialize new fits.
- All 17 seed observations precede the first new suggestion; no random startup
  phase. The multivariate sampler can learn parameter interactions. Each new
  suggestion sees the completed earlier trials.
- Retained baseline: 80 iterations, learning rate 0.1, L2 1, 15 maximum leaves,
  minimum leaf size 100, no class weighting, native NaNs.
- Highest mean yearly AP across baseline, imported history and new trials wins
  the numerical comparison. Exact ties retain baseline, then history/trial
  order. Per-year AP, ROC-AUC, Brier and log loss describe trade-offs.
- No calibration, operating-policy selection, final refit, or 2017--2019 scoring.
  Existing model pickles and original frozen evaluation remain untouched.

| Parameter | New search domain |
| --- | --- |
| Learning rate | 0.03--0.15, continuous log scale |
| Boosting iterations | 40--200, integer |
| L2 regularization | 0.1--10, continuous log scale |
| Minimum samples per leaf | 50, 100, 200 |
| Maximum leaves per tree | 7, 15, 31 |

This deliberately goes beyond the original 162-point discrete search. It admits
intermediate learning rates, regularization values and iteration counts, and
includes all imported local-search settings. The rate/iteration product is not
held fixed. These choices and the 16-trial budget are fixed before new scoring;
this is not a controlled equal-budget comparison of random search versus TPE.
The optimizer has access to earlier experiments' results.

## Executed results

Only B9 beat the baseline's mean yearly AP. Trial labels below count new
configurations; Optuna trial numbers are 17--32 because trials 0--16 contain
the imported observations. B9 is Optuna trial 25.

| New configuration | Mean yearly AP | Relative change vs baseline |
| --- | ---: | ---: |
| Retained coordinate baseline | 0.00696552510 | Reference |
| B1 | 0.00627638750 | -9.89% |
| B2 | 0.00654808972 | -5.99% |
| B3 | 0.00561486847 | -19.39% |
| B4 | 0.00535075859 | -23.18% |
| B5 | 0.00649384137 | -6.77% |
| B6 | 0.00638871037 | -8.28% |
| B7 | 0.00538062694 | -22.75% |
| B8 | 0.00694530385 | -0.29% |
| **B9** | **0.00705502772** | **+1.28%** |
| B10 | 0.00655399660 | -5.91% |
| B11 | 0.00673476830 | -3.31% |
| B12 | 0.00672462107 | -3.46% |
| B13 | 0.00657059760 | -5.67% |
| B14 | 0.00676155306 | -2.93% |
| B15 | 0.00676583158 | -2.87% |
| B16 | 0.00668424429 | -4.04% |

### Winning parameters

| Parameter | B9 |
| --- | ---: |
| `max_iter` | 176 |
| `learning_rate` | 0.03619373689319754 |
| `l2_regularization` | 5.110491839392006 |
| `max_leaf_nodes` | 31 |
| `min_samples_leaf` | 200 |

No class weighting, early stopping or feature changes were introduced.
Parameter ID: `72f8df5b889538dd`. Reported scores belong to these exact
parameters, not rounded substitutes.

| Validation year | Baseline AP | B9 AP | Relative change |
| --- | ---: | ---: | ---: |
| 2012 | 0.01023844534 | 0.01066033526 | +4.12% |
| 2013 | 0.00904243440 | 0.00875998196 | -3.12% |
| 2014 | 0.00174955231 | 0.00192998778 | +10.31% |
| 2015 | 0.00451144882 | 0.00474783854 | +5.24% |
| 2016 | 0.00928574462 | 0.00917699507 | -1.17% |

Unlike the earlier 24-hour-lightning result, the gain is not concentrated in
2013: that year actually worsens. Nevertheless, three wins and two losses on
repeatedly reused development years do not establish a statistically reliable
improvement.

| Mean yearly secondary metric | Baseline | B9 |
| --- | ---: | ---: |
| ROC-AUC (higher better) | 0.8724773144 | 0.8747888769 |
| Brier (lower better) | 0.000378876989 | 0.000378775414 |
| Log loss (lower better) | 0.002892797322 | 0.002889355109 |

All three secondary means improve slightly. No new daily-budget analysis or
calibration was performed. New-trial fitting/scoring took about 95.4 minutes,
excluding initial seed-score reconstruction.

### Decision

The predeclared mean-AP comparison selects B9 as this experiment's development
candidate. This does not automatically replace the retained 80-iteration
configuration, its exported 2010--2016 model, or the original frozen evaluation.
No full-development B9 refit or new final model was created. The result supports
a modest numerical tuning gain, not a claim that Bayesian optimization is
generally superior to random search: this run used more new trials, prior
observations, and a different search domain.


## Reproduction

Install `requirements.txt` in the isolated modelling environment. From the
repository root:

```sh
python -m experiments.ignition.bayesian.experiment
```

`--cache`, `--baseline`, `--output`, and `--trials` select explicit inputs and a
predeclared alternative budget. Use a new output directory per invocation;
existing directories are rejected. Default:
`artifacts/ignition_modeling/reruns/bayesian/`.

Generated prerequisites are the corrected full-row cache, original coordinate
fold predictions, and original randomized/local-search fold predictions under
`artifacts/ignition_modeling/`. Historical trial settings are read from the
adjacent experiments' archived `results.json` files. Missing or incompatible
prerequisites fail rather than silently switching to unseeded optimization.

Outputs include `configuration.json`, recomputed `seed_results.json`, Optuna
`study.sqlite3`, incremental `progress.json`, and final `results.json`. Each new
configuration has its own parameter-ID directory with complete validation
probabilities, fold metrics and fitted fold-model/preprocessor bundles. Training
scratch matrices are removed by the shared helper, including fit failures.
Large predictions, databases and models remain generated artifacts.
Experiment-local `results.json` records the executed scientific results and
configuration; reruns do not rewrite that archive.

## Verification

Independent verification passed after the full run:

- All 80 complete validation vectors had their labels, probability ranges, AP,
  ROC-AUC, Brier and log loss independently checked.
- All 80 saved fold models had their actual hyperparameters, 39-column input
  schema, seed and disabled early stopping checked.
- B9's saved models reproduced all 8,899,160 validation probabilities
  **bit-for-bit**, using independently assembled input matrices.
- The Optuna study contained 17 imported observations and 16 completed new
  trials; recorded scores, seed parameters and the selected winner agreed.
- No transformed training scratch matrix remained.

`results.json` preserves the executed results, `recorded_configuration`, compact
seed observations, comparison-table rows and the verification record. Full local
models, predictions and study database remain under the generated output path.
No 2017--2019 evaluation or selected-model replacement occurred.


## Interpretation boundary

The 2012--2016 development folds have already been reused extensively. Adaptive
optimization can exploit peculiarities of those years; higher development AP
does not establish a generalization gain or statistical significance. Per-year
consistency matters when interpreting a numerical win. The original study has
already examined 2019, so it cannot become a new blind test.
