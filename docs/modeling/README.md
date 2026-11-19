# Retained coordinate ignition model

The main pipeline trains the retained **80-iteration coordinate HGB** on
2010–2016 only: learning rate 0.1, L2 1.0, 15 leaves, minimum leaf size 100,
seed 385, no class weighting or early stopping.

## One input contract

`data/metadata/ignition_feature_selection_v1.json` is the only authoritative
ordered feature list. The panel, cache, preprocessing, experiments and demo
consume its 39 predictors: the original 36, the persisted history-censor flag,
then EPSG:3978 cell-centre easting and northing. HGB preserves all 39 columns
and native NaNs; it does not append another flag or coordinates.

`docs/modeling/feature_manifest.json` is a reference to that contract, not a
second predictor list. Old 36-column caches are rejected. The current cache
version is `ignition-v1-weather-asof-global-date-coordinates-v3`.

The main panel remains a retrospective hindcast on the frozen 10 km grid.
The corrected cache globally indexes the pinned CWFIS archive, selects
eligible stations before top-k, and reconstructs prior-seven-day rain.
It retains every row, label, calendar, terrain and history value and all
coverage/missingness states. Archive publication times are unknown.

## Rebuild and train

Use Python 3.12 and the isolated `requirements-modeling.txt` environment.
Recover the pinned source artifacts using `ABOUT.md` first. Existing panel
replacement requires deliberate `--force`; preserve old caches or select a
new `--cache` directory instead of mixing versions.

```sh
python scripts/build_ignition_feature_panel.py
python -m scripts.ignition_modeling.validation \
  --input data/processed/ontario_fire_region_10km_daily_ignition_features_v1.csv.gz \
  --output-dir artifacts/ignition_modeling/panel_validation
python -m scripts.ignition_modeling.data \
  --input data/processed/ontario_fire_region_10km_daily_ignition_features_v1.csv.gz \
  --audit artifacts/ignition_modeling/panel_validation/data_quality_report.json
python -m scripts.ignition_modeling.run \
  --reference-pickle artifacts/ignition_modeling/selected_coordinate_hgb/model.pkl
```

The optional `--reference-pickle` accepts only a trusted local experiment
pickle and compares all 2010–2016 predictions. Its classifier consumes the
same 39 inputs directly; the legacy 36-column pickle preprocessor is not
used. This is a reproducibility comparison, not a new performance estimate.
No 2017–2019 fitting, calibration, threshold tuning or global scoring occurs.

Output: `artifacts/ignition_modeling/retained_coordinate_hgb/`.

- `selected_system.joblib`: the 39-input pipeline and its feature/cache contract.
- `model_metadata.json`: full settings, ordered features, 2010–2016 fit scope,
  cache/source/model checksums, package versions, commit, dirty-tree state and
  source-file hashes. A dirty tree is disclosed, not attributed to the commit alone.
- `training.json`: actual row counts, classifier width and fitting diagnostics.
- `verification.json`: reload evidence and the optional full pickle comparison.

The cache's audit is generated beside the cache, not over the archived
`docs/modeling/corrected_weather_audit.json`. Exports refuse existing output
directories; choose `--output` explicitly for another run.

## Demo

`python -m scripts.ignition_demo.server` loads this main-pipeline export and
the current cache. `scripts.ignition_demo.reconstruct` delegates to the same
cache builder and main trainer; it does not recreate the old 40-iteration
model. Demo score cutoffs are explicitly illustrative, not the old model's
validated threshold policy. Historical performance is not relabelled as the
new model's test result.

## Historical evaluation and experiments

The [original final report](final_report.md), [portable report](report.html),
and [verification report](verification_report.md) describe the earlier
36-input model comparison and its original 2017/2018/2019 evaluation protocol.
Those scientific results are historical, not rerun by the retained-model
export. The [experiment overview](../../experiments/ignition/README.md) records
the retained configuration's development evidence and later unsuccessful or
inconclusive alternatives. The original experiment pickle remains unchanged.

## Verified 2026-11-19 main-pipeline rebuild

Rebuilt the complete 51-column panel and corrected 39-column v3 cache:
17,798,320 rows, full validation `PASS`, no nonzero validation checks.
The main joblib export fits all 12,458,824 development rows from 2010–2016.
Every prediction matches the experiment pickle bit-for-bit; maximum absolute
difference is **0.0**, and both prediction streams hash to
`96093ef5fcd34f494c864b09287b86170ecfc1a16fa2c64c20986b3118c4dc43`.

The export JSON records base commit
`3de2c4277ab02787ca9f452a7fe8560eb670c601`, `working_tree_dirty: true`,
and hashes of the actual uncommitted source used. No new commit is implied.
Full evidence is in the export's `verification.json` and
`artifacts/ignition_modeling/main_pipeline_rebuild_20261119/rebuild_verification.json`.

The live browser replay scored all 9,673 cells for 2019-07-01, displayed
80 iterations and 39 inspector inputs, and reported no page errors. The map
shows the frozen 10 km grid footprint, not a substituted official boundary.
The original boundary asset is unavailable and its current download differs
from the pinned checksum; the pinned manifest was left unchanged.
