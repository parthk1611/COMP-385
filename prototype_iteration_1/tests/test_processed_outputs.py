import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from scripts.analyze_static_samples import FUEL_GROUP_CODES


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_contains_every_expected_raster():
    manifest = json.loads((ROOT / "data/raw/samples/manifest.json").read_text())

    assert len(manifest["places"]) == 3
    assert len(manifest["files"]) == 39
    assert all((ROOT / item["path"]).is_file() for item in manifest["files"])
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])


def test_processed_feature_table_has_valid_model_grid():
    features = pd.read_parquet(ROOT / "data/processed/static_features_2500m.parquet")
    share_columns = [f"fuel_{group}_share" for group in FUEL_GROUP_CODES]

    assert len(features) == 432
    assert features["cell_id"].nunique() == 432
    assert set(features.groupby("place").size()) == {144}
    assert np.allclose(features[share_columns].sum(axis=1), 1)
    assert features["closure_2020_pct"].between(0, 100).all()
    assert (features["height_2020_m"] >= 0).all()
    assert (features["slope_degrees"] >= 0).all()


def test_scanfi_crs_is_not_mistaken_for_epsg3978():
    scanfi_path = ROOT / "data/raw/samples/red_lake/scanfi_closure_2020.tif"
    fbp_path = ROOT / "data/raw/samples/red_lake/fbp_2024.tif"

    with rasterio.open(scanfi_path) as scanfi, rasterio.open(fbp_path) as fbp:
        assert scanfi.crs != fbp.crs
        assert fbp.crs.to_epsg() == 3978
        assert "latitude_of_origin\",0" in scanfi.crs.to_wkt()
