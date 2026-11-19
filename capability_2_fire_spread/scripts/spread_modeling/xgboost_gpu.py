"""Gradient boosting with XGBoost, trained on the GPU (falls back to the CPU when there is none).

Row and feature subsampling, deeper trees than the scikit-learn version.
Handles missing values itself.
"""

from __future__ import annotations

from .contract import SEED


CANDIDATES = [
    {"n_estimators": trees, "max_depth": depth, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5, "reg_lambda": 1.0}
    for trees in [300, 600] for depth in [6, 8]
]  # fmt: skip


def make_model(params: dict):
    import torch
    from xgboost import XGBClassifier

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return XGBClassifier(**params, tree_method="hist", device=device, random_state=SEED, n_jobs=8)
