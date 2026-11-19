"""Paired, year-stratified whole-day bootstrap of saved baseline and B9 AP."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import argparse
import json
import platform
from importlib.metadata import version
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from experiments.ignition.common import (
    DEFAULT_CACHE, ROOT, SEED, candidate_name, load_predictions, prepare_output,
)
from scripts.ignition_modeling.data import load_cache, year_slice
from scripts.ignition_modeling.run import write_json
from scripts.ignition_modeling.weather import sha256

YEARS = tuple(range(2012, 2017))
REPORT = Path(__file__).with_name("results.json")
DEFAULT_BASELINE = ROOT / "artifacts/ignition_modeling/hgb_coordinates"
DEFAULT_BAYESIAN = ROOT / "artifacts/ignition_modeling/reruns/bayesian"
DEFAULT_OUTPUT = DEFAULT_BAYESIAN / "paired_day_bootstrap"


def day_counts(rng, n_days, n_resamples):
    """Draw n_days whole days with replacement for each replicate."""
    draws = rng.integers(n_days, size=(n_resamples, n_days))
    return np.array([np.bincount(draw, minlength=n_days) for draw in draws])


def day_bootstrap_ap(labels, probability, offsets, counts):
    """Exact AP for integer day multiplicities, including tied score groups.

    Only thresholds containing positives contribute to AP. Precompute each
    day's positive mass and total mass above those thresholds, then weight by
    day multiplicity. This avoids sorting millions of rows per replicate;
    negatives, including negative-only days, still contribute to precision.
    """
    thresholds = np.unique(probability[labels == 1])[::-1]
    if len(thresholds) == 0:
        return np.zeros(len(counts))
    total_ge = np.empty((len(thresholds), len(offsets) - 1))
    positive_ge = np.empty_like(total_ge)
    for day, (start, end) in enumerate(zip(offsets[:-1], offsets[1:])):
        scores = probability[start:end]
        positives = scores[labels[start:end] == 1]
        total_ge[:, day] = len(scores) - np.searchsorted(np.sort(scores), thresholds, side="left")
        positive_ge[:, day] = len(positives) - np.searchsorted(np.sort(positives), thresholds, side="left")
    positive_at = np.diff(positive_ge, axis=0, prepend=np.zeros((1, positive_ge.shape[1])))
    weighted_at = positive_at @ counts.T
    cumulative_positive = np.cumsum(weighted_at, axis=0)
    cumulative_total = total_ge @ counts.T
    precision = np.divide(cumulative_positive, cumulative_total,
                          out=np.zeros_like(cumulative_positive), where=cumulative_total > 0)
    numerator = np.sum(weighted_at * precision, axis=0)
    # Match sklearn's AP=0 convention for draws with no positive labels; do not
    # redraw or discard them, which would change the requested bootstrap law.
    return np.divide(numerator, cumulative_positive[-1], out=np.zeros_like(numerator),
                     where=cumulative_positive[-1] > 0)


def interval(values):
    return np.quantile(values, [0.025, 0.975], method="linear").tolist()


def execute(cache, baseline, bayesian, output, n_resamples=2000, seed=SEED):
    if not 1000 <= n_resamples <= 2000:
        raise ValueError("Use 1000--2000 resamples")
    cache, baseline, bayesian, output = map(Path, (cache, baseline, bayesian, output))
    archive = json.loads(REPORT.read_text())
    b9 = next(row for row in archive["candidates"] if row["candidate"] == "B9")
    base = archive["baseline"]
    manifest_hash = sha256(cache / "manifest.json")
    configurations = [json.loads((directory / "configuration.json").read_text())
                      for directory in (baseline, bayesian)]
    for configuration in configurations:
        if (configuration["cache_manifest_sha256"] != manifest_hash
                or [fold[2] for fold in configuration["fold_years"]] != list(YEARS)):
            raise ValueError("Prediction sources must share the original cache and five folds")
    if sha256(cache / "y.u8") != configurations[0]["cache_files_sha256"]["y.u8"]:
        raise ValueError("Cache labels differ from the baseline's pinned labels")
    _, labels, manifest = load_cache(cache)
    prepare_output(output)
    rng = np.random.default_rng(seed)
    fold_ap = np.empty((n_resamples, len(YEARS), 2))
    observed = np.empty((len(YEARS), 2))
    saved_counts, folds = {}, []
    for index, year in enumerate(YEARS):
        selection = year_slice(manifest, year)
        days = [(day, start, end) for day, (start, end) in manifest["date_slices"].items()
                if day.startswith(str(year))]
        expected_days = np.arange(np.datetime64(f"{year}-05-01"), np.datetime64(f"{year}-11-01"))
        if ([day for day, _, _ in days] != expected_days.astype(str).tolist()
                or days[0][1] != selection.start or days[-1][2] != selection.stop
                or any(end - start != 9673 for _, start, end in days)
                or any(left[2] != right[1] for left, right in zip(days, days[1:]))):
            raise ValueError("Expected complete, contiguous, chronological fire-season days")
        offsets = np.array([start - selection.start for _, start, _ in days]
                           + [selection.stop - selection.start])
        counts = day_counts(rng, len(days), n_resamples)
        saved_counts[str(year)] = counts
        y = labels[selection]
        record = {"year": year, "days": len(days), "rows": len(y),
                  "positives": int(y.sum()), "sources": {}}
        for model, (name, directory, row) in enumerate((
            ("baseline", baseline, base), ("B9", bayesian / b9["parameter_id"], b9),
        )):
            probability = load_predictions(directory, row["params"], year, y)
            observed[index, model] = average_precision_score(y, probability)
            np.testing.assert_allclose(observed[index, model], row["fold_average_precision"][str(year)],
                                       rtol=0, atol=1e-12)
            # The same counts matrix is reused for both models, never row draws.
            fold_ap[:, index, model] = day_bootstrap_ap(y, probability, offsets, counts)
            np.testing.assert_allclose(day_bootstrap_ap(y, probability, offsets, np.ones((1, len(days)))),
                                       observed[index, model], rtol=0, atol=1e-12)
            # Independent full-row, weighted sklearn proof on a real bootstrap
            # draw for each model/year, not just the unresampled point estimate.
            weighted_ap = average_precision_score(y, probability,
                                                  sample_weight=np.repeat(counts[0], np.diff(offsets)))
            np.testing.assert_allclose(fold_ap[0, index, model], weighted_ap, rtol=0, atol=1e-12)
            path = directory / f"fold_{year}_{candidate_name(row['params'])}.npz"
            record["sources"][name] = {"path": str(path), "sha256": sha256(path),
                                        "observed_ap": float(observed[index, model])}
        positive_days = np.array([y[start:end].sum() for start, end in zip(offsets[:-1], offsets[1:])])
        record["zero_positive_resamples"] = int(np.count_nonzero(counts @ positive_days == 0))
        differences = fold_ap[:, index, 1] - fold_ap[:, index, 0]
        record.update(observed_delta_ap=float(observed[index, 1] - observed[index, 0]),
                      delta_ap_95_percentile_interval=interval(differences),
                      fraction_b9_better=float(np.mean(differences > 0)))
        folds.append(record)
        print(f"{year}: verified aligned labels and weighted AP; {n_resamples} paired day draws", flush=True)
    means = fold_ap.mean(axis=1)
    deltas = means[:, 1] - means[:, 0]
    relative_deltas = means[:, 1] / means[:, 0] - 1
    observed_means = observed.mean(axis=0)
    np.savez_compressed(output / "replicates.npz", years=np.array(YEARS), fold_ap=fold_ap,
                        baseline_mean_ap=means[:, 0], b9_mean_ap=means[:, 1], delta_ap=deltas,
                        **{f"day_counts_{year}": counts for year, counts in saved_counts.items()})
    result = {
        "status": "complete", "resamples": n_resamples, "seed": seed,
        "rng": "numpy.default_rng / PCG64; years ascending; integers then bincount",
        "resampling": "Within each year draw 184 whole days with replacement; same draw for both models; years independent",
        "estimand": "B9 minus baseline, unweighted mean of five yearly APs (not pooled AP or mean daily AP)",
        "observed": {"baseline_mean_ap": float(observed_means[0]), "b9_mean_ap": float(observed_means[1]),
                     "delta_ap": float(observed_means[1] - observed_means[0]),
                     "relative_change": float(observed_means[1] / observed_means[0] - 1)},
        "bootstrap": {"mean_delta_ap": float(deltas.mean()), "median_delta_ap": float(np.median(deltas)),
                      "standard_error_delta_ap": float(deltas.std(ddof=1)),
                      "delta_ap_95_percentile_interval": interval(deltas),
                      "relative_change_95_percentile_interval": interval(relative_deltas),
                      "fraction_b9_better": float(np.mean(deltas > 0)),
                      "fraction_b9_worse": float(np.mean(deltas < 0)),
                      "fraction_tied": float(np.mean(deltas == 0)),
                      "n_b9_better": int(np.count_nonzero(deltas > 0)),
                      "n_b9_worse": int(np.count_nonzero(deltas < 0))},
        "folds": folds, "params": {"baseline": base["params"], "B9": b9["params"]},
        "provenance": {"cache_manifest_sha256": manifest_hash, "labels_sha256": sha256(cache / "y.u8"),
                       "experiment_results_sha256": sha256(REPORT), "bootstrap_source_sha256": sha256(Path(__file__)),
                       "replicates_sha256": sha256(output / "replicates.npz"),
                       "python": platform.python_version(),
                       "packages": {name: version(name) for name in ("numpy", "scikit-learn", "threadpoolctl")}},
        "verification": "All 10 original APs match archive; exact AP matches sklearn on uniform weights and first full-row bootstrap draw for each model/year, atol=1e-12",
        "limitations": ["Conditional on saved fits and five fixed development years; no retraining or year resampling",
                        "Does not correct adaptive selection of B9 on repeatedly reused development folds",
                        "Whole-day resampling retains within-day spatial correlation but not dependence between adjacent days",
                        "Bootstrap win fraction is not a posterior probability or a selection-adjusted p-value"],
        "delta_ap_replicates": deltas.tolist(),
    }
    write_json(output / "results.json", result)
    print(json.dumps({"observed": result["observed"], "bootstrap": result["bootstrap"]}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--bayesian", type=Path, default=DEFAULT_BAYESIAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.baseline, args.bayesian, args.output, args.resamples, args.seed)


if __name__ == "__main__":
    main()
