import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from scripts.moisture_state import CODES, coverage, digest, hr_seed, qualify, sample_codes
from scripts.hrdps_live_weather import validate_seed


def candidate():
    return {"ffmc": 85., "dmc": 6., "dc": 15., "date": "2026-11-05",
            "state_kind": "observation_based_analysis", "time_convention": "local_standard_noon",
            "quality_verified": True, "startup_lineage_verified": True, "validation_passed": True,
            "noon_time_utc": "2026-11-05T17:00:00Z", "available_at_utc": "2026-11-05T22:00:00Z",
            "source_sha256": "a" * 64, "metadata_sha256": "b" * 64, "validation_sha256": "c" * 64}


ISSUE = "2026-11-06T00:00:00Z"
NOON = "2026-11-05T17:00:00Z"


@pytest.mark.parametrize("field,value", [
    ("time_convention", "solar_noon"), ("date", None), ("noon_time_utc", "2026-11-05T18:00:00Z"),
    ("available_at_utc", "2026-11-06T01:00:00Z"), ("startup_lineage_verified", False),
    ("quality_verified", False), ("validation_passed", False), ("ffmc", 102.),
    ("dmc", float("nan")), ("source_sha256", "bad"), ("state_kind", "forecast_update"),
])
def test_unverified_and_incompatible_candidates_cannot_become_seeds(field, value):
    record = copy.deepcopy(candidate())
    record[field] = value
    record["trusted"] = True
    assert qualify(record, ISSUE, NOON)
    with pytest.raises(ValueError):
        hr_seed(record, ISSUE, NOON)


def test_verified_contract_connects_to_existing_hrdps_validator():
    # Synthetic contract checks interoperability; it is not accepted real-source evidence.
    record = hr_seed(candidate(), ISSUE, NOON)
    result = validate_seed(record, "2026-11-05", expected_noon=pd.Timestamp(NOON), issue=pd.Timestamp(ISSUE))
    assert result == {"ffmc": 85., "dmc": 6., "dc": 15.}


def test_naive_issue_is_rejected():
    with pytest.raises(ValueError):
        qualify(candidate(), "2026-11-06", NOON)


def test_raster_mapping_retains_nodata_and_invalid_values(tmp_path):
    paths = {}
    for code in CODES:
        path = tmp_path / (code + ".tif")
        values = np.array([[85, -9999], [102 if code == "ffmc" else 6, 10]], dtype="float32")
        with rasterio.open(path, "w", driver="GTiff", height=2, width=2, count=1,
                           dtype="float32", crs="EPSG:4326", transform=from_origin(-90, 50, 1, 1), nodata=-9999) as ds:
            ds.write(values, 1)
        paths[code] = path
    grid = pd.DataFrame({"centroid_longitude": [-89.5, -88.5, -89.5, -100],
                         "centroid_latitude": [49.5, 49.5, 48.5, 60]})
    mapped, metadata = sample_codes(paths, grid)
    assert mapped.codes_present.tolist() == [True, False, False, False]
    assert metadata["ffmc"]["tags"].get("DATE") is None


def test_changed_coverage_is_rejected(tmp_path):
    folder = tmp_path / "data/processed/moisture_state"
    folder.mkdir(parents=True)
    payload = folder / "coverage.json"
    payload.write_text('{"accepted_cells":0}')
    (folder / "latest.json").write_text(json.dumps({"path": str(payload), "sha256": digest(payload)}))
    assert coverage(tmp_path)["accepted_cells"] == 0
    payload.write_text('{"accepted_cells":999}')
    with pytest.raises(OSError):
        coverage(tmp_path)
