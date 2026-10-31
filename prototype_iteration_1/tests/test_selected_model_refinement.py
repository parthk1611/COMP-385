import unittest

import pandas as pd

from scripts.selected_model_refinement import check_development_dates, select


class SelectedRefinementTests(unittest.TestCase):
    def test_calibration_and_final_dates_never_enter_development(self):
        for date in ('2025-08-01', '2025-09-01', '2025-10-01', '2026-06-01'):
            with self.assertRaises(ValueError):
                check_development_dates(pd.DataFrame({'grid_id': ['a'], 'ignition_date': [date], 'ignition': [1]}))

    def test_duplicate_keys_are_rejected(self):
        row = {'grid_id': 'a', 'ignition_date': '2025-06-01', 'ignition': 1}
        with self.assertRaises(ValueError):
            check_development_dates(pd.DataFrame([row, row]))

    def test_months_must_be_complete_and_selection_guard_preserves_recall(self):
        rows = []
        for name, ap, recall in [('lightgbm_reference', .01, .1), ('candidate', .02, .05)]:
            rows += [{'candidate': name, 'month': m, 'average_precision': ap,
                      'daily_budget_recall': recall} for m in ('2025-06', '2025-07')]
        self.assertEqual(select(rows), 'lightgbm_reference')
        with self.assertRaises(ValueError):
            select(rows[:-1])


if __name__ == '__main__':
    unittest.main()
