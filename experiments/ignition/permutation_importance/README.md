# Within-day permutation importance: retained ignition HGB80

This experiment measures the retained 39-input ignition model’s reliance on
spatial differences among cells **conditional on local calendar day**. These
are predictive diagnostics for a retrospective hindcast, not causal effects,
operational forecasting evidence, or a fire-spread result.

## Method

Each May–October validation season from 2012 through 2016 uses a separate HGB
fit on the May–October seasons from 2010 through the preceding year. The fit
uses 80 iterations, learning rate 0.1, L2 regularization 1.0, at most 15 leaves,
minimum leaf size 100, seed 385, no class weights and no early stopping. The
runner reads the corrected v3 cache without rebuilding it or reading 2017–2019
feature or label rows. The main export is unchanged.

In each of five repeats per fold, all targets share one independently seeded
within-day donor mapping. Individual inputs are shuffled alone; a family is
shuffled jointly with the same donor for every member. This preserves
within-family combinations (including the joint missing-history/censor flag)
but can break dependencies with other inputs. An individual history
perturbation can break the history/flag pair, so perturbed values go directly
to the fitted classifier, not through the production history validator. The
runner first checks that pristine classifier and pipeline probabilities match
exactly and that full-year baseline AP matches the archived coordinate run.
Family drops need not add up to the individual drops.

For each target, repeats are averaged within each year. Percent drops divide
that year’s mean AP drop by the same year’s baseline AP. The tables average the
five annual values equally in each unit and report the annual extrema and their
years in both units. Negative drops mean shuffling improved AP. A fold range
that includes zero describes fold variability, not a confidence interval or
significance test. An input that is exactly constant within each day cannot
be tested for spatial reliance by this shuffle; zero for such an input does
not rule out seasonal reliance.

## Reproduce

From the repository root, use `.venv-modeling` with
[`requirements-modeling.txt`](../../../requirements-modeling.txt) and the
existing `data/interim/ignition_modeling_cache` (override with `--cache`).
Point `TMPDIR` to a disk-backed filesystem with more than 3.4 GB of free space
for transient training data. Output must be a fresh directory outside the
experiment and data trees.

```sh
run_dir=$(mktemp -d)
TMPDIR=/var/tmp OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  .venv-modeling/bin/python -m experiments.ignition.permutation_importance.experiment \
  --output "$run_dir/results"
```

## Results

- [Ranked predictors](feature_importance.csv) · [Top 15 chart](top_15_features.png)
- [Ranked families](group_importance.csv) · [Family chart](group_importance.png)

All five baseline APs matched the reference exactly; all 1,100 perturbation
results include any exact no-change cases.

| Year | Baseline AP |
| --- | ---: |
| 2012 | 0.010238445335159507 |
| 2013 | 0.009042434402703234 |
| 2014 | 0.001749552313396256 |
| 2015 | 0.004511448819081327 |
| 2016 | 0.009285744616406409 |

| Top five predictors | Mean drop (% of baseline AP) | Feature family | Mean drop (% of baseline AP) |
| --- | ---: | --- | ---: |
| `fire_history_days_since_same_cell` | 42.538% | Fire history | 72.250% |
| `fire_history_neighborhood_30d` | 37.142% | CWFIS weather | 35.421% |
| `fire_history_neighborhood_365d` | 34.045% | Coordinates | 23.962% |
| `fire_history_same_cell_365d` | 21.620% | Terrain | 23.645% |
| `cell_centroid_northing_m` | 16.709% | Calendar | 8.399% |

- **Negative mean percent drops:** `fire_history_same_cell_30d` (−0.039%),
  `cwfis_precip_mm` (−0.437%), `cwfis_dc` (−0.438%), `cwfis_bui` (−1.409%),
  `cwfis_ffmc` (−2.885%), `cwfis_isi` (−3.353%). The raw mean AP drop was
  negative for these six plus `cwfis_wind_speed_kmh`.
- **Fold AP drops bracketed zero** (inclusive, including all-zero ranges):
  `fire_history_same_cell_365d`, `cwfis_dmc`, `cwfis_rh_pct`,
  `cwfis_nearest_station_km`, `terrain_aspect_cos`, `cwfis_temp_c`,
  `terrain_aspect_sin`, `cwfis_dsr`, `cwfis_precip_7d_mm`, `cwfis_fwi`,
  `terrain_slope_deg`, `cwfis_wind_speed_kmh`, `cwfis_station_count`,
  `calendar_day_of_year`, `calendar_doy_cos`, `calendar_doy_sin`,
  `calendar_is_weekend`, `cwfis_calcstatus_nonzero_fraction`,
  `cwfis_imputed_station_fraction`, `cwfis_missing`,
  `cwfis_observation_coverage_fraction`, `cwfis_precip_7d_coverage_days`,
  `fire_history_days_since_same_cell__censored`, `terrain_coverage_fraction`,
  `terrain_sample_count`, `fire_history_same_cell_30d`, `cwfis_precip_mm`,
  `cwfis_dc`, `cwfis_bui`, `cwfis_isi`.
- **Exactly day-constant in every fold:** `calendar_day_of_year`,
  `calendar_doy_sin`, `calendar_doy_cos`, `calendar_is_weekend`. Their drops
  were exactly zero; `calendar_day_length_hours` varied within days and
  accounted for the measured calendar-family drop.
