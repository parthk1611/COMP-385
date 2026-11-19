"""Acquire, map and qualify observation-based moisture-code candidates."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.warp import transform

from scripts.prepare_selected_weather import FWI
from scripts.workflow_sources import atomic_json, now_utc

CODES = ("ffmc", "dmc", "dc")
BASE = "https://cwfis.cfs.nrcan.gc.ca/downloads/"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquire(url, directory, records):
    path = directory / url.rsplit("/", 1)[1]
    existing = next((r for r in records if r["url"] == url), None)
    if existing:
        if not path.exists() or digest(path) != existing["sha256"]:
            raise ValueError("Pinned source changed: " + path.name)
        return path
    response = requests.get(url, timeout=(15, 90))
    response.raise_for_status()
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(response.content)
    temporary.replace(path)
    records.append({"url": url, "path": str(path), "sha256": digest(path),
                    "bytes": path.stat().st_size, "retrieved_at_utc": now_utc(),
                    "last_modified_http": response.headers.get("Last-Modified")})
    atomic_json(directory / "acquisition.json", records)
    return path


def sample_codes(paths, grid):
    result = grid.copy()
    metadata = {}
    signature = None
    for code in CODES:
        with rasterio.open(paths[code]) as ds:
            if ds.crs is None or ds.count != 1:
                raise ValueError("Expected one georeferenced code band")
            current = (str(ds.crs), ds.shape, tuple(ds.transform))
            if signature is not None and current != signature:
                raise ValueError("Moisture-code grids differ")
            signature = current
            xs, ys = transform("EPSG:4326", ds.crs,
                               grid.centroid_longitude.tolist(), grid.centroid_latitude.tolist())
            values = np.array([float(v[0]) if not np.ma.is_masked(v[0]) else np.nan
                               for v in ds.sample(zip(xs, ys), masked=True)])
            valid = np.isfinite(values) & (values >= 0)
            if code == "ffmc":
                valid &= values <= 101
            result[code] = np.where(valid, values, np.nan)
            metadata[code] = {"crs": str(ds.crs), "shape": list(ds.shape),
                              "resolution": list(ds.res), "nodata": ds.nodata,
                              "tags": ds.tags(), "band_tags": ds.tags(1),
                              "sha256": digest(paths[code])}
    result["codes_present"] = np.isfinite(result[list(CODES)]).all(axis=1)
    return result, metadata


def qualify(candidate, issue, previous_noon):
    """Every requirement is explicit; source presence alone never grants trust."""
    issue, previous_noon = pd.Timestamp(issue), pd.Timestamp(previous_noon)
    if issue.tzinfo is None or previous_noon.tzinfo is None:
        raise ValueError("Timezone-aware issue and previous noon required")
    if previous_noon >= issue:
        raise ValueError("Previous noon must precede forecast issue")
    reasons = []
    if candidate.get("state_kind") != "observation_based_analysis":
        reasons.append("not_observation_based_analysis")
    if candidate.get("time_convention") != "local_standard_noon":
        reasons.append("standard_noon_not_verified")
    for field in ("quality_verified", "startup_lineage_verified", "validation_passed"):
        if candidate.get(field) is not True:
            reasons.append(field + "_missing")
    for field, target in (("noon_time_utc", previous_noon), ("available_at_utc", issue)):
        stamp = pd.Timestamp(candidate[field]) if candidate.get(field) else None
        if stamp is None or stamp.tzinfo is None:
            reasons.append(field + "_unknown")
        elif (field == "noon_time_utc" and stamp != target) or (field == "available_at_utc" and stamp > target):
            reasons.append(field + "_incompatible")
    if candidate.get("date") != previous_noon.date().isoformat():
        reasons.append("state_date_incompatible")
    for field in ("source_sha256", "metadata_sha256", "validation_sha256"):
        value = candidate.get(field, "")
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            reasons.append(field + "_missing")
    values = [candidate.get(c) for c in CODES]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) or v < 0 for v in values):
        reasons.append("missing_or_invalid_codes")
    elif values[0] > 101:
        reasons.append("missing_or_invalid_codes")
    return reasons


def hr_seed(candidate, issue, previous_noon):
    reasons = qualify(candidate, issue, previous_noon)
    if reasons:
        raise ValueError("State rejected: " + ", ".join(reasons))
    return {**candidate, "trusted": True, "state_kind": "observed",
            "measurement_kind": "moisture_codes_derived_from_observed_weather",
            "provenance": "Verified observation-based analysis; metadata and validation hashes retained"}


def station_report(path, day):
    frame = pd.read_csv(path, dtype=str).fillna("").map(lambda v: v.strip())
    frame = frame.loc[frame.REPDATE.eq(day.replace("-", ""))].copy()
    if frame.empty:
        raise ValueError("Station file does not contain requested date")
    frame["station_id"] = frame.AGENCY + "|" + frame.AES + "|" + frame.WMO
    if frame.station_id.duplicated().any():
        raise ValueError("Duplicate station key")
    for field in ["TEMP", "RH", "WS", "PRECIP", "FFMC", "DMC", "DC", "CALCSTATUS"]:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    return frame


def station_diagnostic(reports, locations, bbox):
    locations = pd.read_csv(locations, dtype=str).fillna("").map(lambda v: v.strip())
    locations["station_id"] = locations.agency + "|" + locations.aes + "|" + locations.wmo
    if locations.station_id.duplicated().any():
        raise ValueError("Duplicate station-location key")
    locations["lon"] = pd.to_numeric(locations.lon, errors="coerce")
    locations["lat"] = pd.to_numeric(locations.lat, errors="coerce")
    west, south, east, north = bbox
    local = locations.loc[locations.prov.eq("ON") & locations.lon.between(west, east) & locations.lat.between(south, north)]
    rows = []
    for day, path in sorted(reports.items()):
        previous = (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if previous not in reports:
            continue
        a = station_report(reports[previous], previous)
        b = station_report(path, day)
        joined = b.merge(a, on="station_id", suffixes=("", "_previous"), validate="one_to_one")
        joined = joined.merge(local[["station_id", "lon", "lat", "tz_correct"]], on="station_id", validate="many_to_one")
        for r in joined.to_dict("records"):
            valid = (r["CALCSTATUS"] == r["CALCSTATUS_previous"] == 1
                     and all(np.isfinite(r[k]) for k in ["TEMP", "RH", "WS", "PRECIP", "FFMC_previous", "DMC_previous", "DC_previous", "FFMC", "DMC", "DC"])
                     and -90 <= r["TEMP"] <= 60 and 0 <= r["RH"] <= 100
                     and r["WS"] >= 0 and r["PRECIP"] >= 0
                     and 0 <= r["FFMC_previous"] <= 101 and 0 <= r["FFMC"] <= 101
                     and min(r[k] for k in ["DMC_previous", "DC_previous", "DMC", "DC"]) >= 0)
            if not valid:
                continue
            calculated = FWI.daily_codes(r["TEMP"], r["RH"], r["WS"], r["PRECIP"], pd.Timestamp(day).month,
                                         {c: r[c.upper() + "_previous"] for c in CODES})
            rows.append({"station_id": r["station_id"], "date": day, "longitude": r["lon"], "latitude": r["lat"],
                         "options": r["OPTS"], "options_previous": r["OPTS_previous"],
                         **{c + "_absolute_error": abs(calculated[c] - r[c.upper()]) for c in CODES}})
    frame = pd.DataFrame(rows)
    metrics = {c: {"mae": float(frame[c + "_absolute_error"].mean()),
                   "p95": float(frame[c + "_absolute_error"].quantile(.95))} for c in CODES} if rows else {}
    return frame, {"pairs": len(rows), "stations": int(frame.station_id.nunique()) if rows else 0,
                   "dates": sorted(frame.date.unique()) if rows else [], "metrics": metrics,
                   "bbox": bbox, "scope": "Northwestern Ontario regional station-code consistency diagnostic; not independent forecast validation or standard-noon acceptance",
                   "validation_passed": False}


def run(workspace, raw, output):
    output.mkdir(parents=True, exist_ok=False)
    raw.mkdir(parents=True, exist_ok=True)
    records = json.loads((raw / "acquisition.json").read_text()) if (raw / "acquisition.json").exists() else []
    paths = {c: acquire(BASE + "cffdrs/" + c + "_current.tif", raw, records) for c in CODES}
    for name in ["CWFIS_FWI_export_v3.xml", "WeatherStations_CWFIS_export.xml", "cwfis_allstn2026.csv"]:
        acquire(BASE + "fwi_obs/" + name, raw, records)
    for name in ["Fine_Fuel_Moisture_Code", "Duff_Moisture_Code", "Drought_Code"]:
        acquire(BASE + "cffdrs/README_" + name + "_Dataset.txt", raw, records)
    reports = {}
    # Fixed diagnostic dates are separate from forecast issue-time acceptance.
    for day in pd.date_range("2026-10-15", "2026-10-19").strftime("%Y-%m-%d"):
        reports[day] = acquire(BASE + "fwi_obs/current/cwfis_fwi_" + day.replace("-", "") + ".csv", raw, records)
    latest_day = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    latest_report = acquire(BASE + "fwi_obs/current/cwfis_fwi_" + latest_day.replace("-", "") + ".csv", raw, records)
    latest = station_report(latest_report, latest_day)
    stations, diagnostic = station_diagnostic(reports, raw / "cwfis_allstn2026.csv", [-91, 47, -87, 51])
    stations.to_csv(output / "station_update_checks.csv", index=False)
    grid_path = workspace / "reports/week_4_data_2026-10-16/current_boundary_centroid_grid.csv"
    grid = pd.read_csv(grid_path)
    mapped, metadata = sample_codes(paths, grid)
    reasons = ["raster_observation_date_not_embedded", "raster_observation_clock_not_verified",
               "per_cell_startup_and_quality_lineage_not_verified", "standard_noon_validation_not_accepted"]
    mapped["status"] = np.where(mapped.codes_present, "candidate_unqualified", "missing_codes")
    mapped.to_parquet(output / "grid_candidates.parquet", index=False)
    state_bundle = {"_metadata": {"version": "verified-moisture-state-v1", "grid_sha256": digest(grid_path),
                                   "accepted_cells": 0, "reasons": reasons}}
    atomic_json(output / "accepted_seed.json", state_bundle)
    atomic_json(output / "source_manifest.json", records)
    summary = {"schema_version": 1, "generated_at_utc": now_utc(), "grid_cells": len(mapped),
               "candidate_cells": int(mapped.codes_present.sum()), "accepted_cells": 0,
               "raster_observation_date": None, "station_report_date": latest_day,
               "status_counts": mapped.status.value_counts().to_dict(), "reasons": reasons,
               "mapping": "Nearest native raster pixel at the existing 10 km grid centroid; not an area average or a 90 m moisture observation",
               "raster_metadata": metadata, "station_update_diagnostic": diagnostic,
               "latest_station_status_counts": latest.CALCSTATUS.value_counts().to_dict(),
               "source_manifest": str(output / "source_manifest.json"), "source_manifest_sha256": digest(output / "source_manifest.json"),
               "source_records": records,
               "grid_sha256": digest(grid_path), "outputs": {name: digest(output / name) for name in ["grid_candidates.parquet", "station_update_checks.csv", "accepted_seed.json"]},
               "rows": [{"grid_id": r.grid_id, "longitude": r.centroid_longitude, "latitude": r.centroid_latitude,
                          "status": r.status, **{c: float(getattr(r, c)) if np.isfinite(getattr(r, c)) else None for c in CODES}}
                         for r in mapped.itertuples()]}
    atomic_json(output / "coverage.json", summary)
    pointer = workspace / "data/processed/moisture_state/latest.json"
    atomic_json(pointer, {"path": str((output / "coverage.json").resolve()), "sha256": digest(output / "coverage.json")})
    print(json.dumps({k: summary[k] for k in ["grid_cells", "candidate_cells", "accepted_cells", "station_update_diagnostic"]}, indent=2))


def coverage(workspace):
    root = Path(workspace).resolve()
    pointer = root / "data/processed/moisture_state/latest.json"
    if not pointer.exists():
        return {"status": "not_collected", "rows": [], "accepted_cells": 0}
    index = json.loads(pointer.read_text())
    path = Path(index["path"]).resolve()
    if not path.is_relative_to(root / "data/processed") or digest(path) != index["sha256"]:
        raise OSError("Moisture coverage path or hash is invalid")
    return json.loads(path.read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.workspace.resolve(), args.raw_dir.resolve(), args.output_dir.resolve())
