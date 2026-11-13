"""Three sequential full-row development HGB experiments; no reserved-year work."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import gc
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.ignition.common import (
    ROOT, DEFAULT_CACHE, PARAMS, FOLD_YEARS, BATCH_SIZE, load_data,
    fit_hgb, predict_hgb, candidate_name, save_predictions, fold_metrics,
    summarize, prepare_output,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json

ITERATIONS = (40, 80, 160)
L2_VALUES = (1.0, 0.1, 0.0)
BASE_PARAMS = {**PARAMS, "max_iter": 40}


def staged_predictions(classifier, preprocessor, X, iterations):
    """Score actual boosting prefixes in bounded batches, without refitting."""
    predictions = {n: np.empty(len(X)) for n in iterations}
    for start in range(0, len(X), BATCH_SIZE):
        stop = min(start + BATCH_SIZE, len(X))
        values = preprocessor.transform(X[start:stop])
        for n, probability in enumerate(classifier.staged_predict_proba(values), 1):
            if n in predictions:
                predictions[n][start:stop] = probability[:, 1]
            if n == max(iterations):
                break
    return predictions


def execute(cache, output):
    data = load_data(cache)
    X, y, manifest, grid, centres = data
    output = Path(output)
    prepare_output(output)
    completed = {}

    def evaluate(candidates, staged=False):
        pending = [p for p in candidates if candidate_name(p) not in completed]
        records = {candidate_name(p): [] for p in pending}
        for first, last, year in FOLD_YEARS:
            training = year_slice(manifest, first, last)
            validation = year_slice(manifest, year)
            if not pending:
                break
            fits = [{**pending[0], "max_iter": max(ITERATIONS)}] if staged else pending
            for params in fits:
                classifier, preprocessor = fit_hgb(
                    X[training], y[training], grid[training], centres,
                    scratch_dir=output / "scratch", params=params, coordinates=False)
                predictions = staged_predictions(classifier, preprocessor, X[validation], ITERATIONS) if staged else {
                    params["max_iter"]: predict_hgb(classifier, preprocessor, X[validation], grid[validation], centres, coordinates=False)}
                for candidate in pending if staged else [params]:
                    p = predictions[candidate["max_iter"]]
                    save_predictions(output, candidate, year, y[validation], p)
                    records[candidate_name(candidate)].append({"fold": year, "params": candidate, "metrics": fold_metrics(data, year, p)})
                del classifier, preprocessor, predictions
                gc.collect()
        for params in pending:
            completed[candidate_name(params)] = summarize(params, records[candidate_name(params)])
        rows = [completed[candidate_name(p)] for p in candidates]
        return {"candidates": rows, "selected": max(rows, key=lambda row: row["mean_fold_average_precision"])}

    iterations = evaluate([{**BASE_PARAMS, "max_iter": n} for n in ITERATIONS], staged=True)
    l2 = evaluate([{**iterations["selected"]["params"], "l2_regularization": value} for value in L2_VALUES])
    base = l2["selected"]["params"]
    capacity = evaluate([base, {**base, "max_leaf_nodes": 31}, {**base, "min_samples_leaf": 30}])
    baseline, selected = completed[candidate_name(BASE_PARAMS)], capacity["selected"]
    results = {
        "status": "complete", "iterations": iterations, "l2": l2, "capacity": capacity,
        "baseline": baseline, "selected": selected,
        "relative_mean_ap_gain": selected["mean_fold_average_precision"] / baseline["mean_fold_average_precision"] - 1,
        "year_ap_changes": {year: selected["fold_average_precision"][year] - ap for year, ap in baseline["fold_average_precision"].items()},
        "selection_rule": "Highest unweighted mean yearly AP; exact ties retain stage order",
        "scope": "Development only; no 2017--2019 fitting or evaluation",
    }
    for name, stage in (("iterations", iterations), ("l2", l2), ("capacity", capacity), ("results", results)):
        write_json(output / f"{name}.json", stage)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/tuning")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.output)


if __name__ == "__main__":
    main()
