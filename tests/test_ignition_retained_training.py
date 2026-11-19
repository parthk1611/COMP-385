"""The main export uses all persisted inputs and never fits reserved-year rows."""
import json
import pickle
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

from scripts.ignition_modeling import contract, run


class RetainedExportTests(unittest.TestCase):
    def test_main_joblib_matches_independent_retained_fit_and_excludes_2017(self):
        with tempfile.TemporaryDirectory() as temporary, threadpool_limits(limits=2):
            root = Path(temporary)
            cache = root / "cache"
            cache.mkdir()
            training_rows, reserved_rows = 280, 40
            n = training_rows + reserved_rows
            rng = np.random.default_rng(385)
            X = rng.normal(size=(n, len(contract.FEATURE_NAMES)))
            history = contract.FEATURE_NAMES.index(contract.HISTORY_FEATURE)
            censor = contract.FEATURE_NAMES.index(contract.HISTORY_CENSOR_FEATURE)
            X[:, history] = np.arange(n) + 1
            X[::3, history] = np.nan
            X[:, censor] = np.isnan(X[:, history])
            X[::5, contract.FEATURE_NAMES.index("cwfis_temp_c")] = np.nan
            X[training_rows:, 0] = 1000000
            y = (np.arange(n) % 7 == 0).astype(np.uint8)
            X.tofile(cache / "X.f64")
            y.tofile(cache / "y.u8")
            np.zeros(n, dtype=np.uint16).tofile(cache / "grid.u16")
            source = json.loads((contract.ROOT / "data/raw/cwfis/manifest.json").read_text())
            manifest = {
                "rows": n, "features": list(contract.FEATURE_NAMES),
                "cache_version": contract.CACHE_VERSION,
                "feature_set_version": contract.FEATURE_SET_VERSION,
                "original_panel_sha256": "fixture-panel",
                "corrected_value_checks": {"status": "PASS"},
                "weather_source_audit": {"source_sha256": source["archive_sha256"]},
                "date_slices": {f"{year}-05-01": [40 * (year - 2010), 40 * (year - 2009)]
                                for year in range(2010, 2018)},
            }
            (cache / "manifest.json").write_text(json.dumps(manifest))
            reference = HistGradientBoostingClassifier(
                **contract.RETAINED_HGB_PARAMS, categorical_features=None,
                early_stopping=False, random_state=385).fit(X[:training_rows], y[:training_rows])
            reference_path = root / "experiment.pkl"
            with reference_path.open("wb") as stream:
                pickle.dump({"classifier": reference,
                             "transformed_features": list(contract.FEATURE_NAMES)}, stream)
            output = root / "export"
            verification = run.execute(cache, output, reference_pickle=reference_path)
            bundle = joblib.load(output / "selected_system.joblib")
            metadata = json.loads((output / "model_metadata.json").read_text())
            self.assertEqual(bundle["pipeline"]["preprocessor"].n_samples_seen_, training_rows)
            self.assertEqual(bundle["pipeline"]["classifier"].n_features_in_, 39)
            self.assertEqual(metadata["features"], list(contract.FEATURE_NAMES))
            self.assertEqual(metadata["fit_years"], [2010, 2016])
            self.assertEqual(metadata["training"]["rows"], training_rows)
            self.assertEqual(metadata["cache_version"], contract.CACHE_VERSION)
            self.assertEqual(metadata["params"], reference.get_params())
            self.assertEqual(len(metadata["commit"]), 40)
            self.assertEqual(verification["reference_comparison"]["compared_rows"], training_rows)
            self.assertEqual(verification["reference_comparison"]["differing_predictions"], 0)
            np.testing.assert_array_equal(
                run.predict_bundle(bundle, X).view(np.uint64),
                reference.predict_proba(X)[:, 1].view(np.uint64))
            bundle["cache_version"] = "ignition-v1-weather-asof-global-date-v2"
            with self.assertRaisesRegex(ValueError, "cache version"):
                run.predict_bundle(bundle, X)


if __name__ == "__main__":
    unittest.main()
