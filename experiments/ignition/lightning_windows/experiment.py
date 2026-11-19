"""Fixed one-column lightning ablations with baseline-first exact-tie selection."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import gc
from pathlib import Path
import json

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.ignition.common import (
    ROOT, PARAMS, FOLD_YEARS, DEFAULT_CACHE, RAW_FEATURES as BASE_RAW,
    TRANSFORMED_FEATURES as BASE_TRANSFORMED, load_data, fit_hgb, predict_hgb,
    evaluate_saved, fold_metrics, summarize, prepare_output, save_predictions,
)
from experiments.ignition.lightning.build_features import (
    FEATURE_VERSION as FULL_VERSION, LIGHTNING_NAMES, _development_rows,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json

WINDOWS = {"24h_only": 0, "7d_only": 1}
EXPERIMENT = "ignition-lightning-window-ablation-v1"
DEFAULT_OUTPUT = ROOT / "artifacts/ignition_modeling/reruns/lightning_windows"
DEFAULT_COMBINED = ROOT / "artifacts/ignition_modeling/hgb_lightning"
DEFAULT_FEATURES = DEFAULT_COMBINED / "lightning_features" / FULL_VERSION / "features.npy"


def schema(window):
    if window not in WINDOWS:
        raise ValueError("Choose 24h_only or 7d_only")
    name = LIGHTNING_NAMES[WINDOWS[window]]
    return f"{FULL_VERSION}-{window}", (*BASE_RAW, name), (*BASE_TRANSFORMED, name)


def execute(cache, baseline, combined, features, output):
    data = load_data(cache)
    X, y, manifest, row_ids, centres = data
    variants = {"baseline": evaluate_saved(data, baseline),
                "both_windows": evaluate_saved(data, combined)}
    features = Path(features)
    metadata = json.loads((features.parent / "audit.json").read_text())
    _, nrows, row_hash = _development_rows(row_ids, manifest)
    if (metadata["features"] != list(LIGHTNING_NAMES)
            or metadata["development_years"] != list(range(2010, 2017))
            or metadata["row_ids_sha256"] != row_hash
            or metadata["feature_version"] != FULL_VERSION):
        raise ValueError("Lightning feature definitions or cache-grid alignment differ")
    lightning = np.load(features, mmap_mode="r", allow_pickle=False)
    if lightning.shape != (nrows, 2) or lightning.dtype != np.dtype("float64"):
        raise ValueError("Expected the complete two-column development feature matrix")
    for start in range(0, nrows, 50000):
        block = lightning[start:start + 50000]
        if np.isinf(block).any() or np.any(block < 0):
            raise ValueError("Lightning densities must be nonnegative or NaN")
    output = prepare_output(output)
    for window, column in WINDOWS.items():
        directory = output / window
        directory.mkdir()
        # A one-column slice physically excludes the other window, without copying.
        selected = lightning[:, column:column + 1]
        records = []
        for first, last, year in FOLD_YEARS:
            training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
            if training.stop > validation.start or last >= year or year > 2016:
                raise ValueError("Training must precede development validation")
            print(f"{window} fold {year}: fitting {len(y[training]):,} rows", flush=True)
            model, preprocessor = fit_hgb(
                X[training], y[training], row_ids[training], centres,
                scratch_dir=directory / "scratch", extra=selected[training])
            p = predict_hgb(model, preprocessor, X[validation], row_ids[validation],
                            centres, extra=selected[validation])
            save_predictions(directory, PARAMS, year, y[validation], p)
            records.append({"fold": year, "params": PARAMS, "metrics": fold_metrics(data, year, p)})
            del model, preprocessor, p
            gc.collect()
        variants[window] = summarize(PARAMS, records)
        version, raw, transformed = schema(window)
        write_json(directory / "results.json", {"feature_set_version": version,
                   "raw_features": list(raw), "transformed_features": list(transformed),
                   "summary": variants[window]})
    order = ("baseline", "both_windows", "24h_only", "7d_only")
    baseline_ap = variants["baseline"]["mean_fold_average_precision"]
    results = {
        "status": "complete", "experiment": EXPERIMENT, "params": PARAMS,
        "variants": variants,
        "relative_mean_ap_gain_vs_baseline": {
            name: row["mean_fold_average_precision"] / baseline_ap - 1
            for name, row in variants.items()},
        "selected_variant": max(order, key=lambda name: variants[name]["mean_fold_average_precision"]),
        "selection_rule": "Highest unweighted mean yearly AP; ties keep baseline,both_windows,24h_only,7d_only order",
        "scope": "All rows, five folds per single-window condition; no 2017--2019 construction, fitting or scoring",
    }
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_coordinates")
    parser.add_argument("--combined", type=Path, default=DEFAULT_COMBINED)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.baseline, args.combined, args.features, args.output)


if __name__ == "__main__":
    main()
