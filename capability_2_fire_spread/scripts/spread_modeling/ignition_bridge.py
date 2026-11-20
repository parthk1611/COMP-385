"""Bridge from capability 1 (ignition) to capability 2 (spread): run the FBP simulator from a start point and time.

Capability 1 scores whether a 10 km cell has an ignition on a local day.  This
module takes a point in such a cell (by default its centre) and a start time on
that day, and grows a fire from it with the FBP simulator (`simulator.py`) for
a given number of hours.  Nothing here was fitted on 2019 or later: the two
simulator settings come from `tune_simulator_bridge.py` (tuned on 2012-2016
fires, tested on 2017-2018).

Inputs are fetched for a square window around the point and cached:

- fuel: FBP Fuel Types 2024 (CWFIS web coverage), 90 m on the source lattice,
  exactly as `download_spread_fuel_windows.py` requests it;
- terrain: MRDEM-30 DTM, warped to the same 90 m grid, as in
  `download_spread_terrain_windows.py`;
- weather: hourly ERA5 / ERA5-Land reanalysis at the point from Open-Meteo
  (`era5_seamless`), from 1 April (or 30 days before) so the fire-weather codes
  spin up, turned into daily codes by the same `daily_fire_weather` as the
  spread dataset.

Assumptions (all reported in the result):

- this is a retrospective hindcast: the weather during the run is the
  reanalysis of what happened, not a forecast available at the time;
- the ignition model gives a day, not a time or a point, so both are inputs;
- the 2024 fuel map shows regrowth or non-fuel where fires burned after the
  start date.  Inside the Ontario Fire Disturbance perimeters of fires that
  started on or after the start date (through 2024), land is given the fuel of
  the nearest burnable cell outside them, as the spread dataset does for its
  own fires.  Scars of fires before the start date are kept: they were real;
- if the start point's 90 m cell cannot burn, the nearest burnable cell within
  `MAX_SEED_SHIFT_M` is used instead.

Command line (prints JSON):

    python -m scripts.spread_modeling.ignition_bridge --longitude -91.2 --latitude 50.1 --date 2019-07-01 --hour 14 --hours 24
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy import ndimage

from scripts.spread_common import ARTIFACTS, MODELING_DOCS, PROJECT_ROOT, USER_AGENT

from .fbp import MAP_CODES
from .simulator import CELL_375_M, FireCase, Settings, _repair_burn_scar, grid_convergence, prepare_weather, simulate


# The dataset's build scripts import each other as top-level modules; reuse their exact weather code.
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import build_spread_weather as WEATHER  # noqa: E402


TUNING = MODELING_DOCS / "bridge_simulator_tuning.json"
CACHE = ARTIFACTS / "ignition_bridge"
FUEL_SERVICE = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wcs"
FUEL_COVERAGE = "public:cffdrs_fbp_fuel_types"
SOURCE_WEST, SOURCE_NORTH = -2_341_500.0, 2_851_423.977366649  # the fuel map's 30 m lattice
PIXEL_M = 90.0
TERRAIN_URL = "https://canelevation-dem.s3.ca-central-1.amazonaws.com/mrdem-30/mrdem-30-dtm.tif"
TERRAIN_NODATA = -32767.0
WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_MODEL = "era5_seamless"
WEATHER_VARIABLES = ["temperature_2m", "dew_point_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m", "wind_direction_10m"]
SEASON_START = (4, 1)
MIN_SPINUP_DAYS = 30
CENTRAL_TIME_WEST_OF_LONGITUDE = -90.0  # as the spread dataset: local standard time, CST west of 90 W
MAX_HOURS = 72
MAX_SEED_SHIFT_M = 1_000.0
MAX_FINE_CELLS = 80_000  # above this, only the 375 m cells are returned (keeps the response small)
RESERVED_YEAR = 2019  # the combined run's year: the FBP settings may neither be tuned nor tested on it
FUEL_MAP_YEAR = 2024


def window_half_width_m(hours: float) -> float:
    """Half the side of the square fetched around the start: room for about 0.6 km/h of head run, 10-35 km."""
    return float(min(max(10_000.0, 4_000.0 + 600.0 * hours), 35_000.0))


def tuned_settings() -> tuple[Settings, dict]:
    if not TUNING.exists():
        raise FileNotFoundError(f"{TUNING.name} is missing: run python -m scripts.spread_modeling.tune_simulator_bridge first")
    report = json.loads(TUNING.read_text(encoding="utf-8"))
    if max(report["tune_years"]) >= RESERVED_YEAR or any(first <= RESERVED_YEAR <= last for first, last in report["test_years"]):
        raise ValueError(f"the bridge settings must be tuned before {RESERVED_YEAR} and never tested on {RESERVED_YEAR}, the combined run's year")
    settings = Settings(ros_scale=float(report["chosen_ros_scale"]), flank_scale=float(report["chosen_flank_scale"]), repair_burn_scar=False)
    return settings, {"ros_scale": settings.ros_scale, "flank_scale": settings.flank_scale, "tune_years": report["tune_years"], "test_years": report["test_years"]}


def utc_offset_hours(longitude: float) -> int:
    return -6 if longitude < CENTRAL_TIME_WEST_OF_LONGITUDE else -5


def window_around(x: float, y: float, half_width_m: float) -> dict[str, float | int]:
    """A square around the point, snapped outward to 90 m steps of the fuel map's lattice."""
    west = SOURCE_WEST + math.floor((x - half_width_m - SOURCE_WEST) / PIXEL_M) * PIXEL_M
    north = SOURCE_NORTH - math.floor((SOURCE_NORTH - (y + half_width_m)) / PIXEL_M) * PIXEL_M
    columns = math.ceil((x + half_width_m - west) / PIXEL_M)
    rows = math.ceil((north - (y - half_width_m)) / PIXEL_M)
    return {"west": west, "north": north, "east": west + columns * PIXEL_M, "south": north - rows * PIXEL_M, "columns": columns, "rows": rows}


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _get(url: str, timeout: int, attempts: int = 6) -> bytes:
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as response:  # noqa: S310 - fixed public URLs
                return response.read()
        except HTTPError as error:
            if attempt == attempts - 1 or error.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(65 if error.code == 429 else 5 * (attempt + 1))
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise OSError(f"could not fetch {url}")


def fetch_fuel(window: dict) -> np.ndarray:
    import rasterio

    path = CACHE / "fuel" / f"{_key(window['west'], window['north'], window['columns'], window['rows'])}.tif"
    if not path.exists():
        url = f"{FUEL_SERVICE}?" + urlencode({
            "service": "WCS", "version": "1.0.0", "request": "GetCoverage", "coverage": FUEL_COVERAGE, "crs": "EPSG:3978",
            "bbox": f"{window['west']},{window['south']},{window['east']},{window['north']}", "width": window["columns"], "height": window["rows"],
            "interpolation": "nearest neighbor", "format": "GeoTIFF",
        })  # fmt: skip
        contents = _get(url, timeout=300)
        if contents[:2] not in (b"II", b"MM"):
            raise OSError(f"fuel service returned {contents[:120]!r} instead of a GeoTIFF")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    with rasterio.open(path) as source:
        fuel = source.read(1).astype(np.int32)
    if fuel.shape != (window["rows"], window["columns"]):
        raise ValueError(f"fuel window is {fuel.shape}, expected {(window['rows'], window['columns'])}")
    return fuel


def fetch_terrain(window: dict) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT

    path = CACHE / "terrain" / f"{_key(window['west'], window['north'], window['columns'], window['rows'])}.npy"
    if not path.exists():
        transform = from_origin(window["west"], window["north"], PIXEL_M, PIXEL_M)
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="3"):
            with rasterio.open(TERRAIN_URL) as source, WarpedVRT(source, crs="EPSG:3978", transform=transform, width=window["columns"], height=window["rows"], resampling=Resampling.bilinear, nodata=TERRAIN_NODATA) as warped:
                elevation = warped.read(1).astype(np.float32)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, elevation)
    elevation = np.load(path)
    elevation[elevation <= TERRAIN_NODATA + 1] = np.nan
    if np.isnan(elevation).all():
        return np.zeros_like(elevation)
    return np.where(np.isnan(elevation), np.nanmean(elevation), elevation).astype(np.float32)


def fetch_weather(longitude: float, latitude: float, start_local: pd.Timestamp, hours: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hourly weather at the point from the season start to past the run, and its daily fire-weather codes."""
    day = start_local.date()
    begin = min(date(day.year, *SEASON_START), day - timedelta(days=MIN_SPINUP_DAYS))
    end = (start_local + pd.Timedelta(hours=hours + 24)).date()
    lon, lat = round(longitude, 3), round(latitude, 3)
    path = CACHE / "weather" / f"{_key(lon, lat, begin, end, WEATHER_MODEL)}.json.gz"
    if not path.exists():
        url = f"{WEATHER_URL}?" + urlencode({
            "latitude": lat, "longitude": lon, "start_date": begin.isoformat(), "end_date": end.isoformat(),
            "hourly": ",".join(WEATHER_VARIABLES), "models": WEATHER_MODEL, "wind_speed_unit": "kmh", "timezone": "UTC",
        })  # fmt: skip
        payload = json.loads(_get(url, timeout=180))
        if "hourly" not in payload:
            raise OSError(f"weather service returned no hourly data: {str(payload)[:200]}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as target:
            json.dump(payload, target)
    with gzip.open(path, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    hourly = pd.DataFrame(payload["hourly"]).rename(columns=WEATHER.RENAME)
    hourly["time_utc"] = pd.to_datetime(hourly.pop("time"))
    hourly["time_local"] = hourly.time_utc + pd.Timedelta(hours=utc_offset_hours(longitude))
    hourly = hourly.dropna(subset=["temp_c", "rh_pct", "wind_speed_kmh", "wind_direction_deg"]).reset_index(drop=True)
    hourly["precip_mm"] = hourly.precip_mm.fillna(0.0)
    return hourly, WEATHER.daily_fire_weather(hourly)


def later_perimeters(local_date: str, window: dict):
    """Perimeters (EPSG:3978) of fires that started on or after `local_date` and up to the fuel map's year, inside the window.

    The 2024 fuel map shows these fires' burn scars, which did not exist yet on `local_date`.  Fires that burned
    before the date are left alone: their scars were real fuel conditions at the start.
    """
    import pickle

    import shapely
    from shapely.geometry import box, shape
    from shapely.ops import transform

    index = CACHE / "later_perimeters.pkl"
    if not index.exists():
        source = PROJECT_ROOT / "data/raw/fire_disturbance/fire_disturbance_area.geojson"
        if not source.exists():
            raise FileNotFoundError("Ontario fire perimeters are missing: from capability_2_fire_spread/, run python scripts/download_fire_disturbance.py --layer area")
        to_grid = Transformer.from_crs("EPSG:4326", "EPSG:3978", always_xy=True)
        features = json.loads(source.read_text(encoding="utf-8"))["features"]
        records = []
        for feature in features:
            p = feature["properties"]
            if not feature.get("geometry") or p.get("FIRE_START_DATE") is None or not (2010 <= int(p["FIRE_YEAR"]) <= FUEL_MAP_YEAR):
                continue
            start = pd.Timestamp(p["FIRE_START_DATE"], unit="ms").strftime("%Y-%m-%d")
            records.append((start, f"{p['FIRE_YEAR']}_{p['FIRE_DISTURBANCE_AREA_IDENT']}", shapely.to_wkb(shapely.make_valid(transform(to_grid.transform, shape(feature["geometry"]))))))
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_bytes(pickle.dumps(records))
    area = box(window["west"], window["south"], window["east"], window["north"])
    chosen = [(name, shapely.from_wkb(wkb)) for start, name, wkb in pickle.loads(index.read_bytes()) if start >= local_date]
    chosen = [(name, geometry) for name, geometry in chosen if geometry.intersects(area)]
    return [name for name, _ in chosen], (shapely.union_all([g for _, g in chosen]) if chosen else None)


def seed_cell(fuel: np.ndarray, row: int, column: int) -> tuple[tuple[int, int] | None, float]:
    """The start cell, or the nearest burnable cell within `MAX_SEED_SHIFT_M`; and how far it moved (m)."""
    burnable = np.isin(fuel, list(MAP_CODES))
    if burnable[row, column]:
        return (row, column), 0.0
    if not burnable.any():
        return None, math.inf
    distance, (rows, columns) = ndimage.distance_transform_edt(~burnable, return_indices=True)
    shift = float(distance[row, column]) * PIXEL_M
    if shift > MAX_SEED_SHIFT_M:
        return None, shift
    return (int(rows[row, column]), int(columns[row, column])), shift


def run(longitude: float, latitude: float, local_date: str, start_hour: float = 14.0, hours: float = 24.0, settings: Settings | None = None, repair_later_scars: bool = True) -> dict:
    """Grow a fire from a point for `hours` from `start_hour` local standard time on `local_date`.

    `settings` defaults to the bridge tuning (`tune_simulator_bridge.py`); pass one only for tests.
    """
    if not (0 < hours <= MAX_HOURS):
        raise ValueError(f"hours must be between 0 and {MAX_HOURS}")
    if not (0 <= start_hour < 24):
        raise ValueError("start_hour must be 0-23")
    if settings is None:
        settings, provenance = tuned_settings()
    else:
        provenance = {"ros_scale": settings.ros_scale, "flank_scale": settings.flank_scale, "tune_years": None, "test_years": None, "note": "supplied directly, not the bridge tuning"}
    offset = utc_offset_hours(longitude)
    start_local = pd.Timestamp(local_date) + pd.Timedelta(hours=start_hour)
    start_utc = start_local - pd.Timedelta(hours=offset)
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:3978", always_xy=True).transform(longitude, latitude)
    window = window_around(x, y, window_half_width_m(hours))

    mapped = fetch_fuel(window)
    fuel, repaired_from = mapped, []
    if repair_later_scars:
        import shapely

        repaired_from, scars = later_perimeters(local_date, window)
        if scars is not None:
            gx = window["west"] + (np.arange(window["columns"]) + 0.5) * PIXEL_M
            gy = window["north"] - (np.arange(window["rows"]) + 0.5) * PIXEL_M
            grid_x, grid_y = np.meshgrid(gx, gy)
            fuel = _repair_burn_scar(mapped, shapely.contains_xy(scars, grid_x, grid_y))
    elevation = fetch_terrain(window)
    hourly, daily = fetch_weather(longitude, latitude, start_local, hours)
    weather = prepare_weather(hourly, daily)
    if weather.time_utc.max() < start_utc + pd.Timedelta(hours=hours - 1):
        raise ValueError("the weather record does not cover the whole run")

    case = FireCase(
        fire_id="ignition_bridge", west=window["west"], north=window["north"], pixel=PIXEL_M, fuel=fuel, elevation=elevation,
        weather=weather, convergence_deg=grid_convergence(x, y), ignition_cell=None, arrival=pd.DataFrame(), observation_times=pd.Series(dtype="datetime64[ns]"),  # fmt: skip
        fuel_as_mapped=mapped,
    )  # fmt: skip
    row, column = int((window["north"] - y) // PIXEL_M), int((x - window["west"]) // PIXEL_M)
    seed, shift = seed_cell(fuel, row, column)
    first_hour = int(np.searchsorted(weather.time_utc.values, np.datetime64(start_utc.floor("h"))))
    at_start = weather.iloc[first_hour]
    run_hours = int(math.ceil(hours))
    hourly_weather = [
        {"hour": h, "wind_kmh": round(float(row.wind_speed_kmh), 1), "wind_from_deg": round(float(row.wind_direction_deg)),
         "temp_c": round(float(row.temp_c), 1), "rh_pct": round(float(row.rh_pct))}
        for h, row in enumerate(weather.iloc[first_hour:first_hour + run_hours].itertuples())
    ]  # fmt: skip
    day_codes = daily.set_index("date").loc[start_local.strftime("%Y-%m-%d")] if start_local.strftime("%Y-%m-%d") in set(daily.date) else None
    result = {
        "mode": "retrospective hindcast with reanalysis weather; not an operational forecast",
        "start": {"longitude": longitude, "latitude": latitude, "x_3978": round(x, 1), "y_3978": round(y, 1), "local_date": local_date,
                  "local_standard_time": start_local.strftime("%Y-%m-%d %H:%M"), "utc_offset_hours": offset, "start_utc": start_utc.strftime("%Y-%m-%d %H:%M"),
                  "hours": hours, "seed_shift_m": None if seed is None else round(shift, 1), "grid_convergence_deg": round(case.convergence_deg, 2)},
        "settings": provenance,
        "inputs": {"fuel": "FBP Fuel Types 2024, 90 m (CWFIS)" + (f"; burn scars of {len(repaired_from)} later fire(s) repaired from surrounding fuel" if repaired_from else "; no later burn scars in the window"),
                   "later_fires_repaired": repaired_from, "terrain": "MRDEM-30 DTM, 90 m",
                   "weather": f"ERA5 / ERA5-Land reanalysis via Open-Meteo ({WEATHER_MODEL}) at the start point; FWI codes from {daily.date.iloc[0]}",
                   "window_km": round(window["columns"] * PIXEL_M / 1000, 1)},
        "hourly_weather": hourly_weather,
        "weather_at_start": {"wind_kmh": round(float(at_start.wind_speed_kmh), 1), "wind_from_deg": round(float(at_start.wind_direction_deg)),
                             "temp_c": round(float(at_start.temp_c), 1), "rh_pct": round(float(at_start.rh_pct)),
                             "ffmc": None if day_codes is None else round(float(day_codes.ffmc), 1), "bui": None if day_codes is None else round(float(day_codes.bui), 1),
                             "isi": None if day_codes is None else round(float(day_codes.isi), 1), "fwi": None if day_codes is None else round(float(day_codes.fwi), 1)},
    }  # fmt: skip
    if seed is None:
        return {**result, "spread": False, "message": f"No burnable fuel within {MAX_SEED_SHIFT_M:.0f} m of the start point (water or non-fuel).",
                "reached_cells": [], "area_by_hour_ha": [0.0] * run_hours, "summary": {"cells_reached": 0, "area_ha": 0.0, "head_distance_km": 0.0, "maximum_arrival_minutes": None, "touches_window_edge": False}}  # fmt: skip

    burning = np.zeros(fuel.shape, dtype=bool)
    burning[seed] = True
    arrival = simulate(case, burning, start_utc, hours, settings)
    reached = np.isfinite(arrival)
    rows_hit, columns_hit = np.nonzero(reached)
    cx = window["west"] + (columns_hit + 0.5) * PIXEL_M
    cy = window["north"] - (rows_hit + 0.5) * PIXEL_M
    minutes = arrival[reached]
    # Aggregate to the spread dataset's 375 m satellite grid: the earliest arrival in each 375 m cell.
    cells = pd.DataFrame({"kx": np.floor(cx / CELL_375_M).astype(int), "ky": np.floor(cy / CELL_375_M).astype(int), "minutes": minutes})
    cells = cells.groupby(["kx", "ky"], as_index=False).minutes.min()
    seed_x, seed_y = window["west"] + (seed[1] + 0.5) * PIXEL_M, window["north"] - (seed[0] + 0.5) * PIXEL_M
    distance = np.hypot(cx - seed_x, cy - seed_y)
    head = int(np.argmax(distance))
    edge = bool(reached[0, :].any() or reached[-1, :].any() or reached[:, 0].any() or reached[:, -1].any())
    bearing = (math.degrees(math.atan2(cx[head] - seed_x, cy[head] - seed_y)) + case.convergence_deg) % 360 if distance[head] > 0 else None
    return {
        **result,
        "spread": True,
        "message": "The fire reached the edge of the fetched window, so the spread is cut off there." if edge else "",
        "reached_cells": [{"x": int(r.kx) * int(CELL_375_M), "y": int(r.ky) * int(CELL_375_M), "minutes": round(float(r.minutes), 1)} for r in cells.itertuples()],
        # The simulator's own 90 m cells for close-up drawing: south-west corner of cell (row, col) is
        # (west + col * pixel, north - (row + 1) * pixel) in EPSG:3978.
        "fine_cells": None if len(minutes) > MAX_FINE_CELLS else {
            "pixel_m": PIXEL_M, "west": window["west"], "north": window["north"],
            "rows": rows_hit.tolist(), "cols": columns_hit.tolist(), "minutes": np.round(minutes, 1).tolist()},
        "area_by_hour_ha": [round(float((minutes <= 60.0 * (h + 1)).sum()) * PIXEL_M**2 / 10_000, 1) for h in range(run_hours)],
        "summary": {"cells_reached": int(len(cells)), "area_ha": round(float(reached.sum()) * PIXEL_M**2 / 10_000, 1),
                    "head_distance_km": round(float(distance[head]) / 1000, 2), "head_bearing_deg": None if bearing is None else round(bearing),
                    "maximum_arrival_minutes": round(float(minutes.max()), 1), "touches_window_edge": edge},
    }  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--date", required=True, help="local date, YYYY-MM-DD")
    parser.add_argument("--hour", type=float, default=14.0, help="local standard time the fire starts (default 14)")
    parser.add_argument("--hours", type=float, default=24.0)
    args = parser.parse_args()
    try:
        result = run(args.longitude, args.latitude, args.date, args.hour, args.hours)
    except (ValueError, FileNotFoundError, OSError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
    print(json.dumps(result, allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
