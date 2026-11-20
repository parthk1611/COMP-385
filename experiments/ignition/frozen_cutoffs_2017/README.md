# Frozen 80-iteration HGB: development-only cutoffs and 2017 evaluation

No retraining, calibration, feature changes, cache rebuilding, or commits.
The retained main joblib export has 39 inputs and was fitted on 2010–2016.
2017 was scored once, retaining every cell-day and native missing values, using
that export and the exact v3 cache manifest recorded at training time.
2018–2019 observations were not accessed by this experiment.

## Cutoffs frozen before test access

`cutoffs.json` was durably saved by a separate `select` invocation before the
`score` command accessed any 2017 observations. `scoring_started.json` records
its SHA-256 and the start time; `scoring_completed.json` records completion,
model identity, selected cache-slice hashes, environment, and saved predictions.
An exclusive start marker prevents a second scoring invocation in this directory.

1. **Top 1% per day:** select exactly **97 of 9,673 cells**, rounding upward.
   Rank by descending probability; break score ties by ascending frozen
   grid-file index. This is a daily rank budget, not a single fixed probability
   threshold. It selects 97 cells even on days with very low scores.
2. **Development recall cutoff:** predict fire when
   **`p >= 0.0015253566853376931`**. This is the highest inclusive threshold
   capturing at least half the pooled 2012–2016 OOF fire cell-days. Include all
   score ties. It captures exactly **1,692/3,384** development positives.
   The target is not retuned or guaranteed on 2017.

Only the saved 2012–2016 expanding-window OOF probabilities were used to select
the probability cutoff. Each fold trained on 2010 through the preceding year;
no in-sample predictions from the full-development model were used for selection.
The top-1% budget is specified by the evaluation request, not fitted to labels.

## Raw counts

| Split | Policy | TP | FP | FN | TN | Total cell-days | Fire cell-days | Precision | Recall |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Development 2012–2016 OOF, pooled | Top 97 daily | 413 | 88,827 | 2,971 | 8,806,949 | 8,899,160 | 3,384 | 413/89,240 | 413/3,384 |
| Development 2012–2016 OOF, pooled | Fixed development recall cutoff | 1,692 | 521,782 | 1,692 | 8,373,994 | 8,899,160 | 3,384 | 1,692/523,474 | 1,692/3,384 |
| Held-out 2017 | Top 97 daily | 64 | 17,784 | 672 | 1,761,312 | 1,779,832 | 736 | 64/17,848 | 64/736 |
| Held-out 2017 | Fixed development recall cutoff | 233 | 66,662 | 503 | 1,712,434 | 1,779,832 | 736 | 233/66,895 | 233/736 |

Precision = TP/(TP+FP); recall = TP/(TP+FN). Positives mean cell-days with at
least one ignition, not individual ignition events. Development matrices pool
all five folds, not an average of fold rates. The cutoff was selected on these
same OOF outcomes, so development recall is a selection result, not a separate
unbiased estimate of cutoff performance. Earlier model selection also used
these development folds.

## Files

- `confusion_matrices.csv`: four comparison rows, raw counts, totals, fraction
  strings and numeric precision/recall.
- `results.json`: the same results plus all five development-fold count records.
- `development_results.json`: development-only fold and pooled counts, saved
  before test scoring.
- `cutoffs.json`: immutable selection record, both policies, OOF checksums,
  model/cache/grid identities, and development-only provenance.
- `predictions_2017.npz`: saved `y` and raw uncalibrated `p`, in chronological
  cache order, 9,673 rows per day, May 1–October 31.
- `scoring_started.json`, `scoring_completed.json`: single-pass scoring evidence.
- Four `development_2012_2016_oof_pooled__*.png` / `heldout_2017__*.png`
  figures: plain 2×2 raw-count tables, rows **actual fire / actual no fire**,
  columns **predicted fire / predicted no fire**. Cells contain counts only;
  no percentages or normalization. Layout is `[[TP, FN], [FP, TN]]`.
- `verification.json`: independent count checks without model rescoring.

## Source provenance and limits

Model: `artifacts/ignition_modeling/retained_coordinate_hgb/selected_system.joblib`,
SHA-256 `5dd1c909a9d0ea4903567ee66f4831d9e687e62156b6288812888ec3e830cb89`.
Cache: `data/interim/ignition_modeling_cache`, version
`ignition-v1-weather-asof-global-date-coordinates-v3`, manifest SHA-256
`ebc13ce6b473eebe1696ce571bba884a4408a01e60176062894ff3297282f696`.

OOF predictions: `artifacts/ignition_modeling/reruns/coordinates_20261119/`.
Their verification records the earlier **v2** corrected-weather cache plus
derived censor/coordinate columns, not the v3 manifest. These saved predictions
were reused unchanged after checking their recorded hashes, 39-input order,
frozen grid identity, and every development label against v3. The main export's
existing verification establishes bit-identical full-development predictions
to the retained experiment model. No OOF predictions were regenerated here.

The full cache includes later years, but this experiment only reads 2012–2016
labels/grid indices during selection and 2017 features/labels/grid indices after
freezing. It checks the exact training manifest and file sizes; it does not
rehash whole cache data files, which would read reserved-year observations.
The scoring record hashes the selected 2017 feature and label slices instead.

This is a retrospective ignition hindcast on the frozen grid, not fire spread
or an operational forecast replay. Prior-day timing does not establish archive
availability at the historical issue time. Here “held-out 2017” means excluded
from this retained model's fitting and cutoff selection; the repository also
contains historical evaluation of a different earlier model on reserved years.
No result here claims a previously unseen research-program-wide test year.

## Execution

From the repository root, with the existing modeling environment and artifacts:

```sh
.venv-modeling/bin/python -m experiments.ignition.frozen_cutoffs_2017.experiment select
.venv-modeling/bin/python -m experiments.ignition.frozen_cutoffs_2017.experiment score
```

These commands have already completed. Do not delete the cutoff or start marker
to rerun them. To regenerate the CSV and four figures without model inference:

```sh
.venv-modeling/bin/python -m experiments.ignition.frozen_cutoffs_2017.experiment report
```
