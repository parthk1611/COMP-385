#!/usr/bin/env python3
"""Learned fire-spread models: the per-cell feature contract shared by building, training and scoring.

A learned model answers the simulator's question for one replay step: given the
fire at one satellite pass and the weather until the next, which 375 m cells
will be newly seen burning?  Each row is one candidate cell of one step: an
unburned cell within `RADIUS_M` of the area burned so far.

Every feature is known at the first pass, except the step's weather, which the
simulator is given too (both are retrospective replays with the observed
reanalysis weather, not forecasts).  Nothing is taken from the fire's final
perimeter, final size, out date or later passes, and the fuel is the same
burn-scar-repaired fuel the simulator uses.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import ndimage

from fbp_spread import MAP_CODES, ellipse_rates
from simulate_spread import CELL_375_M, WATER_CODE
from spread_common import PROCESSED


RADIUS_M = 6_000.0  # candidates: unburned cells this close to the burned area (about 97% of calibration head runs)
NEIGHBOURHOOD_CELLS = 3  # half-width, in 375 m cells, of the "nearby" counts (a 7 x 7 block, about 2.6 km)
NIGHT_HOURS = set(range(0, 7)) | {20, 21, 22, 23}  # local hours

KEYS = ["fire_id", "split", "fire_year", "observation", "next_observation", "cell"]
LABEL = "label"
GEOMETRY = [
    "distance_to_burned_m", "distance_to_active_m", "downwind_cos", "crosswind_abs_sin", "along_wind_m", "across_wind_m",
    "previous_head_cos", "active_cells_nearby", "burned_cells_nearby", "burned_cells_total", "active_cells_total",
]
PERSISTENCE = ["previous_new_cells", "previous_spread_p90_m", "previous_frp_total_mw", "hours_since_first_observation"]
WEATHER = [
    "step_hours", "night_share", "wind_mean_kmh", "wind_max_kmh", "wind_steadiness", "temp_mean_c", "rh_min_pct",
    "precip_total_mm", "ffmc", "bui", "isi", "dmc", "dc", "fwi",
]
FUEL = [
    "fuel_conifer_share", "fuel_mixedwood_share", "fuel_deciduous_share", "fuel_grass_share", "fuel_non_fuel_share",
    "fuel_water_share", "burnable_share_nearby", "fbp_head_ros_m_per_min",
]
TERRAIN = ["elevation_m", "rise_from_front_m", "slope_from_front"]
SIMULATOR = ["sim_reached_share", "sim_arrival_fraction"]

# Feature sets.  `no_fuel` leaves out every fuel feature, which shows whether fuel drives the result (a check on
# the burn-scar repair: an unrepaired 2024 map would leak the final perimeter).  `with_simulator` adds the tuned
# simulator's prediction, so a model can learn where the physics goes wrong.
FEATURE_SETS = {
    "base": GEOMETRY + PERSISTENCE + WEATHER + FUEL + TERRAIN,
    "no_fuel": GEOMETRY + PERSISTENCE + WEATHER + TERRAIN,
    "with_simulator": GEOMETRY + PERSISTENCE + WEATHER + FUEL + TERRAIN + SIMULATOR,
}
# The learned models compared with the simulator: name -> (classifier family, feature set).  Every family sees the
# same base features, so differences between them come from the family, not from what it was given.
MODELS = {
    "logistic": ("logistic", "base"),
    "random_forest": ("random_forest", "base"),
    "mlp": ("mlp", "base"),
    "hgb": ("hgb", "base"),
    "hgb_no_fuel": ("hgb", "no_fuel"),
    "hgb_hybrid": ("hgb", "with_simulator"),
    "xgboost": ("xgboost", "base"),
    "xgboost_hybrid": ("xgboost", "with_simulator"),
}


def simulator_score(rows: pd.DataFrame) -> np.ndarray:
    """Rank cells by the simulator: reached share, then earliest arrival; unreached cells by distance from the fire."""
    arrival = rows.sim_arrival_fraction.fillna(2.0).to_numpy()
    return np.where(rows.sim_reached_share > 0, 2.0 + rows.sim_reached_share - arrival / 10, -rows.distance_to_burned_m / 1e5)
# Fire-level outcomes and anything defined by the final perimeter: never a feature.
FORBIDDEN = {
    "reported_size_ha", "perimeter_area_ha", "size_class", "out_date", "duration_days", "growth_steps", "fire_growth_steps",
    "trackable", "detected_share_of_perimeter", "ignition_inside_perimeter", "ignition_distance_to_perimeter_m",
    "observed_new_cells", "new_cells_next", LABEL,
} | {f"fuel_inside_{suffix}" for suffix in ["cells", "conifer_share", "mixedwood_share", "deciduous_share", "open_share", "non_fuel_share", "water_share", "percent_conifer", "dominant_fuel_type"]}

KIND_GROUP = {"conifer": "conifer", "leafless_mixedwood": "mixedwood", "mixedwood": "mixedwood", "aspen": "deciduous", "leafless_aspen": "deciduous", "grass": "grass"}


def _per_cell_mean(case, values: np.ndarray) -> np.ndarray:
    """Mean of a 90 m grid over each 375 m cell."""
    count = np.bincount(case.cell375.ravel(), minlength=len(case.cell375_keys))
    total = np.bincount(case.cell375.ravel(), weights=values.ravel().astype(float), minlength=len(case.cell375_keys))
    return total / np.maximum(count, 1)


def static_cell_layers(case) -> dict[str, np.ndarray]:
    """Per 375 m cell: fuel shares and mean elevation.  These do not change between steps of one fire."""
    layers = {}
    groups = np.full(case.fuel.shape, "non_fuel", dtype=object)
    for code, (kind, _) in MAP_CODES.items():
        groups[case.fuel == code] = KIND_GROUP[kind]
    groups[case.fuel == WATER_CODE] = "water"
    for group in ["conifer", "mixedwood", "deciduous", "grass", "non_fuel", "water"]:
        layers[f"fuel_{group}_share"] = _per_cell_mean(case, groups == group)
    layers["burnable"] = _per_cell_mean(case, np.isin(case.fuel, list(MAP_CODES)))
    layers["elevation_m"] = _per_cell_mean(case, case.elevation)
    return layers


def step_weather(case, start_utc: pd.Timestamp, hours: float, daily: pd.DataFrame) -> dict[str, float]:
    """The step's hourly weather summarised, plus the fire-weather codes of the day the step starts."""
    end = start_utc + pd.Timedelta(hours=hours)
    window = case.weather[(case.weather.time_utc >= start_utc.floor("h")) & (case.weather.time_utc < end)]
    if window.empty:
        window = case.weather.iloc[[int(np.clip(np.searchsorted(case.weather.time_utc.values, np.datetime64(start_utc.floor("h"))), 0, len(case.weather) - 1))]]
    speed = window.wind_speed_kmh.to_numpy(float)
    towards = np.radians(window.wind_direction_deg.to_numpy(float) + 180.0)  # direction the wind blows towards
    east, north = (speed * np.sin(towards)).mean(), (speed * np.cos(towards)).mean()
    local_date = case.weather.time_local[window.index[0]].strftime("%Y-%m-%d")
    day = daily.loc[local_date] if local_date in daily.index else daily.iloc[int(np.clip(np.searchsorted(daily.index.values, local_date), 0, len(daily) - 1))]
    return {
        "step_hours": hours,
        "night_share": float(np.isin(window.time_local.dt.hour, list(NIGHT_HOURS)).mean()),
        "wind_mean_kmh": float(speed.mean()),
        "wind_max_kmh": float(speed.max()),
        "wind_steadiness": float(math.hypot(east, north) / speed.mean()) if speed.mean() > 0 else 0.0,
        "downwind_bearing_deg": float(math.degrees(math.atan2(east, north)) % 360),
        "temp_mean_c": float(window.temp_c.mean()),
        "rh_min_pct": float(window.rh_pct.min()),
        "precip_total_mm": float(window.precip_mm.sum()),
        **{name: float(day[name]) for name in ["ffmc", "bui", "isi", "dmc", "dc", "fwi"]},
        "day_of_year": int(case.weather.time_local[window.index[0]].day_of_year),
    }


def fbp_head_ros(case, weather: dict[str, float]) -> np.ndarray:
    """Per 375 m cell: the mean FBP head rate of spread (m/min) of its 90 m fuel at the step's mean wind."""
    rate = np.zeros(case.fuel.shape, dtype=float)
    for code in np.unique(case.fuel):
        if int(code) in MAP_CODES:
            rate[case.fuel == code] = ellipse_rates(int(code), weather["ffmc"], weather["bui"], weather["wind_mean_kmh"], weather["day_of_year"])[0]
    return _per_cell_mean(case, rate)


def load_observation_history() -> pd.DataFrame:
    """Each observation's own growth record (known at that pass), indexed by fire and observation."""
    columns = ["fire_id", "observation", "new_cells", "spread_distance_p90_m", "head_bearing_deg", "frp_total_mw", "hours_since_first_observation"]
    return pd.read_csv(PROCESSED / "ontario_fire_spread_master_v1.csv", dtype={"fire_id": str}, usecols=columns).set_index(["fire_id", "observation"])


def _bearing_cos(a_deg: np.ndarray, b_deg: float) -> np.ndarray:
    return np.cos(np.radians(a_deg - b_deg))


def step_rows(step, static: dict[str, np.ndarray], daily: pd.DataFrame, history: pd.DataFrame, arrival: np.ndarray | None, detectable_share: float) -> tuple[pd.DataFrame, dict]:
    """Candidate-cell rows for one step and a summary of the step.  `arrival` is the simulator's 90 m arrival grid."""
    case, layout = step.case, step.layout
    weather = step_weather(case, step.start_utc, step.hours, daily)
    burned_grid, active_grid = layout.grid(step.start), layout.grid(step.active)
    burned_distance, burned_index = ndimage.distance_transform_edt(~burned_grid, return_indices=True)
    active_distance, active_index = ndimage.distance_transform_edt(~active_grid, return_indices=True)
    distance_to_burned = layout.flat(burned_distance) * CELL_375_M
    candidate = ~step.start & (distance_to_burned <= RADIUS_M)
    if arrival is not None:
        reached_share = _per_cell_mean(case, np.isfinite(arrival))
        sim_new = (reached_share >= detectable_share) & ~step.start  # exactly the simulator's scored prediction
        candidate_or_sim = candidate | sim_new
    else:
        sim_new = None
        candidate_or_sim = candidate
    cells = np.flatnonzero(candidate_or_sim)
    gx, gy = layout.x[cells], layout.y[cells]
    # offset from the nearest active-perimeter cell, in metres east and north of grid north
    east = (gx - active_index[0][gx, gy]) * CELL_375_M
    north = (gy - active_index[1][gx, gy]) * CELL_375_M
    distance_to_active = active_distance[gx, gy] * CELL_375_M
    true_bearing = (np.degrees(np.arctan2(east, north)) + case.convergence_deg) % 360
    downwind = _bearing_cos(true_bearing, weather["downwind_bearing_deg"])
    downwind = np.where(distance_to_active > 0, downwind, 0.0)
    sin_abs = np.sqrt(np.clip(1 - downwind**2, 0, 1))
    size = 2 * NEIGHBOURHOOD_CELLS + 1
    nearby = lambda grid: np.round(ndimage.uniform_filter(grid.astype(float), size=size, mode="constant") * size * size)  # noqa: E731
    burnable_grid = np.zeros(layout.shape)
    burnable_grid[layout.x, layout.y] = static["burnable"]
    previous = history.loc[(case.fire_id, step.observation)] if (case.fire_id, step.observation) in history.index else None
    previous_bearing = None if previous is None or pd.isna(previous.head_bearing_deg) else float(previous.head_bearing_deg)
    front_cell = np.ravel_multi_index((active_index[0][gx, gy], active_index[1][gx, gy]), layout.shape)
    flat_index = np.full(layout.shape, -1, dtype=int)
    flat_index[layout.x, layout.y] = np.arange(len(layout.x))
    front = flat_index.ravel()[front_cell]
    front_elevation = np.where(front >= 0, static["elevation_m"][np.maximum(front, 0)], np.nan)
    ros = fbp_head_ros(case, weather)
    frame = pd.DataFrame({
        "fire_id": case.fire_id, "observation": step.observation, "next_observation": step.next_observation, "cell": cells,
        "in_radius": candidate[cells], LABEL: step.observed_new[cells].astype(np.uint8),
        "distance_to_burned_m": distance_to_burned[cells], "distance_to_active_m": distance_to_active,
        "downwind_cos": downwind, "crosswind_abs_sin": sin_abs, "along_wind_m": distance_to_active * downwind, "across_wind_m": distance_to_active * sin_abs,
        "previous_head_cos": np.where(distance_to_active > 0, _bearing_cos(true_bearing, previous_bearing), 0.0) if previous_bearing is not None else np.nan,
        "active_cells_nearby": layout.flat(nearby(active_grid))[cells], "burned_cells_nearby": layout.flat(nearby(burned_grid))[cells],
        "burned_cells_total": int(step.start.sum()), "active_cells_total": int(step.active.sum()),
        "previous_new_cells": np.nan if previous is None else previous.new_cells,
        "previous_spread_p90_m": np.nan if previous is None else previous.spread_distance_p90_m,
        "previous_frp_total_mw": np.nan if previous is None else previous.frp_total_mw,
        "hours_since_first_observation": np.nan if previous is None else previous.hours_since_first_observation,
        **{name: weather[name] for name in WEATHER},
        **{name: static[name][cells] for name in FUEL if name in static},
        "burnable_share_nearby": layout.flat(ndimage.uniform_filter(burnable_grid, size=size, mode="constant"))[cells],
        "fbp_head_ros_m_per_min": ros[cells],
        "elevation_m": static["elevation_m"][cells],
        "rise_from_front_m": static["elevation_m"][cells] - front_elevation,
    })  # fmt: skip
    frame["slope_from_front"] = np.where(distance_to_active > 0, frame.rise_from_front_m / np.maximum(distance_to_active, 1.0), 0.0)
    if arrival is not None:
        limit = min(step.hours, 30.0) * 60.0
        earliest = np.full(len(case.cell375_keys), np.inf)
        np.minimum.at(earliest, case.cell375.ravel(), arrival.ravel())
        frame["sim_reached_share"] = reached_share[cells]
        frame["sim_arrival_fraction"] = np.where(np.isfinite(earliest[cells]), earliest[cells] / limit, np.nan)
        frame["sim_new"] = sim_new[cells].astype(np.uint8)
    summary = {
        "fire_id": case.fire_id, "observation": step.observation, "next_observation": step.next_observation, "hours": step.hours,
        "observed_new_cells": int(step.observed_new.sum()), "observed_new_in_radius": int((step.observed_new & candidate).sum()),
        "candidate_cells": int(candidate.sum()), "simulated_new_cells": None if sim_new is None else int(sim_new.sum()),
        "simulated_new_outside_radius": None if sim_new is None else int((sim_new & ~candidate).sum()),
    }  # fmt: skip
    return frame, summary
