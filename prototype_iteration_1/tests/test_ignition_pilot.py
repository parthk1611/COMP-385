import pandas as pd
import pytest
import json

from scripts.fetch_era5_pilot import monthly_requests
from scripts.fetch_static_samples import ROOT, sha256
from scripts.prepare_ignition_pilot import BOUNDS, cell_for_point, fire_events, make_cell_days


def event(ident="THU5", fire_type="IFR", date="2025-05-10"):
    left, _, _, top = BOUNDS
    return {"attributes": {"OGF_ID": 1, "FIRE_DISTURBANCE_AREA_IDENT": ident,
            "FIRE_YEAR": 2025, "FIRE_TYPE_CODE": fire_type,
            "FIRE_START_DATE": int(pd.Timestamp(date, tz="UTC").timestamp() * 1000)},
            "geometry": {"x": left + 1250, "y": top - 1250}}


def test_date_only_utc_serialization_does_not_shift_calendar_day():
    assert fire_events([event()])["date"].iloc[0] == "2025-05-10"


def test_include_both_wildfire_types_exclude_prescribed_burns():
    events = fire_events([event("A"), event("B", "OFR"), event("C", "PB")])
    assert set(events["fire_type"]) == {"IFR", "OFR"}
    assert len(events) == 2


def test_missing_date_and_duplicates_stop_label_creation():
    missing = event()
    missing["attributes"]["FIRE_START_DATE"] = None
    with pytest.raises(ValueError, match="no start date"):
        fire_events([missing])
    with pytest.raises(ValueError, match="Duplicate event"):
        fire_events([event(), event()])


def test_grid_edges_have_single_deterministic_assignment():
    left, bottom, right, top = BOUNDS
    assert cell_for_point(left, top)[0] == "thunder_bay_00_00"
    assert cell_for_point(left + 2500, top - 2500)[0] == "thunder_bay_01_01"
    assert cell_for_point(right, top) is None
    assert cell_for_point(left, bottom) is None


def test_candidates_outside_projected_grid_do_not_label_inside_cells():
    outside = event()
    outside["geometry"]["y"] = BOUNDS[3] + 934
    assert fire_events([outside]).empty


def test_multiple_events_preserve_count_without_duplicate_cell_days():
    static = pd.DataFrame({"cell_id": ["thunder_bay_00_00", "thunder_bay_00_01"]})
    frame = make_cell_days(static, fire_events([event("A"), event("B")]))
    assert len(frame) == 428
    positive = frame.loc[frame["reported_fire_start"] == 1]
    assert len(positive) == 1
    assert positive["recorded_fire_count"].iloc[0] == 2
    assert positive["window_start_utc"].iloc[0] == pd.Timestamp("2025-05-10T05:00:00Z")
    assert positive["window_end_utc"].iloc[0] == pd.Timestamp("2025-05-11T05:00:00Z")
    assert not frame.duplicated(["cell_id", "date"]).any()
    assert not {"cause", "final_size_ha", "FIRE_WEATHER_INDEX", "FIRE_RESPONSE_OBJ_CODE"}.intersection(frame)


def test_empty_fire_snapshot_produces_explicit_archive_negative_labels():
    frame = make_cell_days(pd.DataFrame({"cell_id": ["thunder_bay_00_00"]}), fire_events([]))
    assert len(frame) == 214
    assert frame["reported_fire_start"].sum() == 0


def test_weather_requests_cover_calendar_days_and_all_hourly_variables():
    requests = monthly_requests()
    assert len(requests) == 11
    assert len(requests[1]["day"]) == 28
    assert requests[-1]["month"] == ["11"]
    assert len(requests[0]["time"]) == 24
    assert len(requests[0]["variable"]) == 5
    north, west, south, east = requests[0]["area"]
    assert north > south and east > west


def test_saved_pilot_matches_labels_and_selected_vintages():
    processed = ROOT / "data/processed"
    frame = pd.read_parquet(processed / "thunder_bay_2025_cell_days.parquet")
    summary = json.loads((processed / "ignition_pilot_summary.json").read_text())
    assert len(frame) == summary["cell_days"] == 144 * 214
    assert not frame.duplicated(["cell_id", "date"]).any()
    assert frame["reported_fire_start"].sum() == summary["positive_cell_days"]
    assert frame["recorded_fire_count"].sum() == summary["eligible_events"]
    assert set(frame["scanfi_version"]) == {"v1.2_2020"}
    assert set(frame["fbp_version"]) == {"2024"}
    assert not any("2025_pct" in c or "1985" in c for c in frame)
    assert not {"cause", "final_size_ha", "FIRE_WEATHER_INDEX", "FIRE_RESPONSE_OBJ_CODE"}.intersection(frame)
    assert frame["percent_conifer"].dropna().between(0, 100).all()
    assert frame["closure_2020_pct"].between(0, 100).all()
    assert not summary["training_ready"] and not summary["weather_downloaded"]
    assert set(summary["available_predictor_columns"]).issubset(frame.columns)
    assert not {"reported_fire_start", "recorded_fire_count", "window_end_utc"}.intersection(summary["available_predictor_columns"])


def test_saved_acquisition_manifest_matches_input_bytes():
    manifest = json.loads((ROOT / "data/raw/ignition_pilot/manifest.json").read_text())
    assert len(manifest["scanfi_sources"]) == 11
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        assert path.stat().st_size == entry["bytes"]
        assert sha256(path) == entry["sha256"]
