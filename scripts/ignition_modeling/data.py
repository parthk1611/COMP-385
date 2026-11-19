"""Disk-backed, row-preserving numerical cache with explicit weather correction."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_ignition_feature_panel import output_fields
from .contract import (
    CACHE_VERSION, COORDINATE_FEATURES, FEATURE_NAMES, FEATURE_SELECTION,
    FEATURE_SET_VERSION, HISTORY_CENSOR_FEATURE, HISTORY_FEATURE,
    INDICATOR_FEATURES, ROOT, SELECTION_PATH,
)
from .weather import WEATHER_NAMES, corrected_weather_days, index_archive, sha256

def load_cache(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if (manifest.get("cache_version") != CACHE_VERSION
            or manifest.get("features") != list(FEATURE_NAMES)):
        raise ValueError("Cache feature schema/version mismatch")
    n = manifest.get("rows")
    if type(n) is not int or n <= 0:
        raise ValueError("Cache row count must be a positive integer")
    sizes = {"X.f64": n * len(FEATURE_NAMES) * np.dtype("float64").itemsize,
             "y.u8": n * np.dtype("uint8").itemsize}
    if (directory / "grid.u16").exists():
        sizes["grid.u16"] = n * np.dtype("uint16").itemsize
    for name, expected in sizes.items():
        path = directory / name
        if not path.is_file() or path.stat().st_size != expected:
            raise ValueError(f"Cache file size mismatch: {name}; expected {expected} bytes")
    X = np.memmap(directory / "X.f64", dtype="float64", mode="r",
                  shape=(n, len(FEATURE_NAMES)))
    y = np.memmap(directory / "y.u8", dtype="uint8", mode="r", shape=(n,))
    return X, y, manifest

def year_slice(manifest, first, last=None):
    last = first if last is None else last
    positions = [v for d,v in manifest["date_slices"].items() if first<=int(d[:4])<=last]
    if not positions:
        raise ValueError("Requested years absent from cache")
    return slice(positions[0][0],positions[-1][1])

def dates_for(manifest, selection):
    return np.concatenate([np.repeat(np.datetime64(d,"D"),end-start) for d,(start,end) in manifest["date_slices"].items()
                           if start>=selection.start and end<=selection.stop])

def _write_report(manifest, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    compact = {key: value for key, value in manifest.items() if key != "date_slices"}
    path.write_text(json.dumps(compact, indent=2) + "\n")


def prepare_cache(input_path, directory, chunk_size=50000, *, audit_path=None,
                  report_path=None, grid_path=None, archive_path=None):
    """Write all canonical predictors, replacing only audited weather columns."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    input_path, directory = Path(input_path), Path(directory)
    audit_path = Path(audit_path) if audit_path is not None else directory / "panel_validation/data_quality_report.json"
    report_path = Path(report_path) if report_path is not None else directory / "corrected_weather_audit.json"
    if report_path.resolve() == audit_path.resolve():
        raise ValueError("Corrected-weather report must not overwrite the input audit")
    audit = json.loads(audit_path.read_text())
    if audit.get("status") != "PASS" or audit.get("full_scan_completed") is not True:
        raise ValueError("Full current-panel integrity gate has not passed")
    schema = audit.get("schema", {})
    if (schema.get("feature_set_version") != FEATURE_SET_VERSION
            or schema.get("predictor_count") != len(FEATURE_NAMES)
            or schema.get("predictors") != list(FEATURE_NAMES)
            or schema.get("columns") != output_fields()
            or schema.get("target") != "ignition"
            or schema.get("excluded_labels") != FEATURE_SELECTION["other_labels"]
            or schema.get("metadata_excluded_from_predictors") != FEATURE_SELECTION["metadata"]):
        raise ValueError("Audit feature schema/version/order mismatch")
    if (sha256(input_path) != audit.get("source", {}).get("sha256")
            or input_path.stat().st_size != audit["source"].get("bytes")):
        raise ValueError("Input differs from the audited panel")
    if list(pd.read_csv(input_path, nrows=0).columns) != schema["columns"]:
        raise ValueError("Input column order differs from the canonical audited schema")
    grid_source = Path(grid_path or ROOT / "data/interim/ontario_fire_region_10km_grid.csv")
    grid = pd.read_csv(grid_source, dtype={"grid_id": str}, float_precision="round_trip")
    if (grid.grid_id.isna().any() or grid.grid_id.duplicated().any()
            or not 0 < len(grid) <= np.iinfo(np.uint16).max + 1):
        raise ValueError("Reference grid keys must be unique, non-null and fit uint16")
    if grid_path is None and len(grid) != 9673:
        raise ValueError("Production reference grid must contain 9673 cells")
    inputs = audit.get("inputs", {})
    grid_digest = sha256(grid_source)
    if (inputs.get("reference_grid", {}).get("sha256") != grid_digest
            or inputs.get("feature_selection", {}).get("sha256") != sha256(SELECTION_PATH)):
        raise ValueError("Audit reference-grid/feature-selection provenance mismatch")
    dates = [day.strftime("%Y-%m-%d") for year in range(2010, 2020)
             for day in pd.date_range(f"{year}-05-01", f"{year}-10-31")]
    n = len(grid) * len(dates)
    totals = audit.get("totals", {})
    if (totals.get("rows") != n or totals.get("expected_rows") != n
            or totals.get("grid_cells") != len(grid) or totals.get("fire_season_dates") != len(dates)):
        raise ValueError("Audited full-panel universe mismatch")
    audit_digest = sha256(audit_path)
    if (directory / "manifest.json").exists():
        manifest = load_cache(directory)[2]
        if (manifest.get("original_panel_sha256") != audit["source"]["sha256"]
                or manifest.get("reference_grid_sha256") != grid_digest):
            raise ValueError("Existing cache belongs to another input panel/grid")
        _write_report(manifest, report_path)
        return manifest
    centers = {}
    for name, dimension in zip(COORDINATE_FEATURES, ("grid_x_m", "grid_y_m")):
        lower_edge = pd.to_numeric(grid[dimension], errors="raise").to_numpy(dtype=np.float64)
        if not np.isfinite(lower_edge).all():
            raise ValueError(f"Reference grid {dimension} must be finite and non-null")
        centers[name] = lower_edge + 5000
    directory.mkdir(parents=True, exist_ok=True)
    X = np.memmap(directory / "X.f64", dtype="float64", mode="w+", shape=(n, len(FEATURE_NAMES)))
    y = np.memmap(directory / "y.u8", dtype="uint8", mode="w+", shape=(n,))
    ids = np.memmap(directory / "grid.u16", dtype="uint16", mode="w+", shape=(n,))
    grid_lookup = {key: i for i, key in enumerate(grid.grid_id)}
    required = [i for i, name in enumerate(FEATURE_NAMES)
                if name not in {*INDICATOR_FEATURES, HISTORY_FEATURE}]
    history_column = FEATURE_NAMES.index(HISTORY_FEATURE)
    censor_column = FEATURE_NAMES.index(HISTORY_CENSOR_FEATURE)
    slices, offset, previous, positives = {}, 0, None, 0
    cols = [*FEATURE_NAMES, "ignition", "ignition_date", "grid_id", "feature_set_version"]
    dtypes = {**dict.fromkeys(FEATURE_NAMES, "float64"), "ignition": "float64",
              "grid_id": str, "ignition_date": str, "feature_set_version": str}
    with pd.read_csv(input_path, usecols=cols, dtype=dtypes, chunksize=chunk_size,
                     float_precision="round_trip") as chunks:
        for chunk in chunks:
            end = offset + len(chunk)
            if end > n or not chunk.ignition_date.is_monotonic_increasing:
                raise ValueError("Cache requires audited chronological date order")
            if not chunk.feature_set_version.eq(FEATURE_SET_VERSION).all():
                raise ValueError("Input feature-set version mismatch")
            values = chunk[list(FEATURE_NAMES)].to_numpy()
            if np.isinf(values).any() or np.isnan(values[:, required]).any():
                raise ValueError("Input has infinite or undocumented missing predictor values")
            history, censor = values[:, history_column], values[:, censor_column]
            if (not np.isin(censor, (0, 1)).all()
                    or not np.array_equal(censor, np.isnan(history))
                    or np.any(history <= 0)):
                raise ValueError("Input native history missingness/censor invariant failed")
            labels = chunk.ignition.to_numpy()
            if not np.isin(labels, (0, 1)).all():
                raise ValueError("Input ignition labels must be binary and non-null")
            mapped = chunk.grid_id.map(grid_lookup)
            if mapped.isna().any():
                raise ValueError("Unknown grid ID")
            day_ids = mapped.to_numpy(dtype=np.uint16)
            for name in COORDINATE_FEATURES:
                if not np.array_equal(values[:, FEATURE_NAMES.index(name)], centers[name][day_ids]):
                    raise ValueError(f"Input grid-centroid coordinate mismatch: {name}")
            X[offset:end] = values
            y[offset:end] = labels
            ids[offset:end] = day_ids
            positives += int(labels.sum())
            for day, positions in chunk.groupby("ignition_date", sort=False).indices.items():
                start, stop = offset + int(positions[0]), offset + int(positions[-1]) + 1
                if previous and day < previous:
                    raise ValueError("Input dates go backwards")
                slices[day] = [slices.get(day, [start, stop])[0], stop]
                previous = day
            offset = end
            print(f"Numeric cache {offset:,}/{n:,}", flush=True)
    if (offset != n or list(slices) != dates
            or any(end - start != len(grid) for start, end in slices.values())):
        raise ValueError("Full-panel cache universe mismatch")
    if positives != totals.get("positive_cell_days"):
        raise ValueError("Input labels differ from audited positive count")
    db_path = directory / "cwfis.sqlite"
    source_audit = index_archive(
        archive_path or ROOT / "data/raw/cwfis/cwfis_fwi2010sv3.0_ll.csv.bz2",
        db_path, grid, chunk_size)
    changed = {name: 0 for name in WEATHER_NAMES}
    annual, corrected_count = {}, 0
    weather_columns = [FEATURE_NAMES.index(name) for name in WEATHER_NAMES]
    weather_required = [j for j, name in enumerate(WEATHER_NAMES) if name not in INDICATOR_FEATURES]
    for i, (day, weather) in enumerate(corrected_weather_days(db_path, grid, dates)):
        if i >= len(dates) or day != dates[i] or weather.shape != (len(grid), len(WEATHER_NAMES)):
            raise ValueError("Corrected-weather date/grid/column universe mismatch")
        start, end = slices[day]
        selection = slice(start, end)
        day_ids = ids[selection]
        if len(np.unique(day_ids)) != len(grid):
            raise ValueError("Duplicate grid cells within a cache date")
        values = weather[day_ids]
        if np.isinf(values).any() or np.isnan(values[:, weather_required]).any():
            raise ValueError("Corrected weather has infinite or undocumented missing values")
        for j, name in enumerate(WEATHER_NAMES):
            v = values[:, j]
            finite = v[np.isfinite(v)]
            maximum = 101 if name == "cwfis_ffmc" else 100
            if name in {"cwfis_rh_pct", "cwfis_ffmc"} and (np.any(finite < 0) or np.any(finite > maximum)):
                raise ValueError(f"Corrected source range invalid: {name}")
            if name not in {"cwfis_temp_c", "cwfis_rh_pct", "cwfis_ffmc"} and np.any(finite < 0):
                raise ValueError(f"Corrected source nonnegative range invalid: {name}")
            if name.endswith("fraction") and np.any(finite > 1):
                raise ValueError(f"Corrected fraction exceeds one: {name}")
        count = values[:, WEATHER_NAMES.index("cwfis_station_count")]
        missing = values[:, WEATHER_NAMES.index("cwfis_missing")]
        coverage = values[:, WEATHER_NAMES.index("cwfis_precip_7d_coverage_days")]
        rain = values[:, WEATHER_NAMES.index("cwfis_precip_7d_mm")]
        if (np.any(count > 4) or np.any(count != np.floor(count))
                or not np.array_equal(missing, count == 0)):
            raise ValueError("Corrected station/missing flag consistency failed")
        observation = values[:, WEATHER_NAMES.index("cwfis_observation_coverage_fraction")]
        if not np.allclose(observation, count / 4, rtol=0, atol=1e-6):
            raise ValueError("Corrected station coverage fraction consistency failed")
        if (np.any(coverage > 7) or np.any(coverage != np.floor(coverage))
                or not np.array_equal(np.isnan(rain), coverage < 7)):
            raise ValueError("Corrected seven-day rain coverage consistency failed")
        for j, name in enumerate(WEATHER_NAMES):
            if name in INDICATOR_FEATURES and name != "cwfis_precip_7d_mm":
                if not np.array_equal(np.isnan(values[:, j]), missing == 1):
                    raise ValueError(f"Corrected native weather missingness mismatch: {name}")
            k = weather_columns[j]
            old, new = X[selection, k], values[:, j]
            changed[name] += int((~np.isclose(old, new, rtol=0, atol=1e-6, equal_nan=True)).sum())
            X[selection, k] = new
        stats = annual.setdefault(day[:4], {"rows": 0, "positives": 0, "weather_missing": 0, "rain_7d_missing": 0})
        stats["rows"] += end - start
        stats["positives"] += int(y[selection].sum())
        stats["weather_missing"] += int((missing == 1).sum())
        stats["rain_7d_missing"] += int(np.isnan(rain).sum())
        corrected_count += 1
        if i % 100 == 0:
            print(f"Corrected weather {day} ({i + 1}/{len(dates)})", flush=True)
    if corrected_count != len(dates):
        raise ValueError("Corrected-weather dates are incomplete")
    X.flush()
    y.flush()
    ids.flush()
    manifest = {
        "cache_version": CACHE_VERSION, "feature_set_version": FEATURE_SET_VERSION,
        "features": list(FEATURE_NAMES), "rows": n,
        "original_panel_sha256": audit["source"]["sha256"],
        "panel_audit_path": str(audit_path.resolve()), "panel_audit_sha256": audit_digest,
        "reference_grid_sha256": grid_digest, "date_slices": slices,
        "weather_source_audit": source_audit, "changed_cell_values": changed, "annual": annual,
        "scope": "Retrospective hindcast on frozen v1 grid; edge-cell universe uses study-period events; historical availability unverified",
        "numeric_storage": "float64 C-order memory mapped; all original rows and labels retained",
        "learned_preprocessing": "none; learned model transformations fit later within each training fold",
        "corrected_value_checks": {
            "status": "PASS", "infinities": 0, "range_violations": 0,
            "station_missing_consistency_violations": 0, "rain_coverage_consistency_violations": 0,
            "history_censor_consistency_violations": 0, "coordinate_mismatches": 0,
            "grid_duplicates": 0, "rows_preserved": True, "labels_preserved": True,
        },
    }
    _write_report(manifest, report_path)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--cache",type=Path,default=ROOT/"data/interim/ignition_modeling_cache")
    parser.add_argument("--chunk-size",type=int,default=50000)
    parser.add_argument("--audit", type=Path, help="Panel validation audit input (default: CACHE/panel_validation/data_quality_report.json)")
    parser.add_argument("--report", type=Path, help="Corrected-weather audit output (default: CACHE/corrected_weather_audit.json)")
    parser.add_argument("--grid", type=Path)
    parser.add_argument("--archive", type=Path)
    args=parser.parse_args()
    prepare_cache(args.input, args.cache, args.chunk_size, audit_path=args.audit,
                  report_path=args.report, grid_path=args.grid, archive_path=args.archive)
