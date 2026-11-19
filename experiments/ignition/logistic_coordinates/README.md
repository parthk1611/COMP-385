# Logistic regression with cell-centre coordinates

A fixed-configuration development comparison gives logistic regression the same
two static coordinates used by HGB. This is feature parity, not a fresh broad
model-family optimization or independent held-out test. All inputs come from the
verified corrected-weather cache, not uncorrected v1 weather fields.

## Executed results

**Keep coordinate HGB as the current development choice.** Five new logistic
fits completed with the original logistic hyperparameters fixed.

| Model | Mean AP | Mean ROC-AUC | Raw mean Brier | Raw mean log loss |
| --- | ---: | ---: | ---: | ---: |
| Logistic, original predictors (archived) | 0.003373222 | 0.865078965 | 0.145984769 | 0.462628815 |
| Logistic, plus coordinates | 0.003391282 | 0.864947162 | 0.145133322 | 0.460803172 |
| Tuned 80-iteration HGB, no coordinates | 0.006865466 | 0.869673689 | 0.000379014 | 0.002907912 |
| Tuned HGB, plus coordinates | **0.006965525** | 0.872477314 | 0.000378877 | 0.002892797 |

The logistic coordinate gain is **0.54% relative mean AP versus the archived
baseline**, not an established statistically meaningful improvement. It does
not close the observed gap: coordinate HGB has about **2.05 times** coordinate
logistic's mean AP and higher AP in all five development years.

| Validation year | Archived logistic AP | Coordinate logistic AP | Relative change |
| --- | ---: | ---: | ---: |
| 2012 | 0.006451168 | 0.006373487 | -1.20% |
| 2013 | 0.002668149 | 0.002648608 | -0.73% |
| 2014 | 0.001147332 | 0.001168914 | +1.88% |
| 2015 | 0.002533689 | 0.002704033 | +6.72% |
| 2016 | 0.004065772 | 0.004061369 | -0.11% |

Coordinates improve two of five logistic AP scores. Mean ROC-AUC declines
slightly, while raw Brier/log loss improve slightly. The very large raw
probability-quality gap against unweighted HGB must be read with the balanced
logistic prior/calibration limitation below, not as a comparison after equal
probability calibration.

There is also a concrete optimization limitation: relative movement of averaged
logistic coefficients between epochs 2 and 3 remains approximately **7.2--8.7%**
across folds, and weighted training objectives are not monotonically improving
in every fold. Three epochs therefore do not demonstrate convergence. This
supports HGB under the tested settings; it does not prove that a longer-trained
or differently tuned logistic model cannot improve. No extra epochs or new
hyperparameters were silently added.

The raw predictor information is now matched, but model-appropriate preprocessing
differs (59 logistic transformed fields versus 39 native-missing HGB fields).
HGB also received more tuning. Report the result as an empirical development
comparison under these fixed budgets, not fundamental algorithm superiority.

## Historical verification

Before this refactor, 50 tests and an independent audit checked the optimizer,
train-only coordinate statistics, all 15 available prediction vectors and model
replay. Original logistic baseline vectors were unavailable. Historical resume
and output-boundary checks passed. These are historical conclusions, not a claim
that the simplified runner or full-data experiment has been rerun.

## Protocol

- Five complete expanding chronological folds: train from 2010 through the year
  before validation in 2012--2016; all 1,779,832 validation cell-days/year remain.
- Keep the original best logistic setting: L2 logistic regression optimized with
  averaged SGD, alpha 0.001, balanced class weights, three epochs, batches of at
  most 50,000 rows, seed 385. No parameter search, resampling or extra epochs.
- Preserve the original constant learning-rate rule `eta0 = 0.05 / max(weight)`;
  balanced weights come only from current-fold labels and are applied once via
  `sample_weight`. Chunk and within-chunk shuffling use the same seeded order.
- Fit the original numeric imputation/scaling and 21 missing/censor indicators
  on each training partition only. These remain the first 57 transformed inputs.
- Append EPSG:3978 cell-centre easting/northing, standardized with means and
  population variances computed from training-row cell frequencies only.
  Held-out cells/dates cannot change fitted statistics; constant scales become 1.
  Coordinates are grid-square centres, not incident-point positions. Total input
  information: 36 existing predictors plus two coordinates; 59 transformed fields.
- Primary comparison: equal-weight mean year AP, alongside per-year AP, ROC-AUC,
  Brier and log loss. Compare original/coordinate logistic and tuned 80-iteration
  HGB with/without coordinates. HGB predictions are reused and revalidated.
- No calibration, threshold selection, final-model refit or 2017--2019 evaluation.
  No commits. Dataset/cache files and historical training modules are unchanged.

The original logistic trainer intentionally accepts only its frozen 36-to-57
schema. The new experiment extends that trainer's update rules without changing
its archived implementation. Constant-coordinate regression tests compare actual
coefficients, probabilities and epoch objectives against the original optimizer
under both weighting modes. The simplified runner keeps this preprocessing and optimizer local; it does not
load or save model checkpoints.

## Evidence and limitations

The original selected logistic fold metrics are archived in
`docs/modeling/development_comparison.json`; their per-row prediction files are
not present locally. They are reported as **archived baseline metrics**, not as
freshly reproduced logistic predictions. The corrected cache's original-vintage
equivalence is documented in the existing reconstruction audit; current cache
schema and fold row/positive counts remain checked; runtime source fingerprints
are no longer required. No additional baseline fits are silently added to the
approved five-fit budget.

Three epochs are a finite computation budget, not proof of optimization
convergence. Epoch losses/objectives and coefficient changes are retained for
inspection; no automatic retuning occurs. HGB has received more tuning than this
fixed logistic extension, so the comparison does not establish universal model
superiority or equal optimization effort.

Balanced logistic fitting changes the effective class prior. Its raw output is
not a calibrated natural-prevalence ignition probability. Raw Brier/log-loss
comparisons remain descriptive and must not be interpreted as an operational
probability comparison after equal calibration. No calibration-year data are used
here. Reused development folds do not establish statistical significance or
unseen-geography/operational performance.

## Current execution

Install the experiment-local `requirements.txt` and provide the corrected cache,
frozen grid, archived original logistic comparison and both saved HGB controls
(`hgb_tuning` and `hgb_coordinates`). Run from the repository root:

```sh
python -m experiments.ignition.logistic_coordinates.experiment
```

Default output: `artifacts/ignition_modeling/reruns/logistic_coordinates/`.
`--cache` and `--output` select explicit paths. Output must be a fresh directory;
existing directories and archived/frozen destinations are rejected. New predictions
and full per-year metrics do not overwrite historical results. HGB baseline metrics
are recomputed from aligned saved vectors; the unavailable original logistic
vectors remain explicitly archived metric evidence, not fresh reproduction.

The runner always performs five fresh fits. It has no checkpoint replay,
source/package-equality gates or memory-monitor threads. Numeric/coordinate
statistics, class balancing, shuffled averaged SGD and the three-epoch budget
are unchanged. No 2017--2019 work or final-model replacement occurs.

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
