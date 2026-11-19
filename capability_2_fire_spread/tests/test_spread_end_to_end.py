"""End-to-end tests on the real data: the split, the feature build, the saved models and the published results agree.

These read the generated files (the cell table, fitted models and per-step scores under `artifacts/`, the fuel and
terrain windows) and are skipped when those are absent, as in a fresh clone.  Rebuild them with the commands in
the README to run these tests.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.spread_modeling import contract as C  # noqa: E402
from scripts.spread_modeling import evaluation as EV  # noqa: E402


HAS_TABLE = C.CELL_TABLE.exists() and C.CELL_TABLE_STEPS.exists()
HAS_MODELS = HAS_TABLE and all((C.MODEL_DIR / f"{name}.joblib").exists() for name in C.MODELS) and (C.MODEL_DIR / "cnn.predictions.parquet").exists()
HAS_SCORES = C.HOLDOUT_STEP_SCORES.exists()
HAS_WINDOWS = (PROJECT_ROOT / "data/raw/fuel_terrain/windows").exists() and (PROJECT_ROOT / "data/interim/spread_fire_perimeters.geojson").exists()
VIEWER_DATA = PROJECT_ROOT / "viewer/spread_viewer_data.js"


def steps() -> pd.DataFrame:
    return pd.read_csv(C.CELL_TABLE_STEPS, dtype={"fire_id": str})


@unittest.skipUnless(HAS_TABLE, "needs the cell table (python -m scripts.spread_modeling.cell_table)")
class SplitIntegrityTest(unittest.TestCase):
    """Training uses 2012-2020 fires only, testing 2021-2024 fires only, and the counts match the build audit."""

    def test_years_never_cross_the_split_and_no_fire_is_on_both_sides(self):
        s = steps()
        self.assertLessEqual(s[s.split == "calibration"].fire_year.max(), 2020)
        self.assertGreaterEqual(s[s.split == "holdout"].fire_year.min(), 2021)
        self.assertLessEqual(s[s.split == "holdout"].fire_year.max(), 2024)
        both = set(s[s.split == "calibration"].fire_id) & set(s[s.split == "holdout"].fire_id)
        self.assertEqual(both, set())

    def test_counts_match_the_audit(self):
        audit = json.loads(C.CELL_TABLE_AUDIT.read_text(encoding="utf-8"))
        s = steps()
        self.assertEqual(s.split.value_counts().to_dict(), audit["steps_by_split"])
        self.assertEqual(s.groupby("split").fire_id.nunique().to_dict(), audit["fires_by_split"])
        table = pd.read_parquet(C.CELL_TABLE, columns=["split", C.LABEL])
        self.assertEqual(table.split.value_counts().to_dict(), audit["rows_by_split"])
        self.assertEqual(table.groupby("split")[C.LABEL].sum().astype(int).to_dict(), audit["positive_rows_by_split"])

    def test_the_simulators_published_test_steps_are_all_included(self):
        published = steps()[lambda d: d.simulator_holdout_sample]
        self.assertEqual((len(published), published.fire_id.nunique()), (150, 22))
        scores = json.loads(C.SIMULATOR_SCORES.read_text(encoding="utf-8"))
        self.assertTrue(set(published.fire_id) <= set(scores["holdout_fires"]))


@unittest.skipUnless(HAS_TABLE and HAS_WINDOWS, "needs the cell table and the fire grids")
class FeatureRebuildTest(unittest.TestCase):
    """Rebuilding a test step from the processed dataset gives exactly the rows in the saved cell table."""

    def test_one_holdout_fire_rebuilds_exactly(self):
        from scripts.spread_modeling.features import load_observation_history, static_cell_layers, step_rows
        from scripts.spread_modeling.replay import DETECTABLE_SHARE, iter_steps, simulate_step
        from scripts.spread_modeling.simulator import Settings

        s = steps()
        fire_id = s[s.simulator_holdout_sample].sort_values(["window_cells", "fire_id"]).fire_id.iloc[0]  # the smallest published test fire
        scores = json.loads(C.SIMULATOR_SCORES.read_text(encoding="utf-8"))
        settings, shared, history = Settings(scores["chosen_ros_scale"], scores["chosen_flank_scale"]), {}, load_observation_history()
        saved = pd.read_parquet(C.CELL_TABLE, filters=[("fire_id", "==", fire_id)])
        columns = C.FEATURE_SETS["with_simulator"] + [C.LABEL, "in_radius", "sim_new"]
        rebuilt = 0
        for step in iter_steps(fire_id, settings, shared=shared):
            frame, _ = step_rows(step, static_cell_layers(step.case), shared["daily"][fire_id].set_index("date"), history, simulate_step(step, settings), DETECTABLE_SHARE)
            expected = saved[saved.observation == step.observation].sort_values("cell")
            frame = frame.sort_values("cell")
            np.testing.assert_array_equal(frame.cell.to_numpy(), expected.cell.to_numpy())
            pd.testing.assert_frame_equal(frame[columns].reset_index(drop=True), expected[columns].reset_index(drop=True), check_dtype=False, atol=1e-6)
            rebuilt += 1
        self.assertEqual(rebuilt, int((s.fire_id == fire_id).sum()))


@unittest.skipUnless(HAS_MODELS, "needs the fitted models (python -m scripts.spread_modeling.train / train_cnn)")
class SavedModelReproductionTest(unittest.TestCase):
    """Reloading every saved model and scoring the simulator's 150 published test steps gives the published recalls."""

    @classmethod
    def setUpClass(cls):
        s = steps()
        cls.steps = s.set_index(["fire_id", "observation"])
        fires = sorted(s[s.simulator_holdout_sample].fire_id.unique())
        table = pd.read_parquet(C.CELL_TABLE, filters=[("fire_id", "in", fires)])
        cls.rows = table[table.in_radius].reset_index(drop=True)
        cls.published = json.loads(C.COMPARISON.read_text(encoding="utf-8"))["simulator_published_24_fires"]["all_steps"]["by_model"]

    def check(self, name: str, p: np.ndarray):
        recall = EV.matched_recall(self.rows, p, self.steps)
        self.assertEqual(len(recall), 150)
        self.assertAlmostEqual(float(recall.mean()), self.published[f"{name}_matched"]["mean_recall"], delta=6e-5, msg=name)

    def test_every_per_cell_model_reproduces_its_published_recall(self):
        import joblib

        for name in C.MODELS:
            with self.subTest(model=name):
                bundle = joblib.load(C.MODEL_DIR / f"{name}.joblib")
                self.assertEqual(bundle["features"], C.FEATURE_SETS[C.MODELS[name][1]])
                self.check(name, bundle["model"].predict_proba(self.rows[bundle["features"]].to_numpy(np.float32))[:, 1])

    def test_the_cnns_saved_predictions_reproduce_their_published_recall(self):
        for name in ["cnn", "cnn_hybrid"]:
            with self.subTest(model=name):
                saved = pd.read_parquet(C.MODEL_DIR / f"{name}.predictions.parquet")
                p = self.rows[["fire_id", "observation", "cell"]].merge(saved, how="left").p
                self.assertFalse(p.isna().any(), "a candidate cell has no CNN prediction")
                self.check(name, p.to_numpy())


@unittest.skipUnless(HAS_SCORES, "needs the per-step scores (python -m scripts.spread_modeling.compare)")
class ResultConsistencyTest(unittest.TestCase):
    """The published comparison, the simulator's own scores and the per-step scores all agree."""

    @classmethod
    def setUpClass(cls):
        cls.comparison = json.loads(C.COMPARISON.read_text(encoding="utf-8"))
        cls.scores = pd.read_csv(C.HOLDOUT_STEP_SCORES, dtype={"fire_id": str})

    def test_the_simulator_reproduces_its_published_score(self):
        published = json.loads(C.SIMULATOR_SCORES.read_text(encoding="utf-8"))["holdout"]
        replayed = self.comparison["simulator_published_24_fires"]["all_steps"]["by_model"]["simulator"]
        self.assertEqual((replayed["steps"], replayed["mean_recall"]), (published["steps"], published["mean_recall"]))

    def test_every_models_headline_recall_is_the_mean_of_its_step_scores(self):
        by_model = self.comparison["all_scored_holdout_fires"]["all_steps"]["by_model"]
        for model, group in self.scores[self.scores.model != "even_growth_rank"].groupby("model"):
            with self.subTest(model=model):
                self.assertEqual(len(group), 770)
                self.assertAlmostEqual(round(float(group.recall.mean()), 4), by_model[model]["mean_recall"], places=4)

    def test_the_cnn_beats_the_simulator_with_an_interval_above_zero(self):
        difference = self.comparison["all_scored_holdout_fires"]["all_steps"]["difference_from_simulator"]["cnn_matched"]["recall"]
        self.assertGreater(difference["low"], 0)
        self.assertEqual((difference["steps"], difference["fires"]), (770, 125))


@unittest.skipUnless(HAS_SCORES and VIEWER_DATA.exists(), "needs the per-step scores and the exported viewer data")
class ViewerConsistencyTest(unittest.TestCase):
    """Every number the viewer shows for a step is the comparison's number for that step."""

    def test_viewer_step_scores_match_the_comparison(self):
        text = VIEWER_DATA.read_text(encoding="utf-8")
        data = json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))
        scores = pd.read_csv(C.HOLDOUT_STEP_SCORES, dtype={"fire_id": str}).set_index(["fire_id", "from_observation", "model"]).recall
        checked = 0
        for fire in data["fires"]:
            for step in fire["steps"]:
                for model, key in [("cnn_matched", "cnnRecall"), ("simulator", "fbpRecall")]:
                    self.assertAlmostEqual(step["score"][key], scores[(fire["id"], step["from"], model)], delta=6e-4)
                    checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
