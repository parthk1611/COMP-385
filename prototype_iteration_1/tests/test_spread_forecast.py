from math import inf

import numpy as np
import pandas as pd
import pytest

from scripts.spread_forecast import overlap_score, satellite_target, simulator, weather_for_model
from scripts.spread_forecast_weather import gfs_index


def test_hourly_crossing_keeps_progress_when_weather_changes():
    rates = lambda hour: [[1.0 if hour == 0 else 2.0]]
    # 60 m in the first hour, then the remaining 30 m in 15 minutes.
    assert simulator.hourly_crossing(0, 180, 0, rates, 0, 0, 0, [], 45, 1) == 75
    assert simulator.hourly_crossing(0, 74, 0, rates, 0, 0, 0, [], 45, 1) == inf


def test_hourly_crossing_uses_both_fuels_and_can_resume_after_a_zero_rate():
    rates = lambda hour: [[0.0], [0.0], [0.0]] if hour == 0 else [[1.0], [2.0], [1.0]]
    assert simulator.hourly_crossing(0, 180, 0, rates, 0, 0, 1, [2], 40, 1) == 120
    assert simulator.Settings().integrate_hourly_travel is False


def test_gfs_index_uses_cycle_total_when_first_subtotal_is_identical():
    run = pd.Timestamp("2024-07-11T00:00Z")
    fields = [("TMP", "2 m above ground", "6 hour fcst"),
              ("RH", "2 m above ground", "6 hour fcst"),
              ("UGRD", "10 m above ground", "6 hour fcst"),
              ("VGRD", "10 m above ground", "6 hour fcst"),
              ("APCP", "surface", "0-6 hour acc fcst"),
              ("APCP", "surface", "0-6 hour acc fcst"),
              ("END", "surface", "6 hour fcst")]
    index = "\n".join(f"{i + 1}:{i * 100}:d=2024071100:{element}:{level}:{when}:"
                      for i, (element, level, when) in enumerate(fields))
    assert gfs_index(index, run, 6)["APCP"] == (500, 599)
    with pytest.raises(ValueError, match="different cycle"):
        gfs_index(index, run + pd.Timedelta(hours=6), 6)


def test_satellite_comparison_uses_new_detections_after_the_seed():
    times = pd.to_datetime(["2024-07-11T00:00Z", "2024-07-11T07:00Z", "2024-07-11T07:00Z",
                            "2024-07-11T09:00Z"], utc=True)
    detections = pd.DataFrame({"time_utc": times, "x": [10, 15, 400, 800], "y": [0, 0, 0, 0]})
    stamp, new, old = satellite_target(detections, times[0], 6, 12, None)
    assert stamp == times[1] and old == {(0, 0)} and new == {(1, 0)}
    score = overlap_score({(1, 0), (1, 1)}, new, (187.5, 187.5))
    assert score["recall"] == 1 and score["precision"] == .5 and score["iou"] == .5
    assert overlap_score(set(), new, (187.5, 187.5))["direction_error_deg"] is None


def test_forecast_rain_can_wet_fine_fuel_without_reseeding_buildup():
    data = pd.DataFrame({"time_utc": pd.date_range("2024-07-11T00:00Z", periods=2, freq="h"),
                         "temp_c": [20.0, 20.0], "rh_pct": [40.0, 90.0], "wind_speed_kmh": [12.0, 12.0],
                         "precip_mm": [0.0, 8.0]})
    result = weather_for_model(data, {"ffmc": 85.0, "bui": 30.0}, -5)
    assert result.ffmc.iloc[1] < result.ffmc.iloc[0] and np.all(result.bui == 30.0)


def test_outlook_uses_fresh_ontario_day_and_rejects_archived_dates():
    from scripts.spread_outlook import scenario_request
    now = pd.Timestamp("2026-11-19T02:32Z")
    query = {"incident": ["32655"], "date": ["2026-11-18"]}
    _, day, issue = scenario_request(query, now)
    assert day.isoformat() == "2026-11-18" and issue == pd.Timestamp("2026-11-19T02:30Z")
    assert scenario_request({"date": query["date"]}, now) == (None, day, issue)
    query["date"] = ["2026-11-24"]
    _, _, issue = scenario_request(query, now)
    assert issue == pd.Timestamp("2026-11-24T17:00Z")
    for outside in ("2026-11-17", "2026-11-25"):
        query["date"] = [outside]
        with pytest.raises(ValueError, match="seven outlook days"):
            scenario_request(query, now)


def test_ranked_start_uses_selected_day_and_skips_incomplete_cells(monkeypatch, tmp_path):
    from scripts import spread_outlook

    now = pd.Timestamp("2026-11-19T14:30Z")
    _, day, issue = spread_outlook.scenario_request({"date": ["2026-11-21"]}, now)
    rows = pd.DataFrame([
        {"grid_id": f"cell-{rank}", "longitude": -85.0 - rank, "latitude": 49.0,
         "probability": 0.04 / rank, "method": "weather_plus_history_research"}
        for rank in range(1, 5)
    ])
    checked = []

    def daily_outlook(workspace, query, *, now):
        assert workspace == tmp_path and query == {"date": ["2026-11-21"], "view": ["day"]}
        assert now == pd.Timestamp("2026-11-19T14:30Z")
        return {}, rows

    def landscape(workspace, lon, lat):
        checked.append(lon)
        if lon == -86.0:
            raise ValueError("Insufficient terrain coverage")
        origin = spread_outlook.spread.PROJECT.transform(lon, lat)
        return "ground", origin, {"seed_snap_m": 0}

    def forecast(lon, lat, start, issued):
        assert start == issue and issued == now
        if round(lon) == -87:
            raise ValueError("Incomplete hourly weather")
        return pd.DataFrame({"wind_direction_deg": [270]}), "received", now.date()

    monkeypatch.setattr(spread_outlook, "ignition_outlook", daily_outlook)
    monkeypatch.setattr(spread_outlook, "landscape_at", landscape)
    monkeypatch.setattr(spread_outlook, "forecast_at", forecast)
    record, ground, (weather, _, _) = spread_outlook.ranked_start(tmp_path, day, issue, now)
    assert checked == [-86.0, -87.0, -88.0]
    assert record["name"] == "cell-3"
    assert record["ignition_risk"]["rank"] == 3 and ground[0] == "ground"
    assert weather.wind_direction_deg.tolist() == [270]


def test_outlook_carries_moisture_forward_and_requires_each_hour():
    from scripts.spread_outlook import roll_moisture
    seed = {"ffmc": 84., "dmc": 12., "dc": 100.}
    noon = pd.Timestamp("2026-11-17T17:00Z")
    issue = noon + pd.Timedelta(days=2)
    times = pd.date_range(noon, issue + pd.Timedelta(hours=6), freq="h")
    data = pd.DataFrame({"temp_c": 20., "rh_pct": 45., "wind_speed_kmh": 20.,
                         "wind_direction_deg": 270., "precip_mm": 0., "snow_depth": 0.}, index=times)
    result = roll_moisture(data, seed, noon, issue, -5)
    assert result.time_utc.iloc[0] == issue and len(result) == 7
    assert result.bui.iloc[0] > 0 and result.ffmc.iloc[0] != seed["ffmc"]
    with pytest.raises(ValueError, match="Complete hourly weather"):
        roll_moisture(data.drop(times[2]), seed, noon, issue, -5)
