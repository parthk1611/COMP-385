"""Run a forecast-weather, reported-point spread experiment with the existing simulator."""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
from rasterio.enums import Resampling
import requests

from scripts.complete_spread_replay import source_index, warped_window, simulator
from scripts.prepare_historical_weather_v2 import ROOT, digest
from scripts.spread_forecast_weather import acquire_forecast, acquire_moisture
from scripts.workflow_sources import atomic_json

PIXEL = 90
RADIUS = 225
SHAPE = 2 * RADIUS + 1
HOURS = 12
HORIZONS = (1, 3, 6)
CELL = simulator.CELL_375_M
PROJECT = Transformer.from_crs(4326, 3978, always_xy=True)
GEOGRAPHIC = Transformer.from_crs(3978, 4326, always_xy=True)
GEOD = Geod(ellps="GRS80")
RAW = ROOT / "data/raw/spread_forecast_v1"
OUTPUT = ROOT / "data/processed/spread_forecast_v1"
SOURCE = ROOT / "team_repository/capability_2_fire_spread/data/processed"
FIRE_TABLE = SOURCE / "ontario_fire_spread_fires_v1.csv"
DETECTIONS = SOURCE / "ontario_fire_spread_detections_v1.csv.gz"
CLOCK = "First linked satellite detection on the reported start date"
DISPLAY = "Archived forecast-weather research simulation"


@dataclass(frozen=True)
class Seed:
    id: str
    name: str
    lon: float
    lat: float
    issue: pd.Timestamp
    clock: str
    source_date: str

    def __post_init__(self):
        if not (np.isfinite([self.lon, self.lat]).all() and -96 <= self.lon <= -74 and 41 <= self.lat <= 57):
            raise ValueError("Seed is outside the Ontario study domain")
        if pd.isna(self.issue) or self.issue.tzinfo is None or self.issue.utcoffset() != pd.Timedelta(0):
            raise ValueError("Expected a qualified UTC simulation start")


def reported_seed(fire_id):
    path = RAW / f"ontario-{fire_id}.json"
    if not path.exists():
        snapshot = ROOT / "data/processed/overview_current/latest.json"
        source = json.loads(snapshot.read_text())
        records = [row for row in source["incidents"] if row["incident_id"] == fire_id]
        if len(records) != 1:
            raise ValueError("Reported ID is missing or ambiguous in the Ontario feed")
        record = records[0]
        record = {k: record[k] for k in ("incident_id", "name", "longitude", "latitude", "confirmed_at_utc")}
        atomic_json(path, {"incident": record, "collected_at_utc": source["collected_at_utc"],
                           "snapshot_sha256": digest(snapshot), "source_url": source["source"]["url"]})
    record = json.loads(path.read_text())["incident"]
    issue = pd.Timestamp(record["confirmed_at_utc"]).tz_convert("UTC")
    local_date = issue.tz_convert("America/Toronto").date()
    return Seed(f"{local_date.year}_{record['name']}", record["name"], record["longitude"], record["latitude"], issue,
                "Ontario report confirmation time", str(local_date)), path


def comparison_seeds():
    columns = ["fire_id", "fire_year", "start_date", "ignition_longitude", "ignition_latitude",
               "observations", "first_detection_utc", "utc_offset_hours"]
    rows = pd.read_csv(FIRE_TABLE, usecols=columns).query("fire_year == 2024 and observations >= 2")
    rows = rows.dropna(subset=["ignition_longitude", "ignition_latitude", "first_detection_utc"])
    times = pd.to_datetime(rows.first_detection_utc, utc=True)
    local = times + pd.to_timedelta(rows.utc_offset_hours, unit="h")
    chosen = rows.loc[local.dt.strftime("%Y-%m-%d").eq(rows.start_date)].sort_values("fire_id")
    return [Seed(row.fire_id, row.fire_id.replace("_", " "), row.ignition_longitude, row.ignition_latitude,
                 pd.Timestamp(row.first_detection_utc, tz="UTC"), CLOCK, row.start_date)
            for row in chosen.itertuples()]


def landscape(seed, fuel_index, terrain_index, weather):
    px, py = PROJECT.transform(seed.lon, seed.lat)
    west = np.floor(px / PIXEL) * PIXEL - RADIUS * PIXEL
    north = np.ceil(py / PIXEL) * PIXEL + RADIUS * PIXEL
    window = {"rows": SHAPE, "columns": SHAPE, "west": west, "north": north,
              "east": west + PIXEL * SHAPE, "south": north - PIXEL * SHAPE}
    fuel, fuel_files = warped_window(window, fuel_index, Resampling.nearest, -9999)
    elevation, terrain_files = warped_window(window, terrain_index, Resampling.bilinear, -32767)
    good = np.isfinite(elevation) & (elevation != -32767) & (elevation > -500)
    fuel[~good] = -9999
    coverage = float((good & (fuel != -9999)).mean())
    if coverage < .95:
        raise ValueError(f"Landscape coverage is only {coverage:.1%}")
    fuel = fuel.astype(np.int32)
    burnable = np.isin(fuel, list(simulator.MAP_CODES))
    original = (int((north - py) // PIXEL), int((px - west) // PIXEL))
    seed_row, seed_col = original
    if not burnable[seed_row, seed_col]:
        ys, xs = np.where(burnable[seed_row - 3:seed_row + 4, seed_col - 3:seed_col + 4])
        distance = (ys - 3) ** 2 + (xs - 3) ** 2
        if not len(distance) or distance.min() > 9:
            raise ValueError("Reported point and its three-cell neighbourhood have no burnable cell")
        closest = int(distance.argmin())
        seed_row, seed_col = seed_row + int(ys[closest]) - 3, seed_col + int(xs[closest]) - 3
    dx = (seed_col - original[1]) * PIXEL
    dy = (original[0] - seed_row) * PIXEL
    origin = west + (seed_col + .5) * PIXEL, north - (seed_row + .5) * PIXEL
    lon, lat = GEOGRAPHIC.transform(*origin)
    lon_n, lat_n = GEOGRAPHIC.transform(origin[0], origin[1] + 1000)
    convergence = float(GEOD.inv(lon, lat, lon_n, lat_n)[0])
    xs = np.floor((west + (np.arange(SHAPE) + .5) * PIXEL) / CELL).astype(int)
    ys = np.floor((north - (np.arange(SHAPE) + .5) * PIXEL) / CELL).astype(int)
    xx, yy = np.meshgrid(xs, ys)
    keys, index = np.unique(np.column_stack((xx.ravel(), yy.ravel())), axis=0, return_inverse=True)
    case = simulator.FireCase(seed.id, west, north, PIXEL, fuel, fuel, np.where(good, elevation, 0),
                              weather, convergence, (seed_row, seed_col), pd.DataFrame(), pd.Series(dtype=float),
                              index.reshape(fuel.shape), [tuple(row) for row in keys.tolist()])
    provenance = {"fuel": "FBP Fuel Types 2024", "terrain": "MRDEM30m DTM", "covered_share": coverage,
                  "seed_snap_m": float(np.hypot(dx, dy)),
                  "rasters": {str(Path(p).relative_to(ROOT)): digest(Path(p)) for p in [*fuel_files, *terrain_files]}}
    return case, origin, provenance


def weather_for_model(weather, moisture, local_standard_offset):
    data = weather.copy()
    data["day_of_year"] = (data.time_utc + pd.to_timedelta(local_standard_offset, unit="h")).dt.dayofyear
    data["bui"] = moisture["bui"]
    data["ffmc_daily"] = moisture["ffmc"]
    current = moisture["ffmc"]
    indices = []
    for row in data.itertuples():
        current = simulator.hourly_ffmc(row.temp_c, row.rh_pct, row.wind_speed_kmh, row.precip_mm, current)
        indices.append(current)
    data["ffmc"] = indices
    return data


def movement(xs, ys, origin, minimum_reach=CELL):
    if not len(xs):
        return {"reach_m": 0.0, "direction_deg": None}
    east = np.asarray(xs) - origin[0]
    north = np.asarray(ys) - origin[1]
    distance = np.hypot(east, north)
    reach = float(distance.max())
    if reach < minimum_reach:
        return {"reach_m": reach, "direction_deg": None}
    outer = distance >= .85 * reach
    lon, lat = GEOGRAPHIC.transform(xs[outer], ys[outer])
    seed_lon, seed_lat = GEOGRAPHIC.transform(*origin)
    angles = GEOD.inv(np.full(len(lon), seed_lon), np.full(len(lon), seed_lat), lon, lat)[0]
    heading = np.exp(1j * np.radians(angles)).mean()
    return {"reach_m": reach, "direction_deg": float(np.degrees(np.angle(heading)) % 360) if abs(heading) >= .5 else None}


def frame(arrivals, case, origin, hours):
    reached = arrivals <= hours * 60
    rows, cols = np.nonzero(reached)
    result = movement(case.west + (cols + .5) * PIXEL, case.north - (rows + .5) * PIXEL, origin, minimum_reach=3 * PIXEL)
    return {"hours": hours, "area_ha": len(rows) * PIXEL * PIXEL / 10000,
            "clipped": bool(reached[[0, -1], :].any() or reached[:, [0, -1]].any()), **result}


def satellite_target(detections, issue, minimum, maximum, ideal):
    future = detections[(detections.time_utc > issue) &
                        detections.time_utc.between(issue + pd.Timedelta(hours=minimum),
                                                    issue + pd.Timedelta(hours=maximum))]
    if future.empty:
        return None
    if ideal is None:
        stamp = future.time_utc.min()
    else:
        stamp = min(future.time_utc.unique(), key=lambda t: abs(t - issue - pd.Timedelta(hours=ideal)))
    xy = detections[["x", "y"]].to_numpy()
    keys = np.floor(xy / CELL).astype(int)
    before = set(map(tuple, keys[detections.time_utc.le(issue)]))
    new = set(map(tuple, keys[detections.time_utc.eq(stamp)])) - before
    return stamp, new, before


def overlap_score(predicted, observed, origin):
    common = len(predicted & observed)
    together = len(predicted | observed)
    pr = (np.asarray(sorted(predicted), dtype=float).reshape(-1, 2) + .5) * CELL
    obs = (np.asarray(sorted(observed), dtype=float).reshape(-1, 2) + .5) * CELL
    pm, om = (movement(points[:, 0], points[:, 1], origin) for points in (pr, obs))
    a, b = pm["direction_deg"], om["direction_deg"]
    error = (abs((a - b + 180) % 360 - 180) if a is not None and b is not None else None)
    return {"predicted_cells": len(predicted), "observed_cells": len(observed), "hits": common,
            "iou": common / together if observed and together else None,
            "recall": common / len(observed) if observed else None,
            "precision": common / len(predicted) if predicted and observed else None,
            "direction_error_deg": error, "predicted": pm, "observed": om}


def compare(case, origin, forecast_arrival, fixed_arrival, target, hours):
    stamp, new, before = target
    keys = np.asarray(case.cell375_keys)
    keep = ~(np.array([k in before for k in case.cell375_keys]))
    burnable = case.burned_375(np.isin(case.fuel, list(simulator.MAP_CODES)), .25)
    centres = (keys + .5) * CELL
    distance = np.hypot(centres[:, 0] - origin[0], centres[:, 1] - origin[1])
    eligible = np.flatnonzero(keep & burnable)
    ordered = eligible[np.argsort(distance[eligible], kind="stable")]

    def reached(arrivals):
        return set(map(tuple, keys[keep & case.burned_375(arrivals <= hours * 60, .25)]))

    model = reached(forecast_arrival)
    models = {"forecast_hourly_moisture": model, "fixed_moisture": reached(fixed_arrival),
              "even_growth": set(map(tuple, keys[ordered[:len(model)]]))}
    return {"target_utc": stamp.isoformat(), "simulation_hours": hours,
            "seen_cells": np.asarray(sorted(new), dtype=int).tolist(),
            "scores": {name: overlap_score(cells, new, origin) for name, cells in models.items()}}


def map_data(case, origin, arrivals, comparison):
    selected = np.array(np.nonzero(arrivals <= 6 * 60))
    ys, xs = selected.tolist()
    if comparison:
        for cx, cy in comparison["seen_cells"]:
            xs.append(int(((cx + .5) * CELL - case.west) / PIXEL))
            ys.append(int((case.north - (cy + .5) * CELL) / PIXEL))
    def span(values):
        return max(0, min(values) - 38), min(SHAPE, max(values) + 39)
    first_row, last_row = span(ys)
    first_col, last_col = span(xs)
    window = np.s_[first_row:last_row, first_col:last_col]
    # Use the existing spread dataset's fuel classes, with zero reserved for water.
    from export_spread_viewer_data import FUEL_CLASS
    tags = np.vectorize(lambda code: FUEL_CLASS.get(int(code), 1), otypes=[np.uint8])(case.fuel[window])
    ticks = np.minimum(np.ceil(arrivals[window] * 10), 65535).astype("<u2")
    return {"rows": tags.shape[0], "columns": tags.shape[1],
            "west": case.west + first_col * PIXEL, "north": case.north - first_row * PIXEL,
            "pixel": PIXEL, "origin": list(origin), "convergence_deg": case.convergence_deg,
            "fuel_u8": base64.b64encode(tags.tobytes()).decode("ascii"),
            "arrival_tenths_u16": base64.b64encode(ticks.tobytes()).decode("ascii")}


def run_case(seed, fuel_index, terrain_index, detections):
    raw_case = RAW / seed.id
    local_date = pd.Timestamp(seed.source_date).date()
    # Use standard noon/day convention for weather codes in the existing spread dataset.
    offset = -6 if seed.lon <= -90 else -5
    moisture = acquire_moisture(raw_case / "moisture", seed.lon, seed.lat, local_date - pd.Timedelta(days=1))
    weather, forecast = acquire_forecast(RAW / "noaa", seed.issue, seed.lon, seed.lat, HOURS)
    weather = weather_for_model(weather, moisture, offset)
    weather = weather.loc[weather.time_utc.ge(seed.issue.floor("h"))].reset_index(drop=True)
    case, origin, inputs = landscape(seed, fuel_index, terrain_index, weather)
    burning = np.zeros(case.shape, dtype=bool)
    burning[case.ignition_cell] = True
    settings = simulator.Settings(ros_scale=1.2, flank_scale=.25, hourly_moisture=True, integrate_hourly_travel=True)
    arrival = simulator.simulate(case, burning, seed.issue, HOURS, settings)
    comparisons = []
    primary = None
    if not detections.empty:
        fixed = simulator.simulate(case, burning, seed.issue, HOURS,
                                   simulator.Settings(ros_scale=1.2, flank_scale=.25, integrate_hourly_travel=True))
        target = satellite_target(detections, seed.issue, 6, 12, None)
        if target is not None:
            hours = (target[0] - seed.issue).total_seconds() / 3600
            primary = compare(case, origin, arrival, fixed, target, hours)
        for lead in HORIZONS:
            target = satellite_target(detections, seed.issue, lead - .5, lead + .5, lead)
            if target is not None:
                comparisons.append({"requested_hours": lead, **compare(case, origin, arrival, fixed, target, lead)})
    hour_rows = weather.assign(time_utc=weather.time_utc.map(lambda dt: dt.isoformat())).to_dict("records")
    return {"id": seed.id, "name": seed.name, "reported_location": [seed.lon, seed.lat],
            "start_utc": seed.issue.isoformat(), "start_clock": seed.clock, "forecast": forecast,
            "moisture": moisture, "landscape": inputs, "weather": hour_rows,
            "frames": [frame(arrival, case, origin, h) for h in HORIZONS],
            "map": map_data(case, origin, arrival, primary), "next_pass": primary, "horizon_checks": comparisons,
            "reporting_time_and_extent_known": False}


def run(reported):
    if not reported.isascii() or not reported.isdecimal():
        raise ValueError("Use the numeric reported incident ID")
    official, record = reported_seed(reported)
    seeds = [official, *comparison_seeds()]
    landscape_base = ROOT / "data/raw/ontario"
    fuel = source_index(landscape_base / "fbp/2024")
    terrain = source_index(landscape_base / "mrdem_30m")
    detections = pd.read_csv(DETECTIONS, usecols=["fire_id", "time_utc", "x", "y"])
    detections["time_utc"] = pd.to_datetime(detections.time_utc, utc=True)
    cases, skipped = [], []
    for seed in seeds:
        try:
            case = run_case(seed, fuel, terrain, detections.loc[detections.fire_id.eq(seed.id)])
        except (requests.RequestException, OSError, ValueError, KeyError) as error:
            skipped.append({"id": seed.id, "reason": str(error)})
            print(f"{seed.id}: {error}", flush=True)
            continue
        cases.append(case)
        print(seed.id, [round(f["area_ha"], 1) for f in case["frames"]],
              "comparison", bool(case["next_pass"]), flush=True)
    if not cases:
        raise ValueError("No real-input case could be simulated")
    protocol = ROOT / "reports/spread_forecast_pilot_2026-11-18/protocol.md"
    result = {"schema": 1, "study": DISPLAY, "operational": False,
              "reported_incident_id": reported, "cases": cases, "skipped": skipped,
              "protocol_sha256": digest(protocol),
              "source_sha256": {p.name: digest(p) for p in (record, FIRE_TABLE, DETECTIONS,
                                                          Path(__file__), Path(__file__).with_name("spread_forecast_weather.py"),
                                                          Path(simulator.__file__))}}
    atomic_json(OUTPUT / "latest.json", result)


def read_result(workspace):
    path = Path(workspace) / "data/processed/spread_forecast_v1/latest.json"
    result = json.loads(path.read_text())
    if result.get("schema") != 1 or result.get("operational") is not False or not result.get("cases"):
        raise ValueError("Expected archived spread research data")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reported", default="32655", help="Numeric ID from the saved Ontario reported-fire feed")
    run(parser.parse_args().reported)
