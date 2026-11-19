# Project context

COMP-385 is building data products for Ontario wildfire modelling. Keep the two
prediction problems distinct: the ignition product predicts whether an existing
10 km grid cell has an ignition on a calendar day; a future spread product will
predict incident-conditioned fire-front/perimeter progression. Do not describe
the ignition panel as a spread model or use final perimeters, final size, burn
products, or future detections as ignition predictors.

## Ignition panel and feature layer

The established label universe is the Ontario Fire Region 10 km, fire-season
cell-day ignition panel for 2010--2019: 9,673 cells, 1,840 dates, and
17,798,320 rows. Its key is `(grid_id, ignition_date)`, with `ignition_date` a
local `America/Toronto` date. The current `ignition-feature-v1.1.0` builder
retains that exact row universe and labels and provides 51 columns:

- calendar/solar variables computed at a 00:00 local issue time;
- static CDEM terrain summaries;
- static full-cell centre coordinates: `cell_centroid_easting_m = grid_x_m + 5000`
  and `cell_centroid_northing_m = grid_y_m + 5000`, in EPSG:3978 metres, fixed
  per cell (not ignition points, longitude/latitude, or clipped centroids);
- CWFIS weather/FWI features from only the prior-day observation; and
- NFDB ignition-history features based only on records strictly before the
  issue date.
  `fire_history_days_since_same_cell__censored` is persisted as `1` exactly
  when days-since is blank (no earlier observed same-cell event in the
  available 2010+ history), otherwise `0`; the original blank remains blank.

Preserve source quality rather than filling it away. The feature output carries
missingness, station coverage/distance, interpolation and `calcstatus` flags,
terrain coverage/sample counts, source/version linkage, and audit metadata.
Early history is incomplete by design because the committed event subset begins
in 2010; do not fabricate a pre-2010 history.

The full feature output is
`data/processed/ontario_fire_region_10km_daily_ignition_features_v1.csv.gz`
and its matching audit is
`data/processed/ontario_fire_region_10km_daily_ignition_features_v1_audit.json`.
Both are generated artifacts and may be absent in a fresh clone. The
2026-11-19 v1.1.0 full rebuild wrote 51 columns and all 17,798,320 expected
rows, with zero prior-day weather timing violations. Old 48-column panel
copies were preserved under `_legacy_48cols` names; the old 36-column cache
was preserved as `data/interim/ignition_modeling_cache_legacy_v2`.
Consult the current output's audit, including coordinate semantics and grid
checksum, before use. Modelling still uses separately corrected CWFIS values.

Historical v1.0.0 source coverage is deliberately imperfect: CWFIS weather/FWI values
are unavailable on 9,340,916 rows (52.482010%), and seven-day precipitation is
unavailable on 62.610842% of rows. These are source-coverage states, not zeroes
or values to silently fill in the dataset. Retain `cwfis_missing`, station
count/distance, coverage, interpolation, and calculation-status fields. The
tiny terrain gaps are also represented by terrain sample/coverage fields.

This is a retrospective hindcast/explanatory dataset, not an operational
forecast replay. Although CWFIS rows are restricted to `t - 1`, the historical
CWFIS and NFDB archives do not give per-record `available_at` timestamps. Do
not claim that a modern archive download was known at the historical issue
time. CDEM is allowed only as static ground terrain, not as a proxy for
vegetation, fuels, roads, settlement, or disturbance.
The new coordinates add static grid geometry only, not dynamic observations or
operational forecasting evidence. The static CDEM source retains its
`terrain_feature_version` of `ignition-feature-v1.0.0`.

`data/metadata/ignition_feature_selection_v1.json` is the only authoritative
39-predictor list for the panel, corrected-weather cache, main model and demo.
Order: original 36, persisted history-censor flag, then two coordinates.
HGB preprocessing preserves all 39 inputs; it must not append another flag
or coordinates. Cache version `ignition-v1-weather-asof-global-date-coordinates-v3`
rejects old 36-column caches. `docs/modeling/feature_manifest.json` references
the canonical list; it is not another source. Historical model results remain
archived, but the current main training path fits the retained 80-iteration
coordinate HGB on 2010–2016 only. Export settings, ordered inputs, cache/source
checksums, commit, dirty-tree state and source hashes beside the joblib model.

## Leakage rules

All dynamic inputs must have been observed before the local target day starts.
Keep history updates after a date has completed, use dated source vintages, and
retain unknown/missing source coverage as missing rather than zero. Any fitted
scaling, imputation, target encoding, climatology, smoothing, or feature
selection belongs inside the training side of each temporal/spatial split.

For training, do not delete rows because CWFIS is missing. Prefer a model with
native missing-value handling, or fit numeric imputation and explicit missing
indicators on each training partition only. `fire_history_days_since_same_cell`
being blank means no earlier observed same-cell event in the available 2010+
history; it is a censored state, not ordinary weather missingness. Keep
`large_fire_200ha` out of the ignition-feature inputs because it is a label.

Do not silently backfill current maps into 2010--2019. Land cover/fuels,
roads/access, settlement/population, lightning, satellite phenology, and
ERA5-Land enrichment remain deferred until each has an appropriate historical
asset plus an availability/quality ledger. ERA5-Land remains a hindcast unless
replaced by forecasts archived before each issue time. Operational forecasting
also remains future work.

## Roadmap

First maintain and validate the ignition panel and its time contract, then add
the deferred feature families only with documented source timing and tests.
Build fire spread separately: it needs incident-conditioned candidate cells and
dated fire-front or perimeter progression. It does not yet exist; final
perimeters and final fire size cannot substitute for that target.

## Reproducibility and artifacts

The default feature builder expects `shapely` for the spatial label build. Use
an environment that provides it; do not add a global dependency merely to run a
one-off rebuild. A complete rebuild from a fresh checkout is:

```sh
python -c "import shapely"
python scripts/download_nfdb.py
python scripts/prepare_ontario_ignitions.py
python scripts/download_ontario_fire_region.py
python scripts/build_cpa_daily_ignition_labels.py
python scripts/download_cwfis_fwi.py
python scripts/build_ignition_feature_panel.py
python -m unittest discover -s tests -v
```

The feature build command is unchanged; existing output replacement requires
`python scripts/build_ignition_feature_panel.py --force` and deliberate review
of the generated panel and matching audit. Output and metadata filenames retain
the `_v1` family suffix even though the current feature contract is v1.1.0.

`data/interim/cdem_terrain_10km_summary.csv` is tracked and normally reused.
Only run `python scripts/build_cdem_terrain_summary.py` when deliberately
regenerating that static CDEM summary; it queries the elevation source and must
remain terrain-only. `download_cwfis_fwi.py` checksum-validates its archive and
must not be bypassed with `--allow-source-change` unless an upstream revision
has been consciously reviewed and documented.

Treat large deterministic panels and downloaded source archives as generated
artifacts: do not commit them merely because a rebuild produced them. Keep
small manifests, source registries, audit JSON, and documentation when they
record provenance, checksums, coverage, missingness, alignment, or leakage
validation. Use explicit output/audit paths for any date-range test subset so
it cannot be mistaken for the full panel.

`ABOUT.md` is the human-facing project reference: it contains the complete
51-column dictionary, null semantics, historical v1.0.0 rebuild summary and
validation snapshot, training guidance, and planned work. Read it together
with this file before altering the feature contract.

## Verified main export and demo

The 2026-11-19 main-pipeline rebuild completed the full panel and corrected
39-column v3 cache. `artifacts/ignition_modeling/retained_coordinate_hgb/`
contains the joblib export, settings/feature/training/cache/commit provenance
and verification JSON. All 12,458,824 2010–2016 development predictions
match the original experiment pickle bit-for-bit, with maximum difference 0.
The metadata explicitly records the base commit plus a dirty source tree and
source-file hashes; no new commit was made for this rebuild.

The demo loads that main export and shows the frozen 10 km grid footprint.
The pinned Ontario boundary asset is unavailable; do not substitute a
checksum-mismatched boundary. Its manifest remains unchanged. Score cutoffs
are illustrative, not the old 40-iteration model's validated policy. No
2017–2019 fitting, calibration or global reserved-year scoring was added.
