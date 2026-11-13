"""Past-only detected-CG densities, isolated from the corrected weather cache.

Densities are native-grid approximations, not counts of located flashes in a
10 km target. Only the seven development years are opened or constructed.
"""
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import h5py
import numpy as np
from scipy.sparse import csr_matrix, load_npz

from scripts.ignition_modeling.contract import ROOT
from scripts.ignition_modeling.weather import sha256

FEATURE_VERSION = "ignition-weather-v2-cell-centres-lightning-cg-v1"
LIGHTNING_NAMES = ("lightning_cg_density_24h", "lightning_cg_density_7d")
_YEARS = range(2010, 2017)
_EPOCH = datetime(1998, 1, 1, tzinfo=timezone.utc)
_ZONE = ZoneInfo("America/Toronto")
_GRID = ROOT / "data/interim/ontario_fire_region_10km_grid.csv"
_GRID_SHA = "b22741d83b64c2b78c19fbf182848566644a23fad4aeef3301ff25ef7c6c3f35"
_AREA_SHA = "c2d2d4ab7f8a875b132deed11739a3aedad178f39ecdc6334af68a65a910bd4c"
_CG_UNITS = "frequency_of_cg_lightning_flashes_per_grid_cell_per_3hours"


def _text(value):
    return value.decode() if isinstance(value, bytes) else str(value)



def _file(path, expected=None):
    path = Path(path).resolve()
    digest = sha256(path)
    if expected is not None and digest != expected:
        raise ValueError(f"Source fingerprint mismatch: {path}")
    stat = path.stat()
    return {"path": str(path), "sha256": digest, "bytes": stat.st_size}


def _coordinates(source, latitude, longitude):
    for name, expected, units in (("lat", latitude, "degrees_north"),
                                  ("lon", longitude, "degrees_east")):
        if (not np.array_equal(source[name][:], expected)
                or _text(source[name].attrs.get("units", "")) != units):
            raise ValueError(f"Native {name} coordinates/units disagree")


def _bounds(source, year):
    bounds = source["time_bnds"][:]
    stamps = source["time"][:]
    start = int((datetime(year, 1, 1, tzinfo=timezone.utc) - _EPOCH).total_seconds())
    stop = int((datetime(year + 1, 1, 1, tzinfo=timezone.utc) - _EPOCH).total_seconds())
    expected = np.arange(start, stop, 10800, dtype=np.int64)
    if (_text(source["time"].attrs.get("units", "")) != "seconds since 1998-1-1 0:0:0"
            or _text(source["time"].attrs.get("calendar", "")) != "standard"
            or bounds.shape != (len(expected), 2)
            or not np.array_equal(stamps, expected)
            or not np.array_equal(bounds[:, 0], expected)
            or not np.array_equal(bounds[:, 1], expected + 10800)):
        raise ValueError(f"Unexpected source interval bounds in {year}")
    return bounds


def source_inputs(audit: Path, area_path: Path):
    """Validate generated source prerequisites and the actual source vintage."""
    audit, area_path = Path(audit), Path(area_path)
    config = json.loads((audit / "configuration.json").read_text())
    if config["grid_sha256"] != _GRID_SHA:
        raise ValueError("Unexpected audited target grid")
    files = {name: _file(audit / name) for name in (
        "configuration.json", "download_manifest.json",
        "spatial_mapping.npz", "spatial_area_weights.npz")}
    files["target_grid"] = _file(_GRID, _GRID_SHA)
    provenance_path = Path(str(area_path) + ".json")
    provenance = json.loads(provenance_path.read_text())
    if (provenance["sha256"] != _AREA_SHA
            or provenance["filename"] != "cell_area_0.1-deg.nc"
            or provenance["url"] != "https://crd-data-donnees-rdc.ec.gc.ca/CDAS/products/CanCPLD/CLDN/fixed/cell_area_0.1-deg.nc"):
        raise ValueError("Unexpected native-cell-area provenance")
    files["area_provenance"] = _file(provenance_path)
    files["area"] = _file(area_path, _AREA_SHA)
    if files["area"]["bytes"] != provenance["bytes"]:
        raise ValueError("Native-cell-area byte count mismatch")
    with np.load(audit / "spatial_mapping.npz", allow_pickle=False) as mapping:
        latitude, longitude = mapping["latitude"], mapping["longitude"]
        if (latitude.shape != (350,) or longitude.shape != (950,)
                or not np.all(np.diff(latitude) < 0) or not np.all(np.diff(longitude) > 0)):
            raise ValueError("Unexpected native spatial axes")
    with h5py.File(area_path, "r") as source:
        _coordinates(source, latitude, longitude)
        area = source["cell_area"][:]
        if (_text(source["cell_area"].attrs.get("units", "")) != "m2"
                or area.shape != (350, 950) or not np.all(np.isfinite(area) & (area > 0))):
            raise ValueError("Native area must be finite positive square metres")
    downloads = json.loads((audit / "download_manifest.json").read_text())
    entries = {entry["filename"]: entry for entry in downloads["files"]}
    if downloads["catalogue"] != "https://open.canada.ca/data/en/dataset/9a68a501-9a87-441a-8073-980ae68438ef":
        raise ValueError("Expected ECCC CanCPLDv1 source catalogue")
    for year in _YEARS:
        name = f"cg_flashes_3hr_0.1-deg_{year}.nc"
        entry = entries[name]
        files[str(year)] = _file(audit / "raw" / name, entry["sha256"])
        if files[str(year)]["bytes"] != entry["bytes"]:
            raise ValueError(f"Native CG byte count mismatch: {year}")
        if entry["url"] != f"https://crd-data-donnees-rdc.ec.gc.ca/CDAS/products/CanCPLD/CLDN/cg/{name}":
            raise ValueError(f"Unexpected native CG source archive: {year}")
        with h5py.File(audit / "raw" / name, "r") as source:
            _coordinates(source, latitude, longitude)
            bounds = _bounds(source, year)
            counts = source["cg_flashes"]
            if (counts.shape != (len(bounds), 350, 950)
                    or _text(counts.attrs.get("units", "")) != _CG_UNITS
                    or _text(counts.attrs.get("cell_methods", "")) != "time: sum (interval: 3 hours)"):
                raise ValueError(f"Unexpected native CG schema: {year}")
            if "scale_factor" in counts.attrs or "add_offset" in counts.attrs:
                raise ValueError("Packed CG counts are not supported")
    return {"feature_version": FEATURE_VERSION, "development_years": list(_YEARS),
            "files": files}


def prefix_counts(counts, fill_values=()):
    """Integer counts and unknown-bin prefixes, each shaped (T+1, S)."""
    counts = np.asarray(counts)
    if counts.ndim != 2:
        raise ValueError("Counts must have shape (time, native_cell)")
    missing = ~np.isfinite(counts)
    for fill in np.asarray(fill_values).reshape(-1):
        missing |= counts == fill
    valid = counts[~missing]
    if np.any(valid < 0) or np.any(valid != np.floor(valid)) or np.any(valid >= 2**63):
        raise ValueError("Observed CG counts must be nonnegative int64-representable integers")
    if len(counts) >= 2**32:
        raise ValueError("Too many intervals for missing-count prefix")
    # Guard the sum before casting; the actual source counts are small integers.
    if valid.size and float(valid.max()) * len(counts) >= 2**63:
        raise ValueError("CG count prefix could overflow int64")
    countprefix = np.zeros((len(counts) + 1, counts.shape[1]), dtype=np.int64)
    missingprefix = np.zeros(countprefix.shape, dtype=np.uint32)
    np.cumsum(np.where(missing, 0, counts).astype(np.int64), axis=0,
              dtype=np.int64, out=countprefix[1:])
    np.cumsum(missing, axis=0, dtype=np.uint32, out=missingprefix[1:])
    return countprefix, missingprefix


def issue_window_end(bounds, day: date):
    """Return exclusive complete-bin end and issue lag in seconds.

    Numeric bounds are seconds since 1998-01-01 UTC; datetime64 bounds are
    accepted too. Every interval is [start, end), with exactly 10800 seconds.
    """
    bounds = np.asarray(bounds)
    if bounds.ndim != 2 or bounds.shape[1] != 2 or not len(bounds):
        raise ValueError("Expected nonempty (T, 2) interval bounds")
    issue = datetime.combine(day, time(), _ZONE).astimezone(timezone.utc)
    if np.issubdtype(bounds.dtype, np.datetime64):
        if np.any(np.isnat(bounds)):
            raise ValueError("Missing interval bounds")
        seconds = (bounds - np.datetime64("1998-01-01T00:00:00")) / np.timedelta64(1, "s")
    else:
        seconds = bounds
    if (not np.all(np.isfinite(seconds))
            or not np.all(seconds[:, 1] - seconds[:, 0] == 10800)
            or not np.all(seconds[1:, 0] == seconds[:-1, 1])):
        raise ValueError("Source bounds must be contiguous complete 3h intervals")
    issue_seconds = (issue - _EPOCH).total_seconds()
    end = int(np.searchsorted(seconds[:, 1], issue_seconds, side="right"))
    if not end:
        raise ValueError("No complete source interval before issue")
    lag = issue_seconds - float(seconds[end - 1, 1])
    if not 0 <= lag < 10800:
        raise ValueError("Source ends before the last complete pre-issue interval")
    return end, lag


def window_features(countprefix, missingprefix, weights: csr_matrix, end: int):
    """Project 8/56-bin native sums; unknowns propagate through positive weights."""
    if (countprefix.ndim != 2 or countprefix.shape != missingprefix.shape
            or weights.shape[1] != countprefix.shape[1]
            or not 56 <= end < countprefix.shape[0]):
        raise ValueError("Window lacks 56 consecutive bins or compatible spatial dimensions")
    if np.any(~np.isfinite(weights.data)) or np.any(weights.data < 0):
        raise ValueError("Density weights must be finite and nonnegative")
    positive = weights.copy()
    positive.data = (positive.data > 0).astype(np.float64)
    result = np.empty((weights.shape[0], 2), dtype=np.float64)
    for column, width in enumerate((8, 56)):
        native = countprefix[end] - countprefix[end - width]
        unknown = missingprefix[end] != missingprefix[end - width]
        result[:, column] = weights @ native
        result[(positive @ unknown.astype(np.float64)) > 0, column] = np.nan
    return result


def _development_rows(row_ids, manifest):
    ids = np.asarray(row_ids)
    expected_days = [date(year, 5, 1) + timedelta(days=offset)
                     for year in _YEARS for offset in range(184)]
    selected = [(key, value) for key, value in manifest["date_slices"].items()
                if 2010 <= int(key[:4]) <= 2016]
    if [key for key, _ in selected] != [day.isoformat() for day in expected_days]:
        raise ValueError("Development dates must be May--October 2010--2016 in order")
    if ids.ndim != 1 or ids.dtype != np.dtype("uint16"):
        raise ValueError("row_ids must be the read-only grid.u16 row mapping")
    expected = np.arange(9673, dtype=np.uint16)
    cursor = 0
    digest = hashlib.sha256()
    for day, (start, stop) in selected:
        if start != cursor or stop - start != 9673 or stop > len(ids):
            raise ValueError(f"Noncontiguous or incomplete cache date: {day}")
        daily = ids[start:stop]
        if not np.array_equal(np.sort(daily), expected):
            raise ValueError(f"Duplicate or missing target grid IDs: {day}")
        digest.update(memoryview(np.ascontiguousarray(daily)).cast("B"))
        cursor = stop
    if cursor != 12458824 or len(ids) not in (cursor, manifest["rows"]):
        raise ValueError("Unexpected development row universe")
    return selected, cursor, digest.hexdigest()


def _summary(values):
    result = {}
    for column, name in enumerate(LIGHTNING_NAMES):
        data = values[:, column]
        valid = np.isfinite(data)
        nvalid = int(valid.sum())
        zeros = int(np.count_nonzero(data == 0))
        result[name] = {"rows": len(data), "valid": nvalid, "missing": int(len(data) - nvalid),
                        "zero": zeros, "valid_rate": nvalid / len(data),
                        "zero_rate": zeros / len(data),
                        "zero_rate_among_valid": zeros / nvalid if nvalid else None,
                        "min": float(data[valid].min()) if nvalid else None,
                        "max": float(data[valid].max()) if nvalid else None}
    return result


def _atomic_json(path, value):
    descriptor, name = tempfile.mkstemp(prefix=".audit-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as destination:
            json.dump(value, destination, indent=2, allow_nan=False)
            destination.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def build_features(audit, area_path, row_ids, manifest, output, inputs):
    """Construct a fresh, separately versioned development feature file."""
    audit, area_path = Path(audit), Path(area_path)
    if inputs.get("feature_version") != FEATURE_VERSION:
        raise ValueError("Unexpected source feature definition")
    if (audit.resolve() != Path(inputs["files"]["configuration.json"]["path"]).parent
            or area_path.resolve() != Path(inputs["files"]["area"]["path"])):
        raise ValueError("Build paths differ from validated inputs")
    slices, nrows, row_hash = _development_rows(row_ids, manifest)
    directory = Path(output) / "lightning_features" / FEATURE_VERSION
    directory.mkdir(parents=True, exist_ok=True)
    feature_path, audit_path = directory / "features.npy", directory / "audit.json"
    if feature_path.exists() or audit_path.exists():
        raise FileExistsError("Lightning feature output exists; use a fresh output directory")
    with np.load(audit / "spatial_mapping.npz", allow_pickle=False) as mapping:
        lat_ids, lon_ids = mapping["latitude_indices"], mapping["longitude_indices"]
        coverage = mapping["target_area_fraction"]
    if (len(lat_ids) != 131 or len(lon_ids) != 195
            or not np.all(np.diff(lat_ids) == 1) or not np.all(np.diff(lon_ids) == 1)
            or not np.all(np.isfinite(coverage)) or coverage.shape != (9673,)
            or not np.all(np.abs(coverage - 1) < 1e-6)):
        raise ValueError("Unexpected or incomplete spatial target coverage")
    latitude_slice = slice(int(lat_ids[0]), int(lat_ids[-1]) + 1)
    longitude_slice = slice(int(lon_ids[0]), int(lon_ids[-1]) + 1)
    with h5py.File(area_path, "r") as source:
        areas = source["cell_area"][latitude_slice, longitude_slice].reshape(-1)
    weights = load_npz(audit / "spatial_area_weights.npz").tocsr()
    if weights.shape != (9673, 25545):
        raise ValueError("Unexpected spatial weights shape")
    if (not np.all(np.isfinite(weights.data)) or np.any(weights.data < 0)
            or not np.all(np.abs(np.asarray(weights.sum(axis=1)).ravel() - coverage) < 1e-6)):
        raise ValueError("Intersection weights must be finite, nonnegative and cover each target")
    weights = weights.multiply(1e6 / areas).tocsr()
    descriptor, temporary_name = tempfile.mkstemp(prefix=".features-", suffix=".npy", dir=directory)
    os.close(descriptor)
    temporary = Path(temporary_name)
    values = None
    yearly, lags = {}, []
    try:
        values = np.lib.format.open_memmap(temporary, mode="w+", dtype=np.float64, shape=(nrows, 2))
        for year in _YEARS:
            days = [(day, selection) for day, selection in slices if int(day[:4]) == year]
            with h5py.File(inputs["files"][str(year)]["path"], "r") as source:
                bounds = _bounds(source, year)
                first_end, _ = issue_window_end(bounds, date.fromisoformat(days[0][0]))
                last_end, _ = issue_window_end(bounds, date.fromisoformat(days[-1][0]))
                first = first_end - 56
                length = last_end - first
                counts = np.zeros((length + 1, 25545), dtype=np.int64)
                missing = np.zeros((length + 1, 25545), dtype=np.uint32)
                variable = source["cg_flashes"]
                fills = [value for name in ("_FillValue", "missing_value")
                         if name in variable.attrs for value in np.asarray(variable.attrs[name]).reshape(-1)]
                native_valid = native_zero = native_missing = 0
                for offset in range(0, length, 16):
                    stop = min(offset + 16, length)
                    block = variable[first + offset:first + stop, latitude_slice, longitude_slice].reshape(stop - offset, -1)
                    cp, mp = prefix_counts(block, fills)
                    counts[offset + 1:stop + 1] = cp[1:] + counts[offset]
                    missing[offset + 1:stop + 1] = mp[1:] + missing[offset]
                    nmissing = int(mp[-1].sum(dtype=np.uint64))
                    native_missing += nmissing
                    native_valid += block.size - nmissing
                    native_zero += int(np.count_nonzero(block == 0))
                for day, (start, stop) in days:
                    end, lag = issue_window_end(bounds, date.fromisoformat(day))
                    lags.append(lag)
                    daily = window_features(counts, missing, weights, end - first)
                    values[start:stop] = daily[np.asarray(row_ids[start:stop])]
                start, stop = days[0][1][0], days[-1][1][1]
                yearly[str(year)] = {"rows": stop - start, "dates": len(days),
                                     "earliest_date": days[0][0], "latest_date": days[-1][0],
                                     "features": _summary(values[start:stop]),
                                     "native_bbox_bins": length, "native_bbox_valid_values": native_valid,
                                     "native_bbox_missing_values": native_missing,
                                     "native_bbox_zero_values": native_zero,
                                     "first_consumed_bin_start_seconds_since_1998": int(bounds[first, 0]),
                                     "last_consumed_bin_end_seconds_since_1998": int(bounds[last_end - 1, 1])}
                del counts, missing
        values.flush()
        del values
        values = None
        recorded = {"feature_version": FEATURE_VERSION, "features": list(LIGHTNING_NAMES),
                    "feature_file": feature_path.name, "feature_directory": str(directory.resolve()),
                    "feature_file_sha256": sha256(temporary),
                    "dtype": "float64", "shape": [nrows, 2], "rows": nrows, "dates": len(slices),
                    "earliest_date": slices[0][0], "latest_date": slices[-1][0],
                    "development_years": list(_YEARS), "yearly": yearly,
                    "inputs": inputs, "row_ids_sha256": row_hash,
                    "units": "detected CG flashes / km2",
                    "source_cutoff_lag_seconds": {"min": min(lags), "max": max(lags), "unique": sorted(set(lags))},
                    "window_bins": [8, 56], "issue_time": "00:00 America/Toronto",
                    "projection": "A_ij=intersection_area/target_area; W_ij=A_ij*1e6/native_cell_area_m2; W @ integer native window sums",
                    "missing_rule": "Any explicit fill/NaN in any contributing positive-weight native cell/bin makes the window unknown (NaN).",
                    "source_caveats": ["Approximate native-grid density, not exact located target-cell flash counts.",
                                       "Zeros are observed detector zeros; undocumented historical outages cannot be identified.",
                                       "Retrospective source publication latency is unknown; no per-bin detector outage flags exist.",
                                       "Trailing complete 3-hour bins are not exact previous local calendar days.",
                                       "Native cell bounds are inferred as centres +/-0.05 degrees; audited intersections omit areas below 1 m2."]}
        os.replace(temporary, feature_path)
        _atomic_json(audit_path, recorded)
        return np.load(feature_path, mmap_mode="r", allow_pickle=False), recorded
    finally:
        if values is not None:
            del values
        temporary.unlink(missing_ok=True)
