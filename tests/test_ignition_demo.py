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

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

from scripts.ignition_modeling.contract import CACHE_VERSION, RETAINED_HGB_PARAMS, SEED
from scripts.ignition_modeling.preprocessing import HistoryIndicator
from scripts.ignition_modeling.run import predict_bundle
from scripts.ignition_modeling.weather import sha256
from scripts.ignition_demo.common import read_json, write_json

from scripts.ignition_demo.common import (
    CACHE, OUTPUT, FEATURE_NAMES, alert_policy, checked_probabilities, confusion, validate_date,
)
from scripts.ignition_demo.server import DemoStore, make_handler


class PolicyTests(unittest.TestCase):
    def test_policy_is_illustrative_without_validation_claims(self):
        policy = alert_policy()
        self.assertIsNone(policy["selection_year"])
        self.assertIsNone(policy["metric"])
        self.assertEqual(policy["default_index"], 4)
        self.assertEqual(policy["threshold"], .001)
        self.assertEqual([item["threshold"] for item in policy["choices"]],
                         [1e-5, 5e-5, .0001, .0005, .001, .005, .01, .05])
        self.assertTrue(all(item["validation"] is None for item in policy["choices"]))

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


def export_fixture(root):
    """Small real 39-input persisted model/cache, with reversed on-disk grid order."""
    root = Path(root)
    output, cache = root / "model", root / "cache"
    output.mkdir(); cache.mkdir()
    rng = np.random.default_rng(SEED)
    X = rng.normal(size=(300, len(FEATURE_NAMES)))
    X[:, FEATURE_NAMES.index("cwfis_missing")] = 0
    X[:, FEATURE_NAMES.index("cwfis_station_count")] = 2
    X[:, FEATURE_NAMES.index("fire_history_days_since_same_cell__censored")] = 0
    X[0, FEATURE_NAMES.index("cwfis_fwi")] = np.nan
    y = (X[:, 0] > 0).astype("uint8")
    model = Pipeline([("features", HistoryIndicator()),
                      ("classifier", HistGradientBoostingClassifier(
                          **RETAINED_HGB_PARAMS, early_stopping=False,
                          categorical_features=None, random_state=SEED))])
    with threadpool_limits(limits=2):
        model.fit(X, y)
    training = {"years": list(range(2010, 2017))}
    bundle = {"pipeline": model, "calibrator": None, "features": list(FEATURE_NAMES),
              "cache_version": CACHE_VERSION, "training": training}
    joblib.dump(bundle, output / "selected_system.joblib")
    X[::-1].tofile(cache / "X.f64")
    y[::-1].tofile(cache / "y.u8")
    np.arange(len(y), dtype="uint16")[::-1].tofile(cache / "grid.u16")
    manifest = {"cache_version": CACHE_VERSION, "features": list(FEATURE_NAMES),
                "rows": len(y), "original_panel_sha256": "fixture-panel",
                "date_slices": {"2019-05-01": [0, len(y)]}}
    write_json(cache / "manifest.json", manifest)
    grid = pd.DataFrame({"grid_id": ["cell" if i == 0 else f"cell-{i}" for i in range(len(y))],
                         "grid_x_m": np.arange(len(y)) * 10000, "grid_y_m": 0,
                         "centroid_longitude": -80., "centroid_latitude": 50.})
    grid_path = root / "grid.csv"
    grid.to_csv(grid_path, index=False)
    metadata = {"artifact_version": "retained-coordinate-hgb-v1",
                "params": model.steps[-1][1].get_params(), "features": list(FEATURE_NAMES),
                "fit_years": [2010, 2016], "training": training, "cache_version": CACHE_VERSION,
                "source_panel_sha256": "fixture-panel", "model_sha256": sha256(output / "selected_system.joblib"),
                "cache_manifest_sha256": sha256(cache / "manifest.json"),
                "cache_sha256": {name: sha256(cache / name) for name in
                                 ("manifest.json", "X.f64", "y.u8", "grid.u16")}}
    write_json(output / "model_metadata.json", metadata)
    write_json(output / "verification.json", {
        "status": "PASS", "model_sha256": metadata["model_sha256"],
        "metadata_sha256": sha256(output / "model_metadata.json"),
        "cache_manifest_sha256": metadata["cache_manifest_sha256"]})
    return output, cache, grid_path, X, y, bundle


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output, cls.cache, cls.grid_path, cls.X, cls.y, cls.bundle = export_fixture(cls.temporary.name)
        cls.store = DemoStore(cls.output, cls.cache, cls.grid_path)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.limits = threadpool_limits(limits=2)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.temporary.cleanup()
        cls.limits.restore_original_limits()

    def get(self, path):
        return urlopen(self.url + path, timeout=10)

    def test_metadata_and_real_model_predictions(self):
        for path in ["/api/metadata", "/api/predictions?date=2019-05-01"]:
            with self.get(path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("application/json", response.headers["Content-Type"])
                result = json.load(response)
            if path == "/api/metadata":
                self.assertEqual(result["feature_count"], 39)
                self.assertEqual(result["params"]["max_iter"], 80)
                self.assertEqual(result["features"], list(FEATURE_NAMES))
                self.assertEqual(result["results"], {})
                self.assertIsNone(result["published_2019"])
            else:
                with threadpool_limits(limits=2):
                    expected = predict_bundle(self.bundle, self.X)
                np.testing.assert_array_equal(result["scores"], expected)
                np.testing.assert_array_equal(result["observed"], self.y)

    def test_map_uses_frozen_grid_footprint_without_external_boundary(self):
        from shapely.geometry import shape
        with self.get("/api/grid") as response:
            result = json.load(response)
        self.assertEqual(result["boundary_kind"], "frozen_10km_grid_footprint")
        footprint = shape(result["boundary"])
        self.assertEqual(footprint.bounds, (0, 0, 3000000, 10000))
        self.assertEqual(footprint.area, 300 * 10000 * 10000)
        self.assertEqual([cell["id"] for cell in result["cells"]], self.store.grid.grid_id.tolist())

    def test_missing_duplicate_and_invalid_date_are_400(self):
        for query in ["", "?date=", "?date=2019-11-01", "?date=2019-05-01&date=2019-05-02"]:
            with self.subTest(query=query), self.assertRaises(HTTPError) as raised:
                self.get("/api/predictions" + query)
            self.assertEqual(raised.exception.code, 400)

    def test_cell_null_is_valid_json_and_unknown_cell_is_404(self):
        with self.get("/api/cell?date=2019-05-01&grid_id=cell") as response:
            result = json.load(response)
            self.assertIsNone(result["features"]["cwfis_fwi"])
            self.assertEqual(tuple(result["features"]), FEATURE_NAMES)
        with self.assertRaises(HTTPError) as raised:
            self.get("/api/cell?date=2019-05-01&grid_id=unknown")
        self.assertEqual(raised.exception.code, 404)

    def test_static_allowlist_and_csv_headers(self):
        with self.get("/") as response:
            page = response.read()
            self.assertIn(b"Ontario Ignition Atlas", page)
            self.assertIn(b'href="/architecture"', page)
        with self.get("/architecture") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
            page = response.read()
            self.assertIn(b"implemented architecture", page)
            self.assertIn(b'data-node-id="coordinate-hgb"', page)
            self.assertIn(b'data-node-id="cnn-training"', page)
        with self.get("/api/download?date=2019-05-01") as response:
            self.assertIn("attachment", response.headers["Content-Disposition"])
        with self.assertRaises(HTTPError) as raised:
            self.get("/../AGENTS.md")
        self.assertEqual(raised.exception.code, 404)


class ExportIntegrityTests(unittest.TestCase):
    def test_rejects_old_model_contracts_and_tampered_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            output, cache, grid, _, _, _ = export_fixture(temporary)
            original_metadata = read_json(output / "model_metadata.json")
            original_verification = read_json(output / "verification.json")
            for field, value in [
                ("features", list(FEATURE_NAMES[:36])),
                ("cache_version", "ignition-v1-weather-asof-global-date-v2"),
                ("fit_years", [2010, 2019]),
                ("params", {**original_metadata["params"], "max_iter": 40}),
                ("params", {**original_metadata["params"], "random_state": 1}),
                ("params", {**original_metadata["params"], "early_stopping": True}),
                ("source_panel_sha256", "different-panel"),
            ]:
                with self.subTest(field=field):
                    write_json(output / "model_metadata.json", {**original_metadata, field: value})
                    write_json(output / "verification.json", {
                        **original_verification, "metadata_sha256": sha256(output / "model_metadata.json")})
                    with self.assertRaises(ValueError):
                        DemoStore(output, cache, grid)
            write_json(output / "model_metadata.json", original_metadata)
            write_json(output / "verification.json", original_verification)
            for path in [output / "model_metadata.json", output / "selected_system.joblib", cache / "X.f64"]:
                with self.subTest(path=path.name):
                    original = path.read_bytes()
                    try:
                        with path.open("ab") as stream:
                            stream.write(b" ")
                        with self.assertRaisesRegex(ValueError, "checksum|fingerprint"):
                            DemoStore(output, cache, grid)
                    finally:
                        path.write_bytes(original)


@unittest.skipUnless((OUTPUT / "verification.json").exists(), "Reconstruct real artifacts to run integration checks")
class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = DemoStore()

    def test_served_days_match_main_export_and_grid_ids(self):
        for day in ["2019-05-01", "2019-07-01", "2019-10-31"]:
            start, stop = self.store.manifest["date_slices"][day]
            order = np.argsort(self.store.ids[start:stop])
            result = self.store.predictions(day)
            expected = predict_bundle(self.store.bundle, self.store.X[start:stop][order])
            np.testing.assert_array_equal(result["scores"], expected)
            np.testing.assert_array_equal(result["observed"], self.store.y[start:stop][order])
            self.assertEqual(len(result["scores"]), len(self.store.grid))

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

    def test_main_export_integrity_and_retained_configuration(self):
        self.assertEqual(self.store.verification["status"], "PASS")
        self.assertEqual(self.store.model_metadata["params"]["max_iter"], 80)
        self.assertEqual(self.store.model_metadata["features"], list(FEATURE_NAMES))
        self.assertEqual(self.store.results, {})


if __name__ == "__main__":
    unittest.main()
