# Learned spread models: method

How the ten learned models compared with the FBP simulator were built, trained
and scored. Their results are in the [README](../../README.md#results).

## The question every model answers

Each replay step is a pair of satellite passes 6–30 hours apart. Given the area
burned by the first pass, the stretch of perimeter where flames were seen, and
the weather until the second pass, which 375 m cells will be newly seen burning
at the second pass? The simulator answers by running FBP physics forward. The
learned models answer by scoring every unburned cell within 6 km of the fire
(the *candidate cells*; 96.5% of newly burning cells lie within that distance).

The steps, start areas, active perimeters and scoring function (`score_step` in
`scripts/spread_modeling/replay.py`) are exactly those the simulator was
published with. A test checks the replay reproduces the published simulator
scores exactly.

## The models

Each family is one file in `scripts/spread_modeling/`; the model registry is in
`contract.py`.

| Model | File | What it is | Inputs |
| --- | --- | --- | --- |
| `logistic` | `logistic.py` | Logistic regression: a weighted sum of the inputs | base |
| `random_forest` | `random_forest.py` | 200 deep decision trees on random samples, averaged | base |
| `mlp` | `mlp.py` | A small neural network, two hidden layers (64, 32) | base |
| `hgb` | `gradient_boosting.py` | Histogram gradient boosting: shallow trees, each correcting the last | base |
| `xgboost` | `xgboost_gpu.py` | Gradient boosting with XGBoost, trained on the GPU | base |
| `hgb_no_fuel` | `gradient_boosting.py` | Leakage check: `hgb` without any fuel input | base minus fuel |
| `hgb_hybrid`, `xgboost_hybrid` | as above | Boosting that also sees the simulator's prediction | base + simulator |
| `cnn` | `cnn.py`, `cnn_patches.py` | A small U-Net that reads a 36 × 36 km map around the active perimeter and predicts the whole next-pass map at once | the same information as image channels |
| `cnn_hybrid` | as above | `cnn` with the simulator's reached share as one more channel | as `cnn` + simulator |
| `cnn_runs` | as above | Experiment 5: `cnn` with newly burning cells weighted by their distance from the fire in the loss; not adopted (README) | as `cnn` |

**Base features** (`contract.py`, computed in `features.py`), all known at the
first pass except the step's weather, which the simulator is given too:

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

The CNN's 29 channels (`cnn_patches.py`) carry the same information as maps;
the wind and the last pass's growth are arrows (east and north components).

Never used as inputs: anything about the fire's outcome (final size, final
perimeter, out date, how many steps it was tracked) or later passes.
`contract.FORBIDDEN` lists them and a test checks no model uses one.

## Training and selection

- **Training data:** calibration fires 2012–2020 only: 656 steps on 149 fires,
  1,062,522 candidate cells, 15,913 of them newly burning. Every trackable fire
  with a 90 m window of at most 150,000 cells is used (the simulator is pure
  Python, so the largest windows are left out by size, not by how they burned).
- **Settings:** a small declared grid per family (2–4 settings), chosen by
  leave-one-fire-year-out cross-validation within 2012–2020, on the mean
  per-step average precision. Internal early stopping is off everywhere,
  because a random row split would put cells of one step on both sides.
  Imputation and scaling are fitted inside each training fold.
- **CNN:** every patch is also seen rotated and mirrored (eight symmetries),
  with the arrow channels turned to match (tested), and predictions are
  averaged over the eight views. The loss covers exactly the candidate cells.
- **Area:** each model's predicted count in a step is its summed probabilities
  times a scale chosen on the out-of-fold predictions so that the median
  predicted/observed area is 1.3, the simulator's own tuning target.
- **Testing:** once, on holdout fires 2021–2024 (`compare.py`). All models and
  settings were fixed before any holdout result was read; nothing was retuned.

## How the comparison is scored

- **Matched:** each learned model predicts exactly as many cells as the
  simulator in that step, so only *where* they are placed differs.
- **Own:** each model predicts its own number of cells (area scale × summed
  probabilities), so *how much* is tested too.
- **Step AP:** how well a model's scores rank the cells that will burn,
  averaged over steps; it needs no cell count. The simulator is ranked by
  earliest arrival, even growth by distance from the active perimeter.
- **Intervals:** differences from the simulator are given with 95% intervals
  from 2000 bootstrap resamples of whole fires, because steps of one fire are
  not independent.
- **Two holdout sets:** all 770 scored steps of 125 fires, and the simulator's
  own published 150 steps of 22 fires.

## Limits

- **Hindcast, not forecast.** Every model, like the simulator, is given the
  observed reanalysis weather for the step, not a forecast.
- **Satellite cells are a lower bound.** A pass sees only active flames, so
  observed new cells under-count what burned; recall is the fairer rate.
- **Final-perimeter footprints remain.** Each fire's grid window and the
  satellite matching use its final perimeter, and the fuel repair uses it too.
  This affects the simulator and the learned models alike; the no-fuel ablation
  is the check on the part only the learned models could exploit.
- **Candidate radius.** Learned models score only cells within 6 km of the
  burned area: 3.5% of newly burning cells lie beyond, and count as misses.
- **Fire selection.** Fires with windows over 150,000 90 m cells are left out
  (the simulator's 24 published fires are always in).
- **Small grids, single runs.** Two to four settings per family and one CNN
  architecture; each model is fitted once, and the CNN varies slightly between
  GPU runs.
