import unittest
import numpy as np
from rasterio.transform import from_origin
from scripts.refine_provincial_fuel import weighted_codes
class NativeFuelTest(unittest.TestCase):
 def test_partial_pixel_areas_are_weighted(self):
  counts,area=weighted_codes(np.array([[1.,2.],[1.,2.]]),from_origin(0,2,1,1),(.5,0,2,2));self.assertEqual(area,3.);self.assertEqual(counts,{1:1.,2:2.})
 def test_nodata_is_coverage_loss_not_a_fuel_class(self):
  counts,area=weighted_codes(np.array([[np.nan,2.],[np.nan,2.]]),from_origin(0,2,1,1),(.5,0,2,2));self.assertEqual(area,2.);self.assertEqual(counts,{2:2.})
