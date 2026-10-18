from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.windows import from_bounds, transform as window_transform


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data" / "raw" / "samples"
MODEL_CRS = "EPSG:3978"
GRID_SIZE_M = 2_500
SAMPLE_CELLS_PER_SIDE = 12
RETRIEVED_ON = "2026-10-02"

PLACES = {
    "red_lake": (-93.8280, 51.0180),
    "thunder_bay": (-89.2477, 48.3809),
    "timmins": (-81.3305, 48.4758),
}

FBP_WCS_URL = (
    "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/"
    "cffdrs_fbp_fuel_types/ows"
)
FBP_COVERAGE_ID = "public__cffdrs_fbp_fuel_types"

SCANFI_BASE_URL = (
    "https://ftp.maps.canada.ca/pub/nrcan_rncan/Forests_Foret/SCANFI/v2"
)
SCANFI_FILES = {
    "closure_1985": "SCANFI_att_closure_1985_v2_20260119.tif",
    "closure_2020": "SCANFI_att_closure_2020_v2_20260119.tif",
    "closure_2025": "SCANFI_att_closure_2025_v2_20260119.tif",
    "height_2020": "SCANFI_att_height_2020_v2_20260119.tif",
    "balsam_fir_2020": "SCANFI_spsCC_balsamFir_2020_v2_20260119.tif",
    "black_spruce_2020": "SCANFI_spsCC_blackSpruce_2020_v2_20260119.tif",
    "broadleaf_2020": "SCANFI_spsCC_broadleaf_2020_v2_20260119.tif",
    "jack_pine_2020": "SCANFI_spsCC_jackPine_2020_v2_20260119.tif",
    "other_conifer_2020": "SCANFI_spsCC_otherConiferous_2020_v2_20260119.tif",
    "tamarack_2020": "SCANFI_spsCC_tamarack_2020_v2_20260119.tif",
    "white_red_pine_2020": "SCANFI_spsCC_whiteRedPine_2020_v2_20260119.tif",
}

MRDEM_DTM_URL = (
    "https://canelevation-dem.s3.ca-central-1.amazonaws.com/"
    "mrdem-30/mrdem-30-dtm.tif"
)


def sample_bounds(lon: float, lat: float) -> tuple[float, float, float, float]:
    transformer = Transformer.from_crs("EPSG:4326", MODEL_CRS, always_xy=True)
    x, y = transformer.transform(lon, lat)
    half_cells = SAMPLE_CELLS_PER_SIDE // 2
    left = (math.floor(x / GRID_SIZE_M) - half_cells) * GRID_SIZE_M
    bottom = (math.floor(y / GRID_SIZE_M) - half_cells) * GRID_SIZE_M
    size = SAMPLE_CELLS_PER_SIDE * GRID_SIZE_M
    return left, bottom, left + size, bottom + size


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_remote_window(
    dataset: rasterio.io.DatasetReader,
    model_bounds: tuple[float, float, float, float],
    output_path: Path,
) -> None:
    transformer = Transformer.from_crs(MODEL_CRS, dataset.crs, always_xy=True)
    source_bounds = transformer.transform_bounds(*model_bounds, densify_pts=21)
    window = from_bounds(*source_bounds, transform=dataset.transform)
    window = window.round_offsets().round_lengths()
    data = dataset.read(1, window=window, masked=True)

    profile = dataset.profile.copy()
    profile.update(
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        transform=window_transform(window, dataset.transform),
        compress="deflate",
        tiled=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as output:
        output.write(data.filled(dataset.nodata), 1)


def fetch_fbp(place: str, bounds: tuple[float, float, float, float]) -> Path:
    left, bottom, right, top = bounds
    output_path = OUTPUT_ROOT / place / "fbp_2024.tif"
    response = requests.get(
        FBP_WCS_URL,
        params={
            "service": "WCS",
            "version": "2.0.1",
            "request": "GetCoverage",
            "CoverageId": FBP_COVERAGE_ID,
            "format": "image/tiff",
            "subset": [f"E({left},{right})", f"N({bottom},{top})"],
        },
        timeout=180,
    )
    response.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return output_path


def main() -> None:
    bounds_by_place = {
        place: sample_bounds(lon, lat) for place, (lon, lat) in PLACES.items()
    }
    source_urls: dict[str, str] = {
        "fbp_2024": FBP_WCS_URL,
        "mrdem_dtm": MRDEM_DTM_URL,
    }

    for place, bounds in bounds_by_place.items():
        output_path = fetch_fbp(place, bounds)
        print(f"Fetched {output_path.relative_to(ROOT)}", flush=True)

    rasterio_env = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    }
    with rasterio.Env(**rasterio_env):
        for layer, filename in SCANFI_FILES.items():
            url = f"{SCANFI_BASE_URL}/{filename}"
            source_urls[f"scanfi_{layer}"] = url
            with rasterio.open(url) as dataset:
                for place, bounds in bounds_by_place.items():
                    output_path = OUTPUT_ROOT / place / f"scanfi_{layer}.tif"
                    write_remote_window(dataset, bounds, output_path)
                    print(f"Fetched {output_path.relative_to(ROOT)}", flush=True)

        with rasterio.open(MRDEM_DTM_URL) as dataset:
            for place, bounds in bounds_by_place.items():
                output_path = OUTPUT_ROOT / place / "mrdem_dtm.tif"
                write_remote_window(dataset, bounds, output_path)
                print(f"Fetched {output_path.relative_to(ROOT)}", flush=True)

    files = sorted(OUTPUT_ROOT.glob("*/*.tif"))
    manifest = {
        "retrieved_on": RETRIEVED_ON,
        "model_crs": MODEL_CRS,
        "sample_grid_size_m": GRID_SIZE_M,
        "sample_cells_per_side": SAMPLE_CELLS_PER_SIDE,
        "places": {
            place: {
                "longitude": PLACES[place][0],
                "latitude": PLACES[place][1],
                "bounds_model_crs": bounds_by_place[place],
            }
            for place in PLACES
        },
        "source_urls": source_urls,
        "files": [
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    manifest_path = OUTPUT_ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {manifest_path.relative_to(ROOT)} with {len(files)} rasters")


if __name__ == "__main__":
    main()
