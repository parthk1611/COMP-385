# Fixed coordinate-HGB plus historical CG lightning

Decision: retain coordinate HGB **without** the two lightning predictors. The
completed five-fold experiment reduced mean yearly AP by **2.91%**, despite
complete stored feature coverage. Only 2013 improved on AP. No commits were made.

This experiment adds exactly two detected cloud-to-ground (CG) flash-density
predictors to the coordinate-HGB candidate. It does not retain the unsuccessful
one-/seven-day neighbourhood-history additions. The original v1 panel, corrected
36-column cache, grid, labels, missingness, and original final-study outputs are
unchanged.

## Added features

| Predictor | Definition | Units |
| --- | --- | --- |
| `lightning_cg_density_24h` | Area-weighted native-grid CG flash density over the latest eight completed three-hour intervals before issue | Detected flashes/km² |
| `lightning_cg_density_7d` | The same exposure over the latest 56 completed intervals | Detected flashes/km² |

The target remains ignition in an existing 10 km cell on the local calendar day,
not spread, perimeter progression, or final size. Experimental feature version:
`ignition-weather-v2-cell-centres-lightning-cg-v1`. There are **40 raw predictors
and 41 transformed inputs**: the previous corrected predictors, history-censor
indicator and cell-centre coordinates, followed by the two densities.

### Spatial calculation

The [ECCC CanCPLDv1 catalogue](https://open.canada.ca/data/en/dataset/9a68a501-9a87-441a-8073-980ae68438ef)
provides three-hourly CG flash counts on a 0.1-degree geographic grid. The native
cells do not coincide with the projected study squares. Reuse the checksum-pinned
full-square intersections from the completed coverage audit.

Let `A_ij = intersection_area(target_i, source_j) / target_area_i`. A source
window count must first be divided by that native cell's own area in km², using
the provider's `cell_area_0.1-deg.nc`. The target exposure is the area-fraction
weighted mean of those native densities. Equivalently, form
`W_ij = A_ij * 1e6 / native_cell_area_m2_j`, then compute `W @ native_window_counts`.
Multiplying `A` directly by native counts would not give correctly normalized
density. Counts are summed as integers before spatial projection to avoid
floating-point differences caused solely by temporal accumulation order.

This is a native-grid exposure approximation, not exact lightning locations or
an observed count of strikes inside each target square. Native geographic cell
bounds are inferred from centres +/-0.05 degrees; the audited mapping retains
positive intersections of at least 1 m², with complete target area checked to a
relative tolerance of 1e-6.

### Timing and quality

Issue time is 00:00 America/Toronto. Across the May--October study dates, the last
complete source interval ends at **03:00 UTC, 23:00 on the preceding local date**.
The 03:00--06:00 UTC interval crosses issue and is excluded. These are trailing
24-hour/seven-day windows ending one hour before issue, **not exact previous
local-calendar-day totals**. April observations supply complete May 1 lookbacks.

Explicit source fill values/NaNs invalidate any target-window with a contributing
unknown interval; they are not filled with zero. A valid zero means no CG flashes
were detected in the contributing support. The archive has no per-interval
sensor-outage flag, so a zero does not establish detector uptime or no physical
lightning. Long quiet periods are not automatically masked as outages.

The [provider revision notes](https://crd-data-donnees-rdc.ec.gc.ca/CDAS/products/CanCPLD/README.md)
describe a corrected source-grid assignment defect. The exact corrected annual
files, mapping, native-area file, and metadata are checksum-pinned. The
[peer-reviewed descriptor](https://pmc.ncbi.nlm.nih.gov/articles/PMC12514313/)
discusses detection/classification changes, especially for cloud-to-cloud
lightning; only CG is used here. Processed monthly records do not establish
historical `available_at` timestamps. This remains a retrospective hindcast,
not an operational forecast replay or a same-day lightning forecast.

## Controlled comparison

- Coordinate-HGB control; failed recent-history additions are excluded.
- 80 iterations, learning rate 0.1, L2 1, maximum leaves 15, minimum leaf samples
  100, seed 385, no class weighting or early stopping; two CPU threads.
- Five expanding chronological folds, validating on 2012--2016.
- Every training and validation row retained, including negatives and missing
  weather. No resampling or new hyperparameter search.
- Primary rule: highest unweighted mean yearly AP; an exact tie retains the
  coordinate baseline. Secondary metrics do not replace this rule.
- No 2017--2019 feature construction, fitting, calibration, or scoring. The
  source coverage audit previously examined those years without model evaluation.
- The same development years have been reused in earlier investigations; this
  is not a new independent test or evidence of statistical significance.

The separately versioned generated feature cache contains only 2010--2016 rows,
aligned by the existing per-row `grid.u16` mapping. Each rerun constructs a fresh
file without changing the original features. Source provenance, grid, schema,
coverage and row alignment remain checked; code, mtime and environment equality
are not scientific prerequisites. Temporary training matrices are removed after
success or failure. The original core training modules are unchanged.

## Reproduction prerequisites

Use the existing corrected cache, coordinate-HGB fold predictions, and generated
lightning coverage-audit input directory. These are not supplied in a fresh
clone. The source directory must contain `configuration.json`,
`download_manifest.json`, `spatial_mapping.npz`, `spatial_area_weights.npz`, and
the seven annual 2010--2016 raw CG NetCDF files. Missing spatial matrices are
not reconstructed or substituted. Annual file checksums and ECCC archive URLs
link to the downloaded source vintage, not to training-code immutability.
The provider-native area file and its URL/checksum metadata remain under
`artifacts/ignition_modeling/hgb_lightning/source/`.

```sh
python -m pip install -r experiments/ignition/lightning/requirements.txt
python -m experiments.ignition.lightning.experiment
```

`--cache`, `--baseline`, `--audit`, `--area`, and `--output` override these
prerequisites/output paths. The default fresh output is
`artifacts/ignition_modeling/reruns/lightning/`; an existing output is rejected.
The versioned two-column file and scientific coverage metadata are under
`lightning_features/ignition-weather-v2-cell-centres-lightning-cg-v1/`.
Fitting and prediction use the shared fixed-HGB routines with densities after
coordinates; there is no checkpoint/model replay or source-engine hash gate.
Historical results below predate this refactor; no full-data reproduction is
claimed. No original feature file, saved pickle or archived results are replaced,
and no reserved-year work is performed.

## Results

| Metric | Coordinate HGB | Coordinates + lightning |
| --- | ---: | ---: |
| Mean yearly AP | 0.0069655251 | 0.0067628072 |
| Mean yearly ROC-AUC | 0.87247731 | 0.87249834 |
| Mean yearly Brier score | 0.00037887699 | 0.00037895444 |
| Mean yearly log loss | 0.00289279732 | 0.00289509235 |

The primary criterion worsened, as did Brier and log loss. ROC-AUC changed very
little. These results do not support retaining this particular two-feature
addition under the fixed configuration; they do not establish that lightning
is inherently uninformative or that every representation would fail.

| Validation year | Coordinate AP | AP with lightning |
| --- | ---: | ---: |
| 2012 | 0.01023845 | 0.00913086 |
| 2013 | 0.00904243 | 0.01086787 |
| 2014 | 0.00174955 | 0.00160872 |
| 2015 | 0.00451145 | 0.00426458 |
| 2016 | 0.00928574 | 0.00794201 |

The experiment does not identify the reason for the degradation. Past lightning
does not reveal target-day lightning at a midnight issue time; overlapping
weather/history information or different fitted splits are other possibilities,
not demonstrated causes. No extra capacity or window search was performed.

### Daily review-budget trade-offs

Using the same global daily budgets and label-blind ascending `grid_id` cutoff
ties as the earlier utility analysis:

| Daily budget | Coordinate recall | Lightning recall | Coordinate precision | Lightning precision |
| --- | ---: | ---: | ---: | ---: |
| Top 1% (97 cells/day) | 12.20% | 12.26% | 0.463% | 0.465% |
| Top 2% (194 cells/day) | 18.59% | 19.00% | 0.352% | 0.360% |
| Top 5% (484 cells/day) | 31.91% | 32.12% | 0.243% | 0.244% |

These pooled development results use 3,384 positive cell-days across 920 dates.
The small fixed-budget gains do not overturn the predeclared mean-year-AP rule
or establish an operational benefit. All possible boundary-tie allocations give
the same pooled true-positive counts for the lightning variant at each budget.
The complete year/weather-group counts, false-alert rates, and tie diagnostics
are in [daily_budget_results.json — supporting_results["daily_budget_results.json"]](results.json) and
[daily_budget_comparison.csv — tables["daily_budget_comparison.csv"]](results.json). Weather groups
stratify the same globally selected cells; they are never separately reranked.

## Constructed dataset and verification

Both fields were constructed for **all 12,458,824 development rows**, including
negative rows and rows with missing weather, across 1,288 dates. Every year has
zero missing values in the two new fields; detector-zero is preserved as zero.
This does not certify unrecorded sensor uptime. The generated file is separate
from the original panel and corrected cache. See [feature_audit.json — supporting_results["feature_audit.json"]](results.json).

Four targeted behavioral tests passed: native-area density normalization,
inclusion/expiry boundaries, exclusion of the interval crossing issue, unknown
coverage versus observed zero, learning from lightning with native NaNs, and
owned scratch cleanup after both a successful fit and a post-allocation failed
fit. Following the existing optional-XGBoost convention, discovery cleanly skips
the lightning test module if `h5py` is absent; that path was also exercised.
See optional_dependency_verification.json (historical verification summarized here; standalone log omitted).

A separate checker independently reconstructed all **24,917,648 feature values**
from native files using direct integer window sums rather than prefixes. It
formed native density first, then the area-fraction mean, and independently
calculated the Unix clock boundary and cache-row joins. Values agreed within
4.45e-16 maximum absolute difference, with matching zero and missingness states.
The five saved native models replayed all **8,899,160 validation probabilities
exactly**. All ten metric vectors, the aggregate selection, 108 daily-budget/
year/weather rows, and the previous utility baseline were checked.
All 40 unique protected existing files retained their hashes.
See verification.json (historical verification summarized here; standalone log omitted).

### Quiet-period validation-input stress check

No extra models were trained. For the same five fitted models, a diagnostic
replaced only the lightning columns whose validation lookbacks overlap the
audit's six >=24-hour entire-domain quiet periods with NaN. All validation rows
were retained; these periods were not declared confirmed outages or adopted as
the default feature policy.

Mean yearly AP changed from **0.0067628072 to 0.0067628066**: the conclusion is
unchanged in this validation-input check. It does not test retraining with
unknown intervals or rule out effects of ambiguous zeros in the training data.
See [quiet_period_sensitivity.json — supporting_results["quiet_period_sensitivity.json"]](results.json).

Historical completed-run resume checks also preserved the original artifacts.
Resume machinery and temporary checking scripts are no longer part of the
simplified runner.
No original model promotion, final-model refit, calibration, 2017--2019 scoring,
or commit occurred.

## Archive layout

This report preserves the historical scientific account. `results.json` retains
all original primary fields, the original run configuration under
`recorded_configuration`, scientific JSON documents under `supporting_results`
(keyed by original filename), and CSV records under `tables` (original filenames;
all cells remain strings). Standalone execution-verification, resume, boundary,
and optional-dependency logs are omitted; the historical checks are summarized
above and were not rerun for this move.

Recorded source paths and fingerprints describe the original executed run and
predate relocation; they are not checksums of the current code. The simplified
runner uses fresh outputs rather than resume fingerprints. Generated prerequisites
remain outside this archive. Use the experiment-local `requirements.txt`; run
module commands from the repository root. The [original modelling guide](../../../docs/modeling/README.md)
retains the core dataset and frozen-evaluation context.

Source/download provenance and source-quality metadata from the ignored coverage
audit are preserved under `supporting_results` keys prefixed
`lightning_coverage_audit/`; source arrays are not included.
