import unittest
import numpy as np
from scripts.hrdps_live_weather import choose_available_run,rotate_wind,validate_seed,incremental_rain
class HrdpsLiveTest(unittest.TestCase):
 def test_rotation_preserves_speed_and_true_cardinals(self):
  u,v=rotate_wind(np.array([1.,1.,0.]),np.array([0.,0.,1.]),np.array([0.,90.,90.]));np.testing.assert_allclose(u,[1.,0.,1.],atol=1e-12);np.testing.assert_allclose(v,[0.,-1.,0.],atol=1e-12)
 def test_late_retrieved_newer_run_is_not_available_at_issue(self):
  a={'run_time_utc':'2026-10-16T00:00Z','available_at_utc':'2026-10-16T04:00Z'};b={'run_time_utc':'2026-10-16T06:00Z','available_at_utc':'2026-10-16T08:00Z'};self.assertEqual(choose_available_run([a,b],'2026-10-16T07:00Z'),a)
 def test_unknown_state_cannot_be_treated_as_trusted(self):
  seed={'date':'2026-10-15','ffmc':85.,'dmc':6.,'dc':15.,'trusted':False,'provenance':'research'}
  with self.assertRaisesRegex(ValueError,'Trusted'):validate_seed(seed,'2026-10-15')
  self.assertEqual(validate_seed(seed,'2026-10-15',True)['ffmc'],85.)
 def test_stale_or_out_of_range_state_is_rejected(self):
  seed={'date':'2026-10-14','ffmc':102.,'dmc':6.,'dc':15.,'trusted':True,'provenance':'fixture'}
  with self.assertRaises(ValueError):validate_seed(seed,'2026-10-15')
  seed['date']='2026-10-15'
  with self.assertRaises(ValueError):validate_seed(seed,'2026-10-15')

 def test_cumulative_rain_is_deaccumulated_and_reset_is_explicit(self):
  import pandas as pd
  start=pd.Timestamp('2026-10-16T00:00Z');one=start+pd.Timedelta(hours=1);two=start+pd.Timedelta(hours=2)
  np.testing.assert_allclose(incremental_rain(np.array([3.]),start,two,(np.array([1.]),start,one)),[2.])
  np.testing.assert_allclose(incremental_rain(np.array([.5]),one,two),[.5])
 def test_rain_gaps_and_negative_differences_remain_unknown(self):
  import pandas as pd
  start=pd.Timestamp('2026-10-16T00:00Z');one=start+pd.Timedelta(hours=1);two=start+pd.Timedelta(hours=2)
  self.assertTrue(np.isnan(incremental_rain(np.array([3.]),start,two)).all())
  self.assertTrue(np.isnan(incremental_rain(np.array([.5]),start,two,(np.array([1.]),start,one))).all())

 def test_trusted_seed_requires_exact_previous_noon_clock(self):
  import pandas as pd
  seed={'date':'2026-10-15','ffmc':85.,'dmc':6.,'dc':15.,'trusted':True,'provenance':'fixture'}
  with self.assertRaisesRegex(ValueError,'exact previous'):validate_seed(seed,'2026-10-15',expected_noon=pd.Timestamp('2026-10-15T17:00Z'))
 def test_live_discovery_skips_a_not_yet_listed_cycle(self):
  from unittest.mock import patch,Mock
  from scripts.hrdps_live_weather import discover_run,FIELDS
  import pandas as pd
  names=' '.join(f'20261016T00Z_MSC_HRDPS_{token}_{level}_RLatLon0.0225_PT024H.grib2' for token,level,_ in FIELDS.values())
  with patch('scripts.hrdps_live_weather.requests.get',side_effect=[Mock(status_code=404,text=''),Mock(status_code=200,text=names)]):
   run,trace=discover_run('2026-10-16T07:00Z')
  self.assertEqual(run,pd.Timestamp('2026-10-16T00:00Z'));self.assertEqual(len(trace),2)

 def test_state_checkpoint_retains_forecast_provenance_and_excludes_missing(self):
  import pandas as pd
  from scripts.hrdps_live_weather import state_checkpoint
  daily=pd.DataFrame({'grid_id':['a','b'],'date':['2026-10-16']*2,'noon_time_utc':pd.to_datetime(['2026-10-16T17:00Z']*2),'ffmc':[85.,np.nan],'dmc':[6.,np.nan],'dc':[15.,np.nan]})
  checkpoint=state_checkpoint(daily,'2026-10-16T08:00Z','2026-10-16T00:00Z','gridhash')
  self.assertIn('a',checkpoint);self.assertNotIn('b',checkpoint);self.assertFalse(checkpoint['a']['trusted']);self.assertEqual(checkpoint['a']['state_kind'],'forecast_update')
 def test_seed_not_known_at_issue_is_rejected(self):
  import pandas as pd
  seed={'date':'2026-10-15','ffmc':85.,'dmc':6.,'dc':15.,'trusted':True,'provenance':'fixture','available_at_utc':'2026-10-16T09:00Z'}
  with self.assertRaisesRegex(ValueError,'availability'):validate_seed(seed,'2026-10-15',issue=pd.Timestamp('2026-10-16T08:00Z'))
