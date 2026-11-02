import unittest
import numpy as np
import pandas as pd
from scripts.lightning_pilot import completed_window, density_summary


class LightningPilotTests(unittest.TestCase):
    def test_three_hour_interval_crossing_local_midnight_is_excluded(self):
        ends = pd.date_range("2010-05-30T03:00Z", periods=24, freq="3h")
        issue = (
            pd.Timestamp("2010-06-01").tz_localize("America/Toronto").tz_convert("UTC")
        )
        indexes, cutoff = completed_window(ends, issue, 24)
        self.assertEqual(cutoff, pd.Timestamp("2010-06-01T03:00Z"))
        self.assertEqual(len(indexes), 8)
        self.assertTrue((ends[indexes] <= issue).all())

    def test_missing_time_and_naive_issue_are_rejected(self):
        ends = pd.date_range("2010-05-30T03:00Z", periods=24, freq="3h").delete(15)
        with self.assertRaises(ValueError):
            completed_window(ends, "2010-06-01T04:00Z", 24)
        with self.assertRaises(ValueError):
            completed_window(ends, "2010-06-01", 24)

    def test_density_area_weights_preserve_zero_and_missing_coverage(self):
        density, coverage = density_summary([[0, 8], [0, 0]], [100, 80], [0.25, 0.75])
        self.assertAlmostEqual(density, 0.075)
        self.assertEqual(coverage, 1)
        density, coverage = density_summary(
            [[0, np.nan], [0, 0]], [100, 80], [0.25, 0.75]
        )
        self.assertIsNone(density)
        self.assertAlmostEqual(coverage, 0.625)
        self.assertEqual(density_summary([[0, 0]], [100, 80], [0.25, 0.75]), (0, 1))

    def test_partial_geometry_or_fractional_source_count_cannot_be_complete(self):
        self.assertIsNone(density_summary([[1]], [100], [0.9])[0])
        with self.assertRaises(ValueError):
            density_summary([[0.5]], [100], [1])
