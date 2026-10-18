from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.prepare_selected_weather import deaccumulate_era5, daily_weather, humidity, wind


class SelectedWeatherTest(unittest.TestCase):
    def test_accumulation_crosses_midnight_and_resets_at_one_utc(self):
        times = pd.date_range("2025-01-31 23:00", periods=4, freq="h", tz="UTC")
        rain = deaccumulate_era5(times, np.array([.010, .012, .001, .004]))
        np.testing.assert_allclose(rain, [np.nan, 2, 1, 3], equal_nan=True)

    def test_missing_hour_is_not_a_one_hour_rainfall_total(self):
        times = pd.to_datetime(["2025-01-01 01:00Z", "2025-01-01 03:00Z", "2025-01-01 04:00Z"])
        np.testing.assert_allclose(deaccumulate_era5(times, np.array([.001, .004, .005])), [1, np.nan, 1], equal_nan=True)

    def test_negative_accumulation_change_remains_unknown(self):
        times = pd.date_range("2025-01-01 01:00", periods=3, freq="h", tz="UTC")
        np.testing.assert_allclose(deaccumulate_era5(times, np.array([.002, .001, .003])), [2, np.nan, 2], equal_nan=True)

    def test_duplicate_times_are_rejected(self):
        times = pd.to_datetime(["2025-01-01 01:00Z"] * 2)
        with self.assertRaises(ValueError):
            deaccumulate_era5(times, np.array([0., 0.]))

    def test_equal_temperature_and_dewpoint_is_saturated(self):
        np.testing.assert_allclose(humidity(np.array([273.15, 293.15]), np.array([273.15, 293.15])), [100, 100])

    def test_component_units_and_direction(self):
        speed, direction = wind(np.array([1., 0., 0.]), np.array([0., -1., 0.]))
        np.testing.assert_allclose(speed, [3.6, 3.6, 0.])
        np.testing.assert_allclose(direction, [270., 0., np.nan], equal_nan=True)

    def hourly(self):
        times = pd.date_range("2025-04-01", periods=24 * 6, freq="h", tz="UTC")
        return pd.DataFrame({"time_utc": times, "temp_c": 20., "rh_pct": 40., "wind_kmh": 10., "precip_mm": 0.})

    def test_noon_rain_excludes_the_following_hour(self):
        hourly = self.hourly()
        hourly.loc[hourly.time_utc == "2025-04-03 18:00Z", "precip_mm"] = 9.
        result = daily_weather(hourly, -5, "2025-04-02")
        self.assertEqual(result.loc[result.date == "2025-04-03", "rain_24h_mm"].iloc[0], 0.)
        self.assertEqual(result.loc[result.date == "2025-04-04", "rain_24h_mm"].iloc[0], 9.)

    def test_fwi_waits_for_declared_startup_and_breaks_after_gap(self):
        hourly = self.hourly()
        hourly.loc[hourly.time_utc == "2025-04-04 10:00Z", "precip_mm"] = np.nan
        result = daily_weather(hourly, -5, "2025-04-02")
        self.assertTrue(result.loc[result.date == "2025-04-01", "fwi"].isna().all())
        self.assertTrue(result.loc[result.date == "2025-04-03", "fwi"].notna().all())
        self.assertTrue(result.loc[result.date >= "2025-04-04", "fwi"].isna().all())

    def test_missing_noon_cannot_silently_advance_fwi_state(self):
        hourly = self.hourly()
        hourly = hourly.loc[hourly.time_utc != "2025-04-03 17:00Z"]
        result = daily_weather(hourly, -5, "2025-04-02")
        self.assertFalse((result.date == "2025-04-03").any())
        self.assertTrue(result.loc[result.date >= "2025-04-04", "fwi"].isna().all())

    def test_standard_noon_does_not_follow_summer_dst(self):
        hourly = self.hourly()
        eastern = daily_weather(hourly, -5, "2025-04-02")
        central = daily_weather(hourly, -6, "2025-04-02")
        self.assertEqual(set(eastern.noon_time_utc.dt.hour), {17})
        self.assertEqual(set(central.noon_time_utc.dt.hour), {18})


if __name__ == "__main__":
    unittest.main()
