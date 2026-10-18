import tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling
from scripts.complete_spread_replay import intersects,source_index,warped_window
from scripts.selected_2025_model import select_dates

class CompletionTests(unittest.TestCase):
    def test_half_open_source_intersection(self):
        self.assertFalse(intersects((0,0,10,10),(10,0,20,10)))
        self.assertTrue(intersects((0,0,10,10),(9,9,20,20)))
    def test_native_categorical_window_never_averages_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'fuel.tif'
            with rasterio.open(p,'w',driver='GTiff',count=1,dtype='int16',width=6,height=6,transform=from_origin(0,180,30,30),crs=3978,nodata=-9999) as ds:ds.write(np.tile(np.array([1,1,1,102,102,102],dtype='int16'),(6,1)),1)
            w={'rows':2,'columns':2,'west':0,'north':180,'south':0,'east':180};data,used=warped_window(w,source_index(Path(folder)),Resampling.nearest,-9999)
            self.assertEqual(set(data.ravel()),{1.,102.});self.assertEqual(len(used),1)
            data,_=warped_window(w,[],Resampling.nearest,-9999);self.assertTrue((data==-9999).all())
    def test_selected_temporal_roles_do_not_overlap(self):
        frame=pd.DataFrame({'ignition_date':['2025-07-31','2025-08-01','2025-08-31','2025-09-01']})
        self.assertEqual(select_dates(frame,['2025-08-01','2025-08-31']).ignition_date.tolist(),['2025-08-01','2025-08-31'])
        with self.assertRaises(ValueError):select_dates(frame,['2025-09-01','2025-08-31'])
