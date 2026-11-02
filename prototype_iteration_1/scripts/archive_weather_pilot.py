"""One-off free archived HRDPS/reference pilot; receipt is never backdated."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from scripts.hrdps_live_weather import (
    FIELDS,
    incremental_rain,
    rotate_wind,
    sample_grib,
)
from scripts.ignition_comparison import digest
from scripts.live_qualification import weather_metrics
from scripts.prepare_selected_weather import wind
from scripts.workflow_sources import atomic_json, now_utc


def acquire(session, url, path, records, manifest):
    if path.exists():
        raise FileExistsError("Use a new raw acquisition directory")
    temporary = path.with_suffix(".partial")
    size = 0
    try:
        with session.get(url, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if (
                        size > 15_000_000
                        or sum(r["bytes"] for r in records) + size > 100_000_000
                    ):
                        raise ValueError("Weather pilot download budget exceeded")
                    handle.write(chunk)
            temporary.replace(path)
            records.append(
                {
                    "url": url,
                    "path": str(path),
                    "bytes": size,
                    "sha256": digest(path),
                    "retrieved_at_utc": now_utc(),
                    "last_modified": response.headers.get("Last-Modified"),
                    "cost_usd": 0,
                }
            )
            atomic_json(manifest, records)
    finally:
        temporary.unlink(missing_ok=True)


def run(workspace, output):
    if output.exists():
        raise FileExistsError("Use a new pilot directory")
    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    reference = (
        workspace / "reports/live_qualification_2026-11-01/hourly_reference.parquet"
    )
    run_time = pd.Timestamp("2026-10-15T00:00Z")
    atomic_json(
        output / "protocol.json",
        {
            "mode": "archived_forecast_hindsight_source_comparison",
            "run_time_utc": run_time.isoformat(),
            "leads_downloaded": [18, 19, 20],
            "leads_compared": [19, 20],
            "model_fits": 0,
            "places": ["red_lake", "thunder_bay", "timmins"],
            "historical_receipt_before_issue_verified": False,
            "operational": False,
            "reference_sha256": digest(reference),
        },
    )
    keys = pd.read_csv(
        workspace
        / "reports/zero_cost_sources_2026-11-01/lightning_pilot/lightning_features.csv"
    ).grid_id.unique()
    grid = pd.read_csv(
        workspace / "reports/week_4_data_2026-10-16/current_boundary_centroid_grid.csv"
    )
    grid = grid.loc[grid.grid_id.isin(keys)].copy()
    if len(grid) != 3:
        raise ValueError("Expected the three registered pilot cells")
    records, rows, previous = [], [], None
    with requests.Session() as session:
        session.headers["User-Agent"] = (
            "COMP385-Ontario-Wildfire-research/1.0 one-off-bounded-pilot"
        )
        for lead in (18, 19, 20):
            values, metadata, bearings = {}, {}, {}
            for field, (token, level, _) in FIELDS.items():
                name = f"{run_time:%Y%m%dT%HZ}_MSC_HRDPS_{token}_{level}_RLatLon0.0225_PT{lead:03d}H.grib2"
                path = raw / name
                url = f"https://dd.weather.gc.ca/{run_time:%Y%m%d}/WXO-DD/model_hrdps/continental/2.5km/{run_time:%H}/{lead:03d}/{name}"
                acquire(session, url, path, records, output / "download_manifest.json")
                values[field], bearings[field], metadata[field] = sample_grib(
                    path, grid, run_time, lead, field
                )
            if len({m["grid_signature"] for m in metadata.values()}) != 1:
                raise ValueError("Weather grids differ")
            if not np.allclose(bearings["u_grid_ms"], bearings["v_grid_ms"]):
                raise ValueError("Wind rotation differs")
            u, v = rotate_wind(
                values["u_grid_ms"], values["v_grid_ms"], bearings["u_grid_ms"]
            )
            speed, direction = wind(u, v)
            end = run_time + pd.Timedelta(hours=lead)
            start = pd.Timestamp(metadata["precip_mm"]["accumulation_start_utc"])
            rain = incremental_rain(values["precip_mm"], start, end, previous)
            previous = (values["precip_mm"], start, end)
            if lead == 18:
                continue
            for i, cell in enumerate(grid.itertuples()):
                rows.append(
                    {
                        "grid_id": cell.grid_id,
                        "valid_time_utc": end,
                        "run_time_utc": run_time,
                        "available_at_utc": records[-1]["retrieved_at_utc"],
                        "temp_c": float(values["temp_c"][i]),
                        "rh_pct": float(values["rh_pct"][i]),
                        "wind_kmh": float(speed[i]),
                        "wind_from_degrees": float(direction[i]),
                        "precip_mm": float(rain[i]),
                    }
                )
    forecast = pd.DataFrame(rows)
    paired = forecast.merge(
        pd.read_parquet(reference),
        on=["grid_id", "valid_time_utc"],
        suffixes=("_forecast", "_reference"),
        validate="one_to_one",
    )
    if len(paired) != 6:
        raise ValueError("Expected six exact pilot cell-time pairs")
    paired.to_csv(output / "paired_weather.csv", index=False)
    result = {
        "matched_cell_times": len(paired),
        "grid_cells": 3,
        "valid_hours": 2,
        "run_time_utc": run_time.isoformat(),
        "independent_from_existing_run": "Existing comparison used 2026-10-16 00 UTC",
        "historical_receipt_before_issue_verified": False,
        "operational": False,
        "warning": "Late archive acquisition supports hindsight weather diagnostics only; no prospective replay claim",
        "metrics": weather_metrics(paired),
        "downloaded_bytes": sum(r["bytes"] for r in records),
        "reference_sha256": digest(reference),
    }
    atomic_json(output / "audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.workspace.resolve(), args.output.resolve()), indent=2))
