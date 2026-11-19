"""On-demand point-start spread scenarios with current hourly weather."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, time, timedelta
from functools import lru_cache
from time import monotonic
import base64
import json
import re

import numpy as np
import pandas as pd
import requests

from scripts import spread_forecast as spread
from scripts.seven_day_ignition import outlook as ignition_outlook, parse_query
from scripts.spread_forecast_weather import CWFIS
from fire_weather_index import bui, daily_codes

ZONE = "America/Toronto"
WEATHER = "https://api.open-meteo.com/v1/forecast"
FIELDS = {"temperature_2m": "°C", "relative_humidity_2m": "%", "wind_speed_10m": "km/h",
          "wind_direction_10m": "°", "rain": "mm", "showers": "mm", "snow_depth": "m"}
HOURS = 6
CACHE_MINUTES = 5
SELECTION_SECONDS = 45


def scenario_request(query, now):
    if "date" not in query or set(query) - {"date", "incident"} or any(len(values) != 1 for values in query.values()):
        raise ValueError("Choose one outlook date and, optionally, one reported location.")
    incident = query.get("incident", [None])[0]
    if incident is not None and not re.fullmatch(r"[0-9]{1,12}", incident):
        raise ValueError("Choose a reported location.")
    today, _, _, day = parse_query({"date": query["date"]}, now)
    if day == today:
        issue = now.floor(f"{CACHE_MINUTES}min")
    else:
        issue = pd.Timestamp(datetime.combine(day, time(12)), tz=ZONE).tz_convert("UTC")
    return incident, day, issue


def report_at(workspace, code, now):
    snapshot = json.loads((workspace / "data/processed/overview_current/latest.json").read_text())
    collected = pd.Timestamp(snapshot["collected_at_utc"])
    if not pd.Timedelta(0) <= now - collected <= pd.Timedelta(minutes=45):
        raise ValueError("The reported-fire feed is out of date. Try again after its next refresh.")
    for record in snapshot["incidents"]:
        if record["incident_id"] == code:
            return record
    raise ValueError("This location is no longer in the reported-fire feed.")


@lru_cache(maxsize=24)
def moisture_at(lon, lat, day):
    """Sample the three dated CWFIS fields before rolling them with forecast weather."""
    def request_field(name):
        layer = "public:" + name
        params = {"service": "WMS", "version": "1.3.0", "request": "GetFeatureInfo",
                  "layers": layer, "query_layers": layer, "time": day.isoformat(),
                  "styles": "", "crs": "EPSG:4326", "bbox": f"{lat-.004},{lon-.004},{lat+.004},{lon+.004}",
                  "width": 1, "height": 1, "i": 0, "j": 0, "info_format": "application/json"}
        response = requests.get(CWFIS, params=params, timeout=(5, 12))
        response.raise_for_status()
        features = response.json()["features"]
        if len(features) != 1:
            raise ValueError("No dated CWFIS fuel moisture for this location.")
        return name, float(features[0]["properties"][name.upper()])

    with ThreadPoolExecutor(max_workers=3) as executor:
        values = dict(executor.map(request_field, ("ffmc", "dmc", "dc")))
    if not 0 < values["ffmc"] <= 101 or not all(0 <= values[k] < 2000 for k in ("dmc", "dc")):
        raise ValueError("CWFIS fuel moisture is missing or outside its expected range.")
    return values


@lru_cache(maxsize=24)
def hourly_weather(lon, lat, clock_bucket):
    response = requests.get(WEATHER, params={"latitude": lat, "longitude": lon, "models": "gfs_seamless",
                            "timezone": "GMT", "past_days": 3, "forecast_days": 8,
                            "hourly": ",".join(FIELDS)}, timeout=(5, 15))
    response.raise_for_status()
    doc = response.json()
    if doc["utc_offset_seconds"] != 0 or any(doc["hourly_units"][field] != unit for field, unit in FIELDS.items()):
        raise ValueError("Weather source changed its units or timezone.")
    if abs(doc["latitude"] - lat) > .4 or abs(doc["longitude"] - lon) > .4:
        raise ValueError("Weather is too far from the starting point.")
    data = pd.DataFrame(doc["hourly"])
    data["time_utc"] = pd.to_datetime(data.pop("time"), utc=True)
    data = data.set_index("time_utc")
    if not data.index.is_unique or data.empty:
        raise ValueError("Weather hours are missing or duplicated.")
    data = data.rename(columns={"temperature_2m": "temp_c", "relative_humidity_2m": "rh_pct",
                                "wind_speed_10m": "wind_speed_kmh", "wind_direction_10m": "wind_direction_deg"})
    data["precip_mm"] = data.pop("rain") + data.pop("showers")
    return data, pd.Timestamp.now(tz="UTC").isoformat()


def roll_moisture(data, seed, noon, issue, offset):
    hours = pd.date_range(noon, (issue + pd.Timedelta(hours=HOURS)).ceil("h"), freq="h")
    weather = data.reindex(hours).rename_axis("time_utc").reset_index()
    if weather.iloc[:, 1:].isna().any().any() or not np.isfinite(weather.iloc[:, 1:]).all().all():
        raise ValueError("Complete hourly weather is unavailable for this date.")
    tests = {"temp_c": (-80, 60), "rh_pct": (0, 100), "wind_speed_kmh": (0, 250),
             "wind_direction_deg": (0, 360), "precip_mm": (0, 250), "snow_depth": (0, 20)}
    if not all(weather[f].between(*bounds).all() for f, bounds in tests.items()):
        raise ValueError("One or more forecast values are invalid.")
    local = weather.time_utc + pd.Timedelta(hours=offset)
    weather["day_of_year"] = local.dt.dayofyear
    moisture = seed.copy()
    ffmc = seed["ffmc"]
    ffmc_history, buildup = [ffmc], [bui(seed["dmc"], seed["dc"])]
    for i, row in enumerate(weather.itertuples(index=False), 0):
        if i == 0:
            continue
        ffmc = spread.simulator.hourly_ffmc(row.temp_c, row.rh_pct, row.wind_speed_kmh, row.precip_mm, ffmc)
        stamp = local.iloc[i]
        if stamp.hour == 12:
            rain = float(weather.precip_mm.iloc[i-23:i+1].sum())
            moisture = daily_codes(row.temp_c, row.rh_pct, row.wind_speed_kmh, rain, stamp.month, moisture)
        ffmc_history.append(ffmc)
        buildup.append(bui(moisture["dmc"], moisture["dc"]))
    weather["ffmc"], weather["bui"] = ffmc_history, buildup
    return weather.loc[weather.time_utc.ge(issue.floor("h"))].reset_index(drop=True)


@lru_cache(maxsize=2)
def landscape_indexes(workspace):
    base = workspace / "data/raw/ontario"
    return [spread.source_index(base / folder) for folder in ("fbp/2024", "mrdem_30m")]


@lru_cache(maxsize=12)
def landscape_at(workspace, lon, lat):
    seed = spread.Seed("point", "Start point", lon, lat, pd.Timestamp("2000-01-01", tz="UTC"), "", "")
    terrain, origin, provenance = spread.landscape(seed, *landscape_indexes(workspace), pd.DataFrame())
    return terrain, origin, provenance


def viewer_fire(record, day, issue, case, origin, provenance, arrivals, weather, received, seed_day):
    payload = spread.map_data(case, origin, arrivals, None)
    minute_tenths = np.frombuffer(base64.b64decode(payload["arrival_tenths_u16"]), dtype="<u2")
    indices = np.flatnonzero(minute_tenths <= HOURS * 600).astype("<u4")
    minutes = ((minute_tenths[indices].astype("uint32") + 9) // 10).astype("<u2")
    col = round((origin[0] - payload["west"]) / case.pixel - .5)
    row = round((payload["north"] - origin[1]) / case.pixel - .5)
    frames = [spread.frame(arrivals, case, origin, h) for h in spread.HORIZONS]
    return {
        "id": record["name"] or record["incident_id"], "day": day.isoformat(),
        "pixel": case.pixel, "rows": payload["rows"], "columns": payload["columns"], "west": payload["west"],
        "north": payload["north"], "convergence": case.convergence_deg, "fuel": payload["fuel_u8"],
        "cellX": "", "cellY": "", "firstDetected": "", "firstInArea": "", "steps": [],
        "ignition": {"cells": base64.b64encode(indices.tobytes()).decode(),
                     "minutes": base64.b64encode(minutes.tobytes()).decode(), "row": row, "column": col,
                     "view": {"rows": payload["rows"], "columns": payload["columns"], "r0": 0, "c0": 0},
                     "startLocal": issue.tz_convert(ZONE).strftime("%Y-%m-%d %H:%M"),
                     "startUtc": issue.isoformat(), "offsetHours": issue.minute / 60,
                     "wind": weather[["wind_speed_kmh", "wind_direction_deg"]].round(1).values.tolist(),
                     "ffmc": float(weather.ffmc.iloc[0]), "bui": float(weather.bui.iloc[0]),
                     "tempMax": float(weather.temp_c.max()), "rhMin": float(weather.rh_pct.min()),
                     "rainMm": float(weather.precip_mm.iloc[1:].sum()), "snowM": float(weather.snow_depth.max()),
                     "movedMetres": provenance["seed_snap_m"], "frames": frames},
        "coords": [record["latitude"], record["longitude"]], "confirmation": record.get("confirmed_at_utc"),
        "weatherReceived": received, "moistureDate": seed_day.isoformat(),
        "ignitionRisk": record.get("ignition_risk"),
    }


def forecast_at(lon, lat, issue, now):
    offset = -6 if lon <= -90 else -5
    seed_day = (now + pd.Timedelta(hours=offset)).date() - timedelta(days=1)
    noon = pd.Timestamp(datetime.combine(seed_day, time(12 - offset)), tz="UTC")
    seed = moisture_at(lon, lat, seed_day)
    weather, received = hourly_weather(lon, lat, now.floor(f"{CACHE_MINUTES}min"))
    return roll_moisture(weather, seed, noon, issue, offset), received, seed_day


def ranked_start(workspace, day, issue, now):
    _, cells = ignition_outlook(workspace, {"date": [day.isoformat()], "view": ["day"]}, now=now)
    deadline = monotonic() + SELECTION_SECONDS
    # The daily outlook already returns highest probability first, with grid ID breaking ties.
    for rank, cell in enumerate(cells.itertuples(index=False), start=1):
        if monotonic() >= deadline:
            raise ValueError("Could not verify a usable ignition cell in time. Try refreshing the forecast.")
        try:
            ground, origin, provenance = landscape_at(workspace, cell.longitude, cell.latitude)
            lon, lat = spread.GEOGRAPHIC.transform(*origin)
            weather, received, seed_day = forecast_at(lon, lat, issue, now)
        except ValueError:
            continue
        record = {
            "name": cell.grid_id, "longitude": lon, "latitude": lat,
            "ignition_risk": {"rank": rank, "probability": float(cell.probability), "method": cell.method},
        }
        return record, (ground, origin, provenance), (weather, received, seed_day)
    raise ValueError("No ranked ignition cell has enough fuel, terrain, and weather data for this date.")


def outlook(workspace, query, now=None):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now).tz_convert("UTC")
    code, day, issue = scenario_request(query, now)
    if code is None:
        record, (ground, origin, provenance), (weather, received, seed_day) = ranked_start(workspace, day, issue, now)
    else:
        record = report_at(workspace, code, now)
        lon, lat = record["longitude"], record["latitude"]
        ground, origin, provenance = landscape_at(workspace, lon, lat)
        weather, received, seed_day = forecast_at(lon, lat, issue, now)
    case = replace(ground, weather=weather)
    burned = np.zeros(case.shape, dtype=bool)
    burned[case.ignition_cell] = True
    settings = spread.simulator.Settings(ros_scale=1.2, flank_scale=.25, hourly_moisture=True, integrate_hourly_travel=True)
    arrivals = spread.simulator.simulate(case, burned, issue, HOURS, settings)
    return {"operational": False, "settings": {"forecastScenario": True, "cell375": 375, "ignitionHours": HOURS},
            "fires": [viewer_fire(record, day, issue, case, origin, provenance, arrivals, weather, received, seed_day)]}
