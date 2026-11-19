"""The fixed contract of the spread experiments: paths, label, features and the models compared.

Every learned model answers the simulator's question for one replay step: given
the fire at one satellite pass and the weather until the next, which 375 m cells
will be newly seen burning?  Each row of the cell table is one candidate cell of
one step: an unburned cell within `RADIUS_M` of the area burned so far.
"""

from __future__ import annotations

from scripts.spread_common import ARTIFACTS, MODELING_DOCS


SEED = 385
LABEL = "label"
RADIUS_M = 6_000.0  # candidates: unburned cells this close to the burned area (about 97% of calibration head runs)
TARGET_AREA_RATIO = 1.3  # satellite cells cover a median 77% of a fire's final area, so true growth is about 1.3x the cells seen

# Tracked results (docs/modeling/).
SIMULATOR_SCORES = MODELING_DOCS / "simulator_scores.json"
SIMULATOR_CALIBRATION_STEPS = MODELING_DOCS / "simulator_calibration_steps.csv"
SIMULATOR_HOLDOUT_STEPS = MODELING_DOCS / "simulator_holdout_steps.csv"
CELL_TABLE_AUDIT = MODELING_DOCS / "cell_table_audit.json"
CELL_MODELS_TRAINING = MODELING_DOCS / "cell_models_training.json"
CNN_TRAINING = MODELING_DOCS / "cnn_training.json"
COMPARISON = MODELING_DOCS / "comparison.json"

# Generated, not in git (artifacts/spread_modeling/).
WORK = ARTIFACTS / "spread_modeling"
CELL_TABLE = WORK / "cell_table.parquet"
CELL_TABLE_STEPS = WORK / "cell_table_steps.csv"
CNN_PATCHES = WORK / "cnn_patches.npz"
CNN_PATCH_INDEX = WORK / "cnn_patch_index.parquet"
MODEL_DIR = WORK / "models"
HOLDOUT_STEP_SCORES = WORK / "holdout_step_scores.csv"

# Feature groups.  All are known at the first pass except the step's weather, which the simulator is given too
# (both replay the observed reanalysis weather; neither is a forecast).
GEOMETRY = [
    "distance_to_burned_m", "distance_to_active_m", "downwind_cos", "crosswind_abs_sin", "along_wind_m", "across_wind_m",
    "previous_head_cos", "active_cells_nearby", "burned_cells_nearby", "burned_cells_total", "active_cells_total",
]  # fmt: skip
PERSISTENCE = ["previous_new_cells", "previous_spread_p90_m", "previous_frp_total_mw", "hours_since_first_observation"]
WEATHER = [
    "step_hours", "night_share", "wind_mean_kmh", "wind_max_kmh", "wind_steadiness", "temp_mean_c", "rh_min_pct",
    "precip_total_mm", "ffmc", "bui", "isi", "dmc", "dc", "fwi",
]  # fmt: skip
FUEL = [
    "fuel_conifer_share", "fuel_mixedwood_share", "fuel_deciduous_share", "fuel_grass_share", "fuel_non_fuel_share",
    "fuel_water_share", "burnable_share_nearby", "fbp_head_ros_m_per_min",
]  # fmt: skip
TERRAIN = ["elevation_m", "rise_from_front_m", "slope_from_front"]
SIMULATOR = ["sim_reached_share", "sim_arrival_fraction"]

# Feature sets.  `no_fuel` leaves out every fuel feature: if the result held only because of fuel, the burn-scar
# repair of the 2024 fuel map could be leaking the final perimeter.  `with_simulator` adds the tuned simulator's
# prediction, so a model can learn where the physics goes wrong.
FEATURE_SETS = {
    "base": GEOMETRY + PERSISTENCE + WEATHER + FUEL + TERRAIN,
    "no_fuel": GEOMETRY + PERSISTENCE + WEATHER + TERRAIN,
    "with_simulator": GEOMETRY + PERSISTENCE + WEATHER + FUEL + TERRAIN + SIMULATOR,
}

# The per-cell models compared with the simulator: name -> (family module, feature set).  Every family sees the same
# base features, so differences between families come from the family, not from what it was given.  The CNN models
# (`cnn`, `cnn_hybrid`) read the same information as maps; see cnn.py.
MODELS = {
    "logistic": ("logistic", "base"),
    "random_forest": ("random_forest", "base"),
    "mlp": ("mlp", "base"),
    "hgb": ("gradient_boosting", "base"),
    "hgb_no_fuel": ("gradient_boosting", "no_fuel"),
    "hgb_hybrid": ("gradient_boosting", "with_simulator"),
    "xgboost": ("xgboost_gpu", "base"),
    "xgboost_hybrid": ("xgboost_gpu", "with_simulator"),
}

# Fire-level outcomes and anything defined by the final perimeter: never a feature.
FORBIDDEN = {
    "reported_size_ha", "perimeter_area_ha", "size_class", "out_date", "duration_days", "growth_steps", "fire_growth_steps",
    "trackable", "detected_share_of_perimeter", "ignition_inside_perimeter", "ignition_distance_to_perimeter_m",
    "observed_new_cells", "new_cells_next", LABEL,
} | {f"fuel_inside_{suffix}" for suffix in [
    "cells", "conifer_share", "mixedwood_share", "deciduous_share", "open_share", "non_fuel_share", "water_share",
    "percent_conifer", "dominant_fuel_type",
]}  # fmt: skip
