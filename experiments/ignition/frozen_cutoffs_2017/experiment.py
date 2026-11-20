"""Freeze OOF-only policies, then score the retained model on 2017 once.

Run select and score as separate commands. report only reads saved predictions.
No training, calibration, cache rebuilding, or 2018--2019 data access occurs.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import csv
import hashlib
import json
import math
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from scripts.ignition_modeling.contract import CACHE_VERSION, FEATURE_NAMES
from scripts.ignition_modeling.data import load_cache, year_slice
from scripts.ignition_modeling.run import predict_bundle
from scripts.ignition_modeling.weather import sha256

OUTPUT = Path(__file__).resolve().parent
CACHE = Path("data/interim/ignition_modeling_cache")
MODEL = Path("artifacts/ignition_modeling/retained_coordinate_hgb")
OOF = Path("artifacts/ignition_modeling/reruns/coordinates_20261119")
GRID = Path("data/interim/ontario_fire_region_10km_grid.csv")
YEARS = range(2012, 2017)


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text())


def save_json(path, data, *, exclusive=False):
    with path.open("x" if exclusive else "w") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def validate_probability(y, p):
    if y.ndim != 1 or p.shape != y.shape or not np.isin(y, [0, 1]).all():
        raise ValueError("Invalid prediction/label shape or nonbinary labels")
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("Invalid probabilities")


def recall_threshold(y, p):
    """Highest inclusive threshold achieving at least half the positives."""
    positives = p[y == 1]
    if not len(positives):
        raise ValueError("Cannot select recall threshold without positives")
    required = math.ceil(len(positives) / 2)
    return float(np.partition(positives, len(positives) - required)[-required])


def counts(y, predicted):
    tp = int(np.count_nonzero(predicted & (y == 1)))
    fp = int(np.count_nonzero(predicted & (y == 0)))
    positives = int(y.sum())
    return {"TP": tp, "FP": fp, "FN": positives - tp,
            "TN": len(y) - positives - fp,
            "total_cell_days": len(y), "total_fire_cell_days": positives}


def daily_top(p, grids, daily_sizes, k):
    """Rank descending by score, then ascending frozen grid-file index."""
    predicted = np.zeros(len(p), dtype=bool)
    offset = 0
    for size in daily_sizes:
        end = offset + size
        indices = grids[offset:end]
        if size < k or not np.array_equal(np.sort(indices), np.arange(size)):
            raise ValueError("Daily grid is not the complete frozen cell universe")
        selected = np.lexsort((indices, -p[offset:end]))[:k]
        predicted[offset + selected] = True
        offset = end
    if offset != len(p):
        raise ValueError("Daily slices do not cover the prediction vector")
    return predicted


def daily_sizes(manifest, year):
    days = [(d, start, end) for d, (start, end) in manifest["date_slices"].items()
            if int(d[:4]) == year]
    selection = year_slice(manifest, year)
    if (len(days) != 184 or [d for d, _, _ in days] != sorted(d for d, _, _ in days)
            or days[0][1] != selection.start or days[-1][2] != selection.stop
            or any(end - start != 9673 for _, start, end in days)
            or any(left[2] != right[1] for left, right in zip(days, days[1:]))):
        raise ValueError("Expected 184 contiguous complete 9,673-cell days")
    return [end - start for _, start, end in days]


def context():
    """Only metadata, model bytes, and grid geometry; no test observations."""
    metadata = read_json(MODEL / "model_metadata.json")
    manifest = read_json(CACHE / "manifest.json")
    if (sha256(CACHE / "manifest.json") != metadata["cache_manifest_sha256"]
            or sha256(MODEL / "selected_system.joblib") != metadata["model_sha256"]
            or sha256(GRID) != manifest["reference_grid_sha256"]
            or manifest["cache_version"] != CACHE_VERSION
            or manifest["features"] != list(FEATURE_NAMES)
            or metadata["features"] != list(FEATURE_NAMES)
            or metadata["fit_years"] != [2010, 2016]
            or metadata["params"]["max_iter"] != 80
            or manifest["corrected_value_checks"]["status"] != "PASS"):
        raise ValueError("Frozen model/cache contract mismatch")
    return metadata, manifest


def summarize(y, p, grids, sizes, policies):
    validate_probability(y, p)
    return {
        "top_1pct_daily": counts(y, daily_top(
            p, grids, sizes, policies["top_1pct_daily"]["cells_per_day"])),
        "development_recall_50pct": counts(
            y, p >= policies["development_recall_50pct"]["probability_threshold"]),
    }


def select():
    if (OUTPUT / "cutoffs.json").exists():
        raise FileExistsError("Preserve the frozen cutoffs; selection cannot be repeated here")
    metadata, manifest = context()
    verification = read_json(OOF / "verification.json")
    if (verification["status"] != "PASS"
            or verification["params"]["max_iter"] != 80
            or verification["transformed_features"] != list(FEATURE_NAMES)
            or verification["grid_sha256"] != manifest["reference_grid_sha256"]):
        raise ValueError("Saved OOF predictions are not the retained coordinate configuration")
    # Mapping does not read observations. Only 2012--2016 slices are accessed below.
    labels = np.memmap(CACHE / "y.u8", dtype="uint8", mode="r", shape=(manifest["rows"],))
    grid = np.memmap(CACHE / "grid.u16", dtype="uint16", mode="r", shape=labels.shape)
    folds, sources = {}, []
    for year in YEARS:
        path = OOF / f"fold_{year}_iter_80_l2_1p0_leaves_15_min_100.npz"
        digest = sha256(path)
        recorded = next(f for f in verification["folds"] if f["year"] == year)
        if digest != recorded["prediction_sha256"]:
            raise ValueError(f"Saved OOF checksum mismatch: {year}")
        with np.load(path, allow_pickle=False) as saved:
            y, p = saved["y"], saved["p"]
        validate_probability(y, p)
        selection = year_slice(manifest, year)
        sizes = daily_sizes(manifest, year)
        if not np.array_equal(y, labels[selection]):
            raise ValueError(f"OOF labels differ from training-cache labels: {year}")
        folds[year] = (y, p, grid[selection], sizes)
        sources.append({"year": year, "path": str(path), "sha256": digest,
                        "rows": len(y), "positive_cell_days": int(y.sum()),
                        "training_years": [2010, year - 1]})
    y = np.concatenate([folds[year][0] for year in YEARS])
    p = np.concatenate([folds[year][1] for year in YEARS])
    threshold = recall_threshold(y, p)
    policies = {
        "top_1pct_daily": {
            "type": "daily_rank_budget", "fraction": 0.01,
            "cells_per_day": math.ceil(0.01 * 9673), "total_cells_per_day": 9673,
            "rounding": "ceil", "order": "probability descending, frozen grid-file index ascending",
            "note": "Exactly 97 cells daily, including quiet days; not a fixed probability threshold.",
        },
        "development_recall_50pct": {
            "type": "fixed_probability_threshold", "probability_threshold": threshold,
            "comparison": ">=", "target_recall": 0.5,
            "selection": "Highest inclusive threshold with pooled OOF recall at least 0.5; include all score ties.",
            "development_true_positives": int(np.count_nonzero((y == 1) & (p >= threshold))),
            "development_fire_cell_days": int(y.sum()),
        },
    }
    per_fold = {str(year): summarize(*folds[year], policies) for year in YEARS}
    pooled = {policy: {key: sum(per_fold[str(year)][policy][key] for year in YEARS)
                       for key in per_fold["2012"][policy]} for policy in policies}
    record = {
        "frozen_at_utc": now(), "selection_years": list(YEARS),
        "test_observations_accessed": False, "policies": policies,
        "model_path": str(MODEL / "selected_system.joblib"),
        "model_sha256": metadata["model_sha256"],
        "model_metadata_sha256": sha256(MODEL / "model_metadata.json"),
        "cache_path": str(CACHE), "cache_manifest_sha256": metadata["cache_manifest_sha256"],
        "cache_version": manifest["cache_version"], "grid_sha256": manifest["reference_grid_sha256"],
        "oof_sources": sources, "oof_verification_sha256": sha256(OOF / "verification.json"),
        "oof_recorded_cache_version": verification["cache_version"],
        "oof_recorded_cache_manifest_sha256": verification["cache_manifest_sha256"],
        "oof_cache_note": "Saved OOF used the prior v2 cache plus derived censor/coordinates. Its verified 39-input order and grid match v3; all OOF labels match v3. OOF probabilities are reused unchanged, not regenerated.",
        "experiment_source_sha256": sha256(Path(__file__)),
    }
    save_json(OUTPUT / "development_results.json", {"pooled": pooled, "folds": per_fold}, exclusive=True)
    # This durable write completes before any command can access test observations.
    save_json(OUTPUT / "cutoffs.json", record, exclusive=True)
    print(json.dumps({"saved": str(OUTPUT / "cutoffs.json"), "policies": policies}, indent=2), flush=True)


def score():
    cutoffs = read_json(OUTPUT / "cutoffs.json")
    cutoff_hash = sha256(OUTPUT / "cutoffs.json")
    metadata, manifest = context()
    if (metadata["model_sha256"] != cutoffs["model_sha256"]
            or metadata["cache_manifest_sha256"] != cutoffs["cache_manifest_sha256"]):
        raise ValueError("Frozen selection inputs changed")
    bundle = joblib.load(MODEL / "selected_system.joblib")
    classifier = bundle["pipeline"]["classifier"]
    if (classifier.n_iter_ != 80 or classifier.n_features_in_ != 39
            or bundle["training"] != metadata["training"]
            or classifier.get_params() != metadata["params"]):
        raise ValueError("Loaded estimator differs from the frozen export")
    sizes = daily_sizes(manifest, 2017)
    # An exclusive durable marker prevents accidental second scoring, even after interruption.
    start = {"started_at_utc": now(), "cutoffs_sha256": cutoff_hash,
             "cutoffs_frozen_at_utc": cutoffs["frozen_at_utc"], "year": 2017,
             "model_sha256": cutoffs["model_sha256"]}
    save_json(OUTPUT / "scoring_started.json", start, exclusive=True)
    X, y, _ = load_cache(CACHE)
    selection = year_slice(manifest, 2017)
    # Exactly one prediction per held-out cell-day, in bounded batches.
    with threadpool_limits(limits=2):
        p = predict_bundle(bundle, X[selection])
    test_y = np.asarray(y[selection]).copy()
    validate_probability(test_y, p)
    with (OUTPUT / "predictions_2017.npz").open("xb") as stream:
        np.savez_compressed(stream, y=test_y, p=p)
    evidence = {
        **start, "completed_at_utc": now(), "rows_scored": len(p),
        "prediction_passes": 1, "model_fit_calls": 0,
        "cache_selection": [selection.start, selection.stop],
        "selected_X_sha256": hashlib.sha256(memoryview(X[selection])).hexdigest(),
        "selected_y_sha256": hashlib.sha256(test_y).hexdigest(),
        "predictions_sha256": sha256(OUTPUT / "predictions_2017.npz"),
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("numpy", "scikit-learn", "joblib", "matplotlib")},
        "experiment_source_sha256": sha256(Path(__file__)),
        "scope": "2017 only, frozen 2010--2016 model and unchanged training-period v3 cache; no fitting/calibration or 2018--2019 observation access.",
    }
    save_json(OUTPUT / "scoring_completed.json", evidence, exclusive=True)
    report()


def figure(path, title, record):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    ax.axis("off")
    matrix = [[record["TP"], record["FN"]], [record["FP"], record["TN"]]]
    table = ax.table(cellText=[[f"{value:,}" for value in row] for row in matrix],
                     rowLabels=["actual fire", "actual no fire"],
                     colLabels=["predicted fire", "predicted no fire"],
                     cellLoc="center", rowLoc="center", bbox=[0.27, 0.08, 0.72, 0.70])
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    for cell in table.get_celld().values():
        cell.set_facecolor("white")
        cell.set_edgecolor("black")
        cell.set_linewidth(0.8)
    ax.set_title(title, fontsize=13, pad=12)
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def report():
    """Render from saved predictions only; never invoke model inference."""
    cutoffs = read_json(OUTPUT / "cutoffs.json")
    completed = read_json(OUTPUT / "scoring_completed.json")
    if (sha256(OUTPUT / "cutoffs.json") != completed["cutoffs_sha256"]
            or sha256(OUTPUT / "predictions_2017.npz") != completed["predictions_sha256"]):
        raise ValueError("Frozen policies or saved predictions changed")
    development = read_json(OUTPUT / "development_results.json")
    manifest = read_json(CACHE / "manifest.json")
    grid = np.memmap(CACHE / "grid.u16", dtype="uint16", mode="r", shape=(manifest["rows"],))
    selection = year_slice(manifest, 2017)
    with np.load(OUTPUT / "predictions_2017.npz", allow_pickle=False) as saved:
        y, p = saved["y"], saved["p"]
    heldout = summarize(y, p, grid[selection], daily_sizes(manifest, 2017), cutoffs["policies"])
    results = {"development_2012_2016_oof_pooled": development["pooled"], "heldout_2017": heldout}
    rows = []
    for split, policies in results.items():
        for policy, record in policies.items():
            tp, fp, fn = record["TP"], record["FP"], record["FN"]
            row = {"split": split, "policy": policy, **record,
                   "precision_fraction": f"{tp}/{tp + fp}", "recall_fraction": f"{tp}/{tp + fn}",
                   "precision": tp / (tp + fp) if tp + fp else None,
                   "recall": tp / (tp + fn) if tp + fn else None}
            rows.append(row)
            label = "Development 2012–2016 OOF" if split.startswith("development") else "Held-out 2017"
            policy_label = "Top 97 cells daily" if policy == "top_1pct_daily" else "Development recall cutoff"
            figure(OUTPUT / f"{split}__{policy}.png", f"{label} — {policy_label}", record)
    with (OUTPUT / "confusion_matrices.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    save_json(OUTPUT / "results.json", {"cutoffs_sha256": completed["cutoffs_sha256"],
              "rows": rows, "development_folds": development["folds"]})
    print(json.dumps(rows, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["select", "score", "report"])
    args = parser.parse_args()
    {"select": select, "score": score, "report": report}[args.stage]()
