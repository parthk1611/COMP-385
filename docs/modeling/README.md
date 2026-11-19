# Retrospective ignition model comparison

Status: training and independent verification completed. Read
[the final report](final_report.md), open [the portable report](report.html), or
inspect [verification evidence](verification_report.md). Exact execution state
is recorded in `run_status.json`.

The target is at least one recorded ignition in a frozen v1 10 km cell during
the local date, with issue cutoff 00:00 America/Toronto and a one-day horizon.
Use exactly the 36 fields in `docs/modeling/feature_manifest.json`, the canonical
frozen core contract. Current dataset selection metadata
(`data/metadata/ignition_feature_selection_v1.json`) now lists 39 predictors
and must not expand the original model/cache matrix.
Keep keys and dates outside the model matrix. The frozen study universe includes
edge cells selected using study-period ignition events, so evaluation is
conditional on this universe and does not establish unbiased province-wide or
operational forecasting performance.

The downloaded v1 panel has a source-selection defect: all-time nearest stations
are selected before filtering by first observation date. It also joins an archive
whose date segments are not globally sorted. Modelling uses a separate disk cache
with globally indexed date/station records, nearest eligible stations selected
before top-k, and reconstructed prior-seven-day precipitation. All original rows,
labels, calendar, terrain and history values are retained. The original CSV and
EDA remain unchanged. The corrected cache has its own version and source audit.
First valid FWI wins duplicated station/day records; archive revision and
publication times remain unknown. This is a retrospective hindcast.

The main dataset builder now emits `ignition-feature-v1.1.0` (51 columns),
appending `fire_history_days_since_same_cell__censored`, then
`cell_centroid_easting_m = grid_x_m + 5000` and
`cell_centroid_northing_m = grid_y_m + 5000` in EPSG:3978 metres. The flag is
1 exactly when days-since is blank, otherwise 0; the available history starts
in 2010. These static full-cell centres are not ignition points,
longitude/latitude, or clipped polygon centroids. The selected 39 predictors
exactly match the coordinate experiment's transformed column order.
The original core cache/model still selects only its frozen 36 predictors,
derives history censoring, and coordinate experiments append coordinates
once. Do not append these fields again to a persisted 39-column matrix.

The 2026-10-05 full rebuild and missingness evidence remain historical v1.0.0,
48-column results. Local panels remain unchanged until deliberate regeneration
with `python scripts/build_ignition_feature_panel.py` (`--force` to overwrite,
then review the panel and audit, including coordinate semantics/grid checksum).
Filenames remain `_v1`. This static-geometry contract change does not rerun the
historical models or add operational forecasting evidence.

Development uses five expanding chronological folds ending in validation years
2012 through 2016. Calibration is held out in 2017; threshold tradeoffs use 2018;
the final test is 2019. No labels overlap future dates, so no purge gap is needed.
All fitted preprocessing stays within each training partition. No resampling is
applied; validation/test retain every row and their natural prevalence.

Numeric caches and model binaries are ignored generated artifacts. Compact
manifests, reports, reproduction commands and verification evidence are tracked.
Only the coordinator edits shared configuration, orchestration and this guide.

## Reproduction

Use Python 3.12 and install `requirements-modeling.txt` in an isolated environment.
The original audited CSV is supplied through `--input`; it is not stored in Git.
Recover the exact CWFIS archive URL and checksum from
`data/raw/cwfis/manifest.json` before cache preparation. From the repository root:

```powershell
python -m scripts.ignition_modeling.validation --input '<original audited CSV>' --chunk-size 50000
python -m scripts.ignition_modeling.data --input '<original audited CSV>'
python -m unittest discover -s tests -v
python -m scripts.ignition_modeling.run --smoke --output artifacts/ignition_modeling/smoke
python -m scripts.ignition_modeling.run
python scripts/publish_ignition_modeling_report.py
```

The training runner checks the audited data contract and immutable configuration,
and refuses to overwrite a completed final test. A fresh reproduction uses a new
`--output` directory; preserve the recorded test results and document any
correctness-defect rerun. Report packaging does not train or alter selection.
The publication wrapper is outside the frozen training-module hash set, so the
executed training code and its original fingerprints remain unchanged.

Models and all validation/test prediction vectors are saved locally under
`artifacts/ignition_modeling/full_run/`. `selected_system.joblib` is the final
probability-producing bundle; `final_logistic.joblib` and `final_hgb.joblib`
retain both fitted model-family pipelines. Use `predict_bundle` from
`scripts.ignition_modeling.run` with the exact 36-column schema and corrected
past-only inputs. No operating threshold has been selected.

## Follow-up ignition experiment archive

The [chronological experiment overview](../../experiments/ignition/README.md)
explains eleven modelling investigations and two saved-prediction analyses.
Each experiment has its own script, requirements, detailed recorded
`results.json`, and readable report under `experiments/ignition/`.

The retained development candidate is **coordinate HGB with 80 iterations,
15 maximum leaves, minimum leaf size 100, learning rate 0.1 and L2 1**.
The overview distinguishes that retained choice from the small, inconsistent
numerical AP gain in the 24-hour-lightning ablation and the subsequent
[Bayesian tuning experiment](../../experiments/ignition/bayesian/README.md).
That history-seeded search completed 80 new fits and found a 1.28% relative
mean-development-AP gain, with three yearly wins and two losses; it does not
automatically replace the exported model or add independent test evidence.

The follow-up scripts now use straightforward fresh-run orchestration instead
of source fingerprints, protected-file inventories and checkpoint resumption.
Their scientific settings, folds, feature semantics, metrics and selection
rules are retained. Use each experiment's README for actual commands and its
generated-input prerequisites; default reruns write new ignored directories
under `artifacts/ignition_modeling/reruns/` and never replace historical results.

The [saved coordinate-model bundle](../../experiments/ignition/coordinates/README.md#saved-model-pickle)
is a separate 2010--2016 development refit. Its export and this script cleanup
do not replace the original final-study artifacts or add 2017--2019 evaluation.
The original pipeline and evaluation protocol above remain unchanged.
