import tempfile,unittest
from pathlib import Path
import pandas as pd
from scripts.capstone_app import assess_live_inputs,validate_query,score_response
from unittest.mock import patch

class AppTests(unittest.TestCase):
    def test_research_state_and_time_disjoint_sources_never_allow_live_probability(self):
        state={'a':{'trusted':False,'state_kind':'forecast_update'}}
        r=assess_live_inputs(['2025-10-16'],['2026-10-16'],state,False)
        self.assertEqual(r['status'],'unavailable');self.assertIsNone(r['probability']);self.assertEqual(r['checks']['trusted_observed_state_cells'],0)
        r=assess_live_inputs(['2025-10-16'],['2025-10-16'],{'a':{'trusted':True,'state_kind':'observed'}},True)
        self.assertEqual(r['status'],'unavailable') # Paired dates alone are not validation.
    def test_key_validation_rejects_traversal_bad_dates_and_duplicate_parameters(self):
        for q in [{'date':['2019-05-01'],'grid_id':['../../x']},{'date':['2019-02-30'],'grid_id':['ofr10km_0_0']},{'date':['2019-05-01','2019-05-02'],'grid_id':['ofr10km_0_0']}]:
            with self.assertRaises(ValueError):validate_query(q)
        self.assertEqual(validate_query({'date':['2019-05-01'],'grid_id':['ofr10km_-10000_0']}),('2019-05-01','ofr10km_-10000_0'))
    def test_keyed_api_preserves_predictions_and_missing_does_not_mean_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'p.parquet';pd.DataFrame({'grid_id':['ofr10km_0_0'],'ignition_date':['2019-05-01'],'probability':[.01],'raw_probability':[.02],'ignition':[0],'cwfis_missing':[1]}).to_parquet(source,index=False)
            code,result=score_response(source,'2019-05-01','ofr10km_0_0');self.assertEqual(code,200);self.assertEqual(result['probability'],.01);self.assertTrue(result['weather_missing']);self.assertFalse(result['live'])
            code,result=score_response(source,'2019-05-02','ofr10km_0_0');self.assertEqual(code,404);self.assertIsNone(result['probability'])

    def test_duplicate_saved_keys_and_nonfinite_raw_scores_fail_closed(self):
        row={'grid_id':'ofr10km_0_0','ignition_date':'2019-05-01','probability':.01,'raw_probability':.02,'ignition':0,'cwfis_missing':1}
        for records in ([row,row],[{**row,'raw_probability':float('nan')}]):
            with patch('scripts.capstone_app.pd.read_parquet',return_value=pd.DataFrame(records)):
                code,result=score_response(Path('unused'),'2019-05-01','ofr10km_0_0')
            self.assertEqual(code,503)
            self.assertEqual(result['status'],'unavailable')
            self.assertIsNone(result['probability'])

class DetailTests(unittest.TestCase):
    def test_feature_units_preserve_physical_meaning(self):
        from scripts.capstone_app import feature_unit
        self.assertEqual(feature_unit('cwfis_wind_speed_kmh'),'km/h')
        self.assertEqual(feature_unit('fbp_2024_code_102_share'),'fraction 0–1')
        self.assertEqual(feature_unit('mrdem_elevation_sample_mean_m'),'m')
        self.assertEqual(feature_unit('temp_c'),'°C')
    def test_unknown_study_is_rejected_before_feature_access(self):
        from scripts.capstone_app import cell_details
        with self.assertRaises(ValueError):cell_details('../../x','2025-09-01','ofr10km_0_0')

    def test_date_without_explanation_still_exposes_issue_and_model_provenance(self):
        from scripts.capstone_app import cell_details
        score={'status':'ok','probability':.01,'mode':'retrospective_saved_evaluation'}
        with patch('scripts.capstone_app.score_response',return_value=(200,score)), patch.object(Path,'read_text',return_value='{"date":"2019-05-01","rows":[]}'), patch('scripts.capstone_app.digest',return_value='a'*64):
            code,result=cell_details('historical','2019-06-02','ofr10km_0_0')
        self.assertEqual(code,200)
        self.assertEqual(result['issue_time_utc'],'2019-06-02T04:00:00+00:00')
        self.assertEqual(result['model_sha256'],'a'*64)
        self.assertEqual(result['explanation_status'],'unavailable_for_this_date')
        self.assertEqual(result['factors'],[])


class HttpFailureTests(unittest.TestCase):
    def test_missing_local_asset_returns_json_503_and_server_stays_usable(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.error import HTTPError
        from urllib.request import urlopen
        from scripts.capstone_app import Handler
        import json
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder, patch('scripts.capstone_app.HISTORICAL',Path(folder)/'absent.parquet'), patch.object(Handler,'log_message'):
                with self.assertRaises(HTTPError) as error:
                    urlopen(f'http://127.0.0.1:{server.server_port}/api/historical-score?date=2019-05-01&grid_id=ofr10km_0_0',timeout=5)
                with error.exception as response:
                    self.assertEqual(response.code,503)
                    result=json.loads(response.read())
                self.assertEqual(result['status'],'unavailable')
                self.assertEqual(result['reason'],'local_artifact_unavailable')
                self.assertIsNone(result['probability'])
                with urlopen(f'http://127.0.0.1:{server.server_port}/',timeout=5) as response:
                    self.assertEqual(response.status,200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
