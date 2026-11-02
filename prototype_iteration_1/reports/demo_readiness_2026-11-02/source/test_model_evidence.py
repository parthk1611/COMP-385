import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.model_evidence import EXPERIMENT, evidence_response, geographic_cells


class ModelEvidenceTests(unittest.TestCase):
    def test_development_evidence_cannot_claim_live_qualification(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "reports" / EXPERIMENT
            directory.mkdir(parents=True)
            result = {"operational": False, "promoted": False, "protected_artifacts_unchanged": True,
                      "results": [{"candidate": "reference", "hits": 2, "positives": 92}]}
            path = directory / "results.json"
            path.write_text(json.dumps(result))
            response = evidence_response(folder)
            self.assertIsNone(response["live_probability"])
            self.assertEqual(response["default_budget_percent"], 1)
            result["operational"] = True
            path.write_text(json.dumps(result))
            with self.assertRaises(OSError):
                evidence_response(folder)

    def test_only_registered_development_dates_and_candidates_are_accessible(self):
        for candidate, day in (("../../x", "2017-05-01"), ("reference", "2019-05-01"), ("reference", "2017-02-30")):
            with self.assertRaises(ValueError):
                geographic_cells(Path("unused"), candidate, day)

    def test_keyed_replay_preserves_saved_scores_labels_and_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "data/processed" / EXPERIMENT
            directory.mkdir(parents=True)
            path = directory / "inner_spatial_reference_predictions.parquet"
            row = {"grid_id": "ofr10km_10000_20000", "ignition_date": "2017-05-01",
                   "ignition": 1, "probability": .02, "rank": 3, "daily_cells": 4}
            pd.DataFrame([row]).to_parquet(path, index=False)
            result = geographic_cells(folder, "reference", "2017-05-01")
            self.assertFalse(result["live"])
            self.assertEqual(result["rows"][0]["probability"], .02)
            self.assertEqual(result["rows"][0]["x"], 10000)
            self.assertEqual(result["positives"], 1)
            self.assertFalse(result["recorded_labels_are_predictors"])
            pd.DataFrame([row, row]).to_parquet(path, index=False)
            with self.assertRaises(OSError):
                geographic_cells(folder, "reference", "2017-05-01")


class EvidenceHttpTests(unittest.TestCase):
    def test_bad_queries_are_rejected_and_missing_results_fail_closed(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from unittest.mock import patch
        from urllib.error import HTTPError
        from urllib.request import urlopen
        from scripts.capstone_app import Handler

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(Handler, "log_message"), patch("scripts.capstone_app.evidence_response", side_effect=FileNotFoundError):
                for route, expected in (("/api/model-evidence", 503),
                        ("/api/model-evidence?date=2019", 400),
                        ("/api/model-evidence/cells?candidate=reference&date=2019-05-01", 400),
                        ("/api/model-evidence/cells?candidate=reference&candidate=other&date=2017-05-01", 400)):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(f"http://127.0.0.1:{server.server_port}{route}", timeout=5)
                    self.assertEqual(caught.exception.code, expected)
                    caught.exception.close()
                with urlopen(f"http://127.0.0.1:{server.server_port}/performance.html", timeout=5) as response:
                    self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
