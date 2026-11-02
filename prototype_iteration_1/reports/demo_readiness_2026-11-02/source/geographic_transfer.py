"""Bounded physical-feature model comparison on the existing development geography."""

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from threadpoolctl import threadpool_limits

from scripts.ignition_comparison import candidates, corrected_weights, digest, predict_bundle, save_json
from scripts.lightning_experiment import capacity_curve
from scripts.model_refinement import evaluate, frozen_artifacts, paired_recall_interval
from scripts.weather_history_experiment import reliability
from scripts.week5_ignition import fit_calibration

SPECS = ("reference", "physical_logistic", "physical_monotonic")
FOLDS = (2014, 2015)
PHYSICAL = ["calendar_doy_sin", "calendar_doy_cos", "calendar_is_weekend", "calendar_day_length_hours",
            "terrain_elevation_mean_m", "terrain_slope_deg", "terrain_ruggedness_m",
            "cwfis_temp_c", "cwfis_rh_pct", "cwfis_wind_speed_kmh", "cwfis_precip_mm",
            "cwfis_ffmc", "cwfis_dmc", "cwfis_dc", "cwfis_precip_7d_mm",
            "cg_density_24h", "cg_density_168h"]


def select(records):
    rows = pd.DataFrame(records)
    reference = rows[rows.candidate.eq("reference")].set_index("year").sort_index()
    if len(reference) != 2 or set(reference.index) != set(FOLDS):
        raise ValueError("Complete matched reference folds required")
    eligible = ["reference"]
    for name in SPECS[1:]:
        candidate = rows[rows.candidate.eq(name)].set_index("year").sort_index()
        if len(candidate) != 2 or set(candidate.index) != set(FOLDS):
            raise ValueError("Incomplete candidate folds")
        if (candidate.average_precision.mean() > reference.average_precision.mean()
                and candidate.daily_budget_recall.mean() >= reference.daily_budget_recall.mean()
                and (candidate.average_precision / reference.average_precision >= .9).all()):
            eligible.append(name)
    return max(eligible, key=lambda name: float(rows[rows.candidate.eq(name)].average_precision.mean()))


def train(sample, population, cutoff, spec, contract):
    if spec not in SPECS or cutoff not in (2014, 2015, 2016):
        raise ValueError("Unregistered fit")
    if not sample.inner_role.eq("inner_training").all():
        raise ValueError("Only buffered inner-training geography may be fitted")
    frame = sample[sample._year.lt(cutoff)]
    pop = population[population.year.lt(cutoff)]
    weights = corrected_weights(frame.ignition.to_numpy(), int(pop.rows.sum()), int(pop.positives.sum()))
    features = contract["spatial_candidate_predictors"] if spec == "reference" else PHYSICAL
    if any(x.startswith("fire_history_") for x in features):
        raise ValueError("Geographic fitting cannot use fire-history predictors")
    model = clone(candidates()["logistic" if spec == "physical_logistic" else "lightgbm"])
    if spec == "physical_logistic":
        model.set_params(classifier__C=.1)
        model.fit(frame[features], frame.ignition, scaler__sample_weight=weights, classifier__sample_weight=weights)
    else:
        if spec == "physical_monotonic":
            constraints = [int(x in ("cwfis_ffmc", "cwfis_dmc", "cwfis_dc", "cg_density_24h", "cg_density_168h")) for x in features]
            model.set_params(n_estimators=250, learning_rate=.03, num_leaves=7, max_depth=3,
                             min_child_samples=300, reg_lambda=20., monotone_constraints=constraints)
        model.fit(frame[features], frame.ignition, sample_weight=weights)
    return {"model": model, "features": features, "candidate": spec, "protocol": "inner_spatial",
            "mode": "exposed_development_only", "target_version": "wildfire_explicit_PB_excluded_v1",
            "training_through": cutoff - 1, "fitted_rows": len(frame)}


def run(workspace, output, cache):
    if output.exists() or cache.exists():
        raise FileExistsError("Use new experiment versions")
    base_report = workspace / "reports/lightning_development_2026-11-02"
    source = workspace / "data/processed/lightning_development_2026-11-02"
    manifest = json.loads((base_report / "cache_manifest.json").read_text())
    contract_path = workspace / "data/processed/ignition_weather_v2_development/predictor_contract.json"
    contract = json.loads(contract_path.read_text())
    protected = frozen_artifacts(workspace)
    output.mkdir(parents=True)
    cache.mkdir(parents=True)
    save_json(output / "protocol.json", {
        "registered_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "registered_before_fitting": True,
        "hypothesis": "A simpler physical-response model, excluding station/reporting coverage as learned risk predictors, transfers better across geography.",
        "scope": "New bounded development comparison, not tuning against the 92 known cases",
        "candidates": SPECS, "physical_features": PHYSICAL, "selection_folds": FOLDS,
        "selection_rule": "Higher mean AP, no lower mean 1% recall, no fold AP below 90% reference; otherwise reference",
        "monotonic_constraints": "Nondecreasing FFMC/DMC/DC and CG densities; other predictors unconstrained",
        "quality": "Source quality retained in upstream cache; not silently filled. Logistic imputation/indicators fit on training only; tree handles native missingness.",
        "negative_sampling": "All positives and existing deterministic 1% negatives, population-corrected weights",
        "spatial_protocol": "Existing inner-training geography and buffer; no history features or held geography in fitting/calibration",
        "calibration": "2016 inner-training geography", "diagnostic": "Previously exposed 2017 inner-validation geography",
        "gate": "Selected nonreference candidate improves diagnostic AP and fixed 1% recall, neither Brier nor log loss worse; development only",
        "candidate_choice_uses_diagnostic": False, "automatic_promotion": False,
        "source_manifest_sha256": digest(base_report / "cache_manifest.json"),
        "contract_sha256": digest(contract_path), "code_sha256": digest(Path(__file__)), "protected_before": protected})
    start = time.perf_counter()
    samples, counts = [], []
    for year in range(2010, 2016):
        path = source / f"{year}.parquet"
        if digest(path) != manifest[path.name]["sha256"]:
            raise ValueError("Registered source changed")
        frame = pd.read_parquet(path)
        frame = frame[frame.inner_role.eq("inner_training")]
        counts.append({"year": year, "rows": len(frame), "positives": int(frame.ignition.sum())})
        samples.append(frame[frame.ignition.eq(1) | frame._bucket.lt(1)])
    sample, population = pd.concat(samples, ignore_index=True), pd.DataFrame(counts)
    records = []
    for year in FOLDS:
        validation = pd.read_parquet(source / f"{year}.parquet", filters=[("inner_role", "==", "inner_validation")])
        for spec in SPECS:
            bundle = train(sample, population, year, spec, contract)
            result, _, _ = evaluate(bundle, validation)
            result.update(year=year, candidate=spec, protocol="inner_spatial")
            records.append(result)
            save_json(output / "rolling_results.json", records)
            print("fold", year, spec, result["hits"], result["average_precision"], flush=True)
    selected = select(records)
    save_json(output / "selection_freeze.json", {"selected": selected, "before_2017_scoring": True,
              "frozen_at_utc": pd.Timestamp.now(tz="UTC").isoformat()})
    for year in (2016, 2017):
        if digest(source / f"{year}.parquet") != manifest[f"{year}.parquet"]["sha256"]:
            raise ValueError("Calibration/diagnostic source changed")
    calibration = pd.read_parquet(source / "2016.parquet", filters=[("inner_role", "==", "inner_training")])
    diagnostic = pd.read_parquet(source / "2017.parquet", filters=[("inner_role", "==", "inner_validation")])
    results, budgets, curves = [], {}, {}
    for spec in SPECS:
        bundle = train(sample, population, 2016, spec, contract)
        bundle["calibrator"] = fit_calibration(calibration.ignition.to_numpy(), predict_bundle(bundle, calibration[bundle["features"]]))
        result, budget, probability = evaluate(bundle, diagnostic)
        path = cache / f"inner_spatial_{spec}.joblib"
        joblib.dump(bundle, path, compress=3)
        loaded = joblib.load(path)
        np.testing.assert_allclose(predict_bundle(bundle, diagnostic.iloc[:100][bundle["features"]]), predict_bundle(loaded, diagnostic.iloc[:100][bundle["features"]]), rtol=1e-12)
        result.update(candidate=spec, protocol="inner_spatial", model_sha256=digest(path), save_load_parity=True)
        results.append(result)
        budgets[spec] = budget
        budget.to_csv(output / f"{spec}_daily.csv", index=False)
        curves[spec], ranked = capacity_curve(diagnostic, probability)
        ranked.to_parquet(cache / f"inner_spatial_{spec}_predictions.parquet", index=False)
        ranked[ranked.ignition.eq(1)].to_csv(output / f"{spec}_positive_ranks.csv", index=False)
        reliability(diagnostic, probability).to_csv(output / f"{spec}_reliability.csv", index=False)
        print("diagnostic", spec, result["hits"], result["average_precision"], flush=True)
    ref = next(r for r in results if r["candidate"] == "reference")
    previous = next(r for r in json.loads((base_report / "results.json").read_text())["results"] if r["protocol"] == "inner_spatial" and r["candidate"] == "reference")
    for key in ("hits", "positives", "average_precision", "brier", "log_loss"):
        np.testing.assert_allclose(ref[key], previous[key], rtol=1e-12)
    chosen = next(r for r in results if r["candidate"] == selected)
    gate = bool(selected != "reference" and chosen["average_precision"] > ref["average_precision"]
                and chosen["daily_budget_recall"] > ref["daily_budget_recall"] and chosen["brier"] <= ref["brier"] and chosen["log_loss"] <= ref["log_loss"])
    if frozen_artifacts(workspace) != protected:
        raise RuntimeError("Protected scientific artifacts changed")
    result = {"experiment": output.name, "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
              "results": results, "selected": {"inner_spatial": selected},
              "development_gates_pass": {"inner_spatial": gate}, "capacity_curves": {"inner_spatial": curves},
              "paired_recall_intervals": {name: paired_recall_interval(budgets["reference"], budgets[name]) for name in SPECS[1:]},
              "model_fits": 9, "reference_parity": True, "protected_artifacts_unchanged": True,
              "promoted": False, "operational": False, "elapsed_seconds": time.perf_counter() - start,
              "scope": "Exposed geographic development; no untouched evaluation or live qualification"}
    save_json(output / "results.json", result)
    save_json(output / "cache_manifest.json", {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)} for p in cache.iterdir() if p.is_file()})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "output-dir", "cache-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        run(args.workspace.resolve(), args.output_dir.resolve(), args.cache_dir.resolve())
