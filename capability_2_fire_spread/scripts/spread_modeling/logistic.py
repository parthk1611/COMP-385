"""Logistic regression: a weighted sum of the features, squashed into a probability (the linear model).

Missing values are filled with training medians plus missing-value indicators, and
features are standardised; both are fitted inside each training fold.
"""

from __future__ import annotations

from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


CANDIDATES = [{"C": c} for c in [0.1, 1.0]]


def make_model(params: dict):
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    return make_pipeline(imputer, StandardScaler(), LogisticRegression(**params, max_iter=1000))
