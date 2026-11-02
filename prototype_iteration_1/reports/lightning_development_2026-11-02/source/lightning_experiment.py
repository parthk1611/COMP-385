"""Registered, past-only CG lightning ablation; exposed development data only."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.windows import Window
from scipy.sparse import csr_matrix
from shapely.geometry import box
from threadpoolctl import threadpool_limits

from scripts.ignition_comparison import candidates, corrected_weights, digest, predict_bundle, save_json
from scripts.lightning_pilot import completed_window, interval_clock, overlap_pixels
from scripts.model_refinement import evaluate, frozen_artifacts, paired_recall_interval
from scripts.weather_history_experiment import reliability
from scripts.week5_ignition import fit_calibration

YEARS = tuple(range(2010, 2018))
SPECS = ("reference", "lightning_24h", "lightning_24h_168h")
PROTOCOLS = ("temporal", "inner_spatial")
FOLDS = (2014, 2015)
BUDGETS = (1, 2, 5, 10, 20)
BASE_URL = "https://crd-data-donnees-rdc.ec.gc.ca/CDAS/products/CanCPLD/CLDN/cg/"
KEYS = ["grid_id", "ignition_date"]


def lightning_features(spec):
    if spec not in SPECS:
        raise ValueError("Unregistered candidate")
    windows = () if spec == "reference" else ((24,) if spec == "lightning_24h" else (24, 168))
    return [f"cg_{kind}_{hours}h" for hours in windows for kind in ("density", "coverage")]


def acquire(workspace, raw, output):
    raw.mkdir(parents=True, exist_ok=True)
    receipts = []
    for year in YEARS:
        name = f"cg_flashes_3hr_0.1-deg_{year}.nc"
        old = workspace / "data/raw/zero_cost_sources_2026-11-01" / name
        path = old if old.exists() else raw / name
        url = BASE_URL + name
        if not path.exists():
            temporary = path.with_suffix(".part")
            with requests.get(url, stream=True, timeout=(30, 180), headers={
                "User-Agent": "COMP385-Wildfire-Research/1.0 (academic one-off archive study)"
            }) as response:
                response.raise_for_status()
                with temporary.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
            with rasterio.open(f'NETCDF:"{temporary}":cg_flashes') as source:
                if source.count not in (2920, 2928):
                    raise ValueError("Unexpected annual interval count")
            temporary.replace(path)
        receipts.append({"year": year, "path": str(path), "url": url,
                         "bytes": path.stat().st_size, "sha256": digest(path),
                         "verified_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                         "historical_publication_available_at": None})
        save_json(output / "source_receipts.json", receipts)
        print("source", year, path.stat().st_size, flush=True)
    return receipts


def spatial_weights(grid, archive, area_file):
    records = []
    with rasterio.open(f'NETCDF:"{archive}":cg_flashes') as source, rasterio.open(area_file) as area:
        if source.shape != area.shape or source.transform != area.transform:
            raise ValueError("Lightning and cell-area rasters differ")
        if area.tags().get("cell_area#units") != "m2":
            raise ValueError("Native area unit must be m2")
        for i, cell in enumerate(grid.itertuples()):
            target = box(cell.grid_x_m, cell.grid_y_m, cell.grid_x_m + 10000, cell.grid_y_m + 10000)
            records.extend((i, r, c, w) for r, c, w in overlap_pixels(source, target))
        records = np.asarray(records)
        r0, c0 = records[:, 1:3].min(axis=0).astype(int)
        r1, c1 = records[:, 1:3].max(axis=0).astype(int) + 1
        window = Window(c0, r0, c1 - c0, r1 - r0)
        native = area.read(1, window=window, masked=True).astype(float).filled(np.nan).ravel() / 1e6
        columns = ((records[:, 1] - r0) * (c1 - c0) + records[:, 2] - c0).astype(int)
        matrix = csr_matrix((records[:, 3], (records[:, 0].astype(int), columns)),
                            shape=(len(grid), len(native)))
        used = np.unique(columns)
        if not np.isfinite(native[used]).all() or (native[used] <= 0).any():
            raise ValueError("Missing/nonpositive native area under the model grid")
        np.testing.assert_allclose(np.asarray(matrix.sum(axis=1)).ravel(), 1, atol=1e-6)
        return window, matrix, native, source.transform


def rolling_density(density, coverage, ends, issues, hours):
    """Sum complete three-hour bins ending before each issue; missing is never zero."""
    values = np.vstack([np.zeros((1, density.shape[1])), np.cumsum(density, axis=0, dtype="float64")])
    covered = np.vstack([np.zeros((1, coverage.shape[1])), np.cumsum(coverage, axis=0, dtype="float64")])
    rows, fractions, cutoffs = [], [], []
    for issue in issues:
        indices, cutoff = completed_window(ends, issue, hours)
        a, b = int(indices[0]), int(indices[-1]) + 1
        fraction = (covered[b] - covered[a]) / len(indices)
        total = values[b] - values[a]
        total[fraction < 1 - 1e-6] = np.nan
        rows.append(total)
        fractions.append(fraction)
        cutoffs.append(cutoff)
    return np.asarray(rows, dtype="float32"), np.asarray(fractions, dtype="float32"), pd.DatetimeIndex(cutoffs)


def build_lightning_year(grid, archive, area_file, spatial, year, destination):
    window, matrix, native, transform = spatial
    dates = pd.date_range(f"{year}-05-01", f"{year}-10-31")
    issues = dates.tz_localize("America/Toronto").tz_convert("UTC")
    all_ends = interval_clock(archive)
    wanted = (all_ends > issues[0] - pd.Timedelta(days=8)) & (all_ends <= issues[-1])
    bands = np.flatnonzero(wanted) + 1
    ends = all_ends[wanted]
    densities, coverages = [], []
    with rasterio.open(f'NETCDF:"{archive}":cg_flashes') as source:
        if source.transform != transform or source.tags().get("cg_flashes#units") != "frequency_of_cg_lightning_flashes_per_grid_cell_per_3hours":
            raise ValueError("Source geometry/units changed")
        for offset in range(0, len(bands), 64):
            values = source.read(bands[offset:offset+64].tolist(), window=window, masked=True).astype("float32").filled(np.nan)
            values = values.reshape(len(values), -1)
            valid = np.isfinite(values) & (values >= 0)
            if (np.abs(values[valid] - np.round(values[valid])) > 1e-4).any():
                raise ValueError("Noninteger CG flash counts")
            coverages.append(np.asarray(matrix @ valid.T).T.astype("float32"))
            weighted = np.divide(np.where(valid, values, 0), native, out=np.zeros_like(values), where=np.isfinite(native) & (native > 0))
            densities.append(np.asarray(matrix @ weighted.T).T.astype("float32"))
    density, coverage = np.concatenate(densities), np.concatenate(coverages)
    frame = pd.DataFrame({"ignition_date": np.repeat(dates.strftime("%Y-%m-%d"), len(grid)),
                          "grid_id": np.tile(grid.grid_id, len(dates))})
    audit = {"year": year, "rows": len(frame), "cells": len(grid), "future_interval_violations": 0}
    for hours in (24, 168):
        values, fraction, cutoffs = rolling_density(density, coverage, ends, issues, hours)
        frame[f"cg_density_{hours}h"] = values.ravel()
        frame[f"cg_coverage_{hours}h"] = fraction.ravel()
        if (cutoffs > issues).any():
            raise ValueError("Future lightning interval")
        audit[f"complete_{hours}h_rows"] = int(np.isfinite(values).sum())
        audit[f"nonzero_{hours}h_rows"] = int((values > 0).sum())
    frame.to_parquet(destination, index=False)
    audit.update(sha256=digest(destination), max_lag_to_issue_hours=float(((issues - cutoffs).total_seconds() / 3600).max()))
    return audit


def capacity_curve(frame, probability):
    scored = frame[KEYS + ["ignition"]].copy()
    scored["probability"] = probability
    scored["tie"] = pd.util.hash_pandas_object(scored[KEYS], index=False).to_numpy()
    scored = scored.sort_values(["ignition_date", "probability", "tie"], ascending=[True, False, True])
    scored["rank"] = scored.groupby("ignition_date").cumcount() + 1
    sizes = scored.groupby("ignition_date").size()
    scored["daily_cells"] = scored.ignition_date.map(sizes)
    result = []
    for percent in BUDGETS:
        picked = scored[scored["rank"] <= np.ceil(scored.daily_cells * percent / 100)]
        hits, positives, alerts = int(picked.ignition.sum()), int(scored.ignition.sum()), len(picked)
        result.append({"budget_percent": percent, "hits": hits, "positives": positives,
                       "misses": positives - hits, "alerts": alerts, "false_positives": alerts - hits,
                       "recall": hits / positives if positives else None, "precision": hits / alerts,
                       "reviewed_fraction": alerts / len(scored)})
    scored = scored.drop(columns="tie")
    return result, scored


def choose_candidate(records, protocol):
    frame = pd.DataFrame([r for r in records if r["protocol"] == protocol])
    reference = frame[frame.candidate.eq("reference")].set_index("year").sort_index()
    if set(reference.index) != set(FOLDS) or len(reference) != len(FOLDS):
        raise ValueError("Complete reference folds required")
    eligible = ["reference"]
    for name in SPECS[1:]:
        candidate = frame[frame.candidate.eq(name)].set_index("year").sort_index()
        if len(candidate) != len(FOLDS) or set(candidate.index) != set(FOLDS):
            raise ValueError("Complete matched folds required")
        if (candidate.average_precision.mean() > reference.average_precision.mean()
                and candidate.daily_budget_recall.mean() >= reference.daily_budget_recall.mean()
                and (candidate.average_precision / reference.average_precision >= .9).all()):
            eligible.append(name)
    return max(eligible, key=lambda name: float(frame[frame.candidate.eq(name)].average_precision.mean()))


def fit(sample, population, year, protocol, spec, contract):
    train, pop = sample[sample._year < year], population[population.year < year]
    if protocol == "inner_spatial":
        train, pop = train[train.inner_role.eq("inner_training")], pop[pop.inner_role.eq("inner_training")]
    key = "temporal_candidate_predictors" if protocol == "temporal" else "spatial_candidate_predictors"
    features = contract[key] + lightning_features(spec)
    if protocol == "inner_spatial" and any(f.startswith("fire_history_") for f in features):
        raise ValueError("Fire-history predictors forbidden in geographic transfer")
    model = candidates()["lightgbm"]
    weights = corrected_weights(train.ignition.to_numpy(), int(pop.rows.sum()), int(pop.positives.sum()))
    model.fit(train[features], train.ignition, sample_weight=weights)
    return {"model": model, "features": features, "candidate": spec, "protocol": protocol,
            "mode": "exposed_development_only", "target_version": "wildfire_explicit_PB_excluded_v1",
            "training_through": year - 1, "fitted_rows": len(train)}


def run(workspace, output, cache):
    if output.exists() or cache.exists():
        raise FileExistsError("Use a new experiment/output version")
    history = workspace / "data/processed/weather_history_2026-11-01"
    previous = workspace / "reports/weather_history_2026-11-01/cache_manifest.json"
    manifest = json.loads(previous.read_text())
    protected = frozen_artifacts(workspace)
    output.mkdir(parents=True)
    cache.mkdir(parents=True)
    save_json(output / "protocol.json", {
        "registered_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "registered_before_fitting": True,
        "hypothesis": "Past cloud-to-ground lightning density adds geographically local ignition information absent from weather/terrain inputs.",
        "target": "wildfire_explicit_PB_excluded_v1; reuse verified target and fixed split membership",
        "candidates": SPECS, "selection_folds": FOLDS, "calibration_year": 2016,
        "diagnostic_year": 2017, "diagnostic_is_previously_exposed": True,
        "negative_sample_percent": 1, "all_positives_retained": True, "capacity_percent": 1,
        "cutoff": "Complete 3h intervals ending at/before midnight America/Toronto; 24h/168h windows end at last completed bin; no same-day/future lightning",
        "availability": "2026 processed archive; historical publication time unknown; hindcast only",
        "selection": "Higher mean AP, no lower mean recall at 1%, every fold AP >=90% reference; otherwise reference",
        "confirmation_gate": "Selected nonreference candidate must improve AP and 1% recall without worsening Brier or log loss; development gate only",
        "sensitivity_budgets_percent": BUDGETS, "sensitivity_is_diagnostic_not_selection": True,
        "old_final_records_used": False, "automatic_serving_promotion": False,
        "prior_cache_manifest_sha256": digest(previous), "code_sha256": digest(Path(__file__)),
        "protected_before": protected,
        "references": ["https://www.nature.com/articles/s41597-025-05924-7", BASE_URL]})
    start = time.perf_counter()
    receipts = acquire(workspace, workspace / "data/raw/lightning_development_2026-11-02", output)
    area = workspace / "data/raw/zero_cost_sources_2026-11-01/cell_area_0.1-deg.nc"
    grid = pd.read_csv(workspace / "team_repository/data/interim/ontario_fire_region_10km_grid.csv")
    save_json(output / "geometry_sources.json", {"area_sha256": digest(area), "grid_sha256": digest(workspace / "team_repository/data/interim/ontario_fire_region_10km_grid.csv")})
    spatial = spatial_weights(grid, Path(receipts[0]["path"]), area)
    audits, counts, samples = [], [], []
    contract = json.loads((workspace / "data/processed/ignition_weather_v2_development/predictor_contract.json").read_text())
    columns = KEYS + ["ignition", "inner_role", "_year", "_bucket"] + contract["temporal_candidate_predictors"]
    for receipt in receipts:
        year = receipt["year"]
        source = history / f"{year}.parquet"
        if digest(source) != manifest[source.name]["sha256"]:
            raise ValueError("Previously verified target/feature cache changed")
        lightning = cache / f"lightning_{year}.parquet"
        audits.append(build_lightning_year(grid, Path(receipt["path"]), area, spatial, year, lightning))
        frame = pd.read_parquet(source, columns=columns).merge(pd.read_parquet(lightning), on=KEYS, how="left", validate="one_to_one")
        if len(frame) != len(grid) * 184 or frame.cg_coverage_24h.isna().any():
            raise ValueError("Incomplete lightning key join")
        frame.to_parquet(cache / f"{year}.parquet", index=False)
        for role, group in frame.groupby("inner_role", observed=True):
            counts.append({"year": year, "inner_role": role, "rows": len(group), "positives": int(group.ignition.sum())})
        if year <= 2015:
            samples.append(frame[frame.ignition.eq(1) | frame._bucket.lt(1)])
        save_json(output / "feature_audit.json", audits)
        print("features", year, audits[-1], flush=True)
    sample, population = pd.concat(samples, ignore_index=True), pd.DataFrame(counts)
    records = []
    for year in FOLDS:
        validation = pd.read_parquet(cache / f"{year}.parquet")
        for protocol in PROTOCOLS:
            val = validation if protocol == "temporal" else validation[validation.inner_role.eq("inner_validation")]
            for spec in SPECS:
                bundle = fit(sample, population, year, protocol, spec, contract)
                result, _, _ = evaluate(bundle, val)
                result.update(year=year, protocol=protocol, candidate=spec)
                records.append(result)
                save_json(output / "rolling_results.json", records)
                print("fold", year, protocol, spec, result["hits"], result["average_precision"], flush=True)
    selected = {p: choose_candidate(records, p) for p in PROTOCOLS}
    save_json(output / "selection_freeze.json", {"selected": selected, "frozen_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "before_2017_scoring": True})
    calibration, diagnostic = pd.read_parquet(cache / "2016.parquet"), pd.read_parquet(cache / "2017.parquet")
    results, curves, paired, gates = [], {}, {}, {}
    for protocol in PROTOCOLS:
        cal = calibration if protocol == "temporal" else calibration[calibration.inner_role.eq("inner_training")]
        val = diagnostic if protocol == "temporal" else diagnostic[diagnostic.inner_role.eq("inner_validation")]
        budgets, by_name = {}, {}
        curves[protocol] = {}
        for spec in SPECS:
            bundle = fit(sample, population, 2016, protocol, spec, contract)
            raw = predict_bundle(bundle, cal[bundle["features"]])
            bundle["calibrator"] = fit_calibration(cal.ignition.to_numpy(), raw)
            result, budget, probability = evaluate(bundle, val)
            model_path = cache / f"{protocol}_{spec}.joblib"
            joblib.dump(bundle, model_path, compress=3)
            loaded = joblib.load(model_path)
            np.testing.assert_allclose(predict_bundle(loaded, val.iloc[:100][bundle["features"]]), predict_bundle(bundle, val.iloc[:100][bundle["features"]]), rtol=1e-12)
            result.update(protocol=protocol, candidate=spec, model_sha256=digest(model_path), save_load_parity=True)
            results.append(result)
            by_name[spec], budgets[spec] = result, budget
            budget.to_csv(output / f"{protocol}_{spec}_daily.csv", index=False)
            reliability(val, probability).to_csv(output / f"{protocol}_{spec}_reliability.csv", index=False)
            curves[protocol][spec], ranked = capacity_curve(val, probability)
            if protocol == "inner_spatial":
                ranked.to_parquet(cache / f"{protocol}_{spec}_predictions.parquet", index=False)
                ranked[ranked.ignition.eq(1)].to_csv(output / f"{protocol}_{spec}_positive_ranks.csv", index=False)
            save_json(output / "diagnostic_progress.json", results)
            print("diagnostic", protocol, spec, result["hits"], result["average_precision"], flush=True)
        paired[protocol] = {name: paired_recall_interval(budgets["reference"], budgets[name]) for name in SPECS[1:]}
        ref, candidate = by_name["reference"], by_name[selected[protocol]]
        gates[protocol] = bool(selected[protocol] != "reference" and candidate["average_precision"] > ref["average_precision"]
            and candidate["daily_budget_recall"] > ref["daily_budget_recall"] and candidate["brier"] <= ref["brier"] and candidate["log_loss"] <= ref["log_loss"])
    if frozen_artifacts(workspace) != protected:
        raise RuntimeError("Protected scientific artifacts changed")
    result = {"experiment": output.name, "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
              "results": results, "capacity_curves": curves, "selected": selected,
              "paired_recall_intervals": paired, "development_gates_pass": gates,
              "promoted": False, "operational": False, "protected_artifacts_unchanged": True,
              "model_fits": 18, "scope": "Exposed 2017 development diagnostics; not a new clean test",
              "elapsed_seconds": time.perf_counter() - start}
    save_json(output / "results.json", result)
    save_json(output / "cache_manifest.json", {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(cache.iterdir()) if p.is_file()})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        run(args.workspace.resolve(), args.output_dir.resolve(), args.cache_dir.resolve())
