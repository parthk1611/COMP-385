# Cell-centre coordinate experiment

Historical numerical results and tables below predate the orchestration refactor; they are preserved, not a claim of a new full-data reproduction. Historical verification conclusions remain evidence about that original run.

This experiment adds exactly two static geometry predictors to the tuned HGB
baseline. It leaves the v1 panel, its approved 36-predictor schema, labels,
weather/history semantics, and original frozen evaluation unchanged. This is a
retrospective ignition hindcast, not a fire-spread or operational forecast model.

## Results

Coordinates increased mean development AP by **1.46% relative** and improved AP
in four of five years. The net gain is small because 2013 worsened substantially.
This does not establish a statistically significant or operationally useful
improvement; no uncertainty test, new held-out test, or geographic holdout was
performed.

| Variant | Mean AP | Mean ROC-AUC | Mean Brier | Mean log loss |
| --- | ---: | ---: | ---: | ---: |
| Tuned baseline | 0.00686547 | 0.869674 | 0.00037901 | 0.00290791 |
| Baseline + cell centres | 0.00696553 | 0.872477 | 0.00037888 | 0.00289280 |

| Validation year | Baseline AP | Coordinate AP | Relative change |
| --- | ---: | ---: | ---: |
| 2012 | 0.00889350 | 0.01023845 | +15.12% |
| 2013 | 0.01152891 | 0.00904243 | -21.57% |
| 2014 | 0.00139021 | 0.00174955 | +25.85% |
| 2015 | 0.00384518 | 0.00451145 | +17.33% |
| 2016 | 0.00866953 | 0.00928574 | +7.11% |

The coordinate variant wins the predeclared mean-AP comparison, but is **not**
automatically promoted to replace the original model. Secondary mean metrics
improve slightly. The large year-to-year variation means the average alone
should not be presented as a dependable gain in alert precision or recall.
This was a useful low-cost experiment, not a substantial predictive breakthrough.

## Added predictors

| Predictor | Definition | Units / CRS |
| --- | --- | --- |
| `cell_centroid_easting_m` | `grid_x_m + 5000` | Metres, EPSG:3978 |
| `cell_centroid_northing_m` | `grid_y_m + 5000` | Metres, EPSG:3978 |

The existing coordinates are the southwest origins of 10 km square cells. Adding
5 km along each projected axis gives the geometric centre of that square, not a
clipped study-boundary centroid or an incident's ignition location. Values are
constant for a cell across every date. No event coordinates, arbitrary numeric
grid IDs, duplicate longitude/latitude inputs, scaling, or new external sources
are added as predictors.

Experimental version: `ignition-weather-v2-cell-centres-v1`. Its complete schema
is in [`results.json` → `supporting_results["feature_manifest.json"]` — supporting_results["feature_manifest.json"]](results.json): **38 raw predictors** and
**39 transformed inputs**. The original `HistoryIndicator` preserves the 36
source inputs and appends its censor flag; the two coordinates follow those 37
columns. Native NaNs and history censoring are unchanged.

## Controlled comparison

- Fixed HGB: **80 iterations**, learning rate **0.1**, L2 **1**, maximum leaves
  **15**, minimum samples per leaf **100**, no class weighting, seed **385**.
- Five expanding development folds: train from 2010 through the preceding year,
  then validate on 2012, 2013, 2014, 2015, or 2016.
- Every validation year retains all **1,779,832 cell-days** and natural prevalence.
- Baseline predictions are reused from the verified parameter-tuning run only
  after checking its parameters, Python/packages, code/data fingerprints, labels,
  prediction hashes and recomputed metrics. Only five new models are fitted.
- No further parameter search, negative sampling, calibration, deployment refit,
  or 2017--2019 model fitting/evaluation occurs.

Row-specific `grid.u16` indices join the cache to the original grid-file order.
The entire grid file is checked against its recorded reconstruction checksum
before fitting. This prevents a reordered or changed dimension from silently
attaching another cell's coordinates. Temporary 39-column training matrices are
written in bounded chunks and removed after fitting, including failures. No
expanded full-panel CSV or second large persistent numerical cache is needed.

The comparison criterion is the same unweighted mean development AP as before;
per-year AP, ROC-AUC, Brier and log loss provide context. Exact mean-AP ties retain
the baseline. An improvement would establish only better future-date ranking on
the existing frozen grid, not generalization to unseen geographic regions or
reliable operational alerts. The event-dependent grid-selection and historical
availability limitations remain.

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

## Saved model pickle

The retained 80-iteration, 15-leaf coordinate HGB has been refitted once on
**all 12,458,824 development cell-days from 2010-05-01 through 2016-10-31**
(5,290 positive cell-days). No rows were removed for missing weather. This is a
separate selected-model refit, not a new tuning experiment or a replacement for
the original frozen evaluation. No 2017–2019 fitting, calibration or scoring
was performed.

Local generated files, intentionally outside the commit:

- `artifacts/ignition_modeling/selected_coordinate_hgb/model.pkl`
- `artifacts/ignition_modeling/selected_coordinate_hgb/model_metadata.json`

The pickle contains `classifier`, `preprocessor`, `grid_ids`,
`cell_centres_m`, ordered feature names, and training/source/version metadata.
It does not depend on an experiment module for loading or inference; its
history preprocessor uses the existing core
`scripts.ignition_modeling.preprocessing` module. Use the repository and its
matching Python 3.12 / scikit-learn 1.7.2 / NumPy 2.3.5 environment.
Only load pickle files from a trusted source.

From the repository root:

```python
import pickle
import numpy as np

with open("artifacts/ignition_modeling/selected_coordinate_hgb/model.pkl", "rb") as stream:
    bundle = pickle.load(stream)

def predict_cell_days(X36, grid_ids):
    lookup = {str(key): index for index, key in enumerate(bundle["grid_ids"])}
    indices = np.asarray([lookup[str(key)] for key in grid_ids], dtype=np.int64)
    matrix = np.column_stack((
        bundle["preprocessor"].transform(X36),
        bundle["cell_centres_m"][indices],
    ))
    return bundle["classifier"].predict_proba(matrix)[:, 1]
```

Supply a batch of numeric corrected-cache inputs in `bundle["base_features"]`
order and one known grid ID per row. Keep missing values as NaN; a blank
same-cell history is handled by the bundled censor indicator. The bundled
coordinate lookup supplies the two static cell-centre fields. Do not substitute
uncorrected v1 weather, ignition-point coordinates, or future observations.
Use batches of at most 50,000 rows for bounded-memory inference.

A fresh process loaded the pickle and reproduced all **1,024 probe predictions
bit-for-bit**, including rows with missing inputs and censored history, without
importing an experiment module. The accompanying metadata records its checksum,
actual fit scope and serialization verification. Earlier cross-validation AP
describes the original fold models, not a new performance estimate for this
refit. Outputs are raw, uncalibrated HGB probabilities; no operating threshold
has been selected.

## Current reproduction

Use the corrected full-row cache and the modeling dependencies in `requirements.txt`. Trusted saved baseline fold predictions are required (`--baseline`); their labels/probability ranges and available scientific metadata are checked, and full metrics are recomputed.

```sh
python -m experiments.ignition.coordinates.experiment
```

Default output: `artifacts/ignition_modeling/reruns/coordinates/`. Use `--cache` and `--output` for explicit paths; `--help` lists the real input options without reading data. Choose a new output directory for each invocation. Archived results and the saved selected-model pickle are not overwritten. Results include full candidate/fold metrics and the original probability NPZ basenames. No reserved-year (2017--2019) fitting or evaluation occurs.

Shared `common.py` handles bounded disk-backed fitting, batched prediction and scientific input checks. Script hashes, environment-equality gates, protected-file inventories and checkpoint/model replay for resuming runs have been removed. Each invocation is fresh; existing output directories are rejected.
