from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds, transform as window_transform
from shapely.geometry import box

from scripts.fetch_ontario_static import OUTPUT, ROOT, ZONE_PATH, tiles


STEP = 10
LAYERS = {
    "fbp_2024": OUTPUT / "fbp" / "2024",
    "scanfi_closure_2025": OUTPUT / "scanfi_v2" / "closure_2025",
    "scanfi_height_2025": OUTPUT / "scanfi_v2" / "height_2025",
    "scanfi_balsam_fir_2025": OUTPUT / "scanfi_v2" / "balsam_fir_2025",
    "scanfi_black_spruce_2025": OUTPUT / "scanfi_v2" / "black_spruce_2025",
    "scanfi_broadleaf_2025": OUTPUT / "scanfi_v2" / "broadleaf_2025",
    "scanfi_jack_pine_2025": OUTPUT / "scanfi_v2" / "jack_pine_2025",
    "scanfi_other_conifer_2025": OUTPUT / "scanfi_v2" / "other_conifer_2025",
    "scanfi_tamarack_2025": OUTPUT / "scanfi_v2" / "tamarack_2025",
    "scanfi_white_red_pine_2025": OUTPUT / "scanfi_v2" / "white_red_pine_2025",
    "mrdem_30m": OUTPUT / "mrdem_30m",
}
FBP_2026 = OUTPUT / "fbp" / "2026" / "FBP_FuelTypes_Canada_2026_30m.tif"


def sampled_data(dataset, zone, window=None):
    if window is None:
        window = rasterio.windows.Window(0, 0, dataset.width, dataset.height)
    height = max(1, round(window.height / STEP))
    width = max(1, round(window.width / STEP))
    data = dataset.read(1, window=window, out_shape=(height, width), resampling=Resampling.nearest)
    transform = window_transform(window, dataset.transform) * dataset.transform.scale(
        window.width / width, window.height / height
    )
    footprint = zone.intersection(box(*rasterio.transform.array_bounds(height, width, transform)))
    inside = geometry_mask([footprint], out_shape=data.shape, transform=transform, invert=True)
    return data, inside, dataset.nodata


def main():
    selected = tiles()
    zones = gpd.read_file(ZONE_PATH)
    model_zone = zones.to_crs("EPSG:3978").geometry.union_all()
    metrics = {}
    for name, directory in LAYERS.items():
        with rasterio.open(directory / f"{selected[0][0]}.tif") as first_dataset:
            zone = gpd.GeoSeries([model_zone], crs="EPSG:3978").to_crs(first_dataset.crs).iloc[0]
        counts = Counter()
        inside_count = valid_count = nonzero_count = 0
        total = total_sq = 0.0
        minimum, maximum = float("inf"), float("-inf")
        for tile_id, _ in selected:
            with rasterio.open(directory / f"{tile_id}.tif") as dataset:
                data, inside, nodata = sampled_data(dataset, zone)
                valid = inside & np.isfinite(data) & (data != nodata)
                values = data[valid].astype("float64")
                inside_count += int(inside.sum())
                valid_count += values.size
                if not values.size:
                    continue
                nonzero_count += int(np.count_nonzero(values))
                total += float(values.sum())
                total_sq += float(np.square(values).sum())
                minimum = min(minimum, float(values.min()))
                maximum = max(maximum, float(values.max()))
                if name != "mrdem_30m":
                    unique, frequency = np.unique(values.astype("int32"), return_counts=True)
                    counts.update(dict(zip(unique.tolist(), frequency.tolist())))
        mean = total / valid_count if valid_count else None
        metrics[name] = {
            "tiles": len(selected),
            "sampled_mask_pixels": inside_count,
            "sampled_valid_pixels": valid_count,
            "valid_pct": round(valid_count / inside_count * 100, 3),
            "nonzero_pct_of_valid": round(nonzero_count / valid_count * 100, 3) if valid_count else None,
            "mean": round(mean, 3) if mean is not None else None,
            "std": round(max(0, total_sq / valid_count - mean * mean) ** 0.5, 3) if mean is not None else None,
            "min": minimum if valid_count else None,
            "max": maximum if valid_count else None,
            "counts": {str(k): v for k, v in sorted(counts.items())} if counts else None,
        }
        print(name, metrics[name]["valid_pct"], metrics[name]["mean"], flush=True)

    counts = Counter()
    inside_count = valid_count = 0
    with rasterio.open(FBP_2026) as dataset:
        for _, bounds in selected:
            window = from_bounds(*bounds, transform=dataset.transform).round_offsets().round_lengths()
            data, inside, nodata = sampled_data(dataset, model_zone, window)
            valid = inside & (data != nodata)
            values = data[valid]
            inside_count += int(inside.sum())
            valid_count += values.size
            unique, frequency = np.unique(values, return_counts=True)
            counts.update(dict(zip(unique.tolist(), frequency.tolist())))
    metrics["fbp_2026"] = {
        "tiles": len(selected),
        "sampled_mask_pixels": inside_count,
        "sampled_valid_pixels": valid_count,
        "valid_pct": round(valid_count / inside_count * 100, 3),
        "counts": {str(k): v for k, v in sorted(counts.items())},
    }
    output = {
        "scope": "Ontario historical FMZ union; systematic approximately 300 m sample of native 30 m rasters",
        "sampling_stride_native_pixels": STEP,
        "layers": metrics,
    }
    path = ROOT / "data" / "processed" / "ontario_static_sample_profile.json"
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(path, flush=True)


if __name__ == "__main__":
    main()
