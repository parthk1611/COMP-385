from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from scripts.prepare_historical_weather_v2 import FIELDS, daily_features, load_observations, prior_week_rain


class HistoricalWeatherV2Test(unittest.TestCase):
    def grid(self):
        return pd.DataFrame({'grid_id': ['g'], 'centroid_longitude': [0.], 'centroid_latitude': [0.]})

    def records(self, longitudes):
        n = len(longitudes)
        frame = pd.DataFrame({key: np.full(n, 10.) for key in FIELDS})
        frame['station_key'] = [f's{i}' for i in range(n)]
        frame['lon'], frame['lat'] = longitudes, 0.
        frame['opts'], frame['calcstatus'] = '', 0.
        return frame

    def test_daily_available_fifth_station_replaces_four_inactive_candidates(self):
        records = self.records([.01, .02, .03, .04, .05])
        records.loc[:3, 'fwi'] = np.nan
        frame, _ = daily_features(self.grid(), records)
        self.assertEqual(frame.cwfis_station_count.iloc[0], 1)
        self.assertEqual(frame.cwfis_missing.iloc[0], 0)
        self.assertAlmostEqual(frame.cwfis_fwi.iloc[0], 10.)

    def test_radius_does_not_fill_from_a_remote_station(self):
        frame, coverage = daily_features(self.grid(), self.records([5.]))
        self.assertEqual(frame.cwfis_missing.iloc[0], 1)
        self.assertTrue(np.isnan(frame.cwfis_fwi.iloc[0]))
        self.assertEqual(coverage['300'], 0)

    def test_inverse_distance_weighting_uses_variable_specific_available_values(self):
        records = self.records([.01, .02])
        records['temp'] = [10., 30.]
        records['rh'] = [50., 999.]
        frame, _ = daily_features(self.grid(), records)
        self.assertAlmostEqual(frame.cwfis_temp_c.iloc[0], 14., places=5)
        self.assertAlmostEqual(frame.cwfis_rh_pct.iloc[0], 50.)

    def test_no_valid_fwi_keeps_weather_unknown(self):
        records = self.records([.01]); records['fwi'] = np.inf
        frame, _ = daily_features(self.grid(), records)
        self.assertEqual(frame.cwfis_station_count.iloc[0], 0)
        self.assertTrue(np.isnan(frame.cwfis_precip_mm.iloc[0]))

    def test_station_input_order_does_not_change_scores(self):
        records = self.records([.01, .03, .02, .04, .05])
        records['fwi'] = [1., 2., 3., 4., 5.]
        a, _ = daily_features(self.grid(), records)
        b, _ = daily_features(self.grid(), records.iloc[::-1])
        pd.testing.assert_frame_equal(a, b)

    def test_seven_day_total_does_not_treat_unknown_rain_as_zero(self):
        issue = date(2017, 5, 8)
        window = [(issue - timedelta(days=i), np.array([1., 1.])) for i in range(7, 0, -1)]
        window[2][1][1] = np.nan
        total, coverage = prior_week_rain(window, issue)
        np.testing.assert_allclose(total, [7., np.nan], equal_nan=True)
        np.testing.assert_array_equal(coverage, [7, 6])

    def test_same_day_or_gapped_rain_window_is_rejected(self):
        issue = date(2017, 5, 8)
        window = [(issue - timedelta(days=i), np.array([1.])) for i in range(6, -1, -1)]
        with self.assertRaises(ValueError):
            prior_week_rain(window, issue)

    def test_source_without_requested_dates_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            records = self.records([.01])
            records['aes'], records['wmo'] = '1', ''
            records['rep_date'] = '2019-05-01 12:00:00'
            path = Path(directory) / 'source.csv.bz2'
            records.to_csv(path, compression='bz2', index=False)
            with self.assertRaisesRegex(ValueError, 'No station observations'):
                load_observations(path, {'2017-05-01'}, self.grid())

    def test_overlapping_source_extract_keeps_first_valid_fwi(self):
        with tempfile.TemporaryDirectory() as directory:
            records = self.records([.01, .01, .01, .01])
            records['aes'], records['wmo'] = '1', ''
            records['rep_date'] = '2017-05-01 12:00:00'
            records['fwi'] = [np.nan, 5., 9., 7.]
            records.loc[3, 'rep_date'] = '2019-05-01 12:00:00'
            path = Path(directory) / 'source.csv.bz2'
            records.to_csv(path, compression='bz2', index=False)
            result, profile = load_observations(path, {'2017-05-01'}, self.grid())
            self.assertEqual(len(result), 1)
            self.assertEqual(result.fwi.iloc[0], 5.)
            self.assertEqual(profile['duplicate_date_station_rows'], 2)


if __name__ == '__main__':
    unittest.main()
