import unittest
import tempfile
from pathlib import Path

import pandas as pd

from scripts.join_development_weather_v2 import join_frame, run


class DevelopmentWeatherJoinTest(unittest.TestCase):
    def test_completed_output_is_protected_before_input_access(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                run(Path(directory), Path('/absent'), Path('/absent'))

    def inputs(self):
        original = pd.DataFrame({'grid_id': ['a', 'b'], 'ignition_date': ['2016-06-01'] * 2,
                                 'ignition': [0, 1], 'ignition_count': [0, 2], 'large_fire_200ha': [0, 1],
                                 'feature_set_version': ['v1'] * 2, 'terrain': [2., 3.],
                                 'cwfis_fwi': [None, 1.], 'cwfis_observation_date': ['2016-05-31'] * 2})
        weather = pd.DataFrame({'grid_id': ['b', 'a'], 'ignition_date': ['2016-06-01'] * 2,
                                'cwfis_fwi': [3., 4.], 'cwfis_observation_date': ['2016-05-31'] * 2})
        return original, weather

    def test_join_is_keyed_and_preserves_labels_order_and_static_fields(self):
        original, weather = self.inputs()
        result = join_frame(original, weather, {'b'})
        self.assertEqual(result.cwfis_fwi.tolist(), [4., 3.])
        self.assertEqual(result.ignition_count.tolist(), [0, 2])
        self.assertEqual(result.terrain.tolist(), [2., 3.])
        self.assertEqual(result.current_boundary_centroid_eligible.tolist(), [False, True])

    def test_missing_weather_row_cannot_silently_drop_a_label(self):
        original, weather = self.inputs()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            join_frame(original, weather.iloc[:1], {'a', 'b'})

    def test_duplicate_weather_key_is_rejected(self):
        original, weather = self.inputs()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            join_frame(original, pd.concat([weather, weather]), {'a', 'b'})

    def test_same_day_weather_is_rejected(self):
        original, weather = self.inputs(); weather['cwfis_observation_date'] = '2016-06-01'
        with self.assertRaisesRegex(ValueError, 'prior date'):
            join_frame(original, weather, {'a', 'b'})

    def test_reserved_years_are_rejected(self):
        for year in (2018, 2019):
            original, weather = self.inputs(); original['ignition_date'] = f'{year}-06-01'
            with self.assertRaisesRegex(ValueError, 'development rows'):
                join_frame(original, weather, {'a', 'b'})


if __name__ == '__main__':
    unittest.main()
