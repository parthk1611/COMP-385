import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.demo_model_inference import run, validate_demo_key


class ModelDemoTests(unittest.TestCase):
    def test_reserved_periods_and_invalid_keys_are_rejected(self):
        for day,grid in [('2019-05-01','ofr10km_0_0'),('2025-09-01','ofr10km_0_0'),
                         ('2017-02-30','ofr10km_0_0'),('2017-08-09','../../x')]:
            with self.assertRaises(ValueError):
                validate_demo_key(day,grid)

    def test_valid_example_has_a_calendar_date_and_grid_key(self):
        validate_demo_key('2017-08-09','ofr10km_470000_40000')

    def test_invalid_period_is_rejected_before_reading_model_or_data(self):
        with patch.object(Path,'read_text',side_effect=AssertionError('should not read')):
            with self.assertRaises(ValueError):
                run(Path('/unused'),'2019-05-01','ofr10km_0_0')


if __name__=='__main__':
    unittest.main()
