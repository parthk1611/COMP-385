"""One CPU-histogram XGBoost configuration on five full development folds."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import time
from pathlib import Path

import numpy as np
import xgboost as xgb
from threadpoolctl import threadpool_limits

from experiments.ignition.common import (
    ROOT, SEED, DEFAULT_CACHE, FOLD_YEARS, RAW_FEATURES, TRANSFORMED_FEATURES,
    PARAMS as HGB_PARAMS, coordinate_block, check_join, load_data,
    prepare_output, fold_metrics, evaluate_saved, summarize,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.histogram import _class_counts
from scripts.ignition_modeling.preprocessing import HistoryIndicator
from scripts.ignition_modeling.run import write_json

ROUNDS = 160
PARAMS = {"booster": "gbtree", "objective": "binary:logistic", "tree_method": "hist", "device": "cpu",
          "eta": 0.05, "max_depth": 4, "max_leaves": 15, "grow_policy": "lossguide",
          "min_child_weight": 0.1, "subsample": 0.8, "colsample_bytree": 0.8,
          "sampling_method": "uniform", "lambda": 1.0, "alpha": 0.0, "max_bin": 255,
          "scale_pos_weight": 1.0, "seed": SEED, "nthread": 2,
          "eval_metric": "logloss", "validate_parameters": True}


def float32_block(preprocessor, X, row_ids, centres):
    with np.errstate(over="raise"):
        values = coordinate_block(preprocessor, X, row_ids, centres).astype(np.float32)
    if np.isinf(values).any():
        raise ValueError("XGBoost features exceed the supported float32 range")
    return values


class CoordinateDataIter(xgb.DataIter):
    """Replay complete training rows in bounded batches for train-only quantiles."""
    def __init__(self, X, y, row_ids, centres, preprocessor, *, batch_size=50000):
        super().__init__(cache_prefix=None, release_data=True)
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 50000:
            raise ValueError("XGBoost batches must contain 1--50000 rows")
        check_join(X, row_ids, centres)
        if len(y) != len(X):
            raise ValueError("Iterator labels and feature rows differ")
        self.X, self.y, self.row_ids, self.centres, self.preprocessor = X, y, row_ids, centres, preprocessor
        self.batch_size = batch_size
        self.completed_pass_rows = []
        self.max_batch_rows = 0
        self.position = 0
        self._complete = False
        self._batch = None

    def reset(self):
        self.position = 0
        self._complete = False
        self._batch = None

    def next(self, input_data):
        if self.position == len(self.X):
            if not self._complete:
                self.completed_pass_rows.append(self.position)
                self._complete = True
            return False
        stop = min(self.position + self.batch_size, len(self.X))
        selection = slice(self.position, stop)
        self._batch = float32_block(self.preprocessor, self.X[selection], self.row_ids[selection], self.centres)
        input_data(data=self._batch, label=self.y[selection], feature_names=list(TRANSFORMED_FEATURES))
        self.max_batch_rows = max(self.max_batch_rows, stop - self.position)
        self.position = stop
        return True


def fit_xgboost_coordinates(X, y, row_ids, centres, *, params=None, rounds=ROUNDS, batch_size=50000):
    configuration = {**PARAMS, **(params or {})}
    if set(configuration) != set(PARAMS):
        raise ValueError("Unknown XGBoost benchmark parameter")
    if any(configuration[key] != PARAMS[key] for key in ("booster", "objective", "tree_method", "device", "scale_pos_weight")):
        raise ValueError("Benchmark requires unweighted CPU histogram binary boosting")
    if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 1:
        raise ValueError("Boosting rounds must be a positive integer")
    y = np.asarray(y)
    counts = _class_counts(y, len(X))
    check_join(X, row_ids, centres)
    started = time.perf_counter()
    preprocessor = HistoryIndicator().fit(X)
    iterator = CoordinateDataIter(X, y, row_ids, centres, preprocessor, batch_size=batch_size)
    matrix = xgb.QuantileDMatrix(iterator, max_bin=configuration["max_bin"], nthread=configuration["nthread"],
                                missing=np.nan, enable_categorical=False)
    if matrix.num_row() != len(X) or matrix.num_col() != len(TRANSFORMED_FEATURES):
        raise ValueError("Quantile matrix lost training rows or feature columns")
    training_params = {**configuration, "base_score": counts["1"] / len(X)}
    booster = xgb.train(training_params, matrix, num_boost_round=rounds, verbose_eval=False)
    booster.reset()
    if not iterator.completed_pass_rows or any(rows != len(X) for rows in iterator.completed_pass_rows):
        raise ValueError("Quantile iterator did not cover every training row")
    bundle = {"booster": booster, "preprocessor": preprocessor, "centres": np.array(centres, copy=True),
              "params": configuration, "rounds": rounds, "feature_names": list(TRANSFORMED_FEATURES)}
    diagnostics = {"params": configuration, "rounds": rounds,
                   "training_rows": len(X), "class_counts": counts, "training_base_score": training_params["base_score"],
                   "quantile_iterator_pass_rows": iterator.completed_pass_rows, "max_batch_rows": iterator.max_batch_rows,
                   "raw_features": list(RAW_FEATURES), "transformed_features": list(TRANSFORMED_FEATURES),
                   "native_missing": True, "numeric_dtype": "XGBoost-native float32", "class_weight": None,
                   "early_stopping": False, "validation_quantiles_fitted": False,
                   "row_sampling": f"Uniform {configuration['subsample']:.0%} per-tree sampling; no label-based dataset resampling",
                   "elapsed_seconds": time.perf_counter() - started}
    return bundle, diagnostics


def predict_xgboost_coordinates(bundle, X, row_ids, *, batch_size=50000):
    if not isinstance(batch_size, int) or not 1 <= batch_size <= 50000:
        raise ValueError("Prediction batches must contain 1--50000 rows")
    check_join(X, row_ids, bundle["centres"])
    if bundle["feature_names"] != list(TRANSFORMED_FEATURES):
        raise ValueError("XGBoost feature schema differs")
    probability = np.empty(len(X), dtype=np.float64)
    for start in range(0, len(X), batch_size):
        selection = slice(start, min(start + batch_size, len(X)))
        block = float32_block(bundle["preprocessor"], X[selection], row_ids[selection], bundle["centres"])
        probability[selection] = bundle["booster"].inplace_predict(block, missing=np.nan)
    if not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise FloatingPointError("Invalid XGBoost probabilities")
    return probability


def execute(cache, output):
    data = load_data(cache)
    X, y, manifest, row_ids, centres = data
    output = prepare_output(output)
    hgb = {**evaluate_saved(data, ROOT / "artifacts/ignition_modeling/hgb_coordinates", HGB_PARAMS),
           "variant": "hgb_coordinates"}
    records = []
    for first, last, year in FOLD_YEARS:
        training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
        if training.stop > validation.start or last >= year or year > 2016:
            raise ValueError("XGBoost folds overlap or access reserved years")
        print(f"Fitting XGBoost fold {year}", flush=True)
        bundle, diagnostics = fit_xgboost_coordinates(X[training], y[training], row_ids[training], centres)
        probability = predict_xgboost_coordinates(bundle, X[validation], row_ids[validation])
        np.savez_compressed(output / f"fold_{year}.npz", y=y[validation], p=probability)
        records.append({"fold": year, "params": PARAMS, "rounds": ROUNDS, "training": diagnostics,
                        "metrics": fold_metrics(data, year, probability)})
        del bundle, probability
    xgboost = {**summarize(PARAMS, records), "variant": "xgboost_coordinates"}
    results = {
        "status": "complete", "hgb": hgb, "xgboost": xgboost, "fold_results": records,
        "relative_mean_ap_gain": xgboost["mean_fold_average_precision"] / hgb["mean_fold_average_precision"] - 1,
        "year_ap_deltas": {year: ap - hgb["fold_average_precision"][year]
                           for year, ap in xgboost["fold_average_precision"].items()},
        "preferred_by_mean_ap": "xgboost_coordinates" if xgboost["mean_fold_average_precision"] > hgb["mean_fold_average_precision"] else "hgb_coordinates",
        "scope": "Five fixed XGBoost fits; no search, early stopping, calibration, 2017--2019 evaluation or final refit",
        "neural_network_experiment": "Not pursued",
    }
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/xgboost")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.output)


if __name__ == "__main__":
    main()
