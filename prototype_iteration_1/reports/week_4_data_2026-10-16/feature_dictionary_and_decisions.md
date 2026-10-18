# Week 4 feature dictionary and architecture decisions

Recorded October 16, 2026 after implementation and measured build review. The earlier pre-implementation review and Week 3 architecture constraints remain in their dated artifacts; this record does not retroactively claim independent advance approval.

| Family | Source/version | Representation and units | Time/coverage contract |
| --- | --- | --- | --- |
| Label | Pinned Ontario Fire Disturbance Point snapshot, 2025 IFR | `reported_fire_start` binary; `recorded_start_count` integer, never a predictor | Provider calendar date, May 1–Oct 31; 624 instances / 600 cell-days; 25 exclusions retained |
| Grid | Current non-OFR boundary centroid scenario | EPSG:3978 10 km grid; centroid longitude/latitude | 9,648 fixed cells; current snapshot, not recovered historical eligibility; identifiers/geometry forbidden predictors |
| Fuel | FBP Fuel Types 2024 raster | `fbp_2024_code_*_share`, fraction 0–1; categorical raw codes preserved | Native pixel intersection areas in one nominal tile; shares sum to one over valid area; six unsupported cells null |
| Fuel support | Same | `fbp_native_valid_area_fraction`, 0–1 | Represents uncovered strips/nodata; never silently renormalized to full-cell support |
| Closure | SCANFI v1.2/2020 | `scanfi_2020_closure_sample_mean_pct`, percent | Mean over joint closure/species-valid 100 deterministic strata samples; not a full native mean |
| Conifer | Same, nine conifer components plus prcB | `scanfi_2020_canopy_weighted_conifer_pct`, percent | Normalize composition within each valid pixel, then canopy-weight; zero canopy has undefined share |
| Forest support | Same | `scanfi_species_valid_fraction`, 0–1 | Joint-valid fraction of 100 samples; retain nulls/coverage |
| Elevation | MRDEM 30 m DTM, EPSG:3979 | `mrdem_elevation_sample_mean_m`, standard deviation m | 100 transformed strata-centre samples; static study vintage, not a 2010-available claim |
| Slope | Same | `mrdem_sampled_1km_slope_mean_pct`, percent | Gradient of coarse 1 km samples; not native 30 m slope or degrees |
| Weather | ERA5-Land Jan–Nov 2025 | Temperature °C, RH %, speed km/h, rain mm | Native nearest-pixel at each grid centre; fixed local standard noon, UTC−5/−6, previous-noon day at ignition issue |
| Recent rain | ERA5-Land | `rain_prior_7_noon_days_mm`, mm | Exactly seven complete consecutive noon-day totals; missing remains null |
| FWI | Derived using existing scalar code | FFMC/DMC/DC/ISI/BUI/FWI indices | Explicit Apr 1 research startup; no snow/overwintering validation; state invalidates on missing update |
| Forecast weather | HRDPS actual October 16 run | Hourly °C, RH %, km/h, meteorological from-bearing degrees, rain mm | Rotated-grid wind converted to earth coordinates; cumulative rain intervals validated/deaccumulated; conservative post-retrieval availability |
| Forecast FWI state | Research adapter | JSON checkpoint with codes/date/noon/availability/provenance | Forecast-derived state always untrusted; exact date/clock and pre-issue availability checked on reuse |
| Validation only | Ontario Area and VIIRS | Perimeters/detections and matching metadata | Separate spread/evaluation use; not observed pre-issue ignition predictors |

## Decisions

1. **Keep three input contracts separate.** Historical CWFIS development models, selected 2025 fixed-landscape study and HRDPS research weather have distinct source/timing/distribution assumptions. Shared names and units do not establish interchangeability. No automatic cross-source inference is allowed.
2. **Retain the immutable historical benchmark.** Accept daily-available-station v2 for corrected development work, preserving 200 km support/range rules and the fixed fitting protocol. Retain v1 results and the current-boundary sensitivity separately. Coverage sensitivities are not radius-model optimization.
3. **Promote only a provisional candidate.** LightGBM leads pooled v2 temporal AP, but weak spatial transfer and low alert precision preclude operational acceptance. Calibration/final evaluation are Week 5, not retroactively claimed here.
4. **Use native categorical fuel proportions and explicit continuous estimates.** A sample/native QA check triggered the fuel refinement. Preserve partial support and all classes. Keep cheaper forest/terrain quadrature explicitly labelled; higher-resolution continuous aggregation is a possible future improvement, not an unreported full-area result.
5. **Preserve missingness and label ambiguity.** Source conflicts are excluded with reasons, zero-support cells remain null and incomplete precipitation never becomes zero. Negative labels mean absence of a record in this release.
6. **Separate forecast state from observed state.** Research constants/checkpoints enable reproducible software execution only. A trusted observed-state bridge and source compatibility require separate validation. Checkpoint reuse never upgrades forecast provenance to observed truth.
7. **Bound completion by evidence.** Module 4 data transformations, interfaces, architecture documentation and development experiments are executed. Application acceptance, scientific/field validation, independent review and the deferred native Project audit remain explicit external/later gates.

Dependencies: pandas/NumPy/PyArrow for keyed tables, rasterio/GDAL/pyproj for spatial handling, tzfpy 2.1.1 with runtime timezone polygons 2026e, sklearn/LightGBM for guarded models, and requests for source retrieval. Exact installed versions are in the environment lock. The timezone package's release history is [upstream](https://github.com/ringsaturn/tzfpy/releases); the runtime data version was measured locally. These are tools, not additional source groups or scientific validation.
