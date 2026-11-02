import unittest

import numpy as np
import pandas as pd

from scripts.lightning_experiment import capacity_curve, choose_candidate, lightning_features, rolling_density


class LightningExperimentTests(unittest.TestCase):
    def test_future_bin_is_excluded_and_missing_coverage_is_not_zero(self):
        ends = pd.date_range("2014-06-01", periods=10, freq="3h", tz="UTC")
        density = np.ones((10, 2))
        density[-1] = 999
        coverage = np.ones((10, 2))
        coverage[2, 1] = .5
        issue = pd.DatetimeIndex([ends[8] + pd.Timedelta(hours=1)])
        values, fraction, cutoffs = rolling_density(density, coverage, ends, issue, 24)
        self.assertEqual(values[0, 0], 8)
        self.assertTrue(np.isnan(values[0, 1]))
        self.assertLess(fraction[0, 1], 1)
        self.assertEqual(cutoffs[0], ends[8])

    def test_incomplete_clock_is_rejected(self):
        ends = pd.date_range("2014-06-01", periods=10, freq="3h", tz="UTC").delete(4)
        with self.assertRaises(ValueError):
            rolling_density(np.ones((9, 1)), np.ones((9, 1)), ends, pd.DatetimeIndex([ends[-1]]), 24)

    def test_capacity_counts_hits_misses_and_false_positives(self):
        frame = pd.DataFrame({"grid_id": [f"g{i}" for i in range(100)], "ignition_date": "2017-06-01",
                              "ignition": [1, 0, 0, 0, 1] + [0] * 95})
        curves, ranks = capacity_curve(frame, np.arange(100, 0, -1) / 101)
        self.assertEqual(curves[0]["hits"], 1)
        self.assertEqual(curves[0]["misses"], 1)
        self.assertEqual(curves[2]["hits"], 2)
        self.assertEqual(curves[2]["false_positives"], 3)
        reordered, _ = capacity_curve(frame.sample(frac=1, random_state=1), (101 - frame.sample(frac=1, random_state=1).grid_id.str[1:].astype(int).to_numpy()) / 102)
        self.assertEqual(reordered[2]["hits"], 2)
        self.assertEqual(set(ranks["rank"]), set(range(1, 101)))

    def test_selection_cannot_trade_away_fixed_budget_recall(self):
        records = [{"protocol": "inner_spatial", "candidate": name, "year": year,
                    "average_precision": .02 if name != "reference" else .01,
                    "daily_budget_recall": .01 if name != "reference" else .02}
                   for year in (2014, 2015) for name in ("reference", "lightning_24h", "lightning_24h_168h")]
        self.assertEqual(choose_candidate(records, "inner_spatial"), "reference")
        self.assertNotIn("ignition", lightning_features("lightning_24h_168h"))
        with self.assertRaises(ValueError):
            lightning_features("same_day_lightning")


if __name__ == "__main__":
    unittest.main()
