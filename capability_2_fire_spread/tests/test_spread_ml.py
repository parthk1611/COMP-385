"""Contract tests for the learned spread models: feature safety, past-only inputs and scoring helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import compare_spread_models as CMP  # noqa: E402
import spread_ml as ML  # noqa: E402


WINDOWS = PROJECT_ROOT / "data/raw/fuel_terrain/windows"
PROCESSED = PROJECT_ROOT / "data/processed"
REAL_FIRE = "2012_RED60"  # a calibration fire in the simulator's published tuning sample
HAS_REAL_FIRE = (WINDOWS / f"{REAL_FIRE}_mrdem_dtm_90m.tif").exists() and (PROJECT_ROOT / "data/interim/spread_fire_perimeters.geojson").exists()


class FeatureContractTest(unittest.TestCase):
    def test_no_model_uses_a_forbidden_or_fire_level_column(self):
        fire_columns = set(pd.read_csv(PROCESSED / "ontario_fire_spread_fires_v1.csv", nrows=1).columns)
        for name, (family, feature_set) in ML.MODELS.items():
            features = ML.FEATURE_SETS[feature_set]
            with self.subTest(model=name):
                self.assertEqual(len(features), len(set(features)))
                self.assertFalse(set(features) & ML.FORBIDDEN)
                self.assertFalse(set(features) & fire_columns, "fire-level columns include final outcomes")
                self.assertNotIn(ML.LABEL, features)

    def test_only_the_hybrid_sees_the_simulator_and_the_ablation_has_no_fuel(self):
        for name, (_, feature_set) in ML.MODELS.items():
            sees_simulator = bool(set(ML.FEATURE_SETS[feature_set]) & set(ML.SIMULATOR))
            self.assertEqual(sees_simulator, name.endswith("_hybrid"), name)
        self.assertFalse(set(ML.FEATURE_SETS["no_fuel"]) & set(ML.FUEL))

    def test_every_family_sees_the_same_base_features(self):
        base = {name for name, (_, feature_set) in ML.MODELS.items() if feature_set == "base"}
        self.assertEqual(base, {"logistic", "random_forest", "mlp", "hgb", "xgboost"})


class ScoringHelperTest(unittest.TestCase):
    def test_top_k_mask_takes_the_most_likely_cells(self):
        mask = CMP.predicted_mask(6, np.array([1, 2, 4, 5]), np.array([0.1, 0.9, 0.5, 0.5]), 3)
        np.testing.assert_array_equal(mask, [False, False, True, False, True, True])
        self.assertFalse(CMP.predicted_mask(6, np.array([1, 2]), np.array([0.3, 0.2]), 0).any())

    def test_simulator_ranks_reached_cells_first_then_by_arrival_then_by_distance(self):
        rows = pd.DataFrame({"sim_reached_share": [1.0, 1.0, 0.0, 0.0], "sim_arrival_fraction": [0.2, 0.8, np.nan, np.nan], "distance_to_burned_m": [375, 375, 750, 3000]})
        self.assertEqual(list(np.argsort(-ML.simulator_score(rows))), [0, 1, 2, 3])


try:
    import torch  # noqa: F401

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@unittest.skipUnless(HAS_TORCH, "needs PyTorch (the CNN model)")
class CnnSymmetryTest(unittest.TestCase):
    """Rotating or mirroring a patch must turn its arrows with it, or augmentation would teach the wrong wind."""

    def setUp(self):
        import spread_cnn as CNN

        self.CNN = CNN
        # channel 0: a blob two cells east of the centre; channels 1-2: an arrow pointing east
        self.x = torch.zeros(1, 3, 9, 9)
        self.x[0, 0, 6, 4] = 1.0
        self.x[0, 1], self.x[0, 2] = 1.0, 0.0

    def test_arrows_keep_pointing_at_the_blob_under_all_eight_symmetries(self):
        for flip in (False, True):
            for k in range(4):
                y = self.CNN.apply_symmetry(self.x, flip, k, [(1, 2)])
                east, north = (int(v) - 4 for v in torch.nonzero(y[0, 0])[0])
                arrow = (round(float(y[0, 1, 0, 0])), round(float(y[0, 2, 0, 0])))
                self.assertEqual((east // 2, north // 2), arrow, f"flip={flip}, k={k}")

    def test_label_transform_matches_the_patch_and_undo_reverses_it(self):
        for flip in (False, True):
            for k in range(4):
                moved = self.CNN.apply_symmetry(self.x, flip, k, [(1, 2)])
                torch.testing.assert_close(self.CNN._transform(self.x[:, 0], flip, k), moved[:, 0])
                torch.testing.assert_close(self.CNN.undo(moved[:, 0], flip, k), self.x[:, 0])


@unittest.skipUnless(HAS_REAL_FIRE,"needs the fire's fuel and terrain windows and the perimeters (see README)")
class RealFireTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import run_spread_replay as RUN
        from simulate_spread import Settings

        cls.RUN, cls.settings = RUN, Settings(ros_scale=0.8, flank_scale=0.25)
        cls.history = ML.load_observation_history()

    def features_for(self, observation: int, shared: dict, history: pd.DataFrame) -> pd.DataFrame:
        for step in self.RUN.iter_steps(REAL_FIRE, self.settings, shared=shared):
            if step.observation == observation:
                daily = shared["daily"][REAL_FIRE].set_index("date")
                frame, _ = ML.step_rows(step, ML.static_cell_layers(step.case), daily, history, None, self.RUN.DETECTABLE_SHARE)
                return frame
        self.fail(f"step {observation} not found")

    def test_replay_through_the_step_iterator_reproduces_the_published_simulator_scores(self):
        saved = pd.read_csv(PROCESSED / "simulation/spread_simulator_calibration_steps_v1.csv", dtype={"fire_id": str})
        saved = saved[(saved.fire_id == REAL_FIRE) & (saved.ros_scale == 0.8) & (saved.flank_scale == 0.25)].sort_values("from_observation")
        rows = pd.DataFrame(self.RUN.replay_fire(REAL_FIRE, self.settings))
        columns = [c for c in saved.columns if c in rows.columns and c != "fire_id"]
        np.testing.assert_allclose(rows[columns].round(4).astype(float).values, saved[columns].astype(float).values, rtol=0, atol=1e-9)

    def test_features_do_not_change_when_every_later_pass_is_deleted(self):
        full_shared: dict = {}
        steps = [s.observation for s in self.RUN.iter_steps(REAL_FIRE, self.settings, shared=full_shared)]
        observation = steps[len(steps) // 2]
        full = self.features_for(observation, full_shared, self.history)
        # Keep only what existed up to the next pass (which supplies the label) and remove every later pass.
        cut: dict = {key: value for key, value in full_shared.items()}
        for name, column in [("arrival", "first_observation"), ("detections", "observation"), ("observations", "observation")]:
            cut[name] = {**full_shared[name], REAL_FIRE: full_shared[name][REAL_FIRE][full_shared[name][REAL_FIRE][column] <= observation + 1]}
        history = self.history[~((self.history.index.get_level_values(0) == REAL_FIRE) & (self.history.index.get_level_values(1) > observation))]
        truncated = self.features_for(observation, cut, history)
        pd.testing.assert_frame_equal(full.reset_index(drop=True), truncated.reset_index(drop=True))

    def test_label_marks_exactly_the_cells_first_seen_at_the_next_pass(self):
        shared: dict = {}
        step = next(self.RUN.iter_steps(REAL_FIRE, self.settings, shared=shared))
        daily = shared["daily"][REAL_FIRE].set_index("date")
        frame, summary = ML.step_rows(step, ML.static_cell_layers(step.case), daily, self.history, None, self.RUN.DETECTABLE_SHARE)
        self.assertEqual(int(frame[ML.LABEL].sum()), summary["observed_new_in_radius"])
        np.testing.assert_array_equal(frame[ML.LABEL].to_numpy(), step.observed_new[frame.cell.to_numpy()].astype(np.uint8))
        self.assertFalse(step.start[frame.cell].any(), "a candidate cell is already burned")
        self.assertTrue((frame.distance_to_burned_m <= ML.RADIUS_M).all())


if __name__ == "__main__":
    unittest.main()
