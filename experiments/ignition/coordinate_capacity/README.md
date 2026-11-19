# Fixed coordinate/capacity comparison

Historical numerical results and tables below predate the orchestration refactor; they are preserved, not a claim of a new full-data reproduction. Historical verification conclusions remain evidence about that original run.

This follow-up completes the same-data, same-fold comparison of HGB with/without
cell-centre coordinates at 15 versus 31 maximum leaves per tree. It tests whether
the capacity interaction observed in the 2013 diagnostic transfers to the other
development years. It is not a larger parameter search or a new held-out test.
The original selected model, feature panel, prior results and 2019 evaluation are
not changed.

## Executed results

**Keep the 15-leaf coordinate variant as the best development candidate.**
Increasing capacity repairs the 2013 ranking but does not improve the overall
comparison. AP values below are rounded; the JSON retains full precision.

| Variant | AP 2012 | AP 2013 | AP 2014 | AP 2015 | AP 2016 | Mean AP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No coordinates, 15 leaves | 0.008893500 | 0.011528906 | 0.001390211 | 0.003845181 | 0.008669532 | 0.006865466 |
| No coordinates, 31 leaves | 0.007578190 | 0.013261118 | 0.001419804 | 0.004033562 | 0.004662397 | 0.006191014 |
| Coordinates, 15 leaves | 0.010238445 | 0.009042434 | 0.001749552 | 0.004511449 | 0.009285745 | 0.006965525 |
| Coordinates, 31 leaves | 0.006539791 | 0.013474871 | 0.001774771 | 0.003871111 | 0.007585777 | 0.006649264 |

| Variant | Mean ROC-AUC | Mean Brier | Mean log loss |
| --- | ---: | ---: | ---: |
| No coordinates, 15 leaves | 0.8696736890 | 0.0003790141 | 0.0029079115 |
| No coordinates, 31 leaves | 0.8679794556 | 0.0003794430 | 0.0029240129 |
| Coordinates, 15 leaves | 0.8724773144 | 0.0003788770 | 0.0028927973 |
| Coordinates, 31 leaves | 0.8718785955 | 0.0003794404 | 0.0029194419 |

What this establishes:

- At fixed coordinates, increasing to 31 leaves **reduces mean AP by 4.54%**.
  Only 2013 and 2014 improve; 2012, 2015 and 2016 deteriorate. Repairing one
  conspicuous validation year is not a general improvement.
- Coordinates help the 31-leaf control by 7.40%, but that control was already
  weaker. Coordinate/31 remains 3.15% below the stronger no-coordinate/15
  baseline. Comparing only against the weaker control would be misleading.
- The positive mean interaction is `0.000358190700` absolute AP: coordinates
  reduce the capacity penalty, but do not eliminate it. The earlier 2013
  capacity explanation therefore does not justify a global 31-leaf switch.
- The best variant's coordinate gain remains the previous **1.46% relative
  mean AP**, not a large new improvement. It also has the best mean ROC-AUC,
  Brier and log loss among these four conditions, without establishing
  statistical significance or operational usefulness.

Decision: retain the small coordinate/15 development candidate, reject this
31-leaf change, and do not tune specifically to recover the 2013 hotspot at the
expense of the full development comparison. This result does not establish the
physical cause of the hotspot or prove that every possible training defect is
absent; it establishes the measured trade-off under these fixed settings.

Execution made exactly the four additional fits specified below. An independent
implementation recomputed AP, ROC-AUC, Brier and log loss for all **20 prediction
vectors**, checked identical reused 2013 predictions and prior control results,
and verified the contrasts, selection and protected output/code/data hashes.
An actual CLI resume made **zero additional fits** and left configuration,
results, CSV and all ten fold files byte-identical. No commits were made.

Compact evidence: [configuration — recorded_configuration](results.json), [full results](results.json),
[comparison CSV — tables["development_comparison.csv"]](results.json), independent verification (historical verification summarized here; standalone log omitted),
and actual resume verification (historical verification summarized here; standalone log omitted).

## Controlled protocol

| Variant | Raw predictors | Maximum leaves per tree |
| --- | ---: | ---: |
| `baseline_15` | Original 36 | 15 |
| `baseline_31` | Original 36 | 31 |
| `coordinates_15` | Original 36 + two cell-centre coordinates | 15 |
| `coordinates_31` | Original 36 + two cell-centre coordinates | 31 |

All other settings remain fixed: 80 iterations, learning rate 0.1, L2 1, minimum
leaf size 100, no class weighting, seed 385 and two threads. Coordinates retain
the existing experimental schema: EPSG:3978 easting/northing of each square's
geometric centre, calculated as the projected southwest origin plus 5,000 m.
No additional feature family, source vintage, imputation, scaling, or resampling
is introduced. HGB keeps native NaNs and the explicit history-censor flag.

Each variant is evaluated on five expanding chronological folds: training starts
in 2010 and ends in the year preceding validation in 2012--2016. Each validation
year retains all 1,779,832 cell-days at natural prevalence. The criterion is the
unweighted mean AP over all five years, with per-year AP, ROC-AUC, Brier and log
loss reported alongside it. Exact ties retain the listed variant order. A good
2013 result alone cannot win this comparison.

For interpretation, the report separates:

- The coordinate effect at each fixed leaf budget.
- The capacity effect with and without coordinates.
- The interaction: `(coordinate31 - baseline31) - (coordinate15 - baseline15)`,
  measured as an absolute AP difference, both by year and in the mean.
- The best variant versus the stronger tuned 15-leaf baseline, not just versus
  the weaker 31-leaf no-coordinate control.

The 2013 failure motivated this follow-up after its predictions were examined.
These are therefore exploratory development results, not independent
confirmation, statistical significance, operational alert performance, or
geographic generalization. No 2017--2019 model fitting/evaluation, calibration,
threshold selection or deployment-model refit occurs.

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

Use the corrected full-row cache and the modeling dependencies in `requirements.txt`. Supply trusted tuning and coordinate controls (`--tuning`, `--coordinates`) and the original 2013 diagnostic (`--diagnostic`). The 2013 model is replayed on the exact partition; a missing or invalid diagnostic fails rather than substituting another fit.

```sh
python -m experiments.ignition.coordinate_capacity.experiment
```

Default output: `artifacts/ignition_modeling/reruns/coordinate_capacity/`. Use `--cache` and `--output` for explicit paths; `--help` lists the real input options without reading data. Choose a new output directory for each invocation. Archived results and the saved selected-model pickle are not overwritten. Results include full candidate/fold metrics and the original probability NPZ basenames. No reserved-year (2017--2019) fitting or evaluation occurs.

Shared `common.py` handles bounded disk-backed fitting, batched prediction and scientific input checks. Script hashes, environment-equality gates, protected-file inventories and checkpoint/model replay for resuming runs have been removed. Each invocation is fresh; existing output directories are rejected.
