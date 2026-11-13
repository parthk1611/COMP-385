# Ignition modelling experiments

This directory records our investigation into improving Ontario wildfire
**ignition** prediction: ranking existing 10 km × 10 km grid cells by whether
at least one ignition occurs on a calendar day. It is not a fire-spread model.

**Our retained project configuration is histogram gradient boosting (HGB) with
cell-centre coordinates and 80 boosting iterations, using 15 maximum leaves.**
The clearest retained changes were increasing the original 40-iteration HGB to
80 iterations, then adding coordinates. Later investigations did not establish
a sufficiently consistent improvement to replace that configuration.

## Shared evaluation context

- Follow-up modelling uses the **corrected-weather cache**, not the original
  uncorrected v1 weather values. The original panel's grid, labels and rows are
  retained; experimental features are added separately.
- Five expanding chronological folds validate on **2012–2016**. Every cell-day
  is retained, including negatives and rows with missing weather.
- The main comparison metric is **unweighted mean yearly average precision
  (AP)** across those five folds. ROC-AUC, Brier score, log loss and daily
  ranking-budget measures provide additional context.
- These are retrospective development experiments, not independent final tests
  or operational forecast replays. Dynamic inputs must precede local-midnight
  issue time. The original study already examined 2019; these follow-ups do not
  create a new blind test there.

## Investigation history — chronological order

The order below follows the work as it happened, rather than alphabetical
folder order. There are **10 modelling-experiment groups and two analysis-only
investigations**. Percentage changes describe relative mean yearly AP against
that investigation's stated baseline, not percentage-point gains.

| Order | Investigation | What we tried and learned |
| --- | --- | --- |
| 1 | [Manual HGB tuning](tuning/README.md) | Tested 40/80/160 iterations, then regularization and capacity changes. Moving from 40 to **80 iterations improved mean AP by 6.45%**; 160 iterations, lower L2 and greater capacity did not beat the selected 80-iteration configuration. |
| 2 | [Cell-centre coordinates](coordinates/README.md) | Added static easting/northing for each cell centre: projected grid origin + 5,000 m in each axis, not ignition-point coordinates. Mean AP improved **1.46%** over tuned HGB, with improvement in four years but a substantial decline in 2013. |
| 3 | [Coordinates × capacity follow-up](coordinate_capacity/README.md) | After investigating the 2013 decline, completed the with/without-coordinates × 15/31-leaf comparison. Extra capacity helped 2013 but not the overall result; **coordinates with 15 leaves** remained preferable. |
| 4 | [Randomized HGB search](randomized/README.md) | Used `RandomizedSearchCV` for eight seeded joint parameter combinations on the same chronological folds. None beat the existing coordinate/80-iteration baseline; the best sampled candidate had **16.34% lower** mean AP. |
| 5 | [Complete local HGB grid](local_search/README.md) | Reviewed tuning weaknesses and tested a complete nine-point neighbourhood of learning-rate/iteration pairs and L2 settings. No new configuration beat the baseline; the best new setting had **8.59% lower** mean AP. |
| 6 | [Logistic regression with coordinates](logistic_coordinates/README.md) | Gave logistic regression the same coordinate information rather than comparing unequal feature sets. Its mean AP rose **0.54%** against its archived logistic baseline, but coordinate HGB remained ahead in every development year. |
| 7 | [Fixed XGBoost benchmark](xgboost/README.md) | Tried one CPU-histogram XGBoost configuration with the same predictor information. Mean AP was **14.99% lower** than coordinate HGB. Some secondary metrics improved, but this did not overturn the agreed AP-based choice. A neural-network experiment was not pursued. |
| 8 | [Daily ranking utility — analysis only](ranking_utility/README.md) | Examined saved coordinate-HGB predictions at daily top-1%, top-2% and top-5% review budgets, including weather-coverage and tie sensitivity. The model concentrates positives into smaller review sets, but precision remains low. No new models were fitted. |
| 9 | [Recent neighbourhood fire history](recent_history/README.md) | Added 1-day and 7-day counts in the existing 3×3 neighbourhood. The original 30/365-day history features were already present, not removed. Mean AP declined **9.18%**, with lower AP in every year, so the new short-window features were not retained. |
| 10 | [Combined lightning features](lightning/README.md) | After auditing source availability and timing, added permitted trailing 24-hour and seven-day cloud-to-ground lightning densities. Stored development coverage was complete, but mean AP fell **2.91%**; only 2013 improved. Complete stored coverage does not establish detector uptime. |
| 11 | [Separate lightning-window ablations](lightning_windows/README.md) | Tested 24-hour-only and seven-day-only inputs separately. The 24-hour variant achieved **0.77% higher** mean AP, driven by 2013 while the other four years worsened; seven-day only lost **5.90%**. We did not promote the small, uneven numerical winner as an established improvement. |
| 12 | [Lightning diagnosis — analysis only](lightning_diagnosis/README.md) | Checked natural/human cause groups, permitted exposure and paired global daily ranks. Only **17.2%** of natural-only positive cell-days had 24-hour exposure and **52.7%** had seven-day exposure. Recent-exposure rank gains were modest, not a large hidden natural-fire benefit cancelled by human-fire losses. No new models were fitted. |

## Retained configuration and conclusion

The retained candidate uses the corrected predictors plus the two static
**EPSG:3978 cell-centre coordinates in metres**. With the existing history-censor
indicator, this gives 38 raw predictors and 39 transformed HGB inputs.

- `max_iter=80`, `max_leaf_nodes=15`, `min_samples_leaf=100`.
- `learning_rate=0.1`, `l2_regularization=1.0`.
- Seed 385; no class weighting or early stopping; native weather-missingness
  handling is retained.
- Recorded mean development AP: **0.006965525**.

**Retained choice does not mean strict numerical winner across every trial.**
The 24-hour-lightning variant recorded mean AP **0.007019494**, slightly higher
than coordinate-only HGB, but its improvement was small and concentrated in one
year. We retained the simpler coordinate/80-iteration HGB for this project;
these reused development results do not establish statistical significance or
universal superiority over other models.

The experiments support a limited risk-ranking use, not reliable prediction of
individual ignitions. Further model complexity and the tested feature additions
did not establish a consistent upgrade within this project's scope. The original
frozen model and evaluation artifacts remain unchanged. A separate **2010–2016
development refit** of the retained configuration is now available as a
[verified model pickle](coordinates/README.md#saved-model-pickle); exporting it
did not add a held-out evaluation or calibration.

## Reading each experiment folder

- **`README.md`**: question, method, findings, limitations and decision.
- **`results.json`**: detailed recorded results, including original settings in
  `recorded_configuration`, supporting scientific JSON in `supporting_results`,
  and original comparison-table rows in `tables`.
- **`experiment.py`**: the experiment or analysis implementation.
- **`requirements.txt`**: dependencies, referencing the common modelling
  requirements. Lightning also retains `build_features.py`.

The runners now share a small [`common.py`](common.py) for coordinate assembly,
bounded-memory HGB fitting and metric aggregation. Model/feature calculations,
candidate settings, chronological folds and selection rules are retained; source
fingerprint, environment-equality and resume bookkeeping have been removed.
Reruns write new ignored directories under `artifacts/ignition_modeling/reruns/`
and refuse to replace existing outputs. Saved baseline predictions and native
source/mapping files remain explicit generated prerequisites. Historical
`results.json` files and the selected model pickle are not rewritten by reruns.
See the [original modelling guide](../../docs/modeling/README.md) for the
corrected-data and original evaluation context.

## Simplification checks

The refactor preserved the original feature hashes across all 12,458,824
development rows for both recent history and lightning. Old/new bounded model
probes produced bit-identical HGB, logistic and XGBoost predictions, including
staged iteration scores and preprocessing. A one-iteration chronological search
adapter probe also matched all 1,779,832 validation probabilities exactly.
Both saved-prediction analyses reproduced their original aggregate results.

All twelve command entry points were exercised. Archived results, core pipeline
files and the selected model pickle remained unchanged. These are refactor
parity checks, not new performance claims: the complete tuning searches were
not rerun and no 2017–2019 fitting or scoring was introduced.
