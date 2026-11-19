"""Training-fitted numeric transforms with bounded-memory statistics and output."""
import os
import tempfile
from pathlib import Path

import numpy as np
from pandas.api.types import is_numeric_dtype
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted

from .contract import (
    FEATURE_NAMES, HISTORY_CENSOR_FEATURE, HISTORY_FEATURE, INDICATOR_FEATURES, check_matrix,
)

INDICATOR_INDICES = tuple(FEATURE_NAMES.index(name) for name in INDICATOR_FEATURES)
HISTORY_INDEX = FEATURE_NAMES.index(HISTORY_FEATURE)
HISTORY_CENSOR_INDEX = FEATURE_NAMES.index(HISTORY_CENSOR_FEATURE)
UNSCALED_FEATURES = (
    "calendar_doy_sin", "calendar_doy_cos", "calendar_is_weekend",
    "terrain_aspect_sin", "terrain_aspect_cos", "cwfis_missing", HISTORY_CENSOR_FEATURE,
)


def _validate_input(X):
    check_matrix(X)
    if hasattr(X, "columns"):
        if tuple(X.columns) != FEATURE_NAMES:
            raise ValueError("DataFrame columns must match the exact ordered feature manifest")
        if not all(is_numeric_dtype(dtype) for dtype in X.dtypes):
            raise ValueError("All model feature columns must be numeric")
    elif not hasattr(X, "dtype") or X.dtype.kind not in "biuf":
        raise ValueError("Expected a dense numeric array or numeric DataFrame")


def _block(X, start, stop):
    if hasattr(X, "columns"):
        values = X.iloc[start:stop].to_numpy(dtype=np.float64, na_value=np.nan, copy=True)
    else:
        values = np.array(X[start:stop], dtype=np.float64, copy=True)
    if np.isinf(values).any():
        raise ValueError("Infinite feature values are invalid; missing values must use NaN")
    censor = values[:, HISTORY_CENSOR_INDEX]
    if not np.array_equal(censor, np.isnan(values[:, HISTORY_INDEX])):
        raise ValueError("History censor flag must be binary and match missing history values")
    return values


class _DiskTransformer(TransformerMixin, BaseEstimator):
    def __init__(self, scratch_dir=None, chunk_size=50000):
        self.scratch_dir = scratch_dir
        self.chunk_size = chunk_size

    def __sklearn_tags__(self):
        tags = super().__sklearn_tags__()
        tags.input_tags.allow_nan = True
        return tags

    def _check(self, X, fitting=False):
        _validate_input(X)
        if not isinstance(self.chunk_size, (int, np.integer)) or not 1 <= self.chunk_size <= 50000:
            raise ValueError("chunk_size must be an integer from 1 to 50000")
        if fitting and not len(X):
            raise ValueError("Training data must contain at least one row")

    def _record_schema(self, X, output_names):
        self.n_features_in_ = len(FEATURE_NAMES)
        self.feature_names_in_ = np.asarray(FEATURE_NAMES, dtype=object)
        self.n_samples_seen_ = len(X)
        self.output_names_ = np.asarray(output_names, dtype=object)

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "output_names_")
        if input_features is not None and tuple(input_features) != FEATURE_NAMES:
            raise ValueError("input_features must match the exact ordered feature manifest")
        return self.output_names_.copy()

    def _transform(self, X, disk=False):
        check_is_fitted(self, "output_names_")
        self._check(X)
        shape = (len(X), len(self.output_names_))
        path = None
        if disk and len(X):
            directory = Path(self.scratch_dir)
            directory.mkdir(parents=True, exist_ok=True)
            fd, path = tempfile.mkstemp(prefix=f"{type(self).__name__}-", suffix=".f64", dir=directory)
            os.close(fd)
            result = np.memmap(path, dtype=np.float64, mode="w+", shape=shape, order="C")
        else:
            result = np.empty(shape, dtype=np.float64, order="C")
        try:
            for start in range(0, len(X), self.chunk_size):
                stop = min(start + self.chunk_size, len(X))
                result[start:stop] = self._transform_block(_block(X, start, stop))
            if isinstance(result, np.memmap):
                result.flush()
            return result
        except Exception:
            if path:
                result._mmap.close()
                Path(path).unlink(missing_ok=True)
            raise

    def transform(self, X):
        return self._transform(X)

    def fit_transform(self, X, y=None, **fit_params):
        self.fit(X, y, **fit_params)
        return self._transform(X, disk=self.scratch_dir is not None)


class NumericPreprocessor(_DiskTransformer):
    """Impute and scale selected inputs, preserving the persisted censor flag."""

    def fit(self, X, y=None):
        self._check(X, fitting=True)
        medians = np.zeros(len(FEATURE_NAMES), dtype=np.float64)
        observed_counts = np.zeros(len(FEATURE_NAMES), dtype=np.int64)
        for i in range(len(FEATURE_NAMES)):
            if hasattr(X, "columns"):
                column = X.iloc[:, i].to_numpy(dtype=np.float64, na_value=np.nan, copy=True)
            else:
                column = np.array(X[:, i], dtype=np.float64, copy=True)
            if np.isinf(column).any():
                raise ValueError(f"Infinite training values in {FEATURE_NAMES[i]}")
            observed_counts[i] = np.count_nonzero(~np.isnan(column))
            if observed_counts[i]:
                medians[i] = np.nanmedian(column, overwrite_input=True)
            del column

        count = 0
        mean = np.zeros(len(FEATURE_NAMES), dtype=np.float64)
        squared_deviation = np.zeros_like(mean)
        for start in range(0, len(X), self.chunk_size):
            values = _block(X, start, min(start + self.chunk_size, len(X)))
            self._impute(values, medians)
            size, chunk_mean = len(values), values.mean(axis=0)
            delta, total = chunk_mean - mean, count + size
            squared_deviation += values.var(axis=0) * size + delta**2 * count * size / total
            mean += delta * size / total
            count = total

        self.medians_ = medians
        self.observed_counts_ = observed_counts
        self.all_missing_ = observed_counts == 0
        self.training_mean_ = mean
        self.training_variance_ = np.maximum(squared_deviation / count, 0)
        self.mean_ = mean.copy()
        self.scale_ = np.sqrt(self.training_variance_)
        self.scale_[self.scale_ == 0] = 1
        for name in UNSCALED_FEATURES:
            i = FEATURE_NAMES.index(name)
            self.mean_[i], self.scale_[i] = 0, 1
        indicators = tuple(f"{name}__missing" for name in INDICATOR_FEATURES)
        self._record_schema(X, (*FEATURE_NAMES, *indicators))
        return self

    @staticmethod
    def _impute(values, medians):
        for i, median in enumerate(medians):
            column = values[:, i]
            np.copyto(column, median, where=np.isnan(column))

    def _transform_block(self, values):
        indicators = np.isnan(values[:, INDICATOR_INDICES]).astype(np.float64)
        self._impute(values, self.medians_)
        values -= self.mean_
        values /= self.scale_
        return np.column_stack((values, indicators))


class HistoryIndicator(_DiskTransformer):
    """Preserve selected inputs and native NaN without adding derived columns."""

    def fit(self, X, y=None):
        self._check(X, fitting=True)
        for start in range(0, len(X), self.chunk_size):
            _block(X, start, min(start + self.chunk_size, len(X)))
        self._record_schema(X, FEATURE_NAMES)
        return self

    def _transform_block(self, values):
        return values
