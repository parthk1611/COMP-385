import unittest
import numpy as np
import pandas as pd
from scripts.prepare_provincial_weather import derive_daily,standard_offsets
from scripts.prepare_selected_weather import daily_weather

class ProvincialWeatherTest(unittest.TestCase):
    def inputs(self):
        times=pd.date_range('2025-03-30',periods=24*7,freq='h',tz='UTC');n=len(times)
        raw={'t2m':np.full((n,2),293.15),'d2m':np.full((n,2),283.15),'u10':np.full((n,2),2.),'v10':np.zeros((n,2)),'tp':np.zeros((n,2))}
        return times,raw
    def test_standard_noon_follows_eastern_and_central_standard_time(self):
        times,raw=self.inputs();x=derive_daily(times,raw,np.array([-5,-6]));x=x[x.date=='2025-04-02']
        self.assertEqual(x.noon_time_utc.dt.hour.tolist(),[17,18]);self.assertTrue(x.fwi_state_valid.all())
    def test_missing_rain_invalidates_state_only_in_affected_cell(self):
        times,raw=self.inputs();raw['tp'][times.get_loc('2025-04-02 10:00Z'),0]=np.nan
        x=derive_daily(times,raw,np.array([-5,-5]));last=x[x.date=='2025-04-04'];self.assertEqual(last.fwi_state_valid.tolist(),[False,True])
    def test_scalar_reference_agrees(self):
        times,raw=self.inputs();x=derive_daily(times,raw,np.array([-5,-5]));rh=100*np.exp(17.625*10/(243.04+10)-17.625*20/(243.04+20))
        reference=daily_weather(pd.DataFrame({'time_utc':times,'temp_c':20.,'rh_pct':rh,'wind_kmh':7.2,'precip_mm':0.}),-5,'2025-04-01')
        actual=x[(x.cell_position==0)&(x.date=='2025-04-03')].iloc[0];expected=reference[reference.date=='2025-04-03'].iloc[0]
        for name in ('ffmc','dmc','dc','isi','bui','fwi'):self.assertAlmostEqual(actual[name],expected[name],places=9)
    def test_timezone_mapping_covers_known_ontario_centres(self):
        _,offsets=standard_offsets(pd.DataFrame({'centroid_longitude':[-89.25,-93.8],'centroid_latitude':[48.38,49.8]}))
        self.assertEqual(offsets.tolist(),[-5,-6])
