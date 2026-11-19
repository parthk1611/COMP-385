"""Experiment 2: train the per-cell spread models on calibration fires (2012-2020) only.

Each model in `contract.MODELS` is a family module (`logistic`, `random_forest`,
`mlp`, `gradient_boosting`, `xgboost_gpu`) with a feature set.  Its settings are
chosen by leave-one-fire-year-out cross-validation within 2012-2020, on the mean
per-step average precision.  Holdout fires (2021-2024) are not read.  The
out-of-fold predictions also set its area scale (see `evaluation.area_scale`).
It is then refitted on every calibration fire and saved.  The report also gives
the simulator's and even growth's per-step AP on the same folds, with nothing
fitted.  Writes `docs/modeling/cell_models_training.json`.

    python -m scripts.spread_modeling.train                     # all eight per-cell models
    python -m scripts.spread_modeling.train --models logistic   # only these; the others' results are kept
"""

from __future__ import annotations

import argparse
import importlib
import json
import time
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, log_loss

from scripts.spread_common import DATASET_VERSION, action_log

from .contract import CELL_MODELS_TRAINING, CELL_TABLE, FEATURE_SETS, FORBIDDEN, LABEL, MODEL_DIR, MODELS, TARGET_AREA_RATIO
from .evaluation import area_scale, mean_step_ap, simulator_score


def family(name: str):
    """The module that builds a model of this family: it has CANDIDATES and make_model(params)."""
    return importlib.import_module(f"{__package__}.{name}")


def load_calibration() -> pd.DataFrame:
    """Candidate cells of calibration fires (2012-2020)."""
    table = pd.read_parquet(CELL_TABLE)
    table = table[(table.split == "calibration") & table.in_radius].reset_index(drop=True)
    if table.fire_year.max() > 2020:
        raise ValueError("Calibration rows must come from 2012-2020")
    return table


def reference_scores(table: pd.DataFrame, years: list[int]) -> dict:
    """The simulator's and even growth's per-step AP on the same calibration folds: nothing is fitted."""
    out = {}
    for name, scores in [("simulator", simulator_score(table)), ("even_growth", -table.distance_to_active_m.to_numpy())]:
        folds = {year: mean_step_ap(table[(table.fire_year == year).to_numpy()], scores[(table.fire_year == year).to_numpy()]) for year in years}
        out[name] = {"mean_step_ap": float(np.mean(list(folds.values()))), "fold_mean_step_ap": folds}
    return out


def train(name: str, table: pd.DataFrame, years: list[int], log) -> dict:
    family_name, feature_set = MODELS[name]
    module = family(family_name)
    features = FEATURE_SETS[feature_set]
    if set(features) & FORBIDDEN:
        raise ValueError(f"{name} uses a forbidden feature")
    X, y = table[features].to_numpy(np.float32), table[LABEL].to_numpy()
    results, out_of_fold = [], {}
    for index, params in enumerate(module.CANDIDATES):
        began, fold_ap, fold_pooled, oof = time.perf_counter(), {}, {}, np.zeros(len(table))
        for year in years:
            test = (table.fire_year == year).to_numpy()
            model = module.make_model(params).fit(X[~test], y[~test])
            oof[test] = model.predict_proba(X[test])[:, 1]
            fold_ap[year] = mean_step_ap(table[test], oof[test])
            fold_pooled[year] = float(average_precision_score(y[test], oof[test]))
        result = {"candidate": index, "params": params, "mean_step_ap": float(np.mean(list(fold_ap.values()))),
                  "fold_mean_step_ap": fold_ap, "fold_pooled_ap": fold_pooled, "oof_log_loss": float(log_loss(y, oof)),
                  "seconds": round(time.perf_counter() - began, 1)}  # fmt: skip
        results.append(result)
        out_of_fold[index] = oof
        log.info(f"{name} candidate {index} {params}: mean per-step AP {result['mean_step_ap']:.4f} ({result['seconds']}s)")
    best = max(results, key=lambda r: r["mean_step_ap"])
    scale = area_scale(table, out_of_fold[best["candidate"]])
    model = module.make_model(best["params"]).fit(X, y)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"name": name, "family": family_name, "feature_set": feature_set, "features": features, "model": model, "area_scale": scale, "params": best["params"]}, MODEL_DIR / f"{name}.joblib")
    log.info(f"{name}: chose candidate {best['candidate']}, area scale {scale:.3f}; refitted on all calibration fires")
    return {"family": family_name, "feature_set": feature_set, "features": features, "candidates": results, "selected": best["candidate"],
            "area_scale": scale, "training_rows": int(len(table)), "training_positives": int(y.sum())}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    args = parser.parse_args()
    log = action_log("train per-cell models")
    table = load_calibration()
    years = [int(y) for y in sorted(table.fire_year.unique())]
    log.info(f"START: {args.models} on {len(table):,} candidate rows, {int(table[LABEL].sum()):,} positives, {table.groupby(['fire_id', 'observation']).ngroups} steps, {table.fire_id.nunique()} fires, years {years}")
    previous = json.loads(CELL_MODELS_TRAINING.read_text(encoding="utf-8")).get("models", {}) if CELL_MODELS_TRAINING.exists() else {}
    report = {"dataset_version": DATASET_VERSION, "created_at_utc": datetime.now(UTC).isoformat(), "training_years": years,
              "folds": "leave one fire year out", "selection_metric": "mean over folds of mean per-step average precision",
              "candidates": {name: family(name).CANDIDATES for name in sorted({f for f, _ in MODELS.values()})},
              "target_area_ratio": TARGET_AREA_RATIO, "reference": reference_scores(table, years),
              "models": {name: previous[name] for name in MODELS if name in previous and name not in args.models}}  # fmt: skip
    for name in args.models:
        report["models"][name] = train(name, table, years, log)
        CELL_MODELS_TRAINING.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")  # after each model, so a long run keeps its progress
    report["models"] = {name: report["models"][name] for name in MODELS if name in report["models"]}
    CELL_MODELS_TRAINING.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log.info(f"DONE: wrote {CELL_MODELS_TRAINING.name} and models in {MODEL_DIR}")


if __name__ == "__main__":
    main()
