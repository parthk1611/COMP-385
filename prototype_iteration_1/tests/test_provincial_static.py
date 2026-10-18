import unittest
import numpy as np
import pandas as pd
from scripts.prepare_provincial_static import canopy_summary,fuel_fractions,quadrature
from scripts.prepare_ignition_pilot import CONIFERS
class ProvincialStaticTest(unittest.TestCase):
 def test_unknown_fuel_codes_remain_distinct_categories(self):
  x=fuel_fractions(np.array([[2.,102.,999.,np.nan],[np.nan]*4]));self.assertAlmostEqual(x['fbp_2024_code_999_share'][0],1/3);self.assertEqual(x.fbp_sample_valid_fraction[0],.75);self.assertTrue(np.isnan(x['fbp_2024_code_2_share'][1]))
 def test_quadrature_is_complete_and_inside_cell(self):
  x,y=quadrature(pd.DataFrame({'grid_x_m':[10000],'grid_y_m':[-10000]}));self.assertEqual(x.shape,(1,100));self.assertEqual((x.min(),x.max()),(10500,19500));self.assertEqual((y.min(),y.max()),(-9500,-500))
 def test_canopy_fraction_is_weighted_and_zero_tree_is_unknown(self):
  layers={k:np.zeros((2,2)) for k in (*CONIFERS,'prcB')};layers['closure']=np.array([[20.,80.],[0.,0.]]);layers['blackSpruce'][0]=[100.,0.];layers['prcB'][0]=[0.,100.];x=canopy_summary(layers);self.assertAlmostEqual(x.scanfi_2020_canopy_weighted_conifer_pct[0],20.);self.assertTrue(np.isnan(x.scanfi_2020_canopy_weighted_conifer_pct[1]))
