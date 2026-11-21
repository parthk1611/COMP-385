import unittest

from experiments.ignition.permutation_importance import experiment

import numpy as np


class WithinDayPermutationTest(unittest.TestCase):
    def test_joint_and_individual_permutation_restore(self):
        # Day, correlated value/flag pair, fixed row ID, day-constant input.
        source = np.array([
            [1, 11, 0, 101, 5], [1, np.nan, 1, 102, 5], [1, 13, 0, 103, 5],
            [2, 21, 0, 104, np.nan], [2, 22, 0, 105, np.nan], [2, 23, 0, 106, np.nan],
        ], dtype=np.float64)
        pristine = source.copy()
        source.flags.writeable = False
        work = source.copy(order="C")
        labels = np.array([1, 0, 0, 0, 1, 0], dtype=np.uint8)
        days = ((0, 3), (3, 6))
        donors = np.array([1, 2, 0, 5, 3, 4])
        self.assertEqual(experiment.day_constant_columns(source, days), {0, 4})

        def assert_alignment(matrix):
            np.testing.assert_array_equal(matrix[:, [0, 3, 4]], pristine[:, [0, 3, 4]])
            np.testing.assert_array_equal(labels, [1, 0, 0, 0, 1, 0])
            np.testing.assert_array_equal(source, pristine)

        def score_joint(matrix):
            assert_alignment(matrix)
            for start, stop in days:
                np.testing.assert_array_equal(matrix[start:stop, 1:3], pristine[donors[start:stop], 1:3])
                np.testing.assert_array_equal(np.sort(donors[start:stop]), np.arange(start, stop))
            np.testing.assert_array_equal(np.isnan(matrix[:, 1]), matrix[:, 2])
            return .25

        drop = experiment.perturbation_drop(source, work, (1, 2), donors, .5, score_joint)
        self.assertEqual(drop, .25)
        np.testing.assert_array_equal(work, pristine)

        def score_individual(matrix):
            assert_alignment(matrix)
            np.testing.assert_array_equal(matrix[:, 1], pristine[donors, 1])
            np.testing.assert_array_equal(matrix[:, 2], pristine[:, 2])
            return .75

        drop = experiment.perturbation_drop(source, work, (1,), donors, .5, score_individual)
        self.assertEqual(drop, -.25)
        np.testing.assert_array_equal(work, pristine)

        def never_score(matrix):
            self.fail("A day-constant input must reuse the exact baseline")

        self.assertEqual(experiment.perturbation_drop(source, work, (4,), donors, .5, never_score), 0.)
        np.testing.assert_array_equal(work, pristine)

    def test_seeded_donors_are_day_local(self):
        days = ((0, 3), (3, 6))
        donors = experiment.donor_indices(days, 2012, 0)
        np.testing.assert_array_equal(donors, experiment.donor_indices(days, 2012, 0))
        for start, stop in days:
            np.testing.assert_array_equal(np.sort(donors[start:stop]), np.arange(start, stop))
        self.assertFalse(np.array_equal(donors, np.arange(6)))


class AnnualSummaryTest(unittest.TestCase):
    def test_years_are_normalized_before_equal_weighting(self):
        years = range(2012, 2017)
        baselines = dict(zip(years, (.1, .2, .3, .4, .5)))
        drops = {year: {"input": [mean] * 5}
                 for year, mean in zip(years, (.02, -.01, 0, .04, .05))}
        row, = experiment.summarize(baselines, drops, ("input",))
        self.assertAlmostEqual(row["mean_ap_drop"], .02)
        self.assertAlmostEqual(row["mean_pct_baseline_ap"], 7.)
        self.assertEqual((row["min_pct_baseline_ap"], row["min_pct_year"]), (-5., 2013))
        self.assertEqual((row["max_pct_baseline_ap"], row["max_pct_year"]), (20., 2012))
        self.assertEqual((row["max_ap_drop"], row["max_ap_drop_year"]), (.05, 2016))
        self.assertTrue(experiment.brackets_zero(row))


if __name__ == "__main__":
    unittest.main()
