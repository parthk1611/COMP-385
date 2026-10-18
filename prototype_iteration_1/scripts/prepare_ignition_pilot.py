from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.enums import Resampling

from scripts.analyze_static_samples import block_mean, reproject_array, reproject_file
from scripts.fetch_static_samples import MODEL_CRS, PLACES, ROOT, sample_bounds, sha256, write_remote_window

PLACE = "thunder_bay"
BOUNDS = sample_bounds(*PLACES[PLACE])
RAW = ROOT / "data/raw/ignition_pilot"
PROCESSED = ROOT / "data/processed"
SERVICE = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open09/MapServer"
SCANFI = "https://ftp.maps.canada.ca/pub/nrcan_rncan/Forests_Foret/SCANFI/v1"
CONIFERS = ("balsamFir", "blackSpruce", "douglasFir", "jackPine", "lodgepolePine", "ponderosaPine", "tamarack", "whiteRedPine", "prcC_other")
SCANFI_FILES = {"closure": "SCANFI_att_closure_SW_2020_v1.2.tif"}
SCANFI_FILES.update({name: f"SCANFI_sps_{name}_SW_2020_v1.2.tif" for name in (*CONIFERS, "prcB")})


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def fetch_fire_layer(session: requests.Session, layer: int) -> dict:
    cached = RAW / f"fire_layer_{layer}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    url = f"{SERVICE}/{layer}"

    def get(endpoint: str, params: dict) -> dict:
        response = session.get(endpoint, params=params, timeout=120)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"Ontario layer {layer}: {data['error']}")
        return data

    metadata = get(url, {"f": "json"})
    save_json(RAW / f"fire_layer_{layer}_metadata.json", metadata)
    left, bottom, right, top = BOUNDS
    selection = {
        "where": "FIRE_YEAR = 2025",
        "geometry": json.dumps({"xmin": left, "ymin": bottom, "xmax": right, "ymax": top}),
        "geometryType": "esriGeometryEnvelope", "inSR": 3978,
        "spatialRel": "esriSpatialRelIntersects",
    }
    ids = get(f"{url}/query", {"f": "json", **selection, "returnIdsOnly": "true"})
    object_ids = sorted(ids.get("objectIds") or [])
    features = []
    for offset in range(0, len(object_ids), 500):
        batch = get(f"{url}/query", {
            "f": "json", "objectIds": ",".join(map(str, object_ids[offset:offset + 500])),
            "outFields": "*", "returnGeometry": "true", "outSR": 3978,
        })
        if batch.get("exceededTransferLimit"):
            raise RuntimeError("Ontario query was truncated")
        features.extend(batch.get("features", []))
    received = [f["attributes"][ids["objectIdFieldName"]] for f in features]
    if sorted(received) != object_ids:
        raise RuntimeError("Ontario object-ID inventory does not match downloaded records")
    result = {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "source": url, "selection": selection, "spatialReference": {"wkid": 3978}, "features": features}
    save_json(RAW / f"fire_layer_{layer}.json", result)
    return result


def cell_for_point(x: float, y: float, bounds: tuple = BOUNDS) -> tuple[str, float] | None:
    left, bottom, right, top = bounds
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("Fire point has non-finite coordinates")
    if not (left <= x < right and bottom < y <= top):
        return None
    column = math.floor((x - left) / 2500)
    row = math.floor((top - y) / 2500)
    dx, dy = (x - left) % 2500, (top - y) % 2500
    edge_distance = min(dx, 2500 - dx, dy, 2500 - dy)
    return f"{PLACE}_{row:02d}_{column:02d}", edge_distance


def fire_events(features: list[dict]) -> pd.DataFrame:
    rows, seen = [], set()
    for feature in features:
        a = feature["attributes"]
        fire_type = a.get("FIRE_TYPE_CODE")
        if fire_type == "PB":
            continue
        if fire_type not in {"IFR", "OFR"}:
            raise ValueError(f"Unrecognized fire type: {fire_type}")
        if a.get("FIRE_START_DATE") is None:
            raise ValueError("A wildfire has no start date; labels cannot be considered complete")
        date = pd.to_datetime(a["FIRE_START_DATE"], unit="ms", utc=True).date()
        if date.year != int(a["FIRE_YEAR"]):
            raise ValueError("Fire year and start date disagree")
        ident = a.get("FIRE_DISTURBANCE_AREA_IDENT")
        if not ident:
            raise ValueError("Missing annual fire identifier")
        key = (date.year, fire_type, ident)
        if key in seen:
            raise ValueError(f"Duplicate event key: {key}")
        seen.add(key)
        point = feature.get("geometry") or {}
        cell = cell_for_point(point["x"], point["y"])
        if cell is None:
            continue
        rows.append({"event_id": "-".join(map(str, key)), "ogf_id": a["OGF_ID"],
                     "date": date.isoformat(), "cell_id": cell[0],
                     "distance_to_cell_edge_m": cell[1],
                     "within_100m_of_edge": cell[1] < 100,
                     "fire_type": fire_type, "cause": a.get("FIRE_GENERAL_CAUSE_CODE"),
                     "final_size_ha": a.get("FIRE_FINAL_SIZE")})
    return pd.DataFrame(rows, columns=["event_id", "ogf_id", "date", "cell_id", "distance_to_cell_edge_m", "within_100m_of_edge", "fire_type", "cause", "final_size_ha"])


def make_cell_days(static: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    days = pd.DataFrame({"date": pd.date_range("2025-04-01", "2025-10-31").strftime("%Y-%m-%d")})
    frame = static.merge(days, how="cross")
    counts = events.groupby(["cell_id", "date"]).size().rename("recorded_fire_count").reset_index()
    frame = frame.merge(counts, how="left", on=["cell_id", "date"], validate="one_to_one")
    frame["recorded_fire_count"] = frame["recorded_fire_count"].fillna(0).astype("int16")
    frame["reported_fire_start"] = (frame["recorded_fire_count"] > 0).astype("int8")
    frame["window_start_utc"] = pd.to_datetime(frame["date"], utc=True) + pd.Timedelta(hours=5)
    frame["window_end_utc"] = frame["window_start_utc"] + pd.Timedelta(days=1)
    frame["month"] = pd.to_datetime(frame["date"]).dt.month
    frame["day_of_year"] = pd.to_datetime(frame["date"]).dt.dayofyear
    return frame.sort_values(["date", "cell_id"]).reset_index(drop=True)


def selected_static() -> tuple[pd.DataFrame, dict]:
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        for name, filename in SCANFI_FILES.items():
            target = RAW / f"scanfi_{name}.tif"
            if not target.exists():
                with rasterio.open(f"{SCANFI}/{filename}") as source:
                    write_remote_window(source, BOUNDS, target)
            print(f"SCANFI v1.2: {name}", flush=True)
    arrays = {}
    profile = None
    for name in SCANFI_FILES:
        with rasterio.open(RAW / f"scanfi_{name}.tif") as source:
            current = (source.shape, source.transform, source.crs)
            if profile is not None and current != profile:
                raise ValueError("SCANFI species and closure grids do not align")
            profile = current
            arrays[name] = source.read(1, masked=True).astype("float32").filled(np.nan)
    closure = arrays["closure"]
    conifer = sum(arrays[name] for name in CONIFERS)
    total = conifer + arrays["prcB"]
    valid = np.isfinite(closure) & np.isfinite(total) & ((total > 0) | (closure == 0))
    fraction = np.divide(conifer, total, out=np.zeros_like(total), where=total > 0)
    conifer_canopy = np.where(valid, closure * fraction, np.nan)
    canopy = np.where(valid, closure, np.nan)
    assert profile is not None

    def aggregate(array: np.ndarray) -> np.ndarray:
        return block_mean(reproject_array(array, profile[1], profile[2], BOUNDS, Resampling.average)).ravel()

    numerator, denominator = aggregate(conifer_canopy), aggregate(canopy)
    conifer_pct = np.divide(100 * numerator, denominator, out=np.full_like(numerator, np.nan), where=denominator > 0)
    original = pd.read_parquet(PROCESSED / "static_features_2500m.parquet")
    keep = ["cell_id", "place", "grid_row", "grid_column", "x_epsg3978", "y_epsg3978", "longitude", "latitude", "fbp_dominant_code", "fbp_dominant_name", "fuel_dominant_group", "fbp_valid_fraction", "elevation_m", "aspect_sin", "aspect_cos", "mrdem_valid_fraction"]
    keep += [c for c in original if c.startswith("fuel_") and c.endswith("_share")]
    static = original.loc[original["place"] == PLACE, keep].sort_values(["grid_row", "grid_column"]).reset_index(drop=True)
    if len(static) != 144 or static["cell_id"].duplicated().any():
        raise ValueError("Expected the existing complete 144-cell Thunder Bay grid")
    static["closure_2020_pct"] = block_mean(reproject_file(RAW / "scanfi_closure.tif", BOUNDS, Resampling.average)).ravel()
    static["percent_conifer"] = conifer_pct
    static["scanfi_species_valid_fraction"] = aggregate(valid.astype("float32"))
    with rasterio.open(ROOT / f"data/raw/samples/{PLACE}/mrdem_dtm.tif") as source:
        elevation = source.read(1, masked=True).astype("float32").filled(np.nan)
        dy, dx = np.gradient(elevation, abs(source.transform.e), abs(source.transform.a))
        slope = 100 * np.hypot(dx, dy)
        static["slope_pct"] = block_mean(reproject_array(slope, source.transform, source.crs, BOUNDS, Resampling.average)).ravel()
    static["scanfi_version"] = "v1.2_2020"
    static["fbp_version"] = "2024"
    finite_total = total[np.isfinite(total)]
    positive_total = finite_total[finite_total > 0]
    qc = {"native_species_sum_min": float(np.nanmin(total)), "native_species_sum_max": float(np.nanmax(total)), "native_zero_species_fraction": float(np.mean(finite_total == 0)), "native_positive_species_sum_not_100_fraction": float(np.mean(positive_total != 100)) if len(positive_total) else None, "cells_without_conifer_fraction": int(static["percent_conifer"].isna().sum())}
    return static, qc


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "manifest.json"
    if manifest_path.exists():
        for entry in json.loads(manifest_path.read_text())["files"]:
            if sha256(ROOT / entry["path"]) != entry["sha256"]:
                raise ValueError(f"Cached input checksum changed: {entry['path']}")
    with requests.Session() as session:
        points = fetch_fire_layer(session, 30)
        areas = fetch_fire_layer(session, 28)
        if not (RAW / "scanfi_v1_readme.txt").exists():
            response = session.get(f"{SCANFI}/_readme.txt", timeout=60)
            response.raise_for_status()
            (RAW / "scanfi_v1_readme.txt").write_text(response.text)
    events = fire_events(points["features"])
    static, qc = selected_static()
    frame = make_cell_days(static, events)
    events.to_csv(PROCESSED / "thunder_bay_2025_fire_events.csv", index=False)
    static.to_parquet(PROCESSED / "thunder_bay_static_selected.parquet", index=False)
    frame.to_parquet(PROCESSED / "thunder_bay_2025_cell_days.parquet", index=False)
    frame.to_csv(PROCESSED / "thunder_bay_2025_cell_days.csv", index=False)
    used = sorted(RAW.glob("*")) + [ROOT / f"data/raw/samples/{PLACE}/{name}.tif" for name in ("fbp_2024", "mrdem_dtm")] + [PROCESSED / "static_features_2500m.parquet"]
    manifest = {"assembled_at_utc": datetime.now(timezone.utc).isoformat(), "model_crs": MODEL_CRS, "bounds": BOUNDS,
                "point_source": f"{SERVICE}/30", "area_source": f"{SERVICE}/28", "scanfi_sources": {name: f"{SCANFI}/{filename}" for name, filename in SCANFI_FILES.items()},
                "files": [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in used if p.is_file() and p.name != "manifest.json"]}
    if not manifest_path.exists():
        save_json(manifest_path, manifest)
    outside = sum(cell_for_point(f["geometry"]["x"], f["geometry"]["y"]) is None for f in points["features"] if f["attributes"]["FIRE_TYPE_CODE"] in {"IFR", "OFR"})
    summary = {"cells": len(static), "days": frame["date"].nunique(), "cell_days": len(frame), "point_records": len(points["features"]), "outside_grid_wildfire_records": outside, "intersecting_area_records": len(areas["features"]), "eligible_events": len(events), "positive_cell_days": int(frame["reported_fire_start"].sum()), "events_within_100m_of_cell_edge": int(events["within_100m_of_edge"].sum()), "scanfi_qc": qc,
               "available_predictor_columns": ["fbp_dominant_code", "closure_2020_pct", "percent_conifer", "elevation_m", "slope_pct", "aspect_sin", "aspect_cos", "month", "day_of_year"] + [c for c in static if c.startswith("fuel_") and c.endswith("_share")],
               "categorical_predictor_columns": ["fbp_dominant_code"], "target_column": "reported_fire_start", "label_metadata_columns": ["recorded_fire_count", "date", "window_start_utc", "window_end_utc"],
               "training_ready": False, "weather_downloaded": False, "fwi_computed": False,
               "limitations": ["Start dates are known/estimated dates without ignition times; reported_fire_start is a calendar-day label, not exact rolling 24-hour truth.", "Zero means no event recorded in this snapshot; archive coverage and point/area completeness remain unverified.", "No per-point LOCATION_ACCURACY field; 100 m edge flags are sensitivity checks, not measured location errors.", "Current MRDEM historical availability and source revision history are not verified.", "This small pilot cannot support reliable model-performance assessment."]}
    save_json(PROCESSED / "ignition_pilot_summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
