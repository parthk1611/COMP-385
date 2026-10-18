"""Decode selected CDS weather without altering the historical v1 benchmark."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[1]
FWI_PATH = ROOT / "team_repository/capability_2_fire_spread/scripts/fire_weather_index.py"
SPEC = importlib.util.spec_from_file_location("selected_weather_fwi", FWI_PATH)
FWI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FWI)


def deaccumulate_era5(times: pd.DatetimeIndex, accumulated_m: np.ndarray) -> np.ndarray:
    times = pd.DatetimeIndex(times)
    values = np.asarray(accumulated_m, dtype=float)
    if times.tz is None or not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError("ERA5 timestamps must be unique, ordered and timezone-aware")
    if len(times) != len(values):
        raise ValueError("Time and precipitation dimensions differ")
    times = times.tz_convert("UTC")
    result = np.full_like(values, np.nan)
    consecutive = (times[1:] - times[:-1]) == pd.Timedelta(hours=1)
    result[1:] = np.where(consecutive.reshape((-1,) + (1,) * (values.ndim - 1)), np.diff(values, axis=0), np.nan)
    result[times.hour == 1] = values[times.hour == 1]
    result = np.where(values >= 0, result, np.nan)
    result = np.where(result < -1e-6, np.nan, np.maximum(result, 0))
    return result * 1000


def humidity(temp_k: np.ndarray, dewpoint_k: np.ndarray) -> np.ndarray:
    temp, dewpoint = np.asarray(temp_k) - 273.15, np.asarray(dewpoint_k) - 273.15
    return np.clip(100 * np.exp(17.625 * dewpoint / (243.04 + dewpoint) - 17.625 * temp / (243.04 + temp)), 0, 100)


def wind(u_ms: np.ndarray, v_ms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    speed = np.hypot(u_ms, v_ms) * 3.6
    direction = np.degrees(np.arctan2(-np.asarray(u_ms), -np.asarray(v_ms))) % 360
    return speed, np.where(speed == 0, np.nan, direction)


def daily_weather(hourly: pd.DataFrame, standard_offset_hours: int, startup_date: str) -> pd.DataFrame:
    """Declared fixed-standard-noon research codes; missing updates invalidate state."""
    frame = hourly.copy().set_index("time_utc")
    if frame.index.tz is None or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Weather timestamps must be unique, ordered and timezone-aware")
    frame.index = frame.index.tz_convert("UTC")
    offset = pd.Timedelta(hours=standard_offset_hours)
    dates = pd.date_range((frame.index.min() + offset).normalize(), (frame.index.max() + offset).normalize(), freq="D")
    state = None
    previous_day = None
    rows = []
    for date in dates:
        noon = date + pd.Timedelta(hours=12) - offset
        if noon not in frame.index:
            continue
        window = frame.loc[(frame.index > noon - pd.Timedelta(hours=24)) & (frame.index <= noon), "precip_mm"]
        expected = pd.date_range(noon - pd.Timedelta(hours=23), noon, freq="h")
        valid_rain = window.index.equals(expected) and window.notna().all() and (window >= 0).all()
        weather = frame.loc[noon]
        valid = valid_rain and np.isfinite(weather[["temp_c", "rh_pct", "wind_kmh"]].to_numpy(dtype=float)).all()
        valid = valid and -90 <= weather.temp_c <= 60 and 0 <= weather.rh_pct <= 100 and weather.wind_kmh >= 0
        date_text = date.date().isoformat()
        if date_text == startup_date:
            state = dict(FWI.STARTUP)
        if previous_day is not None and date - previous_day != pd.Timedelta(days=1):
            state = None
        codes = {name: np.nan for name in ("ffmc", "dmc", "dc", "isi", "bui", "fwi")}
        if date_text >= startup_date:
            if valid and state is not None:
                codes = FWI.daily_codes(weather.temp_c, weather.rh_pct, weather.wind_kmh, float(window.sum()), date.month, state)
                state = codes
            else:
                state = None
        rows.append({"date": date_text, "noon_time_utc": noon, "temp_c": weather.temp_c,
                     "rh_pct": weather.rh_pct, "wind_kmh": weather.wind_kmh,
                     "wind_from_degrees": weather.get("wind_from_degrees", np.nan),
                     "rain_24h_mm": float(window.sum()) if valid_rain else np.nan,
                     "rain_coverage_hours": int(window.notna().sum()), "fwi_state_valid": np.isfinite(codes["fwi"]), **codes})
        previous_day = date
    return pd.DataFrame(rows)


def read_era5(paths: list[Path]) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray], object]:
    values = {name: [] for name in ("t2m", "d2m", "u10", "v10", "tp")}
    times = []
    grid = None
    for path in paths:
        for name in values:
            with rasterio.open(f'netcdf:"{path}":{name}') as dataset:
                tags = dataset.tags()
                if tags.get("latitude#units") != "degrees_north" or tags.get("longitude#units") != "degrees_east":
                    raise ValueError("Expected CF latitude/longitude coordinates")
                if not tags.get("valid_time#units", "").startswith("seconds since 1970-01-01"):
                    raise ValueError("Expected Unix-second weather timestamps")
                units = {"t2m": "K", "d2m": "K", "u10": "m s**-1", "v10": "m s**-1", "tp": "m"}
                if tags.get(f"{name}#units") != units[name]:
                    raise ValueError(f"Unexpected {name} units")
                if tags.get(f"{name}#GRIB_stepType") != ("accum" if name == "tp" else "instant"):
                    raise ValueError(f"Unexpected {name} time aggregation")
                if name in ("u10", "v10") and tags.get(f"{name}#GRIB_uvRelativeToGrid") != "0":
                    raise ValueError("Wind components must be earth-relative")
                current_grid = (dataset.height, dataset.width, dataset.transform)
                if grid is not None and current_grid != grid:
                    raise ValueError("Weather grids differ between variables/months")
                grid = current_grid
                current_times = pd.to_datetime([int(dataset.tags(i)["NETCDF_DIM_valid_time"]) for i in range(1, dataset.count + 1)], unit="s", utc=True)
                if name == "t2m":
                    times.append(current_times)
                elif not current_times.equals(times[-1]):
                    raise ValueError("Variable time axes differ")
                values[name].append(dataset.read(masked=True).filled(np.nan).astype(np.float32))
    if not times:
        raise ValueError("No weather files selected")
    combined = times[0].append(times[1:])
    if not combined.is_unique or not combined.is_monotonic_increasing:
        raise ValueError("Monthly weather time axes overlap or are out of order")
    return combined, {name: np.concatenate(parts) for name, parts in values.items()}, grid


def build(input_dir: Path, output_dir: Path, standard_offset_hours: int, startup_date: str) -> dict:
    paths = sorted(input_dir.glob("era5_land_2025_*.nc"))
    if not paths:
        paths = sorted(input_dir.glob("era5_land_ontario_2025_*.nc"))
    times, raw, grid = read_era5(paths)
    rain = deaccumulate_era5(times, raw["tp"])
    rh = humidity(raw["t2m"], raw["d2m"])
    speed, direction = wind(raw["u10"], raw["v10"])
    rows, columns, transform = grid
    tables = []
    for row in range(rows):
        for column in range(columns):
            hourly = pd.DataFrame({"time_utc": times, "temp_c": raw["t2m"][:, row, column] - 273.15,
                                   "rh_pct": rh[:, row, column], "wind_kmh": speed[:, row, column],
                                   "wind_from_degrees": direction[:, row, column],
                                   "precip_mm": rain[:, row, column]})
            daily = daily_weather(hourly, standard_offset_hours, startup_date)
            longitude, latitude = transform * (column + .5, row + .5)
            daily["weather_cell"] = f"era5_{row}_{column}"
            daily["longitude"], daily["latitude"] = longitude, latitude
            tables.append(daily)
    result = pd.concat(tables, ignore_index=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_dir / "era5_daily_weather.parquet", index=False)
    def digest(path):
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()

    summary = {"input_files": [{"path": str(p), "sha256": digest(p)} for p in paths],
               "code_sha256": digest(Path(__file__)), "fwi_code_sha256": digest(FWI_PATH),
               "output_sha256": digest(output_dir / "era5_daily_weather.parquet"),
               "hours": len(times), "weather_cells": rows * columns,
               "daily_rows": len(result), "fwi_valid_rows": int(result.fwi_state_valid.sum()),
               "hourly_precipitation_unknown_samples": int(np.isnan(rain).sum()),
               "fixed_standard_offset_hours": standard_offset_hours, "startup_date": startup_date,
               "startup_policy": "Declared research startup FFMC=85/DMC=6/DC=15; no snow-based startup or overwintering claim",
               "humidity_method": "Magnus approximation over water; RH capped to 0..100 percent",
               "wind": "ERA5 u/v earth-relative (GRIB_uvRelativeToGrid=0); km/h, meteorological from direction",
               "precipitation": "Hourly-ending mm; difference within daily forecast, reset at 01 UTC; unknown gaps remain null",
               "scope": "Derived only over the actual input grid; no province-wide or operational-readiness claim"}
    (output_dir / "weather_build_audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/raw/ignition_pilot/era5")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/selected_weather_v1")
    parser.add_argument("--standard-offset-hours", type=int, choices=(-5, -6), default=-5)
    parser.add_argument("--startup-date", default="2025-04-01")
    args = parser.parse_args()
    print(json.dumps(build(args.input_dir, args.output_dir, args.standard_offset_hours, args.startup_date), indent=2))


if __name__ == "__main__":
    main()
