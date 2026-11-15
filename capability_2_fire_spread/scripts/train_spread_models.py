#!/usr/bin/env python3
"""Train the learned spread models on calibration fires (2012-2020) only.

Four classifier families answer the same per-cell question with the same base
features (geometry, persistence, weather, fuel, terrain; see `spread_ml.py`):

- `logistic`: logistic regression, a weighted sum of the features (linear);
- `random_forest`: many deep decision trees on random row and feature samples, averaged;
- `mlp`: a small neural network (two hidden layers);
- `hgb`: histogram gradient boosting, shallow trees each correcting the last;
- `xgboost`: gradient boosting with XGBoost on the GPU (row and feature subsampling, a deeper search).

Two more gradient-boosting models change the features instead of the family:
`hgb_no_fuel` (an ablation that checks fuel is not leaking the final perimeter)
and `hgb_hybrid` (base features plus the tuned simulator's prediction); `xgboost_hybrid`
does the same for XGBoost.

Each model's settings are chosen by leave-one-fire-year-out cross-validation
within 2012-2020, on the mean per-step average precision (how well it ranks the
cells that will burn within a step).  Holdout fires (2021-2024) are not read.
The out-of-fold predictions also set each model's area scale: how many cells it
predicts in a step is `scale x sum of probabilities`, with the scale chosen so
the median predicted/observed area is 1.3, the simulator's own tuning target.
Each model is then refitted on every calibration fire.  For reference, the
report also gives the simulator's and even growth's per-step AP on the same
calibration steps and folds.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from spread_common import DATASET_VERSION, PROCESSED, PROJECT_ROOT, action_log
from spread_ml import FEATURE_SETS, FORBIDDEN, LABEL, MODELS, simulator_score


TABLE = PROCESSED / "ml/spread_ml_cells_v1.parquet"
MODEL_DIR = PROJECT_ROOT / "artifacts/spread_models"
REPORT = PROCESSED / "simulation/spread_models_v1_training.json"
TARGET_AREA_RATIO = 1.3
SEED = 385
XGB_DEVICE = "cuda"
# A small, declared grid per family.  Internal early stopping is off everywhere: it would hold out a random row
# sample, mixing cells of one step and fire on both sides of the split.
CANDIDATES = {
    "logistic": [{"C": c} for c in [0.1, 1.0]],
    "random_forest": [{"min_samples_leaf": leaf, "n_estimators": 200, "max_features": "sqrt", "max_samples": 0.25} for leaf in [20, 100]],
    "mlp": [{"hidden_layer_sizes": (64, 32), "alpha": alpha, "batch_size": 4096, "max_iter": 20, "learning_rate_init": 1e-3} for alpha in [1e-4, 1e-3]],
    "hgb": [
        {"max_iter": iterations, "learning_rate": 0.05, "max_leaf_nodes": leaves, "min_samples_leaf": 100, "l2_regularization": 1.0}
        for iterations in [200, 400] for leaves in [15, 31]
    ],
    "xgboost": [
        {"n_estimators": trees, "max_depth": depth, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5, "reg_lambda": 1.0}
        for trees in [300, 600] for depth in [6, 8]
    ],
}  # fmt: skip


def make_model(family: str, params: dict):
    """A fresh classifier.  Imputation (with missing-value indicators) and scaling are fitted inside each training fold."""
    impute = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    if family == "hgb":
        return HistGradientBoostingClassifier(**params, early_stopping=False, random_state=SEED)  # handles missing values itself
    if family == "logistic":
        return make_pipeline(impute, StandardScaler(), LogisticRegression(**params, max_iter=1000))
    if family == "random_forest":
        return make_pipeline(impute, RandomForestClassifier(**params, n_jobs=-1, random_state=SEED))
    if family == "xgboost":
        from xgboost import XGBClassifier  # only needed for this family; uses the GPU when one is present

        return XGBClassifier(**params, tree_method="hist", device=XGB_DEVICE, random_state=SEED, n_jobs=8)  # handles missing values itself
    if family == "mlp":
        return make_pipeline(impute, StandardScaler(), MLPClassifier(**params, early_stopping=False, random_state=SEED))
    raise ValueError(f"unknown family {family}")


def mean_step_ap(frame: pd.DataFrame, scores: np.ndarray) -> float:
    """Average precision within each step (ranking the step's candidate cells), averaged over steps."""
    values = []
    for _, index in frame.groupby(["fire_id", "observation"]).indices.items():
        labels = frame[LABEL].values[index]
        if labels.any():
            values.append(average_precision_score(labels, scores[index]))
    return float(np.mean(values))


def area_scale(frame: pd.DataFrame, probability: np.ndarray) -> float:
    """Scale on the summed probabilities that makes the median predicted/observed new area equal the target."""
    steps = frame.assign(p=probability).groupby(["fire_id", "observation"]).agg(expected=("p", "sum"), observed=(LABEL, "sum"))
    steps = steps[steps.observed > 0]
    return float(TARGET_AREA_RATIO / np.median(steps.expected / steps.observed))


def load_calibration() -> pd.DataFrame:
    table = pd.read_parquet(TABLE)
    if not set(table.split) <= {"calibration", "holdout"}:
        raise ValueError("Unexpected split in the learned-model table")
    table = table[(table.split == "calibration") & table.in_radius].reset_index(drop=True)
    if table.fire_year.max() > 2020:
        raise ValueError("Calibration rows must come from 2012-2020")
    return table


def reference_scores(table: pd.DataFrame, years: list[int]) -> dict:
    """The simulator's and even growth's per-step AP on the same calibration folds: nothing is fitted."""
    out = {}
    for name, scores in [("simulator", simulator_score(table)), ("even_growth", -table.distance_to_active_m.to_numpy())]:
        folds = {int(year): mean_step_ap(table[(table.fire_year == year).to_numpy()], scores[(table.fire_year == year).to_numpy()]) for year in years}
        out[name] = {"mean_step_ap": float(np.mean(list(folds.values()))), "fold_mean_step_ap": folds}
    return out


def train(name: str, table: pd.DataFrame, years: list[int], log) -> dict:
    family, feature_set = MODELS[name]
    features = FEATURE_SETS[feature_set]
    if set(features) & FORBIDDEN:
        raise ValueError(f"{name} uses a forbidden feature")
    X, y = table[features].to_numpy(np.float32), table[LABEL].to_numpy()
    results, out_of_fold = [], {}
    for index, params in enumerate(CANDIDATES[family]):
        began, fold_ap, fold_pooled, oof = time.perf_counter(), {}, {}, np.zeros(len(table))
        for year in years:
            test = (table.fire_year == year).to_numpy()
            model = make_model(family, params).fit(X[~test], y[~test])
            oof[test] = model.predict_proba(X[test])[:, 1]
            fold_ap[int(year)] = mean_step_ap(table[test], oof[test])
            fold_pooled[int(year)] = float(average_precision_score(y[test], oof[test]))
        result = {"candidate": index, "params": params, "mean_step_ap": float(np.mean(list(fold_ap.values()))),
                  "fold_mean_step_ap": fold_ap, "fold_pooled_ap": fold_pooled, "oof_log_loss": float(log_loss(y, oof)),
                  "seconds": round(time.perf_counter() - began, 1)}  # fmt: skip
        results.append(result)
        out_of_fold[index] = oof
        log.info(f"{name} candidate {index} {params}: mean per-step AP {result['mean_step_ap']:.4f} ({result['seconds']}s)")
    best = max(results, key=lambda r: r["mean_step_ap"])
    scale = area_scale(table, out_of_fold[best["candidate"]])
    model = make_model(family, best["params"]).fit(X, y)
    joblib.dump({"name": name, "family": family, "feature_set": feature_set, "features": features, "model": model, "area_scale": scale, "params": best["params"]}, MODEL_DIR / f"{name}.joblib")
    log.info(f"{name}: chose candidate {best['candidate']}, area scale {scale:.3f}; refitted on all calibration fires")
    return {"family": family, "feature_set": feature_set, "features": features, "candidates": results, "selected": best["candidate"],
            "area_scale": scale, "training_rows": int(len(table)), "training_positives": int(y.sum())}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS), help="Train only these; the others' saved results are kept.")
    args = parser.parse_args()
    log = action_log("12 train learned spread models")
    table = load_calibration()
    years = [int(y) for y in sorted(table.fire_year.unique())]
    log.info(f"START: {args.models} on {len(table):,} candidate rows, {int(table[LABEL].sum()):,} positives, {table.groupby(['fire_id', 'observation']).ngroups} steps, {table.fire_id.nunique()} fires, years {years}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    previous = json.loads(REPORT.read_text(encoding="utf-8")).get("models", {}) if REPORT.exists() else {}
    report = {"dataset_version": DATASET_VERSION, "created_at_utc": datetime.now(UTC).isoformat(), "training_years": years,
              "folds": "leave one fire year out", "selection_metric": "mean over folds of mean per-step average precision",
              "candidates": CANDIDATES, "target_area_ratio": TARGET_AREA_RATIO, "reference": reference_scores(table, years),
              "models": {name: previous[name] for name in MODELS if name in previous and name not in args.models}}  # fmt: skip
    for name in args.models:
        report["models"][name] = train(name, table, years, log)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")  # after each model, so a long run keeps its progress
    report["models"] = {name: report["models"][name] for name in MODELS if name in report["models"]}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log.info("DONE: wrote spread_models_v1_training.json and models in artifacts/spread_models/")


if __name__ == "__main__":
    main()
