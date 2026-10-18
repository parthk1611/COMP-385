import unittest
import pandas as pd
from scripts.build_ignition_map import map_payload

class MapTests(unittest.TestCase):
    def setUp(self):
        self.grid=pd.DataFrame({'grid_id':['a','b'],'grid_x_m':[0,10000],'grid_y_m':[0,0],'centroid_longitude':[-90.,-89.9],'centroid_latitude':[50.,50.]})
        self.pred=pd.DataFrame({'grid_id':['b','a'],'ignition_date':['2019-05-01']*2,'probability':[.2,.1],'ignition':[1,0],'cwfis_missing':[0,1]})
        self.explain={'date':'2019-05-01','rows':[]}
    def test_keyed_map_preserves_probabilities_and_missing_flags(self):
        result=map_payload(self.grid,self.pred,self.explain)['days']['2019-05-01']
        self.assertEqual(result['p'],[.1,.2]);self.assertEqual(result['missing'],[1,0])
    def test_missing_or_duplicate_cells_and_invalid_scores_fail(self):
        for frame in [self.pred.iloc[:1],pd.concat([self.pred,self.pred]),self.pred.assign(probability=float('nan'))]:
            with self.assertRaises(ValueError):map_payload(self.grid,frame,self.explain)
