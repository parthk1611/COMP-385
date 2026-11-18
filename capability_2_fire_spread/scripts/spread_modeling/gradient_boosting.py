"""Histogram gradient boosting (scikit-learn): shallow trees, each correcting the errors of the last.

Handles missing values itself.  Internal early stopping is off: it would hold out
a random row sample, putting cells of one step on both sides of the split.
"""

from __future__ import annotations

from sklearn.ensemble import HistGradientBoostingClassifier

from .contract import SEED


CANDIDATES = [
    {"max_iter": iterations, "learning_rate": 0.05, "max_leaf_nodes": leaves, "min_samples_leaf": 100, "l2_regularization": 1.0}
    for iterations in [200, 400] for leaves in [15, 31]
]  # fmt: skip


def make_model(params: dict):
    return HistGradientBoostingClassifier(**params, early_stopping=False, random_state=SEED)
