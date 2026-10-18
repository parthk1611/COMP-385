# Frozen evaluation selectors v1

Created October 15, 2026 before new model fitting. The existing 10 km study grid and calendar-day target are retained. The files reserve which dates/cells belong to each experiment. The full v1 panel is now rebuilt and physically exported into four temporal Parquet files, with the frozen spatial role attached to every row. No fitted training pipeline yet enforces the selector/predictor rules.

## Primary chronological experiment

| Role | Years, May–October | Dates | Use |
| --- | --- | --- | --- |
| Training | 2010–2015 | 1,104 | Fit initial candidates and all learned transformations. |
| Validation | 2016–2017 | 368 | Compare candidates and choose hyperparameters/feature decisions. |
| Calibration | 2018 | 184 | Fit a declared probability-calibration map and any declared alert policy after the model/feature choice is frozen. |
| Final test | 2019 | 184 | One final comparative evaluation after decisions are frozen. |

After selecting hyperparameters, refit the base model/preprocessing on 2010–2017, then calibrate on 2018. Never fit ordinary imputation/scaling/feature selection on 2018–2019. Preserve natural prevalence in evaluation; any class weighting or negative sampling is training-only. Match test keys across all candidates.

Report AP, precision/recall at the frozen alert policy, false-positive alerts per 1,000 eligible cell-days, Brier score and calibration diagnostics, with missing-weather/coverage and regional summaries. AP is not an ordinary accuracy score. Report undefined metrics if a subgroup has no positives. Uncertainty intervals must respect grouped spatial/temporal observations; an IID cell-row bootstrap is not automatically justified.

**Prior exposure:** the repository's existing all-year descriptive EDA includes 2019. Therefore 2019 is reserved from new training/tuning, but cannot truthfully be described as a pristine, never-inspected test set. A later independently acquired period, with compatible source vintages, would be needed for that stronger claim.

## Separate spatial-generalization experiment

- Assign the existing cells to **100 km EPSG:3978 blocks** using floored origins.
- Select blocks using a fixed SHA-256 rule, independent of labels. The manifest records the exact seed string and modulo rule; realized selection need not equal exactly 20% of cells.
- Reserve **1,387 cells** for spatial testing and **7,767 cells** for spatial development; exclude **519 buffer cells**.
- Require at least **20 km between retained development-cell and test-cell centres**, leaving at least a 10 km edge gap for axis-aligned 10 km cells.
- Use the same chronological year roles, but fit/validate/calibrate only on spatial-development cells; final spatial test is reserved cells in 2019. Fit a separate model, not the all-geography temporal model.
- Exclude all `fire_history_*` predictors in this strict secondary experiment so engineered ignition history cannot incorporate labels from withheld areas. This ablation answers a more restricted feature question; report it separately.

The historical study mask itself includes cells added because an ignition occurred. Selector reservation does not fix that label-dependent mask. Retain the reproducible baseline and perform a versioned label-independent-mask sensitivity study before strong generalization claims.

![Reserved cells and buffer](figures/ignition_spatial_reservation.png)

## Files and verification

- [Temporal selectors](ignition_temporal_partition_v1.csv): 1,840 unique dates.
- [Spatial selectors](ignition_spatial_partition_v1.csv): 9,673 unique cell IDs and role/distance fields.
- [Frozen manifest](evaluation_reservation_v1.json): source/selector hashes, chronology, policies and explicit prior-exposure limits.

Checks executed: unique keys, complete role assignment, disjoint spatial roles, expected date/cell counts and minimum retained separation. Neither held-out feature values nor fire labels were used to choose spatial blocks. No claim of predictive performance is made.

For spread, retain the existing incident-level calibration/holdout boundary as a reproducibility baseline, then revise outcome-dependent initialization and barrier logic before rescoring. The saved 6–30-hour observation intervals do not become 1-/3-hour truth. Do not combine spread and ignition splits or targets.

## Materialized dataset files

The [materialization manifest](evaluation_materialization_v1.json) records source/selector hashes, fixed type conversion, output schema, row counts and per-file hashes. Files are stored in [the local partition folder](../../data/processed/ignition_evaluation_v1/manifest.json).

| File | Row count | Use |
| --- | ---: | --- |
| `training.parquet` | 10,678,992 | Initial model/preprocessing fits. |
| `validation.parquet` | 3,559,664 | Development comparison; may join training only for the declared final refit after hyperparameter selection. |
| `calibration.parquet` | 1,779,832 | Calibration/declared alert policy only after the base model is frozen. |
| `final_test.parquet` | 1,779,832 | Reserved final evaluation; file set read-only after creation. |

All 48 original fields are retained, with `spatial_role` added as a 49th metadata field. Fixed numeric/string types were declared; no fitted preprocessing, sampling or imputation occurred. Counts are checked from file metadata, and per-column statistics were disabled during export. No new test-label summaries or performance scores were computed. Read-only permissions and hashes help identify accidental changes; they do not themselves enforce scientific separation.

The [candidate predictor contract](predictor_contract_v1.json) allows 36 numeric candidates for the chronological experiment and 31 for the strict spatial experiment. This is a declared baseline candidate list, not a tuned feature selection. Never pass the whole labelled table to a model: `ignition_count` directly reveals the target, `large_fire_200ha` is another outcome, and cell/date/source/version/partition fields are metadata. The spatial experiment must filter cell roles and exclude all `fire_history_*` predictors even though the common cache retains them. Training-time enforcement remains required.
