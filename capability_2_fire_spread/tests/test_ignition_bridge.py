"""The ignition -> spread bridge: start point, window, burn-scar repair, settings provenance, and a synthetic run.

Everything here runs offline: the fuel, terrain and weather fetches are replaced by synthetic grids.
"""

from __future__ import annotations

import json
import math
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from scripts.spread_modeling import ignition_bridge as BRIDGE
from scripts.spread_modeling import tune_simulator_bridge as TUNING
from scripts.spread_modeling.simulator import Settings


C2 = 2  # boreal spruce in the fuel map's codes
WATER = 102


def synthetic_weather(longitude: float, latitude: float, start_local: pd.Timestamp, hours: float, wind_from: float = 270.0):
    """Ten dry days before the start through the end of the run, steady wind from `wind_from`."""
    times = pd.date_range(start_local.normalize() - pd.Timedelta(days=10), start_local + pd.Timedelta(hours=hours + 30), freq="h")
    offset = BRIDGE.utc_offset_hours(longitude)
    hourly = pd.DataFrame({"time_utc": times - pd.Timedelta(hours=offset), "temp_c": 27.0, "dew_point_c": 5.0, "rh_pct": 25.0, "precip_mm": 0.0, "wind_speed_kmh": 20.0, "wind_direction_deg": wind_from})
    hourly["time_local"] = hourly.time_utc + pd.Timedelta(hours=offset)
    return hourly, BRIDGE.WEATHER.daily_fire_weather(hourly)


class WindowAndStartTests(unittest.TestCase):
    def test_window_snaps_to_the_fuel_lattice_and_contains_the_point(self):
        x, y = 118_948.8, 415_516.5
        window = BRIDGE.window_around(x, y, 10_000)
        self.assertAlmostEqual(((window["west"] - BRIDGE.SOURCE_WEST) / BRIDGE.PIXEL_M) % 1, 0)
        self.assertAlmostEqual(((BRIDGE.SOURCE_NORTH - window["north"]) / BRIDGE.PIXEL_M) % 1, 0)
        self.assertLessEqual(window["west"], x - 10_000)
        self.assertGreaterEqual(window["east"], x + 10_000)
        self.assertLessEqual(window["south"], y - 10_000)
        self.assertGreaterEqual(window["north"], y + 10_000)
        self.assertEqual(window["east"] - window["west"], window["columns"] * BRIDGE.PIXEL_M)

    def test_window_grows_with_run_length_within_limits(self):
        self.assertEqual(BRIDGE.window_half_width_m(1), 10_000)
        self.assertLess(BRIDGE.window_half_width_m(24), BRIDGE.window_half_width_m(48))
        self.assertEqual(BRIDGE.window_half_width_m(72), 35_000)

    def test_local_standard_time_follows_the_spread_dataset(self):
        self.assertEqual(BRIDGE.utc_offset_hours(-93.0), -6)
        self.assertEqual(BRIDGE.utc_offset_hours(-85.0), -5)

    def test_seed_moves_off_water_to_the_nearest_burnable_cell_only_when_close(self):
        fuel = np.full((41, 41), WATER)
        fuel[20, 25] = C2
        self.assertEqual(BRIDGE.seed_cell(fuel, 20, 25), ((20, 25), 0.0))
        seed, shift = BRIDGE.seed_cell(fuel, 20, 20)
        self.assertEqual(seed, (20, 25))
        self.assertAlmostEqual(shift, 5 * BRIDGE.PIXEL_M)
        far = np.full((41, 41), WATER)
        far[0, 0] = C2
        self.assertIsNone(BRIDGE.seed_cell(far, 40, 40)[0])
        self.assertIsNone(BRIDGE.seed_cell(np.full((5, 5), WATER), 2, 2)[0])


class LeakageGuardTests(unittest.TestCase):
    def test_tuning_years_end_before_2019_and_no_split_reads_2019(self):
        # tuning may not reach 2019 or later; no split, tuning or test, may contain 2019
        for first, last, tuning in [(2012, 2019, True), (2012, 2020, True), (2020, 2024, True), (2017, 2024, False), (2019, 2019, False)]:
            with self.subTest(first=first, last=last, tuning=tuning), self.assertRaises(ValueError):
                TUNING.eligible_fires(first, last, tuning=tuning)
        self.assertEqual(TUNING.TUNE_YEARS, (2012, 2016))
        self.assertTrue(all(not first <= 2019 <= last for first, last in TUNING.TEST_PERIODS))
        self.assertTrue(TUNING.eligible_fires(2020, 2024, tuning=False))  # after 2019 is fine for testing only

    def test_ties_go_to_the_higher_iou(self):
        grid = pd.DataFrame({"ros_scale": [1.2, 0.9, 0.8], "flank_scale": [0.15, 0.2, 0.25], "error": [0.37, 0.37, 0.44], "mean_iou": [0.093, 0.095, 0.097]})
        self.assertEqual(tuple(TUNING.choose(grid).iloc[0][["ros_scale", "flank_scale"]]), (0.9, 0.2))

    def test_bridge_refuses_settings_tuned_or_tested_on_2019(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tuning.json"
            for bad in [{"tune_years": [2012, 2019], "test_years": []}, {"tune_years": [2012, 2016], "test_years": [[2017, 2019]]}]:
                path.write_text(json.dumps({**bad, "chosen_ros_scale": 1, "chosen_flank_scale": 1}))
                with self.subTest(bad=bad), mock.patch.object(BRIDGE, "TUNING", path), self.assertRaises(ValueError):
                    BRIDGE.tuned_settings()
            path.write_text(json.dumps({"tune_years": [2012, 2016], "test_years": [[2017, 2018], [2020, 2024]], "chosen_ros_scale": 0.7, "chosen_flank_scale": 0.2}))
            with mock.patch.object(BRIDGE, "TUNING", path):
                settings, provenance = BRIDGE.tuned_settings()
            self.assertEqual((settings.ros_scale, settings.flank_scale, settings.repair_burn_scar), (0.7, 0.2, False))
            self.assertEqual(provenance["tune_years"], [2012, 2016])

    def test_only_scars_of_fires_starting_on_or_after_the_date_are_repaired(self):
        import shapely
        from shapely.geometry import box

        window = {"west": 0.0, "south": 0.0, "east": 9_000.0, "north": 9_000.0}
        records = [
            ("2019-06-01", "before", shapely.to_wkb(box(1_000, 1_000, 2_000, 2_000))),
            ("2019-07-01", "same_day", shapely.to_wkb(box(3_000, 3_000, 4_000, 4_000))),
            ("2021-05-20", "later", shapely.to_wkb(box(5_000, 5_000, 6_000, 6_000))),
            ("2021-05-20", "elsewhere", shapely.to_wkb(box(50_000, 50_000, 51_000, 51_000))),
        ]
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "later_perimeters.pkl").write_bytes(pickle.dumps(records))
            with mock.patch.object(BRIDGE, "CACHE", Path(folder)):
                names, union = BRIDGE.later_perimeters("2019-07-01", window)
        self.assertEqual(sorted(names), ["later", "same_day"])
        self.assertAlmostEqual(union.area, 2_000_000)


class SyntheticRunTests(unittest.TestCase):
    """A uniform spruce forest with a steady west wind: the fire must run east from the start point."""

    def run_bridge(self, fuel_value=C2, hours=6.0, wind_from=270.0):
        def fuel(window):
            return np.full((window["rows"], window["columns"]), fuel_value, dtype=np.int32)

        def terrain(window):
            return np.zeros((window["rows"], window["columns"]), dtype=np.float32)

        patches = [
            mock.patch.object(BRIDGE, "fetch_fuel", fuel),
            mock.patch.object(BRIDGE, "fetch_terrain", terrain),
            mock.patch.object(BRIDGE, "fetch_weather", lambda lon, lat, start, h: synthetic_weather(lon, lat, start, h, wind_from)),
            mock.patch.object(BRIDGE, "later_perimeters", lambda day, window: ([], None)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return BRIDGE.run(-85.0, 49.0, "2019-07-01", 14, hours, Settings(ros_scale=0.8, flank_scale=0.25, repair_burn_scar=False))

    def test_fire_runs_downwind_and_reports_its_assumptions(self):
        result = self.run_bridge()
        self.assertTrue(result["spread"])
        self.assertIn("hindcast", result["mode"])
        self.assertEqual(result["start"]["start_utc"], "2019-07-01 19:00")  # 14:00 EST
        self.assertEqual(result["settings"]["ros_scale"], 0.8)
        summary = result["summary"]
        self.assertGreater(summary["area_ha"], 10)
        self.assertLess(abs(((summary["head_bearing_deg"] - 90) + 180) % 360 - 180), 20)  # wind from the west: head runs east
        cells = pd.DataFrame(result["reached_cells"])
        self.assertTrue((cells.minutes <= 6 * 60).all())
        start_x = result["start"]["x_3978"]
        self.assertGreater(cells.x.max() - start_x, 2 * (start_x - cells.x.min()))  # much further downwind than upwind

    def test_reached_cells_are_on_the_375_m_satellite_grid(self):
        cells = pd.DataFrame(self.run_bridge()["reached_cells"])
        self.assertTrue((cells.x % 375 == 0).all() and (cells.y % 375 == 0).all())
        self.assertFalse(cells.duplicated(["x", "y"]).any())

    def test_hourly_area_and_wind_drive_the_demo_animation(self):
        result = self.run_bridge(hours=6)
        by_hour = result["area_by_hour_ha"]
        self.assertEqual(len(by_hour), 6)
        self.assertEqual(by_hour, sorted(by_hour))  # burned area never shrinks
        self.assertAlmostEqual(by_hour[-1], result["summary"]["area_ha"], places=1)
        self.assertEqual([w["hour"] for w in result["hourly_weather"]], list(range(6)))
        self.assertEqual({w["wind_from_deg"] for w in result["hourly_weather"]}, {270})
        self.assertIn("grid_convergence_deg", result["start"])
        self.assertEqual(self.run_bridge(fuel_value=WATER)["area_by_hour_ha"], [0.0] * 6)  # no fuel: nothing burns, every hour

    def test_longer_runs_burn_more(self):
        self.assertGreater(self.run_bridge(hours=12)["summary"]["area_ha"], self.run_bridge(hours=6)["summary"]["area_ha"])

    def test_no_burnable_fuel_gives_no_spread_with_a_reason(self):
        result = self.run_bridge(fuel_value=WATER)
        self.assertFalse(result["spread"])
        self.assertEqual(result["reached_cells"], [])
        self.assertIn("No burnable fuel", result["message"])

    def test_run_length_and_start_hour_are_validated(self):
        for hours, hour in [(0, 14), (73, 14), (24, 24), (24, -1)]:
            with self.subTest(hours=hours, hour=hour), self.assertRaises(ValueError):
                BRIDGE.run(-85.0, 49.0, "2019-07-01", hour, hours, Settings())


if __name__ == "__main__":
    unittest.main()
