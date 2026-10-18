import unittest
import pandas as pd
from scripts.build_selected_2025_panel import provider_dates,shifted_weather
class Selected2025PanelTest(unittest.TestCase):
 def test_epoch_calendar_date_is_not_shifted_back_a_day(self):
  x=provider_dates(pd.Series([pd.Timestamp('2025-05-01T00:00Z').timestamp()*1000,None]));self.assertEqual(x.iloc[0],'2025-05-01');self.assertTrue(pd.isna(x.iloc[1]))
 def test_weather_shift_is_prior_day_and_rain_uses_complete_windows(self):
  dates=pd.date_range('2025-04-20',periods=10);w=pd.DataFrame({'grid_id':'a','date':dates.strftime('%Y-%m-%d'),'noon_time_utc':pd.to_datetime(dates,utc=True)+pd.Timedelta(hours=17),'rain_24h_mm':1.});x=shifted_weather(w);self.assertEqual(x.ignition_date.iloc[0],'2025-04-21');self.assertEqual(x.rain_prior_7_noon_days_mm.iloc[6],7.);self.assertTrue((x.noon_time_utc<x.issue_time_utc).all())
 def test_duplicate_weather_is_rejected(self):
  w=pd.DataFrame({'grid_id':['a','a'],'date':['2025-05-01']*2})
  with self.assertRaises(ValueError):shifted_weather(w)
