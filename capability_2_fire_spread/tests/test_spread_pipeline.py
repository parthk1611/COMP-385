"""Unit tests for the spread modelling pipeline: the data split, the scoring helpers, every model family and the
training loop.  They use small synthetic data, so they run anywhere, without the generated cell table or models."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.spread_modeling import contract as C  # noqa: E402
from scripts.spread_modeling import evaluation as EV  # noqa: E402
from scripts.spread_modeling import train as TRAIN  # noqa: E402


def synthetic_table(years=(2012, 2013, 2014), steps_per_year=4, cells=60, seed=0) -> pd.DataFrame:
    """Candidate-cell rows shaped like the cell table: every base feature, a label, fire, step and year."""
    rng = np.random.default_rng(seed)
    frames = []
    for year in years:
        for step in range(steps_per_year):
            frame = pd.DataFrame(rng.normal(size=(cells, len(C.FEATURE_SETS["base"]))), columns=C.FEATURE_SETS["base"])
            frame["distance_to_burned_m"] = rng.uniform(375, 6000, cells)
            frame[C.LABEL] = (rng.random(cells) < 1 / (1 + frame.distance_to_burned_m / 800)).astype(np.uint8)
            frame.loc[0, C.LABEL] = 1  # every step has new burning
            frame["previous_spread_p90_m"] = np.where(rng.random(cells) < 0.2, np.nan, frame.previous_spread_p90_m)  # missing values
            frame = frame.assign(fire_id=f"{year}_F{step % 2}", observation=step, cell=np.arange(cells), fire_year=year, split="calibration", in_radius=True)
            frames.append(frame)
    return pd.concat(frames, ignore_index=True)


class SplitRuleTest(unittest.TestCase):
    """Fires are split by year alone: calibration 2012-2020, holdout 2021-2024, and 2025 has no satellite archive yet."""

    def test_every_fire_is_split_by_its_year(self):
        fires = pd.read_csv(PROJECT_ROOT / "data/processed/ontario_fire_spread_fires_v1.csv", usecols=["fire_id", "fire_year", "split"])
        expected = np.select([fires.fire_year <= 2020, fires.fire_year <= 2024], ["calibration", "holdout"], "no_satellite_archive")
        self.assertTrue((fires.split == expected).all())
        self.assertEqual(fires.fire_year.min(), 2012)
        self.assertFalse(fires.fire_id.duplicated().any(), "a fire appears twice")


class ScoringTest(unittest.TestCase):
    def test_step_ap_is_undefined_without_new_burning_and_one_for_a_perfect_ranking(self):
        self.assertIsNone(EV.step_ap(np.zeros(5, dtype=int), np.arange(5.0)))
        self.assertAlmostEqual(EV.step_ap(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])), 1.0)

    def test_mean_step_ap_averages_only_steps_with_new_burning(self):
        frame = pd.DataFrame({"fire_id": "F", "observation": [1, 1, 1, 2, 2, 2], C.LABEL: [1, 0, 0, 0, 0, 0]})
        scores = np.array([0.9, 0.1, 0.2, 0.5, 0.5, 0.5])
        self.assertAlmostEqual(EV.mean_step_ap(frame, scores), 1.0)  # step 2 has no new burning and is left out

    def test_area_scale_brings_the_median_area_ratio_to_the_target(self):
        rng = np.random.default_rng(1)
        frame = synthetic_table(steps_per_year=6)
        p = rng.uniform(0, 0.3, len(frame))
        scale = EV.area_scale(frame, p)
        steps = frame.assign(p=p).groupby(["fire_id", "observation", "fire_year"]).agg(expected=("p", "sum"), observed=(C.LABEL, "sum"))
        # the scale is set on (fire, step) groups; with distinct fire ids per year this equals the per-step median
        ratio = np.median(scale * steps.expected / steps.observed)
        self.assertAlmostEqual(ratio, C.TARGET_AREA_RATIO, delta=0.35)
        self.assertGreater(scale, 0)

    def test_matched_recall_counts_new_cells_among_the_top_k_over_all_new_cells(self):
        frame = pd.DataFrame({"fire_id": "F", "observation": 1, "cell": np.arange(6), C.LABEL: [1, 1, 0, 0, 1, 0]})
        steps = pd.DataFrame({"fire_id": ["F"], "observation": [1], "simulated_new_cells": [2], "observed_new_cells": [4]}).set_index(["fire_id", "observation"])
        recall = EV.matched_recall(frame, np.array([0.9, 0.1, 0.8, 0.0, 0.7, 0.2]), steps)
        # top 2 are cells 0 and 2: one new cell found; 4 new cells were seen (one beyond the candidate radius)
        self.assertAlmostEqual(recall.iloc[0], 1 / 4)

    def test_bootstrap_difference_gives_the_mean_and_an_interval_around_it(self):
        rows = []
        for fire in range(12):
            for step in range(3):
                rows += [{"fire_id": f"F{fire}", "from_observation": step, "model": "simulator", "recall": 0.3},
                         {"fire_id": f"F{fire}", "from_observation": step, "model": "cnn", "recall": 0.4 + 0.01 * (fire % 3)}]  # fmt: skip
        result = EV.bootstrap_difference(pd.DataFrame(rows), "cnn", "recall", np.random.default_rng(385))
        self.assertAlmostEqual(result["mean"], 0.11, places=4)
        self.assertLessEqual(result["low"], result["mean"])
        self.assertGreaterEqual(result["high"], result["mean"])
        self.assertEqual((result["steps"], result["fires"]), (36, 12))


class ModelFamilyTest(unittest.TestCase):
    """Every model family builds, trains on rows with missing values and returns valid probabilities."""

    def test_each_family_fits_and_predicts_probabilities(self):
        table = synthetic_table()
        X, y = table[C.FEATURE_SETS["base"]].to_numpy(np.float32), table[C.LABEL].to_numpy()
        for family in sorted({f for f, _ in C.MODELS.values()}):
            with self.subTest(family=family):
                module = TRAIN.family(family)
                self.assertGreater(len(module.CANDIDATES), 0)
                params = dict(module.CANDIDATES[0])
                if family == "random_forest":
                    params["n_estimators"] = 10
                if family == "gradient_boosting":
                    params["max_iter"] = 10
                if family == "xgboost_gpu":
                    params["n_estimators"] = 10
                if family == "mlp":
                    params["max_iter"] = 2
                p = module.make_model(params).fit(X, y).predict_proba(X)[:, 1]
                self.assertEqual(p.shape, (len(X),))
                self.assertTrue(np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all())


class _RecordingModel:
    """A stand-in classifier that records how many rows each fit saw."""

    seen: list[int] = []

    def fit(self, X, y):
        _RecordingModel.seen.append(len(X))
        return self

    def predict_proba(self, X):
        p = np.linspace(0.01, 0.2, len(X))
        return np.column_stack([1 - p, p])


class TrainingLoopTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.saved = TRAIN.MODEL_DIR
        TRAIN.MODEL_DIR = self.folder
        self.stub = types.SimpleNamespace(CANDIDATES=[{"setting": 1}], make_model=lambda params: _RecordingModel())
        self.family = TRAIN.family
        TRAIN.family = lambda name: self.stub
        _RecordingModel.seen = []

    def tearDown(self):
        TRAIN.MODEL_DIR = self.saved
        TRAIN.family = self.family

    def test_each_fold_leaves_out_exactly_its_year_and_the_final_fit_uses_every_row(self):
        table = synthetic_table(years=(2012, 2013, 2014))
        log = types.SimpleNamespace(info=lambda message: None)
        result = TRAIN.train("logistic", table, [2012, 2013, 2014], log)
        per_year = table.groupby("fire_year").size()
        expected = [len(table) - per_year[year] for year in (2012, 2013, 2014)] + [len(table)]
        self.assertEqual(_RecordingModel.seen, expected)
        self.assertEqual(set(result["candidates"][0]["fold_mean_step_ap"]), {2012, 2013, 2014})
        self.assertGreater(result["area_scale"], 0)
        self.assertTrue((self.folder / "logistic.joblib").exists())

    def test_a_forbidden_feature_stops_training(self):
        saved = dict(C.FEATURE_SETS)
        try:
            TRAIN.FEATURE_SETS["base"] = C.FEATURE_SETS["base"] + ["reported_size_ha"]
            with self.assertRaises(ValueError):
                TRAIN.train("logistic", synthetic_table(), [2012, 2013, 2014], types.SimpleNamespace(info=lambda m: None))
        finally:
            TRAIN.FEATURE_SETS.clear()
            TRAIN.FEATURE_SETS.update(saved)

    def test_training_refuses_rows_from_the_test_years(self):
        path = self.folder / "cells.parquet"
        synthetic_table(years=(2019, 2021)).to_parquet(path)
        saved = TRAIN.CELL_TABLE
        try:
            TRAIN.CELL_TABLE = path
            with self.assertRaises(ValueError):
                TRAIN.load_calibration()
        finally:
            TRAIN.CELL_TABLE = saved


if __name__ == "__main__":
    unittest.main()
