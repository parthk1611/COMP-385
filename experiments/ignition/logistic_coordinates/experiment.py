"""Five fixed logistic fits with the same cell-centre inputs as coordinate HGB."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.base import BaseEstimator
from sklearn.linear_model import SGDClassifier
from sklearn.utils.validation import check_is_fitted
from threadpoolctl import threadpool_limits

from experiments.ignition.common import (
    ROOT, FEATURE_NAMES, SEED, FOLD_YEARS, DEFAULT_CACHE, COORDINATE_NAMES,
    RAW_FEATURES, PARAMS as HGB_PARAMS, check_join, load_data, prepare_output,
    fold_metrics, evaluate_saved, summarize,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.logistic import _class_counts, _configuration
from scripts.ignition_modeling.preprocessing import NumericPreprocessor
from scripts.ignition_modeling.run import write_json

PARAMS = {"alpha": 0.001, "class_weight": "balanced", "epochs": 3, "batch_size": 50000}


class CoordinateLogisticPreprocessor(BaseEstimator):
    """Legacy 36-to-57 transform, then two training-standardized coordinates."""
    def __init__(self, chunk_size=50000):
        self.chunk_size = chunk_size

    def fit(self, X, row_ids, centres):
        check_join(X, row_ids, centres)
        self.numeric_ = NumericPreprocessor(chunk_size=self.chunk_size).fit(X)
        counts = np.bincount(row_ids, minlength=len(centres)).astype(np.float64)
        observed = counts > 0
        training_centres = centres[observed]
        frequency = counts[observed] / len(X)
        anchor = training_centres[0]
        offsets = training_centres - anchor
        mean_offset = frequency @ offsets
        self.coordinate_mean_ = anchor + mean_offset
        self.coordinate_variance_ = frequency @ np.square(offsets - mean_offset)
        self.coordinate_scale_ = np.sqrt(self.coordinate_variance_)
        self.coordinate_scale_[self.coordinate_scale_ == 0] = 1
        self.n_samples_seen_ = len(X)
        self.n_features_in_ = len(FEATURE_NAMES)
        self.output_names_ = np.asarray([*self.numeric_.output_names_, *COORDINATE_NAMES], dtype=object)
        return self

    def transform(self, X, row_ids, centres):
        check_is_fitted(self, "output_names_")
        check_join(X, row_ids, centres)
        result = np.empty((len(X), len(self.output_names_)), dtype=np.float64)
        result[:, :-2] = self.numeric_.transform(X)
        result[:, -2:] = (centres[row_ids] - self.coordinate_mean_) / self.coordinate_scale_
        if not np.isfinite(result).all():
            raise FloatingPointError("Nonfinite coordinate logistic input")
        return result


def fit_logistic_coordinates(X, y, row_ids, centres, *, params=None, seed=SEED):
    """Preserve the frozen SGD update/weight/shuffle rules, extending 57 to 59 inputs.

    The historical trainer deliberately rejects anything except its 36-to-57
    schema. This local extension retains its optimizer and preprocessing rules.
    """
    started = time.perf_counter()
    config = _configuration(PARAMS if params is None else params)
    y = np.asarray(y)
    counts = _class_counts(y, len(X), config["batch_size"])
    weights = ({label: len(y)/(2*count) for label, count in counts.items()}
               if config["class_weight"] == "balanced" else {0: 1., 1: 1.})
    preprocessor = CoordinateLogisticPreprocessor(chunk_size=config["batch_size"]).fit(X, row_ids, centres)
    preprocessing_seconds = time.perf_counter() - started
    eta0 = 0.05 / max(weights.values())
    classifier = SGDClassifier(loss="log_loss", penalty="l2", alpha=config["alpha"],
                               learning_rate="constant", eta0=eta0, average=True, shuffle=False,
                               random_state=seed, class_weight=None, max_iter=1, tol=None)
    rng = np.random.default_rng(seed)
    starts = np.arange(0, len(X), config["batch_size"])
    epochs, previous_coef, previous_intercept, previous_objective = [], None, None, None
    for epoch in range(1, config["epochs"] + 1):
        epoch_started = time.perf_counter()
        rows_seen = positives_seen = 0
        for start in rng.permutation(starts):
            stop = min(int(start) + config["batch_size"], len(X))
            indices = rng.permutation(np.arange(int(start), stop))
            labels = y[indices]
            transformed = preprocessor.transform(X[indices], row_ids[indices], centres)
            classifier.partial_fit(transformed, labels, classes=np.array([0, 1]),
                                   sample_weight=np.where(labels == 1, weights[1], weights[0]))
            if not np.isfinite(classifier.coef_).all() or not np.isfinite(classifier.intercept_).all():
                raise FloatingPointError("Nonfinite coordinate logistic coefficients")
            rows_seen += len(labels)
            positives_seen += int(np.count_nonzero(labels))
            del transformed, indices, labels
        if rows_seen != len(y) or positives_seen != counts[1]:
            raise RuntimeError("Logistic epoch did not visit every row and positive exactly once")
        fitting_seconds = time.perf_counter() - epoch_started
        objective_started = time.perf_counter()
        natural_sum = weighted_sum = 0.
        for start in starts:
            selection = slice(int(start), min(int(start) + config["batch_size"], len(X)))
            block = preprocessor.transform(X[selection], row_ids[selection], centres)
            labels = y[selection]
            logits = classifier.decision_function(block)
            losses = np.logaddexp(0, logits) - labels * logits
            if not np.isfinite(losses).all():
                raise FloatingPointError("Nonfinite full-training logistic objective")
            natural_sum += float(losses.sum())
            weighted_sum += float(np.dot(losses, np.where(labels == 1, weights[1], weights[0])))
        penalty = 0.5 * config["alpha"] * float(np.square(classifier.coef_).sum())
        objective = weighted_sum / len(X) + penalty
        change = None if previous_coef is None else float(np.linalg.norm(classifier.coef_ - previous_coef))
        epochs.append({
            "epoch": epoch, "rows_seen": rows_seen, "positives_seen": positives_seen,
            "negatives_seen": rows_seen - positives_seen,
            "natural_prevalence_train_log_loss": natural_sum / len(X),
            "weighted_train_log_loss": weighted_sum / len(X), "l2_penalty": penalty,
            "weighted_train_objective": objective,
            "objective_change": None if previous_objective is None else objective - previous_objective,
            "coefficient_l2_norm": float(np.linalg.norm(classifier.coef_)), "coefficient_l2_change": change,
            "coefficient_relative_change": None if previous_coef is None else change / max(float(np.linalg.norm(previous_coef)), 1e-12),
            "intercept": float(classifier.intercept_[0]),
            "intercept_change": None if previous_intercept is None else float(classifier.intercept_[0] - previous_intercept),
            "fitting_seconds": fitting_seconds, "objective_seconds": time.perf_counter() - objective_started,
        })
        previous_coef, previous_intercept, previous_objective = classifier.coef_.copy(), float(classifier.intercept_[0]), objective
    report = {"params": config, "seed": seed, "training_rows": len(X),
              "class_counts": {str(key): value for key, value in counts.items()},
              "training_class_weights": {str(key): value for key, value in weights.items()},
              "eta0": eta0, "estimator_class_weight": None, "resampling": False,
              "rows_processed": len(y) * config["epochs"], "epochs": epochs,
              "input_features": list(RAW_FEATURES), "transformed_features": preprocessor.output_names_.tolist(),
              "coordinate_mean": preprocessor.coordinate_mean_.tolist(), "coordinate_scale": preprocessor.coordinate_scale_.tolist(),
              "preprocessing_seconds": preprocessing_seconds, "total_seconds": time.perf_counter() - started,
              "convergence_proven": False,
              "convergence_note": "Three fixed epochs are a budget, not evidence of optimization convergence",
              "probability_note": "Balanced-class raw probabilities are not calibrated natural-prevalence ignition probabilities"}
    bundle = {"classifier": classifier, "preprocessor": preprocessor, "centres": np.array(centres, copy=True),
              "raw_features": list(RAW_FEATURES), "params": config}
    return bundle, report


def predict_logistic_coordinates(bundle, X, row_ids, *, batch_size=50000):
    if not 1 <= batch_size <= 50000:
        raise ValueError("Prediction batches must contain 1--50000 rows")
    check_join(X, row_ids, bundle["centres"])
    probability = np.empty(len(X), dtype=np.float64)
    for start in range(0, len(X), batch_size):
        selection = slice(start, min(start + batch_size, len(X)))
        transformed = bundle["preprocessor"].transform(X[selection], row_ids[selection], bundle["centres"])
        probability[selection] = bundle["classifier"].predict_proba(transformed)[:, 1]
    if not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise FloatingPointError("Invalid coordinate logistic probabilities")
    return probability


def execute(cache, output):
    data = load_data(cache)
    X, y, manifest, row_ids, centres = data
    output = prepare_output(output)
    original = json.loads((ROOT / "docs/modeling/development_comparison.json").read_text())
    selected = max((row for row in original["candidate_summary"] if row["family"] == "logistic"),
                   key=lambda row: row["mean_fold_average_precision"])
    if selected["params"] != PARAMS:
        raise ValueError("Archived logistic baseline uses different parameters")
    baseline_records = [row for row in original["fold_results"]
                        if row["family"] == "logistic" and row["candidate"] == selected["candidate"]]
    hgb_base = evaluate_saved(data, ROOT / "artifacts/ignition_modeling/hgb_tuning", HGB_PARAMS)
    hgb_coordinates = evaluate_saved(data, ROOT / "artifacts/ignition_modeling/hgb_coordinates", HGB_PARAMS)
    records = []
    for first, last, year in FOLD_YEARS:
        training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
        if training.stop > validation.start or last >= year or year > 2016:
            raise ValueError("Logistic folds overlap or access reserved years")
        baseline = next(row for row in baseline_records if row["fold"] == year)
        if (baseline["metrics"]["n_samples"] != len(y[validation])
                or baseline["metrics"]["n_positive"] != int(y[validation].sum())):
            raise ValueError("Archived logistic baseline label universe differs")
        print(f"Fitting coordinate logistic fold {year}", flush=True)
        bundle, diagnostics = fit_logistic_coordinates(X[training], y[training], row_ids[training], centres)
        probability = predict_logistic_coordinates(bundle, X[validation], row_ids[validation])
        np.savez_compressed(output / f"fold_{year}.npz", y=y[validation], p=probability)
        records.append({"fold": year, "params": PARAMS, "training": diagnostics,
                        "metrics": fold_metrics(data, year, probability)})
        del bundle, probability
    variants = {
        "logistic_baseline": {**summarize(PARAMS, baseline_records), "variant": "logistic_baseline"},
        "logistic_coordinates": {**summarize(PARAMS, records), "variant": "logistic_coordinates"},
        "hgb_baseline": {**hgb_base, "variant": "hgb_baseline"},
        "hgb_coordinates": {**hgb_coordinates, "variant": "hgb_coordinates"},
    }
    results = {
        "status": "complete", "variants": variants, "fold_results": records,
        "logistic_coordinate_relative_ap_gain": variants["logistic_coordinates"]["mean_fold_average_precision"] / variants["logistic_baseline"]["mean_fold_average_precision"] - 1,
        "hgb_coordinate_relative_ap_gain": hgb_coordinates["mean_fold_average_precision"] / hgb_base["mean_fold_average_precision"] - 1,
        "preferred_by_mean_ap": max(variants, key=lambda name: variants[name]["mean_fold_average_precision"]),
        "baseline_evidence": "Original logistic metrics are archived: per-row baseline predictions are unavailable. HGB metrics are recomputed from saved vectors.",
        "scope": "Five fixed logistic fits; no tuning, calibration, resampling, 2017--2019 evaluation or final refit",
    }
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/logistic_coordinates")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.output)


if __name__ == "__main__":
    main()
