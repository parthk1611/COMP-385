"""Policy, HTTP contracts, and real-artifact alignment for the ignition demo."""
import csv
import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np

from scripts.ignition_demo.common import (
    CACHE, OUTPUT, FEATURE_NAMES, alert_policy, checked_probabilities, confusion, validate_date,
)
from scripts.ignition_demo.server import DemoStore, make_handler


class PolicyTests(unittest.TestCase):
    def test_policy_uses_2018_f2_and_manifest_precision(self):
        policy = alert_policy()
        self.assertEqual(policy["selection_year"], 2018)
        self.assertEqual(policy["default_index"], 4)
        self.assertEqual(policy["threshold"], 0.01502367973189238)
        self.assertAlmostEqual(policy["choices"][4]["f2"], 640 / 13900)

    def test_confusion_is_inclusive_at_cutoff(self):
        self.assertEqual(confusion([1, 0, 1, 0], [.5, .5, .1, .1], .5),
                         dict(true_positive=1, false_positive=1, false_negative=1, true_negative=1,
                              alerts=2, observed=2, precision=.5, recall=.5))

    def test_undefined_precision_and_recall_remain_unknown(self):
        value = confusion([0, 0], [.1, .2], .5)
        self.assertIsNone(value["precision"])
        self.assertIsNone(value["recall"])

    def test_probabilities_reject_invalid_shape_range_and_nonfinite(self):
        for values in [[np.nan], [np.inf], [-.1], [1.1], [[.1]], [.1, .2]]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                checked_probabilities(values, 1)

    def test_date_boundaries_and_format(self):
        for value in ["2019-05-01", "2019-10-31"]:
            self.assertEqual(validate_date(value), value)
        for value in ["2019-04-30", "2019-11-01", "2020-05-01", "2019-02-30", "20190501", "2019-05-01T00:00:00", "", None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_date(value)

    def test_missing_artifacts_have_recovery_instruction(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(FileNotFoundError, "reconstruct first"):
            DemoStore(Path(temporary), Path(temporary))


class FakeStore:
    metadata = {"cells": 1}
    def map_grid(self):
        return {"cells": [{"id": "cell"}]}
    def predictions(self, day):
        return {"date": day, "scores": [.2]}
    def cell(self, day, grid_id):
        if grid_id != "cell":
            raise KeyError("Unknown grid cell")
        return {"features": {"weather": None}, "date": day}
    def download(self, day):
        return b"grid_id,score\r\ncell,0.2\r\n"


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FakeStore()))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def get(self, path):
        return urlopen(self.url + path, timeout=10)

    def test_metadata_grid_and_predictions(self):
        for path in ["/api/metadata", "/api/grid", "/api/predictions?date=2019-05-01"]:
            with self.get(path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("application/json", response.headers["Content-Type"])
                json.load(response)

    def test_missing_duplicate_and_invalid_date_are_400(self):
        for query in ["", "?date=", "?date=2019-11-01", "?date=2019-05-01&date=2019-05-02"]:
            with self.subTest(query=query), self.assertRaises(HTTPError) as raised:
                self.get("/api/predictions" + query)
            self.assertEqual(raised.exception.code, 400)

    def test_cell_null_is_valid_json_and_unknown_cell_is_404(self):
        with self.get("/api/cell?date=2019-05-01&grid_id=cell") as response:
            self.assertIsNone(json.load(response)["features"]["weather"])
        with self.assertRaises(HTTPError) as raised:
            self.get("/api/cell?date=2019-05-01&grid_id=unknown")
        self.assertEqual(raised.exception.code, 404)

    def test_static_allowlist_and_csv_headers(self):
        with self.get("/") as response:
            self.assertIn(b"Ontario Ignition Atlas", response.read())
        with self.get("/api/download?date=2019-05-01") as response:
            self.assertIn("attachment", response.headers["Content-Disposition"])
        with self.assertRaises(HTTPError) as raised:
            self.get("/../AGENTS.md")
        self.assertEqual(raised.exception.code, 404)


@unittest.skipUnless((OUTPUT / "verification.json").exists(), "Reconstruct real artifacts to run integration checks")
class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = DemoStore()

    def test_served_days_match_frozen_prediction_vectors_and_grid_ids(self):
        saved = np.load(OUTPUT / "predictions_2019.npz")
        first = self.store.manifest["date_slices"]["2019-05-01"][0]
        for day in ["2019-05-01", "2019-07-01", "2019-10-31"]:
            start, stop = self.store.manifest["date_slices"][day]
            order = np.argsort(self.store.ids[start:stop])
            result = self.store.predictions(day)
            np.testing.assert_allclose(result["scores"], saved["p"][start-first:stop-first][order], rtol=0, atol=1e-14)
            np.testing.assert_array_equal(result["observed"], saved["y"][start-first:stop-first][order])
            self.assertEqual(len(result["scores"]), 9673)

    def test_cell_feature_order_missingness_and_score_alignment(self):
        X, y, p = self.store.day("2019-07-01")
        missing_index = int(np.flatnonzero(X[:, FEATURE_NAMES.index("cwfis_missing")] == 1)[0])
        result = self.store.cell("2019-07-01", self.store.grid.grid_id.iloc[missing_index])
        self.assertEqual(tuple(result["features"]), FEATURE_NAMES)
        self.assertEqual(result["score"], p[missing_index])
        self.assertEqual(result["features"]["cwfis_missing"], 1)
        self.assertIsNone(result["features"]["cwfis_fwi"])

    def test_csv_retains_all_cells_and_full_precision_scores(self):
        result = self.store.predictions("2019-07-01")
        rows = list(csv.DictReader(io.StringIO(self.store.download("2019-07-01").decode())))
        self.assertEqual(len(rows), 9673)
        self.assertEqual(rows[0]["grid_id"], self.store.grid.grid_id.iloc[0])
        self.assertEqual(float(rows[0]["score"]), result["scores"][0])

    def test_reconstruction_matches_reference_without_test_tuning(self):
        self.assertEqual(self.store.verification["status"], "PASS")
        self.assertEqual(self.store.verification["metric_differences"],
                         dict(average_precision=0, roc_auc=0, brier_score=0, log_loss=0))
        self.assertTrue(self.store.verification["all_eight_confusion_tables_match"])


if __name__ == "__main__":
    unittest.main()
