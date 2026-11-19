"""History-seeded Optuna TPE search for coordinate HGB on development years only."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import gc
import json
import platform
from importlib.metadata import version
from pathlib import Path
from time import monotonic

import joblib
import numpy as np
import optuna
from optuna.distributions import CategoricalDistribution, FloatDistribution, IntDistribution
from threadpoolctl import threadpool_limits

from experiments.ignition.common import (
    ROOT, DEFAULT_CACHE, PARAMS, SEED, FOLD_YEARS, RAW_FEATURES, TRANSFORMED_FEATURES,
    load_data, evaluate_saved, fit_hgb, predict_hgb, save_predictions,
    fold_metrics, summarize, parameter_id, prepare_output,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json
from scripts.ignition_modeling.weather import sha256

N_TRIALS = 16
DISTRIBUTIONS = {
    "learning_rate": FloatDistribution(0.03, 0.15, log=True),
    "max_iter": IntDistribution(40, 200),
    "l2_regularization": FloatDistribution(0.1, 10.0, log=True),
    "min_samples_leaf": CategoricalDistribution([50, 100, 200]),
    "max_leaf_nodes": CategoricalDistribution([7, 15, 31]),
}
HISTORIES = (
    (ROOT / "experiments/ignition/randomized/results.json", ROOT / "artifacts/ignition_modeling/hgb_randomized"),
    (ROOT / "experiments/ignition/local_search/results.json", ROOT / "artifacts/ignition_modeling/hgb_local_search"),
)
SCOPE = "Development only: corrected inputs plus cell centres; no lightning, 2017--2019 scoring, calibration or final refit"


def load_history(data, cache, baseline):
    """Recompute seed scores from aligned saved predictions, never trust AP alone."""
    base = {**evaluate_saved(data, baseline), "candidate": "coordinate_15_baseline", "origin": "baseline"}
    history = [base]
    seen = {parameter_id(PARAMS)}
    for report_path, predictions in HISTORIES:
        report = json.loads(report_path.read_text())
        configuration = report["recorded_configuration"]
        if (configuration["cache_manifest_sha256"] != sha256(Path(cache) / "manifest.json")
                or configuration["fold_years"] != [list(fold) for fold in FOLD_YEARS]
                or configuration["feature_manifest"]["raw_features"] != list(RAW_FEATURES)):
            raise ValueError("Historical trials must use the same corrected cache, features and folds")
        for archived in report["candidates"]:
            params = archived["params"]
            identity = parameter_id(params)
            if identity in seen:
                continue
            row = evaluate_saved(data, predictions / archived["parameter_id"], params)
            if any(not np.isclose(row["fold_average_precision"][year], ap, rtol=0, atol=1e-12)
                   for year, ap in archived["fold_average_precision"].items()):
                raise ValueError("Historical seed AP differs from aligned saved predictions")
            row.update(candidate=f"{report_path.parent.name}_{archived['candidate']}",
                       origin=report_path.parent.name)
            history.append(row)
            seen.add(identity)
    return history


def seed_study(study, history):
    for row in history:
        params = {key: row["params"][key] for key in DISTRIBUTIONS}
        for key, distribution in DISTRIBUTIONS.items():
            if not distribution._contains(distribution.to_internal_repr(params[key])):
                raise ValueError(f"Historical {key} is outside the declared search space")
        study.add_trial(optuna.trial.create_trial(
            params=params, distributions=DISTRIBUTIONS,
            value=row["mean_fold_average_precision"],
            user_attrs={"origin": row["origin"], "candidate": row["candidate"],
                        "fold_average_precision": row["fold_average_precision"]},
        ))


def suggest_params(trial):
    return {**PARAMS,
            "learning_rate": trial.suggest_float("learning_rate", 0.03, 0.15, log=True),
            "max_iter": trial.suggest_int("max_iter", 40, 200),
            "l2_regularization": trial.suggest_float("l2_regularization", 0.1, 10.0, log=True),
            "min_samples_leaf": trial.suggest_categorical("min_samples_leaf", [50, 100, 200]),
            "max_leaf_nodes": trial.suggest_categorical("max_leaf_nodes", [7, 15, 31])}


def execute(cache, baseline, output, n_trials=N_TRIALS):
    if n_trials < 1:
        raise ValueError("Request at least one new configuration")
    output = Path(output).resolve()
    prepare_output(output)
    configuration = {
        "experiment": "coordinate-hgb-bayesian-v1", "algorithm": "Optuna multivariate TPE",
        "seed": SEED, "new_configurations": n_trials, "specified_new_fits": n_trials * len(FOLD_YEARS),
        "search_space": {key: json.loads(optuna.distributions.distribution_to_json(value))
                         for key, value in DISTRIBUTIONS.items()},
        "sampler": {"n_startup_trials": 0, "multivariate": True},
        "fold_years": FOLD_YEARS, "primary_metric": "unweighted mean yearly average precision",
        "baseline_params": PARAMS, "raw_features": RAW_FEATURES, "transformed_features": TRANSFORMED_FEATURES,
        "threads_per_fit": 2, "parallel_trials": 1, "pruning": False,
        "early_stopping": False, "resampling": False,
        "cache": str(Path(cache).resolve()), "cache_manifest_sha256": sha256(Path(cache) / "manifest.json"),
        "baseline_predictions": str(Path(baseline).resolve()),
        "history_reports": [{"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                             "predictions": str(predictions)} for path, predictions in HISTORIES],
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("optuna", "numpy", "scikit-learn", "joblib", "threadpoolctl")},
        "scope": SCOPE,
    }
    write_json(output / "configuration.json", configuration)
    data = load_data(cache)
    X, y, manifest, grid, centres = data
    history = load_history(data, cache, baseline)
    write_json(output / "seed_results.json", history)
    study = optuna.create_study(
        study_name="coordinate_hgb_bayesian", direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=SEED, n_startup_trials=0, multivariate=True),
        pruner=optuna.pruners.NopPruner(), storage=f"sqlite:///{output / 'study.sqlite3'}",
    )
    seed_study(study, history)
    candidates = []
    seen = {parameter_id(row["params"]) for row in history}
    started = monotonic()

    def objective(trial):
        params = suggest_params(trial)
        identity = parameter_id(params)
        if identity in seen:
            raise ValueError("Sampler repeated a completed configuration")
        seen.add(identity)
        directory = output / identity
        directory.mkdir()
        records = []
        candidate_started = monotonic()
        print(f"Trial {len(candidates) + 1}/{n_trials}: {params}", flush=True)
        for first, last, year in FOLD_YEARS:
            training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
            if training.start != 0 or training.stop != validation.start or last >= year or year > 2016:
                raise ValueError("Expected complete expanding chronological development folds")
            fold_started = monotonic()
            classifier, preprocessor = fit_hgb(
                X[training], y[training], grid[training], centres,
                scratch_dir=output / "scratch", params=params,
            )
            probability = predict_hgb(classifier, preprocessor, X[validation], grid[validation], centres)
            save_predictions(directory, params, year, y[validation], probability)
            joblib.dump({"classifier": classifier, "preprocessor": preprocessor, "params": params,
                         "raw_features": RAW_FEATURES, "transformed_features": TRANSFORMED_FEATURES,
                         "fold": year}, directory / f"fold_{year}.joblib")
            records.append({"fold": year, "params": params, "metrics": fold_metrics(data, year, probability)})
            write_json(directory / f"fold_{year}.json", records[-1])
            print(f"  {year}: AP={records[-1]['metrics']['average_precision']:.9f} "
                  f"({monotonic() - fold_started:.1f}s)", flush=True)
            del classifier, preprocessor, probability
            gc.collect()
        row = {**summarize(params, records), "candidate": f"B{len(candidates) + 1}",
               "trial_number": trial.number, "parameter_id": identity,
               "elapsed_seconds": monotonic() - candidate_started}
        base = history[0]
        row["relative_mean_ap_vs_baseline"] = row["mean_fold_average_precision"] / base["mean_fold_average_precision"] - 1
        row["year_ap_deltas"] = {year: ap - base["fold_average_precision"][year]
                                 for year, ap in row["fold_average_precision"].items()}
        row["years_beating_baseline"] = [year for year, delta in row["year_ap_deltas"].items() if delta > 0]
        candidates.append(row)
        trial.set_user_attr("origin", "bayesian")
        trial.set_user_attr("fold_average_precision", row["fold_average_precision"])
        write_json(directory / "results.json", row)
        write_json(output / "progress.json", {"completed_new_configurations": len(candidates), "candidates": candidates})
        return row["mean_fold_average_precision"]

    study.optimize(objective, n_trials=n_trials, n_jobs=1, gc_after_trial=True)
    selected = max([*history, *candidates], key=lambda row: row["mean_fold_average_precision"])
    results = {
        "status": "complete", "algorithm": "Optuna multivariate TPE", "n_candidates": len(candidates),
        "n_seed_configurations": len(history), "n_splits": len(FOLD_YEARS),
        "specified_candidate_fold_fits": n_trials * len(FOLD_YEARS),
        "baseline": history[0], "candidates": candidates,
        "best_search_candidate": max(candidates, key=lambda row: row["mean_fold_average_precision"]),
        "selected_development_candidate": selected,
        "selected_relative_mean_ap_gain": selected["mean_fold_average_precision"] / history[0]["mean_fold_average_precision"] - 1,
        "selection_rule": "Highest unweighted yearly mean AP; exact ties retain baseline, then history/trial order",
        "elapsed_search_seconds": monotonic() - started, "scope": SCOPE,
    }
    write_json(output / "results.json", results)
    print(f"Selected {selected['candidate']}: mean AP={selected['mean_fold_average_precision']:.9f}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_coordinates")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/bayesian")
    parser.add_argument("--trials", type=int, default=N_TRIALS, help="New full-five-fold configurations (default: 16)")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.baseline, args.output, args.trials)


if __name__ == "__main__":
    main()
