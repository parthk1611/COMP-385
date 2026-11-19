"""Shared data, feature assembly and scoring for the ignition experiments."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.utils.validation import check_is_fitted
from threadpoolctl import threadpool_limits

from scripts.build_ignition_feature_panel import load_grid
from scripts.ignition_modeling.contract import FEATURE_NAMES, HISTORY_FEATURE, ROOT, SEED
from scripts.ignition_modeling.data import dates_for, load_cache, year_slice
from scripts.ignition_modeling.evaluation import evaluate_predictions
from scripts.ignition_modeling.preprocessing import HistoryIndicator
from scripts.ignition_modeling.histogram import _class_counts
from scripts.ignition_modeling.run import check_gate
from scripts.ignition_modeling.splits import FOLD_YEARS
from scripts.ignition_modeling.weather import sha256

DEFAULT_CACHE = ROOT / "data/interim/ignition_modeling_cache"
GRID_PATH = ROOT / "data/interim/ontario_fire_region_10km_grid.csv"
GRID_SHA256 = "b22741d83b64c2b78c19fbf182848566644a23fad4aeef3301ff25ef7c6c3f35"
BATCH_SIZE = 50000
COORDINATE_NAMES = ("cell_centroid_easting_m", "cell_centroid_northing_m")
RAW_FEATURES = (*FEATURE_NAMES, *COORDINATE_NAMES)
TRANSFORMED_FEATURES = (*FEATURE_NAMES, f"{HISTORY_FEATURE}__censored", *COORDINATE_NAMES)
PARAMS = dict(max_iter=80, class_weight=None, learning_rate=0.1,
              max_leaf_nodes=15, min_samples_leaf=100, l2_regularization=1.0)


def cell_centres(path=GRID_PATH):
    """Grid-file order is the dimension encoded by cache grid.u16."""
    cells = list(load_grid(Path(path)).values())
    origins = np.array([(cell.x_m, cell.y_m) for cell in cells], dtype=np.float64)
    if not np.isfinite(origins).all() or np.any(origins % 10000 != 0):
        raise ValueError("Expected 10 km EPSG:3978 cell origins")
    return origins + 5000


def load_data(cache=DEFAULT_CACHE):
    X, y, manifest = load_cache(cache)
    check_gate(manifest)
    if manifest.get("corrected_value_checks", {}).get("status") != "PASS":
        raise ValueError("Use the validated corrected-weather cache")
    dates = list(manifest["date_slices"])
    if dates != sorted(dates):
        raise ValueError("Cache dates must be globally chronological")
    if sha256(GRID_PATH) != GRID_SHA256:
        raise ValueError("Grid order/geometry differs from the frozen cache dimension")
    grid = np.memmap(Path(cache) / "grid.u16", dtype=np.uint16, mode="r", shape=y.shape)
    return X, y, manifest, grid, cell_centres()


def prepare_output(path):
    """A rerun always owns a new directory, never an archived result or model."""
    path = Path(path).resolve()
    protected = (ROOT / "experiments", ROOT / "docs", ROOT / "data",
                 ROOT / "artifacts/ignition_modeling/selected_coordinate_hgb")
    if any(path == parent or parent in path.parents for parent in protected):
        raise ValueError("Output must not replace scientific archives, source data or the selected model")
    path.mkdir(parents=True, exist_ok=False)
    return path


def check_join(X, grid_indices, centres):
    grid_indices, centres = np.asarray(grid_indices), np.asarray(centres)
    if grid_indices.ndim != 1 or len(grid_indices) != len(X) or grid_indices.dtype.kind not in "iu":
        raise ValueError("Expected one integer grid index per feature row")
    if centres.ndim != 2 or centres.shape[1] != 2 or not len(centres) or not np.isfinite(centres).all():
        raise ValueError("Expected finite easting/northing for every grid cell")
    if len(grid_indices) and (grid_indices.min() < 0 or grid_indices.max() >= len(centres)):
        raise ValueError("Grid index is outside the coordinate dimension")


def feature_block(preprocessor, X, grid_indices, centres, *, coordinates=True, extra=None):
    check_join(X, grid_indices, centres)
    base = preprocessor.transform(X)
    if extra is not None and (extra.ndim != 2 or len(extra) != len(X) or np.isinf(extra).any()):
        raise ValueError("Extra feature columns must align with rows and use NaN for missingness")
    n_extra = 0 if extra is None else extra.shape[1]
    values = np.empty((len(X), len(FEATURE_NAMES) + 1 + 2 * coordinates + n_extra))
    values[:, :len(FEATURE_NAMES) + 1] = base
    stop = len(FEATURE_NAMES) + 1
    if coordinates:
        values[:, stop:stop + 2] = centres[grid_indices]
        stop += 2
    if extra is not None:
        values[:, stop:] = extra
    return values


def coordinate_block(preprocessor, X, grid_indices, centres):
    return feature_block(preprocessor, X, grid_indices, centres)


def fit_hgb(X, y, grid_indices, centres, *, scratch_dir, params=None, coordinates=True, extra=None):
    params = dict(PARAMS if params is None else params)
    if set(params) != set(PARAMS) or params["class_weight"] is not None:
        raise ValueError("Expected the experiment's six unweighted HGB settings")
    _class_counts(y, len(X))
    check_join(X, grid_indices, centres)
    if extra is not None and (extra.ndim != 2 or len(extra) != len(X)):
        raise ValueError("Extra training features do not align")
    preprocessor = HistoryIndicator().fit(X)
    columns = len(FEATURE_NAMES) + 1 + 2 * coordinates + (0 if extra is None else extra.shape[1])
    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(scratch).free < len(X) * columns * 8 + 64 * 1024**2:
        raise OSError("Insufficient space for the transformed training matrix")
    classifier = HistGradientBoostingClassifier(
        **params, early_stopping=False, categorical_features=None, random_state=SEED)
    with tempfile.TemporaryDirectory(prefix="hgb-", dir=scratch) as directory:
        mapped = np.memmap(Path(directory) / "features.f64", mode="w+", dtype=np.float64,
                           shape=(len(X), columns), order="C")
        try:
            for start in range(0, len(X), BATCH_SIZE):
                stop = min(start + BATCH_SIZE, len(X))
                additions = None if extra is None else extra[start:stop]
                mapped[start:stop] = feature_block(preprocessor, X[start:stop], grid_indices[start:stop],
                    centres, coordinates=coordinates, extra=additions)
            mapped.flush()
            with threadpool_limits(limits=2):
                classifier.fit(mapped, y)
        finally:
            mapped._mmap.close()
    return classifier, preprocessor


def predict_hgb(classifier, preprocessor, X, grid_indices, centres, *, coordinates=True, extra=None):
    probability = np.empty(len(X))
    with threadpool_limits(limits=2):
        for start in range(0, len(X), BATCH_SIZE):
            stop = min(start + BATCH_SIZE, len(X))
            additions = None if extra is None else extra[start:stop]
            values = feature_block(preprocessor, X[start:stop], grid_indices[start:stop], centres,
                                   coordinates=coordinates, extra=additions)
            probability[start:stop] = classifier.predict_proba(values)[:, 1]
    if not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise ValueError("Invalid predicted probabilities")
    return probability


def candidate_name(params):
    l2 = str(float(params["l2_regularization"])).replace(".", "p")
    return (f"iter_{params['max_iter']}_l2_{l2}_"
            f"leaves_{params['max_leaf_nodes']}_min_{params['min_samples_leaf']}")


def parameter_id(params):
    # Candidate filenames omit learning rate; this preserves full-param identity.
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]


def load_predictions(directory, params, year, labels):
    path = Path(directory) / f"fold_{year}_{candidate_name(params)}.npz"
    metadata = path.with_suffix(".json")
    if metadata.exists():
        record = json.loads(metadata.read_text())
        if record["fold"] != year or record["params"] != params:
            raise ValueError("Baseline predictions have different settings or validation year")
        if "prediction_sha256" in record and sha256(path) != record["prediction_sha256"]:
            raise ValueError("Baseline prediction bytes changed")
    with np.load(path) as saved:
        probability = saved["p"].copy()
        if not np.array_equal(saved["y"], labels):
            raise ValueError("Baseline labels do not match the complete validation partition")
    if probability.shape != labels.shape or not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise ValueError("Invalid baseline probabilities")
    return probability


def save_predictions(directory, params, year, labels, probability):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"fold_{year}_{candidate_name(params)}.npz"
    with path.open("wb") as stream:
        np.savez_compressed(stream, y=labels, p=probability)


def fold_metrics(data, year, probability):
    X, y, manifest, _, _ = data
    validation = year_slice(manifest, year)
    return evaluate_predictions(y[validation], probability, dates=dates_for(manifest, validation),
                                weather_missing=X[validation, FEATURE_NAMES.index("cwfis_missing")])


def summarize(params, records):
    years = [year for _, _, year in FOLD_YEARS]
    if sorted(record["fold"] for record in records) != years or any(record["params"] != params for record in records):
        raise ValueError("A candidate needs all five chronological folds with identical settings")
    ap = [record["metrics"]["average_precision"] for record in records]
    if not np.isfinite(ap).all():
        raise ValueError("Every development fold must have finite AP")
    return {"candidate": candidate_name(params), "params": params,
            "mean_fold_average_precision": float(np.mean(ap)),
            "fold_average_precision": {str(r["fold"]): r["metrics"]["average_precision"] for r in records},
            "mean_fold_roc_auc": float(np.mean([r["metrics"]["roc_auc"] for r in records])),
            "mean_fold_brier_score": float(np.mean([r["metrics"]["brier_score"] for r in records])),
            "mean_fold_log_loss": float(np.mean([r["metrics"]["log_loss"] for r in records])),
            "fold_metrics": {str(r["fold"]): r["metrics"] for r in records}}


def evaluate_saved(data, directory, params=PARAMS):
    records = []
    for _, _, year in FOLD_YEARS:
        validation = year_slice(data[2], year)
        probability = load_predictions(directory, params, year, data[1][validation])
        records.append({"fold": year, "params": params, "metrics": fold_metrics(data, year, probability)})
    return summarize(params, records)


def temporal_cv(manifest):
    pairs = []
    limit = year_slice(manifest, 2010, 2016).stop
    for first, last, year in FOLD_YEARS:
        train, valid = year_slice(manifest, first, last), year_slice(manifest, year)
        if train.start != 0 or train.stop > valid.start or valid.stop > limit or last >= year:
            raise ValueError("Search folds overlap, skip initial history or access reserved years")
        pairs.append((np.arange(train.start, train.stop, dtype=np.int32),
                      np.arange(valid.start, valid.stop, dtype=np.int32)))
    return pairs


def contiguous_slice(rows, limit):
    values = np.asarray(rows)
    if values.ndim != 2 or values.shape[1] != 1 or not len(values) or values.dtype.kind not in "iu":
        raise ValueError("Expected a column of integer cache-row positions")
    first, stop = int(values[0, 0]), int(values[-1, 0]) + 1
    if first < 0 or stop > limit or stop - first != len(values):
        raise ValueError("Row positions are noncontiguous or access reserved years")
    for start in range(0, len(values), BATCH_SIZE):
        block = values[start:start + BATCH_SIZE, 0]
        if not np.array_equal(block, np.arange(first + start, first + start + len(block), dtype=values.dtype)):
            raise ValueError("Row positions must be contiguous and increasing")
    return slice(first, stop)


class CoordinateHGB(ClassifierMixin, BaseEstimator):
    """Search adapter: row indices avoid copies of the multi-GB feature matrix."""
    def __init__(self, cache_dir, output_dir, max_iter=80, learning_rate=0.1,
                 l2_regularization=1.0, min_samples_leaf=100, max_leaf_nodes=15):
        self.cache_dir = cache_dir
        self.output_dir = output_dir
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.l2_regularization = l2_regularization
        self.min_samples_leaf = min_samples_leaf
        self.max_leaf_nodes = max_leaf_nodes

    def hgb_params(self):
        return dict(max_iter=self.max_iter, class_weight=None, learning_rate=self.learning_rate,
                    max_leaf_nodes=self.max_leaf_nodes, min_samples_leaf=self.min_samples_leaf,
                    l2_regularization=self.l2_regularization)

    def fit(self, X, y):
        self.data_ = load_data(self.cache_dir)
        raw, labels, manifest, grid, centres = self.data_
        self.limit_ = year_slice(manifest, 2010, 2016).stop
        training = contiguous_slice(X, self.limit_)
        matches = [(year, year_slice(manifest, year)) for first, last, year in FOLD_YEARS
                   if training == year_slice(manifest, first, last)]
        if len(matches) != 1 or not np.array_equal(y, labels[training]):
            raise ValueError("Fit rows/labels must match a complete chronological training fold")
        self.year_, self.validation_ = matches[0]
        self.classifier_, self.preprocessor_ = fit_hgb(raw[training], labels[training], grid[training], centres,
            scratch_dir=Path(self.output_dir) / "scratch", params=self.hgb_params())
        self.classes_ = self.classifier_.classes_
        self.n_features_in_ = 1  # Interface indices are never predictors.
        return self

    def predict_proba(self, X):
        check_is_fitted(self, "classifier_")
        validation = contiguous_slice(X, self.limit_)
        if validation != self.validation_:
            raise ValueError("Prediction rows must match the fitted fold's full validation year")
        raw, labels, _, grid, centres = self.data_
        probability = predict_hgb(self.classifier_, self.preprocessor_, raw[validation], grid[validation], centres)
        # Preserve predictions for the same post-search multi-metric comparison.
        save_predictions(Path(self.output_dir) / parameter_id(self.hgb_params()), self.hgb_params(),
                         self.year_, labels[validation], probability)
        return np.column_stack((1 - probability, probability))
