import unittest

import numpy as np
import pandas as pd

from scripts.missed_fire_audit import audit_labels, cohort_summary, random_capacity_reference, rank_daily, validate_grid


class MissedFireAuditTests(unittest.TestCase):
    def test_daily_capacity_uses_each_days_population_and_stable_key_ties(self):
        frame = pd.DataFrame({'grid_id': [f'ofr10km_{i*10000}_0' for i in range(101)],
                              'ignition_date': '2017-06-01', 'ignition': 0,
                              'probability': .01})
        first = rank_daily(frame)
        shuffled = rank_daily(frame.sample(frac=1, random_state=4))
        self.assertEqual(int(first.selected.sum()), 2)
        self.assertEqual(set(first[first.selected].grid_id), set(shuffled[shuffled.selected].grid_id))

    def test_missing_or_invalid_probability_and_duplicate_keys_are_rejected(self):
        row = {'grid_id': 'ofr10km_0_0', 'ignition_date': '2017-06-01', 'ignition': 1, 'probability': .01}
        for records in [[row, row], [{**row, 'probability': np.nan}], [{**row, 'probability': -1}]]:
            with self.assertRaises(ValueError):
                rank_daily(pd.DataFrame(records))

    def test_reconciliation_distinguishes_events_from_positive_cell_days(self):
        panel = pd.DataFrame({'grid_id': ['a', 'b'], 'ignition_date': ['2017-06-01']*2,
                              'ignition': [1, 0], 'ignition_count': [2, 0]})
        events = pd.DataFrame({'grid_id': ['a', 'a'], 'ignition_date': ['2017-06-01']*2})
        result = audit_labels(panel, events)
        self.assertEqual(result['source_events'], 2)
        self.assertEqual(result['source_positive_cell_days'], 1)
        self.assertEqual(result['label_mismatches'], 0)

    def test_missing_events_and_incorrect_event_count_are_visible(self):
        panel = pd.DataFrame({'grid_id': ['a'], 'ignition_date': ['2017-06-01'],
                              'ignition': [1], 'ignition_count': [1]})
        events = pd.DataFrame({'grid_id': ['b'], 'ignition_date': ['2017-06-01']})
        result = audit_labels(panel, events)
        self.assertEqual(result['source_keys_missing_from_panel'], 1)
        self.assertEqual(result['label_mismatches'], 1)

    def test_grid_keys_are_lower_left_origins_and_not_centroids(self):
        from pyproj import Transformer
        lon, lat = Transformer.from_crs(3978, 4326, always_xy=True).transform(5000, 5000)
        grid = pd.DataFrame({'grid_id': ['ofr10km_0_0'], 'grid_x_m': [0], 'grid_y_m': [0],
                             'centroid_longitude': [lon], 'centroid_latitude': [lat]})
        self.assertEqual(validate_grid(grid)['key_origin_mismatches'], 0)
        grid.loc[0, 'grid_x_m'] = 5000
        self.assertGreater(validate_grid(grid)['key_origin_mismatches'], 0)

    def test_a_month_without_recorded_starts_has_undefined_recall(self):
        frame = pd.DataFrame({'grid_id': ['a'], 'ignition_date': ['2017-10-01'],
                              'ignition': [0], 'probability': [.01], 'cwfis_missing': [0]})
        self.assertIsNone(cohort_summary(rank_daily(frame))['recall'])

    def test_uniform_random_reference_uses_the_exact_daily_budget(self):
        frame = pd.DataFrame({'grid_id': [f'g{i}' for i in range(100)],
                              'ignition_date': '2017-06-01', 'ignition': [1]+[0]*99,
                              'probability': .01})
        result = random_capacity_reference(rank_daily(frame))
        self.assertAlmostEqual(result['expected_hits'], .01)
        self.assertAlmostEqual(result['probability_of_zero_hits'], .99)


if __name__ == '__main__':
    unittest.main()
