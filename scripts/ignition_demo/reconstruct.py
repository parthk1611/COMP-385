"""Reconstruct only the frozen winner; preserve the original experiment's reports."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import gc
import gzip
import hashlib
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, log_loss
from threadpoolctl import threadpool_limits

from scripts.ignition_modeling.contract import CACHE_VERSION, FEATURE_NAMES, ROOT, SEED
from scripts.ignition_modeling.data import load_cache, prepare_cache, year_slice
from scripts.ignition_modeling.histogram import train_hgb
from scripts.ignition_modeling.run import check_gate, predict_bundle
from scripts.ignition_modeling.weather import sha256
from .common import CACHE, OUTPUT, alert_policy, checked_probabilities, confusion, read_json, write_json


def verify_cache(directory):
    """Scan daily keys/labels/quality independently of the cache writer."""
    X, y, manifest = load_cache(directory)
    grid = pd.read_csv(ROOT / "data/interim/ontario_fire_region_10km_grid.csv")
    ids = np.memmap(Path(directory) / "grid.u16", dtype="uint16", mode="r", shape=(len(y),))
    reference = read_json(ROOT / "docs/modeling/corrected_weather_audit.json")
    quality = {name: FEATURE_NAMES.index(name) for name in
               ("cwfis_missing", "cwfis_station_count", "cwfis_precip_7d_mm", "cwfis_precip_7d_coverage_days")}
    annual, end, previous = {}, 0, ""
    for day, (start, stop) in manifest["date_slices"].items():
        if not (day > previous and start == end and stop - start == len(grid)):
            raise ValueError("Cache date slices are not complete and chronological")
        if not np.array_equal(np.sort(ids[start:stop]), np.arange(len(grid))):
            raise ValueError("Cache day has duplicated or missing grid IDs")
        block, labels = X[start:stop], y[start:stop]
        if np.isinf(block).any() or not np.isin(labels, [0, 1]).all():
            raise ValueError("Invalid numeric cache values")
        missing = block[:, quality["cwfis_missing"]]
        count = block[:, quality["cwfis_station_count"]]
        coverage = block[:, quality["cwfis_precip_7d_coverage_days"]]
        rain_missing = np.isnan(block[:, quality["cwfis_precip_7d_mm"]])
        if not np.array_equal(missing, count == 0) or np.any((count < 0) | (count > 4)):
            raise ValueError("Weather missingness disagrees with station count")
        if not np.array_equal(rain_missing, coverage < 7) or np.any((coverage < 0) | (coverage > 7)):
            raise ValueError("Rain missingness disagrees with completed-date coverage")
        stats = annual.setdefault(day[:4], dict(rows=0, positives=0, weather_missing=0, rain_7d_missing=0))
        stats["rows"] += stop - start
        stats["positives"] += int(labels.sum())
        stats["weather_missing"] += int(missing.sum())
        stats["rain_7d_missing"] += int(rain_missing.sum())
        previous, end = day, stop
    if end != 17798320 or len(manifest["date_slices"]) != 1840 or annual != reference["annual"]:
        raise ValueError("Cache counts disagree with published corrected-cache audit")
    check_gate(manifest)
    return {"status": "PASS", "rows": end, "dates": 1840, "cells": len(grid),
            "annual": annual, "source_checksum": manifest["original_panel_sha256"],
            "weather_checksum": manifest["weather_source_audit"]["source_sha256"],
            "cache_sha256": {name: sha256(Path(directory) / name) for name in ("X.f64", "y.u8", "grid.u16")},
            "checks": ["exact feature schema", "full daily grid permutations", "chronological contiguous dates",
                       "binary labels", "no infinities", "station/missing consistency", "rain/coverage consistency",
                       "all annual counts match published reference", "original training gate"]}


def metrics(y, p):
    return {"rows": len(y), "positive_cell_days": int(y.sum()),
            "average_precision": float(average_precision_score(y, p)),
            "roc_auc": float(roc_auc_score(y, p)),
            "brier_score": float(np.mean((p - y) ** 2)), "log_loss": float(log_loss(y, p)),
            "prevalence": float(y.mean())}


def reconstruct(source, cache, output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "verification.json").exists():
        print("Completed reconstruction exists; preserve it. Use a new --output for another run.", flush=True)
        return
    if source.suffix == ".gz":
        target = ROOT / "data/processed/ontario_fire_region_10km_daily_ignition_features_v1.csv"
        expected = read_json(ROOT / "docs/modeling/data_quality_report.json")["source"]["sha256"]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".csv.recovering")
            digest = hashlib.sha256()
            with gzip.open(source, "rb") as reader, temporary.open("wb") as writer:
                for block in iter(lambda: reader.read(8 << 20), b""):
                    writer.write(block); digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError("Decompressed input differs from the original audited CSV")
            temporary.replace(target)
        if sha256(target) != expected:
            raise ValueError("Existing uncompressed panel differs from the original audited CSV")
        source = target
    original = read_json(ROOT / "docs/modeling/final_freeze.json")
    # prepare_cache publishes a compact audit. Capture the new copy while restoring
    # the exact original report bytes, including when reconstruction is interrupted.
    audit_path = ROOT / "docs/modeling/corrected_weather_audit.json"
    original_audit = audit_path.read_bytes()
    try:
        prepare_cache(source, cache)
        (output / "rebuilt_cache_audit.json").write_bytes(audit_path.read_bytes())
    finally:
        if audit_path.read_bytes() != original_audit:
            audit_path.write_bytes(original_audit)
    print("Independently scanning corrected cache", flush=True)
    verified = verify_cache(cache)
    write_json(output / "cache_verification.json", verified)
    X, y, manifest = load_cache(cache)
    policy = alert_policy()
    write_json(output / "alert_policy.json", policy)
    selected = original["selected"]
    train = year_slice(manifest, 2010, 2016)
    model_path = output / "selected_system.joblib"
    if (output / "freeze.json").exists():
        freeze = read_json(output / "freeze.json")
        if sha256(model_path) != freeze["system_sha256"] or freeze["cache_sha256"] != verified["cache_sha256"]:
            raise ValueError("Existing reconstruction no longer matches its freeze")
        bundle = joblib.load(model_path)
    else:
        print(f"Fitting frozen HGB winner on {train.stop - train.start:,} training rows", flush=True)
        pipeline, diagnostics = train_hgb(X[train], y[train], selected["params"], scratch_dir=output / "scratch", seed=SEED)
        bundle = {"pipeline": pipeline, "calibrator": None, "features": list(FEATURE_NAMES),
                  "cache_version": CACHE_VERSION, "thresholds": original["thresholds"]}
        joblib.dump(bundle, model_path)
        indices = np.linspace(train.start, train.stop - 1, 512, dtype=int)
        np.testing.assert_allclose(predict_bundle(bundle, X[indices]),
                                   predict_bundle(joblib.load(model_path), X[indices]), rtol=0, atol=1e-14)
        write_json(output / "training.json", diagnostics)
        freeze = {"kind": "reconstructed frozen winner; original experiment preserved",
                  "frozen_at_utc": datetime.now(timezone.utc).isoformat(), "fit_years": [2010, 2016],
                  "seed": SEED, "selected": selected, "calibrator": None, "policy": policy,
                  "python": platform.python_version(),
                  "packages": {n: version(n) for n in ["numpy", "pandas", "scipy", "scikit-learn", "joblib", "threadpoolctl"]},
                  "cache_version": CACHE_VERSION, "source_sha256": manifest["original_panel_sha256"],
                  "cache_sha256": verified["cache_sha256"], "system_sha256": sha256(model_path),
                  "original_system_sha256": original["system_sha256"],
                  "source_code_sha256": {p.name: sha256(p) for p in (ROOT / "scripts/ignition_modeling").glob("*.py")}}
        write_json(output / "freeze.json", freeze)
    print("System frozen. Evaluating reconstructed 2018 and 2019 scores without tuning.", flush=True)
    results = {}
    for year in [2018, 2019]:
        selection = year_slice(manifest, year)
        p = checked_probabilities(predict_bundle(bundle, X[selection]), selection.stop - selection.start)
        labels = np.asarray(y[selection])
        results[str(year)] = {**metrics(labels, p), "thresholds": [
            {"threshold": choice["threshold"], **confusion(labels, p, choice["threshold"])} for choice in policy["choices"]]}
        np.savez_compressed(output / f"predictions_{year}.npz", p=p, y=labels)
        write_json(output / f"results_{year}.json", results[str(year)])
        print(f"Reconstructed {year} AP: {results[str(year)]['average_precision']:.12f}", flush=True)
        del p; gc.collect()
    reference = read_json(ROOT / "docs/modeling/final_test.json")
    differences = {key: results["2019"][key] - reference[key] for key in
                   ("average_precision", "roc_auc", "brier_score", "log_loss")}
    thresholds_match = all(
        all(actual[key] == expected[key] for key in ("true_positive", "false_positive", "true_negative", "false_negative"))
        for actual, expected in zip(results["2019"]["thresholds"], reference["threshold_tradeoffs"]))
    verification = {"status": "PASS" if max(abs(v) for v in differences.values()) < 1e-8 and thresholds_match else "DISCREPANCY",
                    "comparison": "Reconstructed results versus original published 2019 results; no test-driven tuning",
                    "metric_differences": differences, "metric_absolute_tolerance": 1e-8,
                    "all_eight_confusion_tables_match": thresholds_match, "reload_max_absolute_tolerance": 1e-14,
                    "original_model_bytes_recovered": False, "cache_status": verified["status"],
                    "freeze_sha256": sha256(output / "freeze.json")}
    write_json(output / "verification.json", verification)
    print(f"Reconstruction verification: {verification['status']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/processed/ontario_fire_region_10km_daily_ignition_features_v1.csv")
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        reconstruct(args.input, args.cache, args.output)
