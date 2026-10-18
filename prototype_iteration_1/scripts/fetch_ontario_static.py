from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path

import geopandas as gpd
import rasterio
import requests
from pyproj import Transformer
from rasterio.windows import from_bounds, transform as window_transform
from shapely.geometry import box


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "ontario"
ZONE_PATH = OUTPUT / "fire_management_zone" / "service_2026-10-02.geojson"
RESPONSE_AREA_PATH = OUTPUT / "fire_response_plan_area" / "fire_response_plan_area_2026-10-02.geojson"
MODEL_CRS = "EPSG:3978"
TILE_M = 100_000

FBP = {
    "2024": (
        "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/cffdrs_fbp_fuel_types/ows",
        "public__cffdrs_fbp_fuel_types",
        ("E", "N"),
    ),
}
FBP_2026_RAW = "https://ca.nfis.org/fss/fss?command=retrieveByName&fileName=FBP_FuelTypes_Canada_2026_30m.tif&fileNamespace=fire_behaviour_prediction"

SCANFI_BASE = "https://ftp.maps.canada.ca/pub/nrcan_rncan/Forests_Foret/SCANFI/v2"
SCANFI = {
    "closure_2025": "SCANFI_att_closure_2025_v2_20260119.tif",
    "height_2025": "SCANFI_att_height_2025_v2_20260119.tif",
    "balsam_fir_2025": "SCANFI_spsCC_balsamFir_2025_v2_20260119.tif",
    "black_spruce_2025": "SCANFI_spsCC_blackSpruce_2025_v2_20260119.tif",
    "broadleaf_2025": "SCANFI_spsCC_broadleaf_2025_v2_20260119.tif",
    "jack_pine_2025": "SCANFI_spsCC_jackPine_2025_v2_20260119.tif",
    "other_conifer_2025": "SCANFI_spsCC_otherConiferous_2025_v2_20260119.tif",
    "tamarack_2025": "SCANFI_spsCC_tamarack_2025_v2_20260119.tif",
    "white_red_pine_2025": "SCANFI_spsCC_whiteRedPine_2025_v2_20260119.tif",
}
MRDEM = "https://canelevation-dem.s3.ca-central-1.amazonaws.com/mrdem-30/mrdem-30-dtm.tif"


def tiles() -> list[tuple[str, tuple[int, int, int, int]]]:
    zone = gpd.read_file(ZONE_PATH).to_crs(MODEL_CRS).geometry.union_all()
    left, bottom, right, top = zone.bounds
    x0, y0 = math.floor(left / TILE_M) * TILE_M, math.floor(bottom / TILE_M) * TILE_M
    x1, y1 = math.ceil(right / TILE_M) * TILE_M, math.ceil(top / TILE_M) * TILE_M
    selected = []
    for x in range(x0, x1, TILE_M):
        for y in range(y0, y1, TILE_M):
            bounds = (x, y, x + TILE_M, y + TILE_M)
            if zone.intersects(box(*bounds)):
                selected.append((f"x{x:+08d}_y{y:+08d}", bounds))
    return selected


def remote_window(dataset, bounds, destination):
    if destination.exists():
        return
    transform = Transformer.from_crs(MODEL_CRS, dataset.crs, always_xy=True)
    native_bounds = transform.transform_bounds(*bounds, densify_pts=21)
    window = from_bounds(*native_bounds, transform=dataset.transform)
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial.tif")
    with rasterio.open(temporary, "w", **profile) as output:
        output.write(data.filled(dataset.nodata), 1)
    temporary.replace(destination)


def fetch_fbp(year, tile_id, bounds):
    destination = OUTPUT / "fbp" / year / f"{tile_id}.tif"
    if destination.exists():
        return
    url, coverage, (east, north) = FBP[year]
    left, bottom, right, top = bounds
    response = requests.get(
        url,
        params={
            "service": "WCS",
            "version": "2.0.1",
            "request": "GetCoverage",
            "CoverageId": coverage,
            "format": "image/tiff",
            "subset": [f"{east}({left},{right})", f"{north}({bottom},{top})"],
        },
        timeout=300,
    )
    response.raise_for_status()
    if response.content[:4] not in (b"II*\x00", b"MM\x00*"):
        raise ValueError(f"{year} {tile_id}: source did not return a TIFF")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial.tif")
    temporary.write_bytes(response.content)
    temporary.replace(destination)


def manifest(selected):
    files = sorted(OUTPUT.rglob("*.tif"))
    files += [ZONE_PATH, RESPONSE_AREA_PATH]
    records = []
    for path in files:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        records.append({
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        })
    output = {
        "retrieved_on": date.today().isoformat(),
        "coverage": "Ontario Fire Management Zone union in EPSG:3978; 100 km intersecting tiles",
        "tile_count": len(selected),
        "sources": {
            "fbp_2024": FBP["2024"][0],
            "fbp_2025": "No official public 2025 raster located in the Canadian Open Data catalogue on 2026-10-02",
            "fbp_2026": FBP_2026_RAW,
            "scanfi_v2": SCANFI_BASE,
            "mrdem_30m": MRDEM,
            "fire_management_zone": "https://ws.lioservices.lrc.gov.on.ca/arcgis1071a/rest/services/LIO_OPEN_DATA/LIO_Open09/MapServer/32",
            "fire_response_plan_area": "https://ws.lioservices.lrc.gov.on.ca/arcgis1071a/rest/services/LIO_OPEN_DATA/LIO_Open09/MapServer/33",
        },
        "files": records,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(output, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["fbp_2024", "scanfi", "mrdem", "all"], default="all")
    parser.add_argument("--scanfi-layer", choices=sorted(SCANFI))
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    selected = tiles()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("shard index must be within shard count")
    selected_for_run = selected[args.shard_index::args.shard_count]
    print(f"Ontario tiles: {len(selected)}; this run: {len(selected_for_run)}", flush=True)

    if args.source in ("fbp_2024", "all"):
        years = list(FBP)
        for year in years:
            for index, (tile_id, bounds) in enumerate(selected_for_run, 1):
                fetch_fbp(year, tile_id, bounds)
                print(f"FBP {year}: {index}/{len(selected_for_run)} {tile_id}", flush=True)

    rasterio_env = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    }
    with rasterio.Env(**rasterio_env):
        if args.source in ("scanfi", "all"):
            scanfi_files = SCANFI.items() if args.scanfi_layer is None else [(args.scanfi_layer, SCANFI[args.scanfi_layer])]
            for layer, filename in scanfi_files:
                with rasterio.open(f"{SCANFI_BASE}/{filename}") as dataset:
                    for index, (tile_id, bounds) in enumerate(selected_for_run, 1):
                        destination = OUTPUT / "scanfi_v2" / layer / f"{tile_id}.tif"
                        remote_window(dataset, bounds, destination)
                        print(f"SCANFI {layer}: {index}/{len(selected_for_run)} {tile_id}", flush=True)

        if args.source in ("mrdem", "all"):
            with rasterio.open(MRDEM) as dataset:
                for index, (tile_id, bounds) in enumerate(selected_for_run, 1):
                    destination = OUTPUT / "mrdem_30m" / f"{tile_id}.tif"
                    remote_window(dataset, bounds, destination)
                    print(f"MRDEM: {index}/{len(selected_for_run)} {tile_id}", flush=True)

    if args.shard_count == 1 and args.scanfi_layer is None:
        manifest(selected)
        print(f"Manifest: {OUTPUT / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
