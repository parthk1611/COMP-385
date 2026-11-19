"""Train and export the retained coordinate HGB on 2010--2016 only."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import csv
import hashlib
import json
import pickle
import platform
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .contract import CACHE_VERSION, FEATURE_NAMES, RETAINED_HGB_PARAMS, ROOT, SEED, check_matrix
from .data import load_cache, year_slice
from .histogram import train_hgb
from .weather import sha256

DEFAULT_OUTPUT = ROOT / "artifacts/ignition_modeling/retained_coordinate_hgb"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def write_csv(path, records):
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def predict_chunks(pipeline, X, batch_size=50000):
    check_matrix(X)
    p = np.empty(len(X))
    for start in range(0, len(X), batch_size):
        p[start:start + batch_size] = pipeline.predict_proba(X[start:start + batch_size])[:, 1]
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("Prediction contains invalid probabilities")
    return p


def predict_bundle(bundle, X):
    if bundle["features"] != list(FEATURE_NAMES) or bundle["cache_version"] != CACHE_VERSION:
        raise ValueError("Saved feature schema/cache version mismatch")
    if bundle["calibrator"] is not None:
        raise ValueError("The retained coordinate model exports raw uncalibrated probabilities")
    return predict_chunks(bundle["pipeline"], X)


def check_gate(manifest):
    if manifest["cache_version"] != CACHE_VERSION or manifest["features"] != list(FEATURE_NAMES):
        raise ValueError("Training requires the current ordered feature/cache contract")
    if manifest.get("corrected_value_checks", {}).get("status") != "PASS":
        raise ValueError("Corrected-cache quality gate has not passed")
    expected = json.loads((ROOT / "data/raw/cwfis/manifest.json").read_text())["archive_sha256"]
    if manifest["weather_source_audit"]["source_sha256"] != expected:
        raise ValueError("Cache weather source differs from the pinned archive")


def compare_reference(pipeline, X, reference_pickle):
    """Compare fitted classifiers on identical 39-column development inputs.

    The historical pickle's 36-input preprocessor is intentionally not called:
    the main cache already materializes its censor flag and coordinates.
    """
    reference_pickle = Path(reference_pickle)
    with reference_pickle.open("rb") as stream:
        reference = pickle.load(stream)
    if reference["transformed_features"] != list(FEATURE_NAMES):
        raise ValueError("Reference pickle has a different ordered model input schema")
    if reference["classifier"].get_params() != pipeline["classifier"].get_params():
        raise ValueError("Reference pickle has different classifier settings")
    old_digest, new_digest = hashlib.sha256(), hashlib.sha256()
    differences = 0
    maximum = 0.0
    for start in range(0, len(X), 50000):
        block = X[start:start + 50000]
        old = reference["classifier"].predict_proba(block)[:, 1]
        new = pipeline.predict_proba(block)[:, 1]
        if not np.isfinite(old).all() or not np.isfinite(new).all():
            raise ValueError("Reference comparison contains nonfinite probabilities")
        differences += int(np.count_nonzero(old.view(np.uint64) != new.view(np.uint64)))
        maximum = max(maximum, float(np.max(np.abs(old - new))))
        old_digest.update(old.tobytes())
        new_digest.update(new.tobytes())
    return {
        "reference_pickle": str(reference_pickle), "reference_sha256": sha256(reference_pickle),
        "compared_rows": len(X), "differing_predictions": differences,
        "max_absolute_difference": maximum, "bit_identical": differences == 0,
        "reference_prediction_sha256": old_digest.hexdigest(),
        "main_prediction_sha256": new_digest.hexdigest(),
        "scope": "Development-input reproducibility, not a held-out performance estimate",
    }


def execute(cache, output, reference_pickle=None):
    output, cache = Path(output), Path(cache)
    if output.exists():
        raise FileExistsError("Preserve existing model exports; choose a new output directory")
    X, y, manifest = load_cache(cache)
    check_gate(manifest)
    train = year_slice(manifest, 2010, 2016)
    if not all(day[:4] in {str(year) for year in range(2010, 2017)}
               for day, (start, stop) in manifest["date_slices"].items()
               if start >= train.start and stop <= train.stop):
        raise ValueError("Training selection includes a reserved year")
    output.mkdir(parents=True)
    print(f"Training retained 80-iteration coordinate HGB on {train.stop - train.start:,} rows, 2010--2016", flush=True)
    with threadpool_limits(limits=2):
        pipeline, diagnostics = train_hgb(
            X[train], y[train], RETAINED_HGB_PARAMS, scratch_dir=output / "scratch", seed=SEED)
        if pipeline["classifier"].n_features_in_ != len(FEATURE_NAMES):
            raise ValueError("Training changed the persisted feature width")
        training = {
            "years": list(range(2010, 2017)), "first_date": "2010-05-01", "last_date": "2016-10-31",
            "rows": train.stop - train.start, "positive_cell_days": int(y[train].sum()),
        }
        bundle = {
            "pipeline": pipeline, "calibrator": None, "features": list(FEATURE_NAMES),
            "cache_version": CACHE_VERSION, "training": training,
        }
        model_path = output / "selected_system.joblib"
        joblib.dump(bundle, model_path)
        reloaded = joblib.load(model_path)
        probe = np.linspace(train.start, train.stop - 1, min(1024, training["rows"]), dtype=int)
        before, after = predict_bundle(bundle, X[probe]), predict_bundle(reloaded, X[probe])
        np.testing.assert_array_equal(before.view(np.uint64), after.view(np.uint64))
        comparison = compare_reference(reloaded["pipeline"], X[train], reference_pickle) if reference_pickle else None
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=ROOT, check=False).returncode
    if dirty not in (0, 1):
        raise RuntimeError("Cannot record the model's source-tree provenance")
    source_paths = [ROOT / "data/metadata/ignition_feature_selection_v1.json",
                    *sorted(Path(__file__).parent.glob("*.py"))]
    metadata = {
        "artifact_version": "retained-coordinate-hgb-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "params": pipeline["classifier"].get_params(), "seed": SEED, "threads": 2,
        "features": list(FEATURE_NAMES), "fit_years": [2010, 2016], "training": training,
        "cache_version": CACHE_VERSION, "source_panel_sha256": manifest["original_panel_sha256"],
        "cache_manifest_sha256": sha256(cache / "manifest.json"),
        "cache_sha256": {name: sha256(cache / name) for name in ("manifest.json", "X.f64", "y.u8", "grid.u16")},
        "model_sha256": sha256(model_path), "commit": commit, "working_tree_dirty": bool(dirty),
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in source_paths},
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn", "joblib", "threadpoolctl")},
        "scope": "Uncalibrated retained 2010--2016 model; no 2017--2019 fitting, calibration or global scoring",
    }
    write_json(output / "model_metadata.json", metadata)
    write_json(output / "training.json", diagnostics)
    passed = comparison is None or comparison["bit_identical"]
    verification = {
        "status": "PASS" if passed else "MISMATCH", "model_sha256": metadata["model_sha256"],
        "metadata_sha256": sha256(output / "model_metadata.json"),
        "cache_manifest_sha256": metadata["cache_manifest_sha256"],
        "reload_probe_rows": len(probe), "reload_max_absolute_difference": float(np.max(np.abs(before - after))),
        "reference_comparison": comparison,
    }
    write_json(output / "verification.json", verification)
    if not passed:
        raise ValueError("Main-pipeline predictions differ from the reference pickle; see verification.json")
    print(json.dumps(verification, indent=2), flush=True)
    return verification


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "data/interim/ignition_modeling_cache")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference-pickle", type=Path, help="Trusted local experiment pickle for a full development-input comparison")
    args = parser.parse_args()
    execute(args.cache, args.output, args.reference_pickle)
