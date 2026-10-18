# Data dictionary

## Source datasets

| Dataset | Version used | Licence | Source format | Native coordinate system | Resolution / grain | Local representation | Notes |
|---|---|---|---|---|---|---|---|
| [FBP Fuel Types 2024](https://open.canada.ca/data/en/dataset/4e66dd2f-5cd0-42fd-b82c-a430044b31de) | 2024 | Open Government Licence – Canada | GeoTIFF; WCS | EPSG:3978, NAD83 Canada Atlas Lambert | 30 m categorical raster | `data/raw/samples/*/fbp_2024.tif` | Assigned version. A [2026 replacement](https://open.canada.ca/data/en/dataset/851e6a27-a250-41e6-9cd0-d7ff96455dd6) was released July 23, 2026; do not mix vintages silently. |
| [SCANFI v2](https://open.canada.ca/data/en/dataset/07653869-f303-46c2-a04e-9ab479b73cbf) | v2, published 2026; 1985–2025 five-year layers | Open Government Licence – Canada | GeoTIFF | Custom NAD83 Canada Lambert: central meridian −95°, standard parallels 49°/77°, latitude of origin 0°, metres; no EPSG authority in the files | 30 m raster | `data/raw/samples/*/scanfi_*.tif` | v2 species layers are actual crown closure percentages. This CRS is not EPSG:3978 and must be reprojected. |
| [MRDEM 30 m](https://open.canada.ca/data/en/dataset/18752265-bda3-498c-a4ba-9dfe68cb98da) | Current source retrieved 2026-10-02 | Open Government Licence – Canada | Cloud Optimized GeoTIFF; STAC | EPSG:3979, NAD83(CSRS) Canada Atlas Lambert; elevations use CGVD2013 | 30 m digital terrain model | `data/raw/samples/*/mrdem_dtm.tif` | Elevation is supplied. Slope and aspect are derived by this project. |
| [Historical Fire Management Zones](https://www.arcgis.com/home/item.html?id=561f41e54f8e4ab28a2684f9e93239cb) | Historical layer; source business-effective date 2005-04-01 | Open Government Licence – Ontario | ArcGIS Feature Service; downloaded as GeoJSON | EPSG:4269, NAD83 geographic | 95 polygon features | `data/raw/boundaries/fire_management_zones.geojson` | Historical, not the current operational boundary. Four duplicate geometries and 28,651 km² of overlap were found; dissolve before using it as a study mask. |

All model-ready coordinates and areas are calculated in EPSG:3978. Latitude/longitude columns are EPSG:4326 display coordinates.

## FBP 2024 codes observed or defined by the source style

| Code | Meaning | Analysis group |
|---:|---|---|
| 1 | C-1 Spruce-Lichen Woodland | conifer |
| 2 | C-2 Boreal Spruce | conifer |
| 3 | C-3 Mature Jack or Lodgepole Pine | conifer |
| 4 | C-4 Immature Jack or Lodgepole Pine | conifer |
| 5 | C-5 Red and White Pine | conifer |
| 7 | C-7 Ponderosa Pine / Douglas Fir | conifer |
| 11 | D-1 Leafless Aspen | deciduous |
| 13 | D-1/D-2 Aspen | deciduous |
| 31 | O-1a Matted Grass | open |
| 101 | Non-fuel | nonfuel |
| 102 | Water | water |
| 105 | Vegetated Non-Fuel | nonfuel |
| 415 | M-1 Boreal Mixedwood Leafless (15% Conifer) | mixedwood |
| 625 | M-1/M-2 Boreal Mixedwood (25% Conifer) | mixedwood |
| 650 | M-1/M-2 Boreal Mixedwood (50% Conifer) | mixedwood |
| 675 | M-1/M-2 Boreal Mixedwood (75% Conifer) | mixedwood |

## Static pilot feature table

File: `data/processed/static_features_2500m.parquet` and `.csv`. Grain: one 2.5 km × 2.5 km cell within a named pilot sample.

| Field | Type | Unit / allowed values | Definition |
|---|---|---|---|
| `cell_id` | string | unique | Stable `{place}_{row}_{column}` key. |
| `place` | category | `red_lake`, `thunder_bay`, `timmins` | Pilot sample name. |
| `grid_row`, `grid_column` | integer | 0–11 | Position inside the 12 × 12 sample grid. |
| `x_epsg3978`, `y_epsg3978` | float | metres | Cell-centre coordinates in EPSG:3978. |
| `longitude`, `latitude` | float | decimal degrees | Cell-centre display coordinates in EPSG:4326. |
| `fbp_dominant_code` | integer | FBP code | Most frequent 100 m resampled FBP code in the cell. |
| `fbp_dominant_name` | string | source legend name | Human-readable dominant FBP class. |
| `fuel_dominant_group` | category | conifer, deciduous, open, mixedwood, nonfuel, water | Coarse group of the dominant code. |
| `fbp_valid_fraction` | float | 0–1 | Share of 100 m pixels with valid FBP data. |
| `fuel_*_share` | float | 0–1 | Share of valid pixels belonging to each coarse fuel group; the six fields sum to 1. |
| `closure_1985_pct`, `closure_2020_pct`, `closure_2025_pct` | float | percent | Mean SCANFI canopy closure in the cell for each reference year. |
| `closure_change_1985_2020_pct_points`, `closure_change_2020_2025_pct_points` | float | percentage points | Descriptive differences between SCANFI reference layers; not validated local forest-change estimates. |
| `height_2020_m` | float | metres | Mean SCANFI canopy height. |
| `balsam_fir_pct`, `black_spruce_pct`, `broadleaf_pct`, `jack_pine_pct`, `other_conifer_pct`, `tamarack_pct`, `white_red_pine_pct` | float | percent | Mean SCANFI v2 species-group crown closure. |
| `conifer_crown_closure_pct` | float | percent | Sum of the six conifer species-group crown-closure fields. |
| `conifer_share_pct` | float, nullable | percent | Conifer crown closure divided by conifer plus broadleaf closure. Null where total species closure is zero. |
| `elevation_m` | float | metres above CGVD2013 | Mean MRDEM elevation. |
| `slope_degrees` | float | degrees | Mean terrain slope derived at native scale and averaged to the cell. |
| `slope_max_degrees` | float | degrees | Maximum derived 100 m slope within the cell. |
| `aspect_sin`, `aspect_cos` | float | −1 to 1 | Circular encoding of terrain aspect; preferred model inputs. |
| `aspect_degrees` | float | 0–360 degrees | Reconstructed mean aspect for interpretation. |
| `scanfi_valid_fraction`, `mrdem_valid_fraction` | float | 0–1 | Cell coverage by valid source pixels. |

## Supporting outputs

| File | Grain | Purpose |
|---|---|---|
| `data/processed/fuel_distribution.csv` | place × FBP code | Native 30 m pixel counts, mapped area, and share. |
| `data/processed/fire_management_zone_summary.csv` | zone designation | Feature counts and summed polygon areas. |
| `data/processed/validation_summary.json` | one run | Row counts, invariant failures, value-range checks, and boundary audit. |
| `data/raw/samples/manifest.json` | one acquisition run | Source URLs, sample bounds, byte counts, and SHA-256 hashes for all 39 rasters. |

## Modelling restrictions

- Do not treat water or non-fuel codes as missing values.
- Use FBP nearest-neighbour resampling. Do not average categorical codes.
- Use `aspect_sin` and `aspect_cos` instead of raw aspect degrees in LightGBM if smooth directional relationships matter.
- Pin every static layer to a publication/reference year available at prediction time. SCANFI 2025 and FBP 2024 are future leakage for older historical labels unless the model explicitly represents a current/future deployment period.
- These fields are predictors, not the target `y`. A proposed target is `fire_start_next_24h`, defined from historical fire-start records after space-time joins and deduplication.

## Team source contract — 2026-10-09

The team selected the following seven source groups. This contract supersedes the earlier broad acquisition wishlist. The sections above describe existing pilot outputs; they do not establish that all selected inputs have been acquired. Source field names below follow the team's supplied specification and still require schema, unit, timezone, and coverage verification against downloaded files.

| # | Selected dataset | Purpose and fields | Exclusions and handling |
| --- | --- | --- | --- |
| 1 | [Ontario Fire Disturbance Point](https://geohub.lio.gov.on.ca/datasets/lio::fire-disturbance-point/about) + [Area](https://geohub.lio.gov.on.ca/datasets/lio::fire-disturbance-area/about), one source with two layers | Point geometry, `FIRE_START_DATE`, `FIRE_YEAR`: labels and splits. `FIRE_GENERAL_CAUSE_CODE`: outcome reporting. `FIRE_TYPE_CODE`, `LOCATION_ACCURACY`: filtering/quality. `FIRE_FINAL_SIZE`, `FIRE_OUT_DATE`, area polygons: final-outcome and spread endpoint checks. | Exclude all final-outcome/cause fields from contemporaneous ignition predictors. Exclude fire-record `FIRE_WEATHER_INDEX` and `FIRE_RESPONSE_OBJ_CODE`. Verify date precision, point meaning, identifiers, and event deduplication before constructing labels; final polygons do not label intermediate spread times. |
| 2 | [NASA FIRMS VIIRS 375 m archive](https://firms.modaps.eosdis.nasa.gov/download/) | Validation only: `latitude`, `longitude`, `acq_date`, `acq_time` in UTC, `confidence`, `type`, `daynight`, `frp`. Filter vegetation-fire type and low-confidence detections according to the downloaded product's schema. | Exclude from ignition classifier inputs. Match observations to events and actual overpass times; missing detections are not proof of no fire. S-NPP archive starts 2012-01-20; other satellites have different start dates. |
| 3 | [ERA5-Land hourly](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land) | Historical `2t`, `2d`, `u10`, `v10`, `tp`; derive RH, wind speed/direction, 24-hour and 7-day rainfall, days since rain, lagged weather, and FFMC/DMC/DC/ISI/BUI/FWI. | Exclude soil, leaf-area, and radiation fields from the chosen feature set. Convert units and decode precipitation accumulation before aggregation. Native weather resolution remains approximately 9 km even when aligned to 2.5 km cells. |
| 4 | [HRDPS 2.5 km](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/) | Live 2 m temperature/humidity, 10 m wind, precipitation; surface weather for scoring and wind for simulation. Keep forecast issue time, retrieval/availability time, valid time, and lead hour. | Exclude upper-air and unrelated surface fields. Select an available run whose valid times cover the simulation start through +6 h; run hours 0–6 alone may not do so for an older run. If next-24-hour forecast summaries are model inputs, fetch sufficient lead hours; HRDPS provides forecasts through 48 h. |
| 5 | [FBP Fuel Types 2024, 30 m](https://open.canada.ca/data/en/dataset/4e66dd2f-5cd0-42fd-b82c-a430044b31de) | Fuel code, dominant category, and conifer/deciduous/mixedwood/open/nonfuel shares for ignition and simulation. Keep water, unknown/unmapped, and missing states distinct. | Treat codes categorically and retain the 2024 legend. Verify simulator support for each fuel class. Existing 2026 EDA material is not a silent replacement. |
| 6 | [Team-linked SCANFI product, 2020 reference](https://open.canada.ca/data/en/dataset/18e6a919-53fd-41ce-b4e2-44a9707c52dc) | Canopy closure, species composition rolled into percent conifer for mixedwood fuels, optional canopy height. | Exclude biomass and land-cover fields. Verify the exact product version and species-band definitions before computing percent conifer; the existing pilot uses SCANFI v2, which must not be assumed identical to the team's linked product. |
| 7 | [MRDEM 30 m DTM](https://open.canada.ca/data/en/dataset/18752265-bda3-498c-a4ba-9dfe68cb98da) | Elevation; derive slope percent and aspect encoded as sine/cosine. | Existing pilot slope is in degrees. Convert with `slope_pct = 100 * tan(slope_degrees * pi / 180)` where appropriate, with units explicit. Review negative elevations and terrain artifacts before simulation. |

### Derived weather and validation requirements

- RH and FWI are derived features, so no additional RH/FWI source is required. Implement and validate these transformations; their derivation is not yet complete. [ECMWF humidity guidance](https://confluence.ecmwf.int/pages/viewpage.action?pageId=177484060) documents RH from temperature and dewpoint.
- FWI needs moisture-code initialization/history, a chosen algorithm version, fire-season handling, and local-standard-time noon weather with the preceding 24-hour rainfall. Maintain state across days. [NRCan calculation guidance](https://cwfis.cfs.nrcan.gc.ca/downloads/docs/en/references/seasonal-forecast/seasonal-forecast-backgrounder.pdf) describes these inputs and startup requirements. A morning prediction cannot use that day's observed noon conditions; use the latest eligible state or forecasts issued before the cutoff.
- ERA5-Land historical processing and HRDPS live processing require a common feature contract, but reanalysis-based evaluation is not a verified forecast-based deployment result. Retain HRDPS run history, bridge the recent-weather gap, and assess the input-distribution change before operational scoring. A latest-run six-hour slice alone cannot initialize seasonal FWI or seven-day rainfall features.
- VIIRS observations are overpass snapshots, not an hourly perimeter series. Keep 1-, 3-, and 6-hour simulation horizons, but score only horizons with suitable observations and report coverage. [NASA temporal-sampling guidance](https://wiki.earthdata.nasa.gov/spaces/FIRMS/blog/2024/09/20/391318378/How%2Bto%2Btrack%2Bdaily%2Bfire%2Bprogression%2Busing%2Bgeostationary%2Bactive%2Bfire%2Bdata) explains why regular subdaily validation cannot be assumed.
- Verify source publication and reference dates before choosing training years. Selected FBP 2024 and SCANFI 2020 cannot automatically be used as contemporaneous inputs for earlier fires. Any retrospective fixed-landscape experiment must be labelled separately from a cutoff-honest prediction evaluation.

No separate lightning or road/access dataset is planned under this source contract. Historical boundary downloads remain study-mask/EDA material, not an additional predictive source. Complete coverage of proposal requirements is pending a requirement-by-requirement review, especially the spread-validation and live-input requirements.

### Verified Week 5 pilot schema — 2026-10-09

The [new ignition pilot](ignition_pilot.md) uses selected SCANFI v1.2/2020 rather than the earlier v2 EDA inputs. Its 30,816 Thunder Bay cell-days contain one recorded start. The Ontario point API lacks `LOCATION_ACCURACY`; only the area schema includes it. Point start dates have no measured ignition clock time. The source query returned two candidates, one outside the exact projected grid and excluded from labels.

| New/changed field | Units or type | Handling |
| --- | --- | --- |
| `reported_fire_start` | 0/1 | Calendar-day recorded-start label; zero does not establish complete absence of fire. |
| `recorded_fire_count` | count | Label metadata, **exclude from predictors**. |
| `date`, `window_start_utc`, `window_end_utc` | ISO date; UTC timestamps | Fixed UTC−05:00 midnight convention; timestamps are assumptions, not measured ignition times. |
| `closure_2020_pct` | percent | Selected SCANFI v1.2 canopy closure, not the original v2 column. |
| `percent_conifer` | percent of canopy | Nine conifer species normalized against conifer plus broadleaf, canopy-weighted; missing in 31 zero-canopy cells. |
| `slope_pct` | percent | Native DTM gradient magnitude multiplied by 100, then aggregated; not the tangent of averaged slope degrees. |
| `scanfi_version`, `fbp_version` | strings | v1.2/2020 and 2024; source metadata, exclude from predictors. |

Available predictor and label-metadata lists are recorded in `data/processed/ignition_pilot_summary.json`. No weather columns or computed FWI are present, and `training_ready` is false. Raw v1 species proportions are not the same units as v2 species crown-closure bands. The saved v1 README records the November 2024 release and CC BY 4.0 attribution requirement.
