"""Point weather for spread research from one archived NOAA GFS cycle."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import json
import re

import numpy as np
import pandas as pd
import rasterio
import requests


GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
CWFIS = "https://cwfis.cfs.nrcan.gc.ca/geoserver/ows"
SURFACE = {("TMP", "2 m above ground"), ("RH", "2 m above ground"),
           ("UGRD", "10 m above ground"), ("VGRD", "10 m above ground")}
UNITS = {"TMP": "[C]", "RH": "[%]", "UGRD": "[m/s]", "VGRD": "[m/s]", "APCP": "[kg/(m^2)]"}


def gfs_index(index, run, lead):
    rows = [line.split(":", 6) for line in index.splitlines() if line.strip()]
    stamp = f"d={run:%Y%m%d%H}"
    if not rows or any(len(row) < 6 or row[2] != stamp for row in rows):
        raise ValueError("GFS index is for a different cycle")
    found = {}
    for row, following in zip(rows, rows[1:]):
        element, level, timing = row[3:6]
        instant = (element, level) in SURFACE and timing == f"{lead} hour fcst"
        rain = element == "APCP" and level == "surface" and timing == f"0-{lead} hour acc fcst"
        if instant or rain:
            # At leads 1–6 the short-period subtotal starts at the cycle time.
            # The total is listed last in the GFS inventory.
            if element in found and (element != "APCP" or not 1 <= lead <= 6):
                raise ValueError(f"Ambiguous forecast field {element}")
            found[element] = (int(row[1]), int(following[1]) - 1)
    if set(found) != set(UNITS):
        raise ValueError("GFS index lacks required surface measurements or cycle-total precipitation")
    return found


def parse_grib(path, run, lead, lon, lat):
    selected = {}
    with rasterio.open(path) as dataset:
        xx = lon % 360 if dataset.bounds.left >= 0 else lon
        row, col = dataset.index(xx, lat)
        if not 0 <= row < dataset.height or not 0 <= col < dataset.width:
            raise ValueError("Location is outside the weather grid")
        value_window = rasterio.windows.Window(col, row, 1, 1)
        for band in dataset.indexes:
            meta = dataset.tags(band)
            element = meta["GRIB_ELEMENT"]
            if element == f"APCP{lead:02d}":
                element = "APCP"
            if element not in UNITS:
                continue
            descriptor = meta.get("GRIB_SHORT_NAME", "")
            expected_level = {"TMP": "2-HTGL", "RH": "2-HTGL", "UGRD": "10-HTGL",
                              "VGRD": "10-HTGL", "APCP": "0-SFC"}[element]
            if descriptor != expected_level:
                continue
            if element == "APCP" and int(meta["GRIB_FORECAST_SECONDS"]) != 0:
                continue
            ref = pd.Timestamp(int(meta["GRIB_REF_TIME"]), unit="s", tz="UTC")
            valid = pd.Timestamp(int(meta["GRIB_VALID_TIME"]), unit="s", tz="UTC")
            if ref != run or valid != run + pd.Timedelta(hours=lead) or meta["GRIB_UNIT"] != UNITS[element]:
                raise ValueError("GFS time or units differ from the requested field")
            if element in selected:
                raise ValueError(f"Duplicate decoded forecast field {element}")
            field = dataset.read(band, window=value_window, masked=True)
            if field.mask.any() or not np.isfinite(field).all():
                raise ValueError(f"Missing forecast field {element} at the incident")
            selected[element] = float(field[0, 0])
        grid_lon, grid_lat = dataset.xy(row, col)
        grid_lon = (grid_lon + 180) % 360 - 180
    if set(selected) != set(UNITS):
        raise ValueError(f"Required GRIB fields missing: {sorted(set(UNITS) - set(selected))}")
    return selected, [float(grid_lon), float(grid_lat)]


def archived_hour(folder, run, lead, issue, lon, lat):
    stem = f"gfs.t{run:%H}z.pgrb2.0p25.f{lead:03d}"
    url = f"{GFS}/gfs.{run:%Y%m%d}/{run:%H}/atmos/{stem}"
    path = folder / f"{run:%Y%m%dT%H}_{lead:03d}.grib2"
    receipt = path.with_suffix(".json")
    if receipt.exists():
        info = json.loads(receipt.read_text())
        if info["sha256"] != sha256(path.read_bytes()).hexdigest() or info["url"] != url:
            raise ValueError("Cached weather bytes do not match the receipt")
    else:
        index = requests.get(url + ".idx", timeout=(8, 25))
        index.raise_for_status()
        fields = gfs_index(index.text, run, lead)
        payload, dates = [], set()
        for start, end in sorted(fields.values()):
            response = requests.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=(8, 35))
            content_range = response.headers.get("Content-Range", "")
            if (response.status_code != 206 or not content_range.startswith(f"bytes {start}-{end}/")
                    or len(response.content) != end - start + 1 or not response.content.startswith(b"GRIB")
                    or not response.content.endswith(b"7777")):
                raise ValueError("NOAA range response did not match the requested GRIB message")
            payload.append(response.content)
            dates.add(pd.Timestamp(response.headers["Last-Modified"]))
        if len(dates) != 1:
            raise ValueError("NOAA forecast source changed during download")
        content = b"".join(payload)
        info = {"url": url, "object_last_modified_utc": dates.pop().isoformat(),
                "sha256": sha256(content).hexdigest(), "byte_ranges": fields}
        path.write_bytes(content)
        receipt.write_text(json.dumps(info, indent=2) + "\n")
    if not run <= pd.Timestamp(info["object_last_modified_utc"]) <= issue:
        raise ValueError("The NOAA archived forecast object did not precede the simulation clock")
    values, location = parse_grib(path, run, lead, lon, lat)
    return values, location, info


def acquire_forecast(folder, issue, lon, lat, hours):
    folder.mkdir(parents=True, exist_ok=True)
    run = issue.floor("6h") - pd.Timedelta(hours=6)
    times = pd.date_range(run + pd.Timedelta(hours=1), (issue + pd.Timedelta(hours=hours)).ceil("h"), freq="h")
    leads = ((times - run).total_seconds() / 3600).astype(int)
    with ThreadPoolExecutor(max_workers=5) as worker:
        decoded = list(worker.map(lambda lead: archived_hour(folder, run, lead, issue, lon, lat), leads))
    values, points, receipts = zip(*decoded)
    if any(point != points[0] for point in points) or not np.isfinite(points[0]).all():
        raise ValueError("GFS grid point changed during the run")
    data = pd.DataFrame(values, index=times)
    rain = data.APCP.diff()
    rain.iloc[0] = data.APCP.iloc[0]
    if (rain < -0.01).any() or not data.RH.between(0, 100).all() or not data.TMP.between(-80, 60).all():
        raise ValueError("GFS accumulation or surface observations failed physical checks")
    weather = pd.DataFrame({
        "time_utc": data.index, "temp_c": data.TMP.to_numpy(), "rh_pct": data.RH.to_numpy(),
        "wind_speed_kmh": np.hypot(data.UGRD, data.VGRD).to_numpy() * 3.6,
        "wind_direction_deg": (np.degrees(np.arctan2(-data.UGRD, -data.VGRD)).to_numpy() + 360) % 360,
        "precip_mm": rain.clip(lower=0).to_numpy(),
    })
    return weather, {"provider": "NOAA GFS 0.25°", "run_utc": run.isoformat(), "grid_point": points[0],
                     "latest_object_time_utc": max(info["object_last_modified_utc"] for info in receipts),
                     "objects": list(receipts)}


def acquire_moisture(folder, lon, lat, date):
    folder.mkdir(parents=True, exist_ok=True)
    values, sources = {}, {}
    for name in ("ffmc", "bui"):
        layer = f"public:{name}"
        params = {"service": "WMS", "version": "1.3.0", "request": "GetFeatureInfo",
                  "layers": layer, "query_layers": layer, "time": str(date), "styles": "", "crs": "EPSG:4326",
                  "bbox": f"{lat-.004},{lon-.004},{lat+.004},{lon+.004}", "width": 1, "height": 1,
                  "i": 0, "j": 0, "info_format": "application/json"}
        path = folder / f"{name}.json"
        if path.exists():
            stored = json.loads(path.read_text())
            if stored["params"] != params:
                raise ValueError("Cached moisture sample is for a different point or date")
        else:
            response = requests.get(CWFIS, params=params, timeout=(8, 25))
            response.raise_for_status()
            stored = {"params": params, "url": response.url, "data": response.json()}
            path.write_text(json.dumps(stored, indent=2) + "\n")
        features = stored["data"]["features"]
        if len(features) != 1:
            raise ValueError(f"No single {name.upper()} value for this date and location")
        values[name] = float(features[0]["properties"][name.upper()])
        sources[name] = stored["url"]
    if not 0 <= values["ffmc"] <= 101 or not 0 <= values["bui"] <= 500:
        raise ValueError("Fuel moisture is outside the supported range")
    return {**values, "date": str(date), "sources": sources,
            "availability_at_issue_verified": False,
            "kind": "archived CWFIS gridded daily analysis"}
