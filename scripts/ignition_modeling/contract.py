"""Authoritative ignition feature contract; labels never enter model matrices."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELECTION_PATH = ROOT / "data/metadata/ignition_feature_selection_v1.json"
FEATURE_SELECTION = json.loads(SELECTION_PATH.read_text())
FEATURE_NAMES = tuple(FEATURE_SELECTION["predictors"])
FEATURE_SET_VERSION = FEATURE_SELECTION["feature_set_version"]
if len(FEATURE_NAMES) != FEATURE_SELECTION["predictor_count_before_preprocessing"] or len(set(FEATURE_NAMES)) != len(FEATURE_NAMES):
    raise ValueError("Feature selection must contain the declared number of unique predictors")
WEATHER_FEATURES = tuple(n for n in FEATURE_NAMES if n in {
    "cwfis_temp_c", "cwfis_rh_pct", "cwfis_wind_speed_kmh", "cwfis_precip_mm",
    "cwfis_ffmc", "cwfis_dmc", "cwfis_dc", "cwfis_isi", "cwfis_bui",
    "cwfis_fwi", "cwfis_dsr", "cwfis_precip_7d_mm"})
HISTORY_FEATURE = "fire_history_days_since_same_cell"
HISTORY_CENSOR_FEATURE = f"{HISTORY_FEATURE}__censored"
COORDINATE_FEATURES = ("cell_centroid_easting_m", "cell_centroid_northing_m")
INDICATOR_FEATURES = tuple(n for n in FEATURE_NAMES if n in set(WEATHER_FEATURES) | {
    "terrain_elevation_mean_m", "terrain_slope_deg", "terrain_aspect_sin",
    "terrain_aspect_cos", "terrain_ruggedness_m", "cwfis_nearest_station_km",
    "cwfis_imputed_station_fraction", "cwfis_calcstatus_nonzero_fraction"})
SEED = 385
CACHE_VERSION = "ignition-v1-weather-asof-global-date-coordinates-v3"
RETAINED_HGB_PARAMS = {
    "max_iter": 80, "class_weight": None, "learning_rate": 0.1,
    "max_leaf_nodes": 15, "min_samples_leaf": 100, "l2_regularization": 1.0,
}

def check_matrix(X):
    if getattr(X, "ndim", None) != 2 or X.shape[1] != len(FEATURE_NAMES):
        raise ValueError(f"Expected numeric inputs in the exact {len(FEATURE_NAMES)}-feature selection order")
