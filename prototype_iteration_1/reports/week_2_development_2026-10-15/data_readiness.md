# Week 2 data-readiness audit

Executed October 15, 2026. Fresh checks below are distinguished from saved repository evidence. Original raw inputs, team branches and the active 10 km ignition contract were preserved. This audit does not create a trained model or complete a province-wide training table.

## Seven selected source groups

| Source | Fresh work and evidence | Scope/remaining limitation |
| --- | --- | --- |
| Ontario point + area | Copied the existing point CSV from the team's fire-disturbance branch into a local raw audit folder; recorded source commit and SHA-256. Reprofiled all **65,655 rows and 17 columns**. | Full province-wide point/area GeoJSON sources were subsequently restored with exact pinned hashes. Cross-source correspondence and geometry checks are now recorded below; baseline labels remain unchanged. |
| VIIRS | Reprofiled the processed matched table: **300,601 detections, 631 fires**, no missing values in its 12 columns, no duplicate event/time/coordinate keys. It spans May 2012–October 2024. | The complete pinned 20-file Ontario-box raw subset is now restored and profiled: 1,037,059 detections. Event matching and observation gaps still affect evaluation; no continuous perimeter truth or 2025 archive is implied. |
| CDS ERA5-Land | Opened all **11 NetCDF files**, read all five variables and checked timestamps, missingness, units, ranges and grid. | **2025 Thunder Bay pilot**, not 2010–2019 province-wide historical weather. Reset-aware rain, RH/wind and research FWI are now derived/tested over this pilot. The separate January provincial download is profiled below; model joins and complete provincial integration remain later implementation. |
| HRDPS | Downloaded and decoded five surface-variable GRIB2 files for **one run and one lead**; checked metadata, full-grid ranges and samples at Thunder Bay, Red Lake and Timmins. | Bounded feasibility/EDA sample, not a run-selection service, history archive, FWI state or model adapter. |
| FBP 2024 | Fresh profiles of the three existing pilot sample rasters include native codes, missingness, CRS, resolution and hashes. | 145 existing provincial tiles checked against all 9,673 grid centres: 9,654 valid centre pixels and 19 missing. This is not full-cell aggregation or historically eligible fuel for 2010–2019. |
| Selected SCANFI 2020 | Profiled all **11 v1.2 pilot rasters**: closure plus ten species composition layers. Rechecked species sums. | Selected product is now directly inspected at pilot scale; it is not the SCANFI v2 material used in older broader EDA. No historical eligibility for 2010–2019 is inferred. |
| MRDEM | Fresh profiles of three existing terrain samples include CRS, value range, missingness and hashes. | 145 existing provincial tiles checked: all 9,673 grid centres have valid elevation pixels. Whole-cell summaries and publication/availability semantics still require a versioned feature build. |

Every source group now has either fresh sample/full-table inspection or explicitly bounded processed-data evidence. This does **not** mean seven complete, mutually compatible, province-wide datasets.

## ERA5: acquisition is now checked beyond hashes

- **8,016 unique hourly timestamps**, January 1, 2025 00:00 through November 30, 2025 23:00 UTC.
- **No missing or duplicated hourly timestamps** within that interval.
- Every file contains `t2m`, `d2m`, `u10`, `v10` and `tp` on a **7 × 8** latitude/longitude grid.
- All files have the same grid bounds. Time metadata explicitly uses seconds since 1970-01-01. GDAL does not expose a CRS authority for these NetCDF subdatasets; retain the CF latitude/longitude metadata and verify the geographic mapping before spatial joins.
- No missing numeric samples in these downloaded arrays. No dewpoint exceeded temperature by more than the 0.05 K audit tolerance.
- Temperature values span approximately **-33.88 to 28.61 C** after unit conversion. Raw winds remain signed component values in m/s, not wind direction or FBP wind speed.
- `tp` metadata says **metres** and **accumulated**, with raw range 0–0.05656 m. This is not an hourly rainfall rate and cannot be summed over hourly timestamps as-is.

[ECMWF documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=505384848) specifies accumulation from forecast initialization, with 00 UTC representing the preceding 24 hours. Implement/reset-test the appropriate deaccumulation, midnight/month boundaries and local aggregation before deriving rainfall or FWI. The tested pilot conversion below now implements those transformations; whole-province model integration is separate.

![Daily temperature, dewpoint and wind exploration](figures/era5_pilot_exploration.png)

The plot averages the downloaded pilot weather grid. It does not demonstrate Ontario-wide coverage or validate a fire-prediction model. The CSV retains raw accumulated precipitation under an explicitly named field, rather than presenting it as a daily total.

Evidence: [file/time audit](era5_file_audit.json), [variable profile](era5_variable_profile.csv), [daily exploration](era5_daily_exploration.csv).

## HRDPS: a bounded public sample works locally

Five public files were retrieved for the October 15, 2026 00 UTC run and +1-hour valid time: 2 m temperature/RH, 10 m u/v wind and surface precipitation. Combined size is about **11.4 MB**. Every file decoded on the **1,290 × 2,540 rotated grid**, and all three chosen Ontario locations were inside it.

The current GDAL reader exposes temperature in **C**, RH in **percent**, wind components in **m/s** and precipitation in **kg/m²**. Preserve reader-level units rather than applying an extra Kelvin conversion based on filename assumptions. The precipitation metadata identifies a one-hour interval; its `GRIB_FORECAST_SECONDS` is zero even though valid time minus run time is one hour. Lead/interval interpretation must therefore use the complete GRIB metadata, not that single field.

This sample was retrieved **after its valid time**. It proves access/decoding, not that the run was available at a historical prediction cutoff. Last-modified and retrieval times are retained; neither is claimed as proof of first availability. Wind components need a verified rotated-grid/earth-bearing convention before directional simulation or 10 km aggregation.

[ECCC documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/) describes the run/lead layout and rotated grid. Evidence: [raw acquisition manifest](../../data/raw/week_2_audit/hrdps_20261015T00Z_lead001/manifest.json), [decoded profile and point samples](hrdps_sample_audit.json).

## Fire-point and selected-forest findings

The province-wide point CSV has no exact duplicate rows or duplicate nonmissing OBJECTID/OGF_ID values. There are **49 missing/unparseable start dates**, **79 PB-coded records**, **371 OFR-coded records**, **76 missing general causes** and **1,202 missing out dates**. These are quality/filter candidates, not rows silently removed by this audit. FIRE_START_DATE values are examined as recorded date strings; parsing does not establish exact ignition times. Preserve incident identity and review source meanings before producing a reconciled label version.

For the selected SCANFI v1.2/2020 pilot, positive species sums equal **100**, while **56.7705%** of sampled pixels have zero total species composition. Percent conifer is undefined at zero-total pixels. These composition shares cannot be treated as v2 species crown-closure bands. Values being numerically readable does not imply valid forest coverage everywhere.

Evidence: [point profile](ontario_point_quality.json), [branch-copy provenance](../../data/raw/week_2_audit/ontario_points/manifest.json), [forest profiles](selected_static_quality.json), [species-sum check](scanfi_species_quality.json), [fuel/terrain samples](fuel_terrain_sample_quality.json), [VIIRS profile](viirs_processed_quality.json).

## Full-source restoration and reconciliation

Both provincial GeoJSON files match the repository's pinned hashes: **65,655 points and 2,751 areas**. There are no missing/invalid point geometries; the area source has **27 invalid geometries**, retained unchanged in raw storage. Point keys `(year, identifier)` repeat in 788 rows and area keys in 14 rows. Across unique area keys, 2,545 have point-key candidates and 199 have none; a final perimeter is not guaranteed for every fire.

All **8,109** retained NFDB rows have at least one normalized identifier/year point candidate. Requiring the recorded date and 10 km cell as well produces **8,107 unique correspondences and two conflicts**. Preserve original labels and source-instance identities. Eight NFDB rows share four repeated IDs but differ in dates/locations, so ID-only deduplication would lose events. The [adjudication table](nfdb_ontario_adjudication.csv), [reconciliation summary](fire_source_reconciliation.json), [point/area key table](point_area_key_reconciliation.csv) and [full profiles](ontario_point_area_full_profile.json) account for these cases. A normalized, flagged point audit is saved as [compressed CSV](ontario_points_normalized_audit.csv.gz); raw data was not changed.

The **20 VIIRS sensor-years** contain **1,037,059 raw box detections**, with **zero invalid acquisition timestamps**. Counts are 907,399 type-0 records, 69,231 type-2 and 60,429 type-3; confidence is 933,558 nominal, 61,182 high and 42,319 low. Two rows participate in within-file duplicate detection keys. These counts describe raw observations; apply the declared vegetation/confidence/duplicate rules in a separate derived version. All source-file hashes matched the pinned manifest. [Raw quality report](viirs_raw_quality.json), [restoration manifest](viirs_restoration_manifest.json).

The current official boundary ZIP is now an OpenFileGDB rather than the older downloader's expected Shapefile. It was decoded separately: 31 input records, 15 non-OFR sectors. All retained NFDB event locations are inside its union, while **25 of the 9,673 pinned grid-cell centres lie outside**. The current archive has a different hash and is not described as the old pinned boundary. See [boundary audit](boundary_source_audit.json) and [cell diagnostic](grid_boundary_diagnostic.csv). The known label-dependent edge-cell rule still needs a sensitivity study.

## Historical ignition baseline readiness

The pinned **CWFIS archive is restored**, with **4,159,936 rows** across 2010–2019 and its expected SHA-256. The **17,798,320-row label artifact** has been reconstructed from the unchanged 9,673-cell grid and 8,109 selected NFDB event rows, retaining the established five-field semantics. No current boundary or alternate fire source was substituted. [CWFIS provenance](cwfis_restored_manifest.json), [label restoration audit](label_restoration_audit.json).

The unmodified repository feature builder completed a fresh **17,798,320-row, 48-column v1 panel** (746.71 MiB compressed). Its audit validates the row universe, key uniqueness and terrain alignment and reports **zero weather observation-date violations**. It reproduces **9,340,916 missing-weather rows (52.482010%)** and 1,840 rows without terrain elevation. Reproduction preserves v1 behaviour, including known station-candidate and source-coverage limitations; it does not establish corrected features or operational availability. The 2025 pilot cannot fill 2010–2019 gaps. [Fresh build audit](historical_feature_rebuild_audit.json).

Restoring the area source also allowed the spread dataset validator to finish: **18/18 structural checks passed**, with source sanity summaries recorded in the [fresh validation](spread_validation_fresh.json). That result does not fix the water-barrier defect or establish forecast skill.

## Access, storage and handling

[Measured local storage inventory](storage_inventory.json) records the current source files and byte counts, separately from any planned province-wide acquisition. Public fire/environment observations require source attribution and version retention; this prototype requires no personal-data collection. Do not export CDS credentials or API keys. Existing authorized downloads are used; no new account, licence acceptance, payment or redistribution was performed.

Keep raw downloads unchanged, derived normalizations separately versioned, and missing values/quality flags explicit. Retrieve future large rasters/weather by bounded extent/time chunks, check available storage against raw plus derived/intermediate sizes and preserve checksums. Current samples cannot be used to assert whole-Ontario storage or coverage.

## What remains for full data preparation

1. Resolve or explicitly version the weather-station and label-dependent grid design issues before final modelling claims. Cross-source conflicts have a documented preserve-and-flag policy, not an invented ground truth.
2. Acquire/build full selected-source coverage for a declared eligible period. The sample rasters and 2025 pilot weather are not province-wide historical coverage.
3. Extend the now-tested ERA5 pilot converter into a chunked province-wide, timezone-aware feature join; preserve its state and cutoff rules.
4. Build HRDPS issue/availability/valid-time selection, 10 km aggregation, wind convention and recent-weather/FWI-state bridge for live work.
5. Enforce the frozen selectors and training-only transformations during fitting.

The Week 2 investigation and representative-source EDA now have complete local evidence. Acquired samples establish access/schema feasibility; measured coverage limits are part of the EDA result. The checklist retains a separate **partial full-source-readiness item** so that later coverage/integration work is not marked complete merely because the audit is finished. [Decisions and handoff](data_decisions.md).


## Selected-weather conversion and provincial coverage follow-up

The new [weather converter](../../scripts/prepare_selected_weather.py) derives reset-aware hourly rain in mm, relative humidity, wind speed/bearing, local-standard-noon observations, past 24-hour rain and stateful research FWI. It checks source units, accumulation type, coordinate conventions and earth-relative wind metadata. All 11 pilot months produced **18,704 daily cell records**, with **13,664 valid FWI records** from the declared April 1 startup. The first unknown precipitation increment causes 56 unknown daily-rain records; none was silently replaced with zero. No model was fitted and no same-day weather was joined to a midnight ignition target.

Ten focused tests cover midnight/month reset, missing hours, invalid negative increments, duplicate times, RH/wind conventions, causal rain windows, seasonal startup, missing-noon state breaks and fixed standard-noon offsets. The combined local/repository test run passes **53 tests**. The converter reuses the repository FWI equations, whose existing tests include published reference days. Automated heuristic review and manual source review were performed; this is not an independent-agent review. Heuristic complexity flags are retained in the report rather than treated as model-validity results. [Build/verification](selected_weather_audit.json), [daily profile](selected_weather_daily_profile.csv), [contract](selected_weather_contract.json), [test output](unit_tests_combined.txt), [code-quality scan](selected_weather_code_quality.json).

The existing provincial static archive contains **145 FBP-2024 and 145 MRDEM tiles** covering every pinned 10 km cell centre. Direct source-pixel probes find 9,654 valid fuel centres and 9,673 valid terrain centres. These are centre samples, not area-weighted 10 km features. Selected SCANFI v1.2/2020 remains the inspected pilot; the broader SCANFI-v2 archive is explicitly excluded from selected-version coverage. [Tile/centre audit](provincial_static_coverage.json), [centre values](provincial_static_centre_samples.csv).

An authorized CDS request also retrieved **January 2025** over the Ontario bounding box: **744 continuous hours**, **166 × 221 weather points**, all five variables, about 240 MiB. Every model centre is inside the requested box; 9,661 have valid temperature at the first-hour centre probe and 12 are masked. Each full-box variable has 2,772,144 missing samples out of 27,294,384; this includes masked locations outside the model region and must not be reported as Ontario-model missingness. [Full January profile](era5_provincial_january_profile.json). Further month downloads are acquisition work, not evidence of complete weather coverage; 2025 weather cannot repair the historical 2010–2019 benchmark.

The Week 2 deliverable is investigation, EDA, source/quality decisions and evaluation reservation. Full preparation, province-wide joins, learned preprocessing and live serving remain visibly tracked under the later data-preparation/implementation milestones. These were not marked complete by finishing this audit.
