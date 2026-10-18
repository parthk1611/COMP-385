import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.ignition_comparison import corrected_weights, inner_spatial_roles, predict_bundle, read_development, run, sample_mask, validate_features, validate_years


class ComparisonContractTest(unittest.TestCase):
    def test_completed_run_is_protected_before_input_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'model_comparison.json').write_text('{}')
            with self.assertRaises(FileExistsError):
                run(output)

    def test_all_positives_are_retained_and_negative_sampling_is_stable(self):
        frame = pd.DataFrame({'grid_id': ['a', 'b', 'c'], 'ignition_date': ['2011-06-01'] * 3, 'ignition': [0, 1, 0]})
        first = sample_mask(frame)
        self.assertTrue(first[1])
        np.testing.assert_array_equal(first[::-1], sample_mask(frame.iloc[::-1]))

    def test_weights_restore_population_event_fraction(self):
        y = np.array([1, 1, 0, 0])
        weights = corrected_weights(y, population_rows=202, population_positives=2)
        self.assertAlmostEqual(np.average(y, weights=weights), 2 / 202)
        self.assertEqual(weights.sum(), 202)

    def test_final_test_and_calibration_years_cannot_enter_development(self):
        for date in ['2018-05-01', '2019-05-01']:
            with self.assertRaises(ValueError):
                validate_years(pd.Series([date]), 'validation')

    def test_wrong_partition_year_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_years(pd.Series(['2016-05-01']), 'training')

    def test_reserved_partition_is_rejected_before_file_access(self):
        with self.assertRaises(ValueError):
            read_development('final_test', [], {}, pd.DataFrame())

    def test_scoring_rejects_feature_order_changes(self):
        with self.assertRaises(ValueError):
            predict_bundle({'features': ['a', 'b']}, pd.DataFrame({'b': [0.], 'a': [0.]}))

    def test_outcome_and_metadata_are_never_predictors(self):
        contract = {'never_predictors': ['ignition', 'grid_id']}
        with self.assertRaises(ValueError):
            validate_features(['fwi', 'ignition'], contract, spatial=False)

    def test_spatial_experiment_cannot_use_fire_history(self):
        with self.assertRaises(ValueError):
            validate_features(['fire_history_same_cell_30d'], {'never_predictors': []}, spatial=True)

    def test_inner_blocks_preserve_outer_reservations_and_distance_buffer(self):
        frame = pd.DataFrame({'grid_id': [f'g{i}' for i in range(100)],
                              'grid_x_m': np.arange(100) * 10000, 'grid_y_m': 0,
                              'block_x': np.arange(100) // 10, 'block_y': 0,
                              'spatial_role': ['spatial_development'] * 99 + ['spatial_test']})
        result = inner_spatial_roles(frame)
        self.assertEqual(result.iloc[-1].inner_role, 'outer_reserved')
        kept = result[result.inner_role == 'inner_training']
        self.assertTrue((kept.nearest_inner_validation_m >= 20000).all())
        self.assertTrue((result.inner_role == 'inner_validation').any())


    def test_explicit_dataset_path_and_boundary_filter_preserve_counts(self):
        from scripts.ignition_comparison import digest
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            frame = pd.DataFrame({'grid_id': ['a', 'b'], 'ignition_date': ['2016-06-01'] * 2,
                                  'ignition': [1, 0], 'current_boundary_centroid_eligible': [False, True]})
            path = folder / 'validation.parquet'
            frame.to_parquet(path, index=False)
            manifest = {'files': {'validation': {'path': str(path), 'sha256': digest(path)}}}
            inner = pd.DataFrame({'grid_id': ['a', 'b'], 'inner_role': ['inner_validation', 'inner_training']})
            result, counts = read_development('validation', list(frame.columns), manifest, inner, folder, True)
            self.assertEqual(result.grid_id.tolist(), ['b'])
            self.assertEqual(counts['temporal'], {'rows': 1, 'positives': 0})
            self.assertEqual(counts['inner_spatial'], {'rows': 0, 'positives': 0})

    def test_changed_candidate_file_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / 'validation.parquet'
            path.write_text('not a valid parquet')
            manifest = {'files': {'validation': {'path': str(path), 'sha256': 'wrong'}}}
            with self.assertRaisesRegex(ValueError, 'content differs'):
                read_development('validation', [], manifest, pd.DataFrame(), folder)


if __name__ == '__main__':
    unittest.main()
