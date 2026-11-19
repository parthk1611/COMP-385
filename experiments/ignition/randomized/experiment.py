"""Eight seeded RandomizedSearchCV draws on full chronological development folds."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
from pathlib import Path
import numpy as np
from sklearn.model_selection import RandomizedSearchCV
from threadpoolctl import threadpool_limits
from experiments.ignition.common import (
    ROOT, DEFAULT_CACHE, PARAMS, SEED, FOLD_YEARS, CoordinateHGB, temporal_cv,
    load_data, evaluate_saved, load_predictions, fold_metrics, summarize,
    parameter_id, prepare_output,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json

N_CANDIDATES = 8
PARAMETER_SPACE = {
    "learning_rate": [0.03, 0.05, 0.1], "max_iter": [80, 160],
    "l2_regularization": [0.1, 1.0, 10.0], "min_samples_leaf": [50, 100, 200],
    "max_leaf_nodes": [7, 15, 31],
}


def execute(cache, baseline, output):
    data = load_data(cache)
    X, y, manifest, grid, centres = data
    base = {**evaluate_saved(data, baseline), "candidate": "coordinate_15_baseline"}
    output = Path(output)
    prepare_output(output)
    limit = year_slice(manifest, 2010, 2016).stop
    positions = np.arange(limit, dtype=np.int32).reshape(-1, 1)
    search = RandomizedSearchCV(
        CoordinateHGB(cache, output), PARAMETER_SPACE, n_iter=N_CANDIDATES, random_state=SEED,
        scoring="average_precision", cv=temporal_cv(manifest), n_jobs=1,
        pre_dispatch=1, refit=False, error_score="raise", return_train_score=False, verbose=1)
    search.fit(positions, y[:limit])
    if len(search.cv_results_["params"]) != 8 or search.n_splits_ != 5:
        raise ValueError("Executed search differs from the declared design")
    candidates = []
    for index, parameters in enumerate(search.cv_results_["params"]):
        params = {**PARAMS, **parameters}
        records = []
        for split, (_, _, year) in enumerate(FOLD_YEARS):
            validation = year_slice(manifest, year)
            p = load_predictions(output / parameter_id(params), params, year, y[validation])
            metrics = fold_metrics(data, year, p)
            if not np.isclose(metrics["average_precision"], search.cv_results_[f"split{split}_test_score"][index], rtol=0, atol=1e-12):
                raise ValueError("Search AP differs from saved fold probabilities")
            records.append({"fold": year, "params": params, "metrics": metrics})
        row = {**summarize(params, records), "candidate": f"C{index + 1}",
               "parameter_id": parameter_id(params), "search_rank": int(search.cv_results_["rank_test_score"][index]),
               "fold_ap_std": float(search.cv_results_["std_test_score"][index])}
        if not np.isclose(row["mean_fold_average_precision"], search.cv_results_["mean_test_score"][index], rtol=0, atol=1e-12):
            raise ValueError("Search mean differs from five-year mean AP")
        row["relative_mean_ap_vs_baseline"] = row["mean_fold_average_precision"] / base["mean_fold_average_precision"] - 1
        row["year_ap_deltas"] = {year: ap - base["fold_average_precision"][year] for year, ap in row["fold_average_precision"].items()}
        row["years_beating_baseline"] = [year for year, delta in row["year_ap_deltas"].items() if delta > 0]
        candidates.append(row)
    selected = max([base, *candidates], key=lambda row: row["mean_fold_average_precision"])
    results = {
        "status": "complete", "algorithm": "RandomizedSearchCV", "n_candidates": len(candidates),
        "n_splits": search.n_splits_, "specified_candidate_fold_fits": 40,
        "baseline": base, "candidates": candidates,
        "best_search_candidate": candidates[search.best_index_], "selected_development_candidate": selected,
        "selected_relative_mean_ap_gain": selected["mean_fold_average_precision"] / base["mean_fold_average_precision"] - 1,
        "selection_rule": "Highest unweighted yearly mean AP including baseline; exact ties retain baseline then search order",
        "scope": "Development only; no 2017--2019 evaluation or final-model refit",
    }
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_coordinates")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/randomized")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.baseline, args.output)


if __name__ == "__main__":
    main()
