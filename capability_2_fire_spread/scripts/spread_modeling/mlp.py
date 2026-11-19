"""A small neural network on the per-cell features: two hidden layers (64 and 32 units).

Missing values are filled with training medians plus missing-value indicators, and
features are standardised; both are fitted inside each training fold.  A fixed
20 epochs: internal early stopping would hold out a random row sample, putting
cells of one step on both sides of the split.
"""

from __future__ import annotations

from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .contract import SEED


CANDIDATES = [{"hidden_layer_sizes": (64, 32), "alpha": alpha, "batch_size": 4096, "max_iter": 20, "learning_rate_init": 1e-3} for alpha in [1e-4, 1e-3]]


def make_model(params: dict):
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    return make_pipeline(imputer, StandardScaler(), MLPClassifier(**params, early_stopping=False, random_state=SEED))
