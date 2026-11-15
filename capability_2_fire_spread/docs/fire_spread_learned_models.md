# Learned spread models compared with the FBP simulator

Can a model trained on past Ontario fires predict where a fire will spread
next better than the physics-based simulator (Canadian FBP rates of spread,
`scripts/simulate_spread.py`)? This note compares ten learned models with that
simulator on fires from 2021–2024 that none of them saw in training.

**Short answer: yes, on most measures.** The best model, a spatial neural
network (CNN), reaches 46% of the newly burning cells where the simulator
reaches 36% for the same predicted area, and ranks the cells that will burn
half as well again (average precision 0.33 against 0.22). All the tree
ensembles also beat the simulator. The gap narrows on long runs: on the
simulator's own 44 long-run test steps the CNN only ties it on how much new
burning it reaches.

## The question every model answers

Each replay step is a pair of satellite passes 6–30 hours apart. Given the
area burned by the first pass, the stretch of perimeter where flames were
seen, and the weather until the second pass, which 375 m cells will be newly
seen burning at the second pass? The simulator answers by running FBP physics
forward. The learned models answer by scoring every unburned cell within 6 km
of the fire (the *candidate cells*; 96.5% of newly burning cells lie within
that distance).

The steps, start areas, active perimeters and scoring function
(`score_step` in `scripts/run_spread_replay.py`) are exactly those the
simulator was published with. A regression test checks the refactored replay
reproduces the published simulator scores to the fourth decimal.

## The models

| Model | What it is | Inputs |
| --- | --- | --- |
| `logistic` | Logistic regression: a weighted sum of the inputs | base features |
| `random_forest` | 200 deep decision trees on random samples, averaged | base features |
| `mlp` | A small neural network, two hidden layers (64, 32) | base features |
| `hgb` | Histogram gradient boosting: shallow trees, each correcting the last | base features |
| `xgboost` | Gradient boosting with XGBoost, trained on the GPU | base features |
| `hgb_no_fuel` | `hgb` without any fuel input: a leakage check (below) | base features minus fuel |
| `hgb_hybrid`, `xgboost_hybrid` | Boosting that also sees the simulator's prediction for the cell | base features + simulator |
| `cnn` | A small U-Net that reads a 36 × 36 km map around the active perimeter and predicts the whole next-pass map at once, trained on the GPU | the same information as image channels |
| `cnn_hybrid` | `cnn` with the simulator's reached share as one more channel | as `cnn` + simulator |

**Base features** (`scripts/spread_ml.py`), all known at the first pass except
the step's weather, which the simulator is given too:

- *geometry*: distance to the burned area and to the active perimeter, the
  cell's direction from the front relative to the wind (downwind/crosswind),
  burned and active cells nearby;
- *persistence*: how many cells the fire added at the last pass, how far and in
  which direction it ran, its radiative power, how long it has been observed;
- *weather*: step length, night share, mean and maximum wind, wind steadiness,
  temperature, minimum humidity, rain, FFMC, BUI, ISI, DMC, DC, FWI;
- *fuel*: shares of conifer, mixedwood, deciduous, grass, non-fuel and water in
  the cell, burnable share nearby, the FBP head rate of spread of its fuel;
- *terrain*: elevation, rise and slope from the nearest active front cell.

The CNN's 29 channels carry the same information as maps; the wind and the
last pass's growth are arrows (east and north components).

## How they were trained and chosen

- **Training data:** calibration fires 2012–2020 only: 656 steps on 149 fires,
  1,062,522 candidate cells, 15,913 of them newly burning. Every trackable fire
  with a 90 m window of at most 150,000 cells is used (the simulator is pure
  Python, so the largest windows are left out by size, not by how they burned).
- **Settings:** chosen by leave-one-fire-year-out cross-validation within
  2012–2020, on the mean per-step average precision. Internal early stopping is
  off everywhere, because a random row split would put cells of one step on
  both sides. Imputation and scaling are fitted inside each training fold.
- **CNN:** every patch is also seen rotated and mirrored (eight symmetries),
  with the arrow channels turned to match (tested), and predictions are
  averaged over the eight views. The loss covers exactly the candidate cells.
- **Area:** each model's predicted count in a step is its summed probabilities
  times a scale chosen on the out-of-fold predictions so that the median
  predicted/observed area is 1.3, the simulator's own tuning target.
- **Testing:** once, on holdout fires 2021–2024. The models and settings of the
  six CPU models were fixed before any holdout result was read; the XGBoost and
  CNN models and their settings were also written before those results were
  read, and nothing was retuned after.

Cross-validated mean per-step average precision, 2012–2020 (higher is better;
the simulator and even growth are scored on the same folds, with nothing fitted):

| Model | CV AP |
| --- | ---: |
| `cnn_hybrid` | 0.278 |
| `cnn` | 0.274 |
| `xgboost_hybrid` | 0.258 |
| `hgb_hybrid` | 0.255 |
| `random_forest` | 0.253 |
| `hgb` | 0.253 |
| `xgboost` | 0.250 |
| `logistic` | 0.245 |
| `hgb_no_fuel` | 0.241 |
| `mlp` | 0.219 |
| FBP simulator | 0.201 |
| Even growth | 0.153 |

## Holdout results

Two holdout sets are reported: all 770 scored steps of 125 fires from
2021–2024, and the simulator's published 150 steps of 22 fires (where the
simulator reproduces its published recall of 0.302 exactly).

### Same area as the simulator ("matched")

Each learned model predicts exactly as many cells as the simulator in each
step, so only *where* they are placed differs. All 770 holdout steps:

| Model | Recall | IoU | Precision | Step AP | Direction within 45° |
| --- | ---: | ---: | ---: | ---: | ---: |
| **`cnn_hybrid`** | **0.456** | **0.152** | **0.264** | **0.332** | 60% |
| `cnn` | 0.456 | 0.150 | 0.261 | 0.330 | 59% |
| `xgboost` | 0.446 | 0.144 | 0.254 | 0.307 | 55% |
| `random_forest` | 0.444 | 0.144 | 0.254 | 0.309 | 58% |
| `hgb_hybrid` | 0.444 | 0.142 | 0.247 | 0.304 | 55% |
| `hgb` | 0.441 | 0.141 | 0.244 | 0.307 | 57% |
| `xgboost_hybrid` | 0.441 | 0.141 | 0.244 | 0.297 | 55% |
| `hgb_no_fuel` | 0.423 | 0.133 | 0.230 | 0.279 | 54% |
| `logistic` | 0.401 | 0.125 | 0.221 | 0.272 | 58% |
| `mlp` | 0.383 | 0.120 | 0.212 | 0.252 | 52% |
| **FBP simulator** | 0.356 | 0.113 | 0.204 | 0.221 | 53% |

Recall is the share of newly burning cells reached; IoU is the overlap of
predicted and observed new cells; step AP is how well a model ranks the cells
that will burn, needing no cell count. Even growth, the published no-physics
baseline, reaches 0.387 at the same area and ranks at 0.200 step AP.

Difference from the simulator, mean over steps with a 95% interval from 2000
bootstrap resamples of fires (steps of one fire are not independent):

| Model | Recall | IoU | Step AP |
| --- | --- | --- | --- |
| `cnn_hybrid` | +0.100 [+0.081, +0.119] | +0.039 [+0.031, +0.047] | +0.111 [+0.093, +0.131] |
| `cnn` | +0.100 [+0.079, +0.120] | +0.037 [+0.029, +0.046] | +0.109 [+0.091, +0.129] |
| `xgboost` | +0.090 [+0.073, +0.108] | +0.032 [+0.023, +0.040] | +0.086 [+0.071, +0.100] |
| `random_forest` | +0.088 [+0.071, +0.107] | +0.031 [+0.023, +0.039] | +0.088 [+0.073, +0.102] |
| `hgb` | +0.085 [+0.068, +0.102] | +0.028 [+0.020, +0.035] | +0.086 [+0.070, +0.101] |
| `hgb_no_fuel` | +0.067 [+0.048, +0.086] | +0.021 [+0.013, +0.029] | +0.058 [+0.043, +0.072] |
| `logistic` | +0.045 [+0.028, +0.062] | +0.013 [+0.005, +0.020] | +0.051 [+0.036, +0.065] |
| `mlp` | +0.027 [+0.008, +0.046] | +0.007 [-0.001, +0.015] | +0.031 [+0.016, +0.046] |

On the simulator's published 150 steps the order is the same: `cnn_hybrid`
recall 0.401 against 0.302 (+0.100 [+0.058, +0.146]), `cnn` 0.395, random
forest 0.394. Logistic regression and the MLP do not beat the simulator there.

### Long runs (observed head ran 1,500 m or more)

| Set | Simulator recall | `cnn_hybrid` recall | Difference |
| --- | ---: | ---: | --- |
| All holdout fires, 270 steps | 0.302 | 0.362 | +0.060 [+0.043, +0.079] |
| Simulator's published fires, 44 steps | 0.265 | 0.288 | +0.023 [-0.003, +0.057] |

On the published 44 long-run steps only the CNN matches the simulator; the
per-cell models fall slightly behind it (not significantly). The learned
models still rank cells better there (step AP +0.03 to +0.09; significant for
the CNNs and the tree ensembles, not for the MLP). All models
under-predict how far the head runs: the median simulated/observed head
distance on long runs is 0.53 for the simulator and 0.46 for the CNN.

### Each model's own area ("own")

With each model choosing its own count, the learned models predict a smaller
area than the simulator (median 1.2–1.4 times the observed cells against 1.69)
and are much more precise. All 770 steps:

| Model | Recall | IoU | Precision |
| --- | ---: | ---: | ---: |
| `cnn` | 0.374 | 0.185 | 0.304 |
| `random_forest` | 0.380 | 0.175 | 0.290 |
| `cnn_hybrid` | 0.352 | 0.181 | 0.310 |
| FBP simulator | 0.356 | 0.113 | 0.204 |

The CNN reaches as many new cells as the simulator (+0.018 [-0.034, +0.067])
with a 64% larger overlap (IoU +0.073 [+0.058, +0.089]).

## What the results say

- **Learned models beat the FBP simulator at predicting where a fire grows
  next.** The spatial CNN is best on every all-step measure; random forest and
  the two boosting libraries form a close second group.
- **Seeing the map helps.** The CNN, which reads the whole fire neighbourhood,
  beats every one-cell-at-a-time model, most clearly on long runs.
- **Adding the simulator's prediction barely helps** (`hgb_hybrid`,
  `xgboost_hybrid`, `cnn_hybrid` are within noise of their plain versions):
  the learned inputs already carry what the physics adds.
- **The fuel check passed.** Without any fuel input, gradient boosting still
  beats the simulator and loses only a little, so the fuel map (the 2024 map,
  repaired inside each final perimeter) is not leaking where the fire ended up.
- **Big runs remain hard for everyone.** The advantage shrinks on long runs, and
  all models, the CNN included, under-predict how far the head travels.

## Limits

- **Hindcast, not forecast.** Every model, like the simulator, is given the
  observed reanalysis weather for the step, not a forecast.
- **Satellite cells are a lower bound.** A pass sees only active flames, so
  observed new cells under-count what burned; recall is the fairer rate.
- **Final-perimeter footprints remain.** Each fire's grid window and the
  satellite matching use its final perimeter, and the fuel repair uses it too.
  This affects the simulator and the learned models alike; the no-fuel ablation
  is the check on the part that only the learned models could exploit.
- **Candidate radius.** Learned models score only cells within 6 km of the
  burned area: 3.5% of newly burning cells lie beyond, and count as misses.
- **Fire selection.** Fires with windows over 150,000 90 m cells are left out
  (the simulator's 24 published fires are always in). Results describe these
  fires, not every Ontario fire.
- **Small grids.** Two to four settings per family; the CNN has one
  architecture. A wider search could change the order within the close groups.
- **Single runs.** Each model is fitted once; the CNN's result also varies
  slightly between GPU runs.

## Reproduce

Needs the fuel and terrain windows and the perimeters (see the README build),
and `requirements.txt`, including scikit-learn, XGBoost, PyArrow and PyTorch
(a CUDA build of PyTorch for the GPU; everything also runs, slowly, on a CPU).

```sh
cd capability_2_fire_spread/scripts
python build_spread_ml_table.py          # per-cell table: features, labels, simulator prediction (data/processed/ml/)
python train_spread_models.py            # the eight per-cell models: cross-validate, choose, refit (artifacts/spread_models/)
python spread_cnn.py build               # 96 x 96 map patches for the CNN
python spread_cnn.py train               # the two CNNs: cross-validate, choose, refit, predict holdout fires
python compare_spread_models.py          # score everything against the simulator on 2021-2024 fires, once
cd .. && python -m unittest discover -s tests -v
```

| Output | What it holds |
| --- | --- |
| `data/processed/ml/spread_ml_steps_v1.csv`, `spread_ml_table_v1_audit.json` | Every replay step and the table's counts and rules |
| `data/processed/simulation/spread_models_v1_training.json` | Per-cell models: every setting's fold scores, the choice, area scale; simulator and even-growth reference |
| `data/processed/simulation/spread_cnn_v1_training.json` | The same for the CNNs |
| `data/processed/simulation/spread_models_v1_comparison.json` | Holdout results, both holdout sets, all steps and long runs, differences with intervals |
| `data/processed/simulation/spread_models_v1_holdout_steps.csv` | Every model's score on every holdout step |

The cell table, CNN patches and fitted models are rebuilt by the scripts and are
not in git.
