"""Audit a bounded CanCPLD lightning feature pilot; never fit or activate a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
import rasterio
from rasterio.windows import Window
from shapely.geometry import box
from shapely.ops import transform

from scripts.ignition_comparison import digest
from scripts.workflow_sources import atomic_json

EPOCH = pd.Timestamp("1998-01-01", tz="UTC")
PLACES = {
    "red_lake": (-93.82, 51.03),
    "thunder_bay": (-89.25, 48.38),
    "timmins": (-81.33, 48.48),
}


def interval_clock(path):
    with rasterio.open(f'NETCDF:"{path}":cg_flashes') as source:
        if source.tags().get("time#units") != "seconds since 1998-1-1 0:0:0":
            raise ValueError("Unexpected CanCPLD time units")
        starts = np.array(
            [int(source.tags(i)["NETCDF_DIM_time"]) for i in range(1, source.count + 1)]
        )
    with rasterio.open(f'NETCDF:"{path}":time_bnds') as source:
        bounds = source.read(1)
    # GDAL may reverse a non-geographical Y dimension; reconcile explicit bounds.
    bounds = bounds[np.argsort(bounds[:, 0])]
    if bounds.shape != (len(starts), 2) or not np.array_equal(bounds[:, 0], starts):
        raise ValueError("CanCPLD band clocks differ from interval bounds")
    if (
        not (np.diff(starts) == 10800).all()
        or not (bounds[:, 1] - bounds[:, 0] == 10800).all()
    ):
        raise ValueError("CanCPLD requires consecutive three-hour intervals")
    return EPOCH + pd.to_timedelta(bounds[:, 1], unit="s")


def completed_window(ends, issue, hours):
    issue = pd.Timestamp(issue)
    if issue.tzinfo is None or hours not in (24, 168):
        raise ValueError("Timezone-aware issue and a 24/168-hour window required")
    if not ends.is_unique or not ends.is_monotonic_increasing:
        raise ValueError("Interval ends must be unique and ordered")
    eligible = ends[ends <= issue]
    if eligible.empty:
        raise ValueError("No complete interval before issue")
    cutoff = eligible[-1]
    mask = (ends > cutoff - pd.Timedelta(hours=hours)) & (ends <= cutoff)
    expected = pd.date_range(cutoff - pd.Timedelta(hours=hours - 3), cutoff, freq="3h")
    if not ends[mask].equals(expected):
        raise ValueError("Incomplete lightning time window")
    return np.flatnonzero(mask), cutoff


def density_summary(counts, areas_km2, weights):
    counts = np.asarray(counts, dtype=float)
    areas_km2, weights = np.asarray(areas_km2), np.asarray(weights)
    if (
        counts.ndim != 2
        or counts.shape[1] != len(weights)
        or len(weights) != len(areas_km2)
    ):
        raise ValueError("Lightning dimensions differ")
    if (
        not np.isfinite(areas_km2).all()
        or (areas_km2 <= 0).any()
        or not np.isfinite(weights).all()
        or (weights < 0).any()
    ):
        raise ValueError("Invalid native-cell areas or overlap weights")
    valid = np.isfinite(counts) & (counts >= 0)
    if (np.abs(counts[valid] - np.round(counts[valid])) > 1e-4).any():
        raise ValueError("Source observations must be integer flash counts")
    coverage = float(np.sum(valid * weights) / len(counts))
    complete = valid.all() and abs(weights.sum() - 1) <= 1e-6
    density = float(np.sum(counts / areas_km2 * weights)) if complete else None
    return density, coverage


def overlap_pixels(source, target):
    to_geo = Transformer.from_crs(3978, 4326, always_xy=True).transform
    to_area = Transformer.from_crs(4326, 3978, always_xy=True).transform
    west, south, east, north = transform(to_geo, target).bounds
    r0, c0 = source.index(west, north)
    r1, c1 = source.index(east, south)
    result = []
    for row in range(max(0, r0 - 1), min(source.height, r1 + 2)):
        for col in range(max(0, c0 - 1), min(source.width, c1 + 2)):
            left, top = source.transform * (col, row)
            right, bottom = source.transform * (col + 1, row + 1)
            polygon = transform(to_area, box(left, bottom, right, top))
            overlap = target.intersection(polygon).area
            if overlap > 0:
                result.append((row, col, overlap / target.area))
    if not result or abs(sum(p[2] for p in result) - 1) > 1e-6:
        raise ValueError("Native cells do not cover the model cell")
    return result


def run(workspace, archive, area_file, output):
    if output.exists():
        raise FileExistsError("Use a new pilot output directory")
    output.mkdir(parents=True)
    protocol = {
        "scope": "Acquisition/feature validation only; no model fit or promotion",
        "places": PLACES,
        "target_dates": ["2010-06-01", "2010-06-10"],
        "windows_hours": [24, 168],
        "issue": "00:00 America/Toronto",
        "aggregation": "Area-weighted native CG flash density across the existing 10 km cell",
        "availability": "Processed archive retrieved in 2026; historical issue-time receipt unknown",
        "operational": False,
        "archive_sha256": digest(archive),
        "area_sha256": digest(area_file),
    }
    atomic_json(output / "protocol.json", protocol)
    grid = pd.read_csv(
        workspace / "reports/week_4_data_2026-10-16/current_boundary_centroid_grid.csv"
    )
    project = Transformer.from_crs(4326, 3978, always_xy=True)
    gx, gy = project.transform(
        grid.centroid_longitude.to_numpy(), grid.centroid_latitude.to_numpy()
    )
    ends = interval_clock(archive)
    rows = []
    with rasterio.open(f'NETCDF:"{archive}":cg_flashes') as source, rasterio.open(
        area_file
    ) as areas:
        if source.shape != areas.shape or source.transform != areas.transform:
            raise ValueError("Count and area grids differ")
        if (
            source.tags().get("lat#units") != "degrees_north"
            or source.tags().get("lon#units") != "degrees_east"
        ):
            raise ValueError("Expected geographic longitude/latitude coordinates")
        if areas.tags().get("cell_area#units") != "m2":
            raise ValueError("Expected native cell areas in square metres")
        for place, (lon, lat) in PLACES.items():
            x, y = project.transform(lon, lat)
            cell = grid.iloc[np.argmin((gx - x) ** 2 + (gy - y) ** 2)]
            target = box(
                cell.grid_x_m,
                cell.grid_y_m,
                cell.grid_x_m + 10000,
                cell.grid_y_m + 10000,
            )
            pixels = overlap_pixels(source, target)
            weights = np.array([p[2] for p in pixels])
            native_areas = np.array(
                [
                    areas.read(1, window=Window(c, r, 1, 1))[0, 0] / 1e6
                    for r, c, _ in pixels
                ]
            )
            for date in pd.date_range("2010-06-01", "2010-06-10"):
                issue = date.tz_localize("America/Toronto").tz_convert("UTC")
                row = {
                    "place": place,
                    "grid_id": cell.grid_id,
                    "date": date.date().isoformat(),
                    "issue_time_utc": issue.isoformat(),
                    "native_cells": len(pixels),
                }
                for hours in (24, 168):
                    indexes, cutoff = completed_window(ends, issue, hours)
                    values = np.column_stack(
                        [
                            source.read(
                                (indexes + 1).tolist(),
                                window=Window(c, r, 1, 1),
                                masked=True,
                            )
                            .astype(float)
                            .filled(np.nan)[:, 0, 0]
                            for r, c, _ in pixels
                        ]
                    )
                    density, coverage = density_summary(values, native_areas, weights)
                    row.update(
                        {
                            f"cg_density_{hours}h_per_km2": density,
                            f"coverage_{hours}h": coverage,
                        }
                    )
                    row["last_complete_interval_end_utc"] = cutoff.isoformat()
                    row["lag_to_issue_hours"] = float(
                        (issue - cutoff).total_seconds() / 3600
                    )
                rows.append(row)
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "lightning_features.csv", index=False)
    audit = {
        "rows": len(frame),
        "distinct_model_cells": int(frame.grid_id.nunique()),
        "native_intervals_in_year": len(ends),
        "source_interval_end_min": ends.min().isoformat(),
        "source_interval_end_max": ends.max().isoformat(),
        "nonzero_24h_rows": int(frame.cg_density_24h_per_km2.gt(0).sum()),
        "nonzero_168h_rows": int(frame.cg_density_168h_per_km2.gt(0).sum()),
        "complete_24h_rows": int(frame.coverage_24h.ge(1 - 1e-6).sum()),
        "future_interval_violations": int(
            (
                pd.to_datetime(frame.last_complete_interval_end_utc)
                > pd.to_datetime(frame.issue_time_utc)
            ).sum()
        ),
        "model_fits": 0,
        "operational": False,
        "features_sha256": digest(output / "lightning_features.csv"),
    }
    atomic_json(output / "audit.json", audit)
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "archive", "area-file", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.workspace.resolve(),
                args.archive.resolve(),
                args.area_file.resolve(),
                args.output.resolve(),
            ),
            indent=2,
        )
    )
