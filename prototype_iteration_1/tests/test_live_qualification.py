import unittest
import numpy as np
import pandas as pd
from scripts.live_qualification import pair_weather, parse_station_file, validate_state_lineage, qualification_decision


class LiveQualificationTests(unittest.TestCase):
    def forecast(self):
        return pd.DataFrame({'grid_id':['a','a'],'valid_time_utc':pd.to_datetime(['2026-10-16T09:00Z','2026-10-16T10:00Z']),
            'run_time_utc':pd.to_datetime(['2026-10-16T00:00Z']*2),'available_at_utc':pd.to_datetime(['2026-10-16T08:00Z']*2),
            'temp_c':[10.,11.],'rh_pct':[50.,51.],'wind_kmh':[4.,5.],'precip_mm':[0.,1.]})

    def test_pairing_requires_exact_cell_time_and_post_issue_forecast(self):
        f=self.forecast();r=f[['grid_id','valid_time_utc','temp_c','rh_pct','wind_kmh','precip_mm']].copy()
        r.loc[1,'grid_id']='b'
        p,a=pair_weather(f,r,pd.Timestamp('2026-10-16T08:00Z'))
        self.assertEqual(len(p),1);self.assertEqual(a['unmatched_eligible_rows'],1)

    def test_after_issue_availability_is_rejected(self):
        f=self.forecast();f['available_at_utc']=pd.Timestamp('2026-10-16T08:01Z')
        with self.assertRaises(ValueError):pair_weather(f,f,pd.Timestamp('2026-10-16T08:00Z'))

    def test_duplicates_naive_clocks_and_reference_nonuniqueness_rejected(self):
        f=self.forecast()
        for other in [pd.concat([f,f.iloc[:1]]),f.assign(valid_time_utc=f.valid_time_utc.dt.tz_localize(None))]:
            with self.assertRaises(ValueError):pair_weather(other,f,pd.Timestamp('2026-10-16T08:00Z'))
        with self.assertRaises(ValueError):pair_weather(f,pd.concat([f,f.iloc[:1]]),pd.Timestamp('2026-10-16T08:00Z'))

    def test_station_adapter_handles_repeated_headers_and_sentinels(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.csv';p.write_text('NAME,AGENCY,AES,WMO,REPDATE,TEMP,RH,WS,PRECIP,FFMC,DMC,DC,FWI,CALCSTATUS,OPTS\nNAME,AGENCY,AES,WMO,REPDATE,TEMP,RH,WS,PRECIP,FFMC,DMC,DC,FWI,CALCSTATUS,OPTS\n A ,MSC, 1 ,2,20261015,-999,50,3,0,80,2,20,4,1,M=1:\n')
            frame=parse_station_file(p,'2026-10-15')
            self.assertEqual(len(frame),1);self.assertTrue(np.isnan(frame.temp_c.iloc[0]))
            self.assertFalse(frame.trusted.any())

    def test_forecast_state_cannot_become_observed_by_setting_trusted(self):
        seed={'trusted':True,'state_kind':'forecast_update','date':'2026-10-15','available_at_utc':'2026-10-15T23:00Z',
              'noon_time_utc':'2026-10-15T17:00Z','provenance':'forecast'}
        with self.assertRaises(ValueError):validate_state_lineage(seed,pd.Timestamp('2026-10-16T08:00Z'),pd.Timestamp('2026-10-15T17:00Z'))

    def test_observed_state_needs_exact_noon_hash_and_issue_availability(self):
        s={'trusted':True,'state_kind':'observed','date':'2026-10-15','available_at_utc':'2026-10-17T00:00Z','noon_time_utc':'2026-10-15T17:00Z',
           'source_sha256':'a'*64,'provenance':'station','ffmc':80,'dmc':5,'dc':30}
        with self.assertRaises(ValueError):validate_state_lineage(s,pd.Timestamp('2026-10-16T08:00Z'),pd.Timestamp('2026-10-15T17:00Z'))
        s['available_at_utc']='2026-10-15T23:00Z';s['noon_time_utc']='2026-10-15T18:00Z'
        with self.assertRaises(ValueError):validate_state_lineage(s,pd.Timestamp('2026-10-16T08:00Z'),pd.Timestamp('2026-10-15T17:00Z'))

    def test_presence_of_overlap_and_trusted_labels_cannot_qualify_model(self):
        d=qualification_decision({'paired_days':1,'paired_rows':1000},10)
        self.assertEqual(d['status'],'unavailable');self.assertIsNone(d['probability']);self.assertFalse(d['operational'])


class AcquisitionTests(unittest.TestCase):
    def test_planning_only_does_not_access_network_or_credentials(self):
        from pathlib import Path
        from unittest.mock import patch
        import tempfile
        from scripts.acquire_live_reference import run
        grid=pd.DataFrame({'centroid_latitude':[45.],'centroid_longitude':[-85.]})
        with tempfile.TemporaryDirectory() as d,patch('scripts.acquire_live_reference.pd.read_csv',return_value=grid),patch('scripts.acquire_live_reference.requests.get',side_effect=AssertionError('No download')):
            result=run(Path(d),Path(d)/'plan',False)
            self.assertEqual(result['status'],'plan_only')
            self.assertEqual(result['request']['year'],['2026'])

class ReferenceMetadataTests(unittest.TestCase):
    def test_reference_units_wind_orientation_and_geographic_axes_are_checked(self):
        from types import SimpleNamespace
        from scripts.live_qualification import reference_clock
        metadata={'latitude#units':'degrees_north','longitude#units':'degrees_east','u10#units':'m s**-1','u10#GRIB_stepType':'instant','u10#GRIB_uvRelativeToGrid':'0'}
        ds=SimpleNamespace(count=2,transform=SimpleNamespace(a=.1,b=0,d=0,e=-.1),
            tags=lambda band=None:metadata if band is None else {'NETCDF_DIM_valid_time':str(1792108800+3600*(band-1))})
        self.assertEqual(len(reference_clock(ds,'u10','m s**-1')),2)
        for key,bad in [('u10#units','km/h'),('u10#GRIB_uvRelativeToGrid','1'),('latitude#units','m')]:
            old=metadata[key];metadata[key]=bad
            with self.assertRaises(ValueError):reference_clock(ds,'u10','m s**-1')
            metadata[key]=old


if __name__=='__main__':unittest.main()
