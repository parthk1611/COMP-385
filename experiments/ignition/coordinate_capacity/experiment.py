"""Fixed 15/31-leaf by absent/present-coordinate development comparison."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import gc
import json
from pathlib import Path
import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.ignition.common import (
    ROOT, DEFAULT_CACHE, PARAMS, SEED, FOLD_YEARS, RAW_FEATURES, TRANSFORMED_FEATURES,
    load_data, fit_hgb, predict_hgb, load_predictions, save_predictions,
    fold_metrics, summarize, prepare_output,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.evaluation import evaluate_predictions
from scripts.ignition_modeling.run import write_json

PARAMS31 = {**PARAMS, "max_leaf_nodes": 31}
VARIANTS = ("baseline_15", "baseline_31", "coordinates_15", "coordinates_31")


def ap_change(before, after):
    return {
        "mean_ap_delta": after["mean_fold_average_precision"] - before["mean_fold_average_precision"],
        "relative_mean_ap_change": after["mean_fold_average_precision"] / before["mean_fold_average_precision"] - 1,
        "year_ap_deltas": {year: after["fold_average_precision"][year] - score
                           for year, score in before["fold_average_precision"].items()},
    }


def compare_variants(records):
    if set(records) != set(VARIANTS):
        raise ValueError("The comparison requires all four feature/capacity variants")
    summaries = {}
    for name in VARIANTS:
        params = PARAMS31 if name.endswith("31") else PARAMS
        summaries[name] = {**summarize(params, records[name]), "variant": name}
    effects = {
        "coordinates_at_15_leaves": ap_change(summaries["baseline_15"], summaries["coordinates_15"]),
        "coordinates_at_31_leaves": ap_change(summaries["baseline_31"], summaries["coordinates_31"]),
        "capacity_without_coordinates": ap_change(summaries["baseline_15"], summaries["baseline_31"]),
        "capacity_with_coordinates": ap_change(summaries["coordinates_15"], summaries["coordinates_31"]),
    }
    effect15, effect31 = effects["coordinates_at_15_leaves"], effects["coordinates_at_31_leaves"]
    best = max(VARIANTS, key=lambda name: summaries[name]["mean_fold_average_precision"])
    return {
        "status": "complete", "variants": summaries, "effects": effects,
        "mean_ap_interaction": effect31["mean_ap_delta"] - effect15["mean_ap_delta"],
        "year_ap_interactions": {year: effect31["year_ap_deltas"][year] - value
                                 for year, value in effect15["year_ap_deltas"].items()},
        "best_variant_by_mean_ap": best,
        "best_vs_tuned_baseline": ap_change(summaries["baseline_15"], summaries[best]),
        "selection_rule": "Highest unweighted mean AP over all five development years; exact ties retain variant order",
        "scope": "Exploratory development comparison; no final-model promotion or 2017--2019 evaluation",
    }


def reuse_diagnostic(diagnostic, X_train, y_train, X_valid, y_valid, row_ids, centres):
    """Replay the trusted local 2013 model before reusing its saved predictions."""
    diagnostic = Path(diagnostic)
    bundle = joblib.load(diagnostic / "coordinates_31leaf_2013.joblib")
    report = json.loads((diagnostic / "capacity_interaction_2013.json").read_text())
    training = report["new_fit_diagnostics"]
    classifier, preprocessor = bundle["classifier"], bundle["preprocessor"]
    counts = {"0": int((y_train == 0).sum()), "1": int((y_train == 1).sum())}
    if (bundle["params"] != PARAMS31 or training["params"] != PARAMS31
            or any(classifier.get_params()[key] != value for key, value in PARAMS31.items())
            or classifier.early_stopping or classifier.categorical_features is not None
            or classifier.random_state != SEED or classifier.n_iter_ != 80
            or classifier.n_features_in_ != len(TRANSFORMED_FEATURES)):
        raise ValueError("Diagnostic model differs from the fixed coordinate/31-leaf condition")
    if (preprocessor.n_samples_seen_ != len(X_train) or training["n_rows"] != len(X_train)
            or training["class_counts"] != counts or training["raw_features"] != list(RAW_FEATURES)
            or training["transformed_features"] != list(TRANSFORMED_FEATURES)
            or not np.array_equal(bundle["centres"], centres)):
        raise ValueError("Diagnostic training partition, schema, or geometry differs")
    with np.load(diagnostic / "coordinates_31leaf_2013.npz") as saved:
        if not np.array_equal(saved["y"], y_valid):
            raise ValueError("Diagnostic validation labels differ")
        probability = saved["p"].copy()
    replay = predict_hgb(classifier, preprocessor, X_valid, row_ids, centres)
    if probability.shape != replay.shape or not np.allclose(probability, replay, rtol=0, atol=1e-14):
        raise ValueError("Diagnostic predictions do not reproduce from the saved model")
    metrics = evaluate_predictions(y_valid, probability)
    for name in ("n_samples", "n_positive", "average_precision", "roc_auc", "brier_score", "log_loss"):
        if not np.isclose(metrics[name], report["new_fit_metrics"][name], rtol=0, atol=1e-12):
            raise ValueError(f"Diagnostic saved metric differs: {name}")
    return probability, {**training, "reused_2013_diagnostic": True}


def execute(cache, tuning, coordinates, diagnostic, output):
    data = load_data(cache)
    X, y, manifest, grid, centres = data
    output = Path(output)
    prepare_output(output)
    records = {name: [] for name in VARIANTS}
    for first, last, year in FOLD_YEARS:
        training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
        labels = y[validation]
        for name, folder, params in (("baseline_15", tuning, PARAMS), ("baseline_31", tuning, PARAMS31),
                                     ("coordinates_15", coordinates, PARAMS)):
            p = load_predictions(folder, params, year, labels)
            records[name].append({"fold": year, "params": params, "metrics": fold_metrics(data, year, p)})
        if year == 2013:
            p, _ = reuse_diagnostic(diagnostic, X[training], y[training], X[validation], labels, grid[validation], centres)
        else:
            classifier, preprocessor = fit_hgb(X[training], y[training], grid[training], centres,
                                             scratch_dir=output / "scratch", params=PARAMS31)
            p = predict_hgb(classifier, preprocessor, X[validation], grid[validation], centres)
            del classifier, preprocessor
        save_predictions(output, PARAMS31, year, labels, p)
        records["coordinates_31"].append({"fold": year, "params": PARAMS31, "metrics": fold_metrics(data, year, p)})
        del p
        gc.collect()
    results = compare_variants(records)
    results["fit_provenance"] = {"new_fit_years": [2012, 2014, 2015, 2016], "reused_fit_years": [2013]}
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--tuning", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_tuning")
    parser.add_argument("--coordinates", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_coordinates")
    parser.add_argument("--diagnostic", type=Path, default=ROOT / "artifacts/ignition_modeling/coordinate_2013_diagnostics")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/coordinate_capacity")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.tuning, args.coordinates, args.diagnostic, args.output)


if __name__ == "__main__":
    main()
