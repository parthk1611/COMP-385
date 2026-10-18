import numpy as np

from scripts.analyze_static_samples import (
    CELLS_PER_SIDE,
    FUEL_GROUP_CODES,
    PIXELS_PER_CELL,
    block_mean,
    dominant_code,
    fuel_cell_features,
    fuel_group,
)
from scripts.fetch_static_samples import PLACES, sample_bounds


def test_sample_bounds_are_exact_30_km_squares_aligned_to_model_grid():
    for longitude, latitude in PLACES.values():
        left, bottom, right, top = sample_bounds(longitude, latitude)
        assert right - left == 30_000
        assert top - bottom == 30_000
        assert left % 2_500 == 0
        assert bottom % 2_500 == 0


def test_block_mean_aggregates_to_twelve_by_twelve_cells():
    size = CELLS_PER_SIDE * PIXELS_PER_CELL
    array = np.arange(size * size, dtype=float).reshape(size, size)
    result = block_mean(array)

    assert result.shape == (CELLS_PER_SIDE, CELLS_PER_SIDE)
    assert result[0, 0] == np.mean(array[:PIXELS_PER_CELL, :PIXELS_PER_CELL])
    assert result[-1, -1] == np.mean(array[-PIXELS_PER_CELL:, -PIXELS_PER_CELL:])


def test_fuel_code_mapping_and_dominant_code():
    assert fuel_group(2) == "conifer"
    assert fuel_group(650) == "mixedwood"
    assert fuel_group(102) == "water"
    assert fuel_group(999) == "unknown"
    assert dominant_code(np.array([[2, 2], [102, np.nan]])) == 2


def test_fuel_shares_partition_every_valid_pixel():
    size = CELLS_PER_SIDE * PIXELS_PER_CELL
    array = np.full((size, size), 2.0)
    array[:PIXELS_PER_CELL, : PIXELS_PER_CELL // 2] = 102
    features = fuel_cell_features(array)

    assert len(features) == CELLS_PER_SIDE**2
    for record in features:
        total = sum(record[f"fuel_{group}_share"] for group in FUEL_GROUP_CODES)
        assert np.isclose(total, 1)
    assert features[0]["fuel_conifer_share"] > 0
    assert features[0]["fuel_water_share"] > 0
