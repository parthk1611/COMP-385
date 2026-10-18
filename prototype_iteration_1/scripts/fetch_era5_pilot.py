from __future__ import annotations

import argparse
import calendar
import json
import math

from pyproj import Transformer

from scripts.fetch_static_samples import MODEL_CRS, ROOT, sha256
from scripts.prepare_ignition_pilot import BOUNDS

OUTPUT = ROOT / "data/raw/ignition_pilot/era5"
VARIABLES = ["2m_temperature", "2m_dewpoint_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind", "total_precipitation"]


def monthly_requests() -> list[dict]:
    west, south, east, north = Transformer.from_crs(MODEL_CRS, "EPSG:4326", always_xy=True).transform_bounds(*BOUNDS, densify_pts=21)
    area = [math.ceil(north * 10) / 10 + .1, math.floor(west * 10) / 10 - .1,
            math.floor(south * 10) / 10 - .1, math.ceil(east * 10) / 10 + .1]
    return [{"variable": VARIABLES, "year": ["2025"], "month": [f"{month:02d}"],
             "day": [f"{day:02d}" for day in range(1, calendar.monthrange(2025, month)[1] + 1)],
             "time": [f"{hour:02d}:00" for hour in range(24)], "area": [round(v, 1) for v in area],
             "data_format": "netcdf", "download_format": "unarchived"} for month in range(1, 12)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare ERA5-Land pilot requests; downloading requires local CDS credentials and accepted licence.")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    requests = monthly_requests()
    plan = {"dataset": "reanalysis-era5-land", "requests": requests,
            "purpose": "January-March warm-up and April-October labels; November includes the trailing UTC boundary.",
            "precipitation_convention": "ERA5-Land hourly accumulated precipitation; deaccumulate before rainfall features.",
            "fwi_status": "Not implemented. Initialization, seasonal startup and overwintering require validation before training."}
    (OUTPUT / "requests.json").write_text(json.dumps(plan, indent=2) + "\n")
    if not args.download:
        print("Prepared 11 monthly requests; no weather downloaded.")
        return
    import cdsapi
    client = cdsapi.Client()
    downloaded = []
    for request in requests:
        target = OUTPUT / f"era5_land_2025_{request['month'][0]}.nc"
        client.retrieve(plan["dataset"], request, str(target))
        downloaded.append({"path": str(target.relative_to(ROOT)), "bytes": target.stat().st_size, "sha256": sha256(target)})
        (OUTPUT / "download_manifest.json").write_text(json.dumps({"dataset": plan["dataset"], "files": downloaded}, indent=2) + "\n")


if __name__ == "__main__":
    main()
