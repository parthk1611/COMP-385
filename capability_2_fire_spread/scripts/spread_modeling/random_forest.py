"""Random forest: 200 deep decision trees, each grown on a random quarter of the rows, averaged.

Missing values are filled with training medians plus missing-value indicators,
fitted inside each training fold.
"""

from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from .contract import SEED


CANDIDATES = [{"min_samples_leaf": leaf, "n_estimators": 200, "max_features": "sqrt", "max_samples": 0.25} for leaf in [20, 100]]


def make_model(params: dict):
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    return make_pipeline(imputer, RandomForestClassifier(**params, n_jobs=-1, random_state=SEED))
