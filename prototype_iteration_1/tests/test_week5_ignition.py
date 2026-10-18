import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.week5_ignition import apply_calibration, fit_calibration, validate_role, join_reserved, require_final_freeze


class Week5Tests(unittest.TestCase):
    def test_reserved_role_years_cannot_cross(self):
        for role, date in [('calibration','2019-06-01'),('final_test','2018-06-01'),('training','2018-06-01')]:
            with self.assertRaises(ValueError):validate_role(pd.Series([date]),role)
        validate_role(pd.Series(['2018-05-01']),'calibration')

    def test_final_content_requires_committed_calibration_freeze(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):require_final_freeze(Path(folder))

    def test_calibration_is_finite_monotonic_and_keeps_input_order(self):
        p=np.array([.001,.01,.1,.3,.7,.9]);y=np.array([0,0,0,1,0,1])
        c=fit_calibration(y,p);q=apply_calibration(c,p)
        self.assertTrue(np.isfinite(q).all());self.assertTrue((np.diff(q)>=0).all())
        np.testing.assert_allclose(q[::-1],apply_calibration(c,p[::-1]))

    def test_invalid_calibration_probabilities_rejected(self):
        for p in [np.array([0.2,np.nan]),np.array([-.1,.2])]:
            with self.assertRaises(ValueError):fit_calibration(np.array([0,1]),p)
        with self.assertRaises(ValueError):fit_calibration(np.array([0,0]),np.array([.1,.2]))

    def test_boundary_filter_is_not_used_to_change_reserved_universe(self):
        original=pd.DataFrame({'grid_id':['a'],'ignition_date':['2018-06-01'],'ignition':[1],'ignition_count':[1],'large_fire_200ha':[0],'cwfis_fwi':[1.]})
        weather=pd.DataFrame({'grid_id':['a'],'ignition_date':['2018-06-01'],'cwfis_observation_date':['2018-05-31'],'cwfis_fwi':[2.]})
        result=join_reserved(original,weather,'calibration')
        self.assertEqual(result.ignition.tolist(),[1]);self.assertEqual(result.cwfis_fwi.tolist(),[2.])
        with self.assertRaises(ValueError):join_reserved(original,weather.iloc[:0],'calibration')

    def test_future_weather_and_duplicates_rejected(self):
        original=pd.DataFrame({'grid_id':['a'],'ignition_date':['2018-06-01'],'ignition':[0],'ignition_count':[0],'large_fire_200ha':[0],'cwfis_fwi':[1.]})
        weather=pd.DataFrame({'grid_id':['a'],'ignition_date':['2018-06-01'],'cwfis_observation_date':['2018-06-01'],'cwfis_fwi':[2.]})
        with self.assertRaises(ValueError):join_reserved(original,weather,'calibration')
        weather.cwfis_observation_date='2018-05-31'
        with self.assertRaises(ValueError):join_reserved(pd.concat([original,original]),weather,'calibration')
