# Week 4 - historical data preparation increment

Completed increment: October 16, 2026. Week 4 remains in progress; the full selected-source/live build is not complete.

## Verified outcome

A separate candidate weather layer and feature join now cover **14,238,656 unchanged development cell-days** in 2010-2017. Weather missingness is 54.0506% in v1 versus 11.4542% in the candidate. It gains 6,274,051 previously unavailable rows and loses 208,899 previously available rows under the finite/range and 200 km support rules. Coverage alone does not establish interpolation quality or improved model performance. No candidate was promoted and no existing model was applied to incompatible features.

| Year | Rows | Original missing | Candidate missing | Newly available | No longer available |
| --- | --- | --- | --- | --- | --- |
| 2010 | 1,779,832 | 27.110% | 14.022% | 268,264 | 35,314 |
| 2011 | 1,779,832 | 31.214% | 9.784% | 427,720 | 46,310 |
| 2012 | 1,779,832 | 36.733% | 14.052% | 438,455 | 34,762 |
| 2013 | 1,779,832 | 36.801% | 13.121% | 457,057 | 35,605 |
| 2014 | 1,779,832 | 29.110% | 10.227% | 377,470 | 41,380 |
| 2015 | 1,779,832 | 99.999% | 8.431% | 1,629,766 | 0 |
| 2016 | 1,779,832 | 98.532% | 9.135% | 1,591,460 | 340 |
| 2017 | 1,779,832 | 72.905% | 12.862% | 1,083,859 | 15,188 |

![Weather coverage comparison](weather_coverage_comparison.png)

## What changed

The original implementation chooses four nearest stations from a global catalogue before checking daily reporting. The candidate selects the four nearest stations with finite nonnegative FWI on the specific previous observation date and limits support to 200 km. Spherical distances and inverse-square weights use a 1 km floor. Numeric measurements use declared finite/physical range rules; unavailable measurements remain null. Each field normalizes only over its valid contributing values. Quality fractions/counts and distance metadata are retained.

The new loader groups required dates independently of physical archive ordering and specifies stable first-valid date/station deduplication. In the actual requested dates/geographic buffer there were no duplicate station/date rows, so the duplicate preference did not affect this build. Reordering, daily candidate selection, distance caps and range rules jointly differ from v1; the measured coverage change is not attributed solely to one change. The source archive itself remains unchanged.

The source scan examined 4,159,936 archive rows and retained 385,108 station/date observations within the requested dates and generous geographic buffer. Missing/range-invalid fields are counted in historical_weather_v2_audit.json. Daily nearest-station coverage at 100/200/300 km is 63.31% / 88.55% / 96.54%. These are coverage sensitivities, not alternative radius recommendations selected from outcomes.

Seven-day precipitation is available only for seven consecutive complete prior-day values. Same-day/future observations and incomplete joins fail checks. The 200 km radius was declared before the build as a research support bound; meteorological/reference validation and model sensitivity remain necessary. Archives lack historical available-at timestamps, so all outputs remain hindcast data.

The prior model comparison used the original v1 weather. In particular its validation years have substantial missing weather, so its results must not be relabelled as performance on this candidate. A new fair model comparison is required before adoption.

## Boundary sensitivity

A full 10 km centroid grid was generated from the downloaded current non-OFR boundary without consulting fire records. It contains **9,648 cells**, all already in the 9,673-cell v1 grid; **25 v1 cells are excluded**. The old pinned boundary GeoJSON is missing locally. This is a current-boundary scenario, not exact recovery or a historically available 2010 boundary. Derived geometry repairs are recorded; raw geometry is unchanged.

Both original training/validation row universes and labels are retained. current_boundary_centroid_eligible is a forbidden-predictor metadata flag, not an ignition input. The excluded development positives are audit counts only, never the criterion for choosing grid cells. Across 2010-2017 the scenario excludes 26 positive cell-days. No additional cells or negative labels were invented.

## Provincial selected weather verified

All **11 January-November 2025 provincial ERA5-Land files** are present (2,476,841,286 bytes) and match their pinned SHA-256 hashes. Each variable has the expected contiguous hourly monthly axis and recorded metadata: temperature/dewpoint K; earth-relative wind m/s; precipitation accumulated metres. This is distinct from the earlier small pilot files.

This increment verifies hashes and grid/time/unit metadata across the full set. It does not fully profile every provincial data value, derive provincial noon/FWI tables, join the seven selected sources or establish live HRDPS state/availability. Those remain open tasks. No 2025 weather, FBP 2024 or SCANFI 2020 was backfilled into 2010-2017.

## Artifacts and reproduction

- scripts/prepare_historical_weather_v2.py: pinned raw archive to eight candidate yearly weather files and mask sensitivity.
- scripts/join_development_weather_v2.py: strict keyed join into separate training/validation candidate partitions.
- data/processed/historical_weather_development_v2/: weather outputs, observations, config and hash manifest.
- data/processed/ignition_weather_v2_development/: candidate training/validation, predictor contract and manifest.
- historical_weather_v2_audit.json, weather_feature_join_audit.json: counts, policies, per-year differences and hashes.
- current_boundary_centroid_grid.csv, v1_grid_boundary_sensitivity.csv: independent current-boundary scenario and v1 mapping.
- provincial_era5_verified.json: full eleven-file hash/metadata ledger.
- unit_tests.txt: **86 passed**; fifteen new weather/join tests.
- integrity_verification.json: unchanged original partitions/eight Week 3 models and matching source/config hashes.

The existing v2 build is complete and protected from overwrite. To reproduce to new versioned paths, run these commands one at a time from the CAPSTONE directory (inputs and local `.venv` must already exist):

```sh
.venv/bin/python -m scripts.prepare_historical_weather_v2 --output-dir data/processed/historical_weather_development_v3 --report-dir reports/week4_repeat_v3
.venv/bin/python -m scripts.join_development_weather_v2 --weather-dir data/processed/historical_weather_development_v3 --report-dir reports/week4_repeat_v3 --output-dir data/processed/ignition_weather_v3_development
```

Use an unused version basename for later repeats. The joined candidate was rebuilt after adding explicit CLI input paths; its training and validation content hashes exactly match the first join. The archived before-CLI source/log/manifest and duplicate output directory preserve that provenance. The final primary result is weather_feature_join_audit.json. Only the CLI wiring changed; the scientific join did not.

Run checks with `.venv/bin/python -m pytest tests team_repository/tests team_repository/capability_2_fire_spread/tests -q`. No original labels, reserved evaluation content, fitted bundles, remote branches or synced project files were changed. The first data-build attempt hit an empty pandas chunk; it was preserved under a failed-attempt path, corrected with an explicit empty/no-observation rule, tested, and rerun successfully. Failed-attempt files are not completed data.

## Review and remaining Week 4 work

An implementer review and automated code-quality scans were run; independent reviewer sign-off is not claimed. The scans flag long orchestration functions and numeric-policy constants. No unrelated refactor was made after the source/config freeze. Tests establish join/selection software behavior, not field accuracy.

Before adoption, compare/refit the agreed models fairly on the candidate using the existing development selectors; evaluate station/radius/mask sensitivity and freeze a new source/feature contract. Then complete provincial selected-source transformations and 10 km joins, categorical fuel fractions and selected SCANFI/MRDEM coverage, date/identity adjudication, and HRDPS available-run/wind/rain/FWI-state compatibility. Preserve the separate historical, fixed-landscape and live scopes. Calibration/final scoring and the map remain later prototype work.
