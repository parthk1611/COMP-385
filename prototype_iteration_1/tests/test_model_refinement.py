import unittest

import numpy as np
import pandas as pd

from scripts.model_refinement import (
    candidate_specs, choose_candidate, fold_masks, paired_recall_interval,
    sampling_mask, validate_development, validate_predictors,
)


class RefinementContracts(unittest.TestCase):
    def test_reserved_years_are_rejected(self):
        for year in (2018, 2019, 2025):
            frame = pd.DataFrame({'ignition_date': [f'{year}-06-01'], 'ignition': [1]})
            with self.assertRaises(ValueError):
                validate_development(frame, 'validation')

    def test_training_and_validation_roles_cannot_be_swapped(self):
        frame = pd.DataFrame({'ignition_date': ['2016-06-01'], 'ignition': [1]})
        with self.assertRaises(ValueError):
            validate_development(frame, 'training')
        with self.assertRaises(ValueError):
            validate_development(frame, 'final_test')

    def test_sampling_is_nested_and_keeps_every_positive(self):
        frame = pd.DataFrame({'ignition': [1, 0, 0, 0], '_bucket': [99, 0, 3, 8]})
        np.testing.assert_array_equal(sampling_mask(frame, 1), [True, True, False, False])
        np.testing.assert_array_equal(sampling_mask(frame, 5), [True, True, True, False])
        with self.assertRaises(ValueError):
            sampling_mask(frame, 0)

    def test_fold_is_forward_in_time_and_spatially_disjoint(self):
        frame = pd.DataFrame({'ignition_date': ['2013-06-01', '2014-06-01'] * 2,
                              'inner_role': ['inner_training'] * 2 + ['inner_validation'] * 2})
        train, val = fold_masks(frame, 2014, 'inner_spatial')
        self.assertEqual(np.flatnonzero(train).tolist(), [0])
        self.assertEqual(np.flatnonzero(val).tolist(), [3])
        with self.assertRaises(ValueError):
            fold_masks(frame, 2019, 'temporal')

    def test_predictor_allowlist_rejects_metadata_and_spatial_history(self):
        contract = {'temporal_candidate_predictors': ['temp', 'fire_history_30d'],
                    'spatial_candidate_predictors': ['temp'], 'never_predictors': ['ignition']}
        for names, protocol in [(['ignition'], 'temporal'), (['unknown'], 'temporal'),
                                (['fire_history_30d'], 'inner_spatial'), (['temp', 'temp'], 'temporal')]:
            with self.assertRaises(ValueError):
                validate_predictors(names, contract, protocol)

    def test_selection_uses_complete_development_folds_with_recall_guard(self):
        records = []
        for candidate, ap, recall in [('lightgbm_reference', .01, .1),
                                       ('better', .012, .11), ('bad_recall', .02, .05)]:
            for year in (2014, 2015):
                records.append({'candidate': candidate, 'year': year,
                                'average_precision': ap, 'daily_budget_recall': recall})
        self.assertEqual(choose_candidate(records), 'better')
        with self.assertRaises(ValueError):
            choose_candidate(records[:-1])
        with self.assertRaises(ValueError):
            choose_candidate(records + [{**records[0], 'year': 2017}])

    def test_no_improvement_keeps_reference(self):
        records = [{'candidate': 'lightgbm_reference', 'year': y,
                    'average_precision': .01, 'daily_budget_recall': .1} for y in (2014, 2015)]
        self.assertEqual(choose_candidate(records), 'lightgbm_reference')

    def test_paired_interval_requires_identical_dates_and_populations(self):
        a = pd.DataFrame({'date': ['2017-06-01', '2017-06-02'],
                          'rows': [100, 100], 'positives': [2, 2], 'alerts': [1, 1], 'hits': [0, 1]})
        b = a.assign(hits=[1, 1])
        result = paired_recall_interval(a, b)
        self.assertEqual(result['observed_delta'], .25)
        np.testing.assert_allclose(result['ci95'], [.25, .25])
        with self.assertRaises(ValueError):
            paired_recall_interval(a, b.assign(positives=[3, 2]))
        with self.assertRaises(ValueError):
            paired_recall_interval(a, b.iloc[:1])

    def test_no_random_early_stopping_or_class_prior_distortion(self):
        for spec in candidate_specs():
            self.assertNotIn('scale_pos_weight', spec.get('params', {}))
            self.assertIn(spec['negative_percent'], (1, 5))


if __name__ == '__main__':
    unittest.main()
