"""Measure retained ignition HGB reliance by shuffling predictors within validation dates."""

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.ignition.common import DEFAULT_CACHE, prepare_output  # sets thread defaults

import numpy as np
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from scripts.ignition_modeling import contract, data, histogram, run, splits

FEATURES = contract.FEATURE_NAMES
YEARS = tuple(year for _, _, year in splits.FOLD_YEARS)
ROWS_PER_DAY = 9673
DAYS_PER_YEAR = 184
REPEATS = 5
REFERENCE = Path(__file__).resolve().parents[1] / "coordinate_capacity" / "results.json"
GROUP_SPECS = (
    ("calendar", "calendar_", 5),
    ("terrain", "terrain_", 7),
    ("CWFIS weather", "cwfis_", 19),
    ("fire history", "fire_history_", 6),
    ("coordinates", "cell_centroid_", 2),
)


def feature_groups():
    groups = {}
    for name, prefix, count in GROUP_SPECS:
        columns = tuple(i for i, feature in enumerate(FEATURES) if feature.startswith(prefix))
        if len(columns) != count:
            raise ValueError(f"Expected {count} {name} predictors; found {len(columns)}")
        groups[name] = columns
    if sorted(i for columns in groups.values() for i in columns) != list(range(len(FEATURES))):
        raise ValueError("Feature groups must partition the canonical ordered predictors")
    return groups


def checked_season(manifest, first, last):
    selection = data.year_slice(manifest, first, last)
    expected = [
        (date(year, 5, 1) + timedelta(days=offset)).isoformat()
        for year in range(first, last + 1)
        for offset in range(DAYS_PER_YEAR)
    ]
    if not 0 <= selection.start < selection.stop <= manifest["rows"]:
        raise ValueError(f"Invalid cache row bounds for {first}–{last}")
    selected = [
        (day, start, stop)
        for day, (start, stop) in manifest["date_slices"].items()
        if first <= int(day[:4]) <= last or (start < selection.stop and stop > selection.start)
    ]
    if [day for day, _, _ in selected] != expected:
        raise ValueError(f"Cache dates do not match ordered May–October seasons for {first}–{last}")
    cursor = selection.start
    for day, start, stop in selected:
        if start != cursor or stop != cursor + ROWS_PER_DAY:
            raise ValueError(f"Cache date {day} does not tile its slice with {ROWS_PER_DAY} rows")
        cursor = stop
    if cursor != selection.stop:
        raise ValueError(f"Cache date blocks do not cover {first}–{last} slice")
    return selection, tuple((start - selection.start, stop - selection.start)
                            for _, start, stop in selected)


def fold_slices(manifest):
    folds = []
    for first, last, year in splits.FOLD_YEARS:
        train, _ = checked_season(manifest, first, last)
        valid, days = checked_season(manifest, year, year)
        if train.stop != valid.start:
            raise ValueError(f"Training and validation seasons do not meet at fold {year}")
        folds.append((year, train, valid, days))
    return folds


def fit_fold(X, y, scratch):
    pipeline, _ = histogram.train_hgb(
        X, y, contract.RETAINED_HGB_PARAMS, scratch_dir=scratch, seed=contract.SEED,
    )
    classifier = pipeline["classifier"]
    if classifier.n_iter_ != 80 or classifier.n_features_in_ != len(FEATURES):
        raise ValueError("Fitted classifier must retain 80 iterations and the canonical feature width")
    if tuple(pipeline["preprocessor"].get_feature_names_out()) != FEATURES:
        raise ValueError("Fitted transformer changed canonical feature order")
    return pipeline


def baseline_probability(pipeline, X, y, year, reference_ap):
    if not np.array_equal(np.unique(y), [0, 1]):
        raise ValueError(f"Validation fold {year} must contain both binary classes")
    probability = run.predict_chunks(pipeline, X)
    ap = average_precision_score(y, probability)
    if not math.isfinite(ap) or ap <= 0 or not math.isclose(ap, reference_ap, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"Fold {year} baseline AP {ap!r} disagrees with {reference_ap!r}; "
                         "compare corrected cache version/provenance and retained HGB settings")
    return probability, ap


def donor_indices(days, year, repeat):
    rng = np.random.default_rng(np.random.SeedSequence([contract.SEED, year, repeat]))
    indices = np.empty(days[-1][1], dtype=np.intp)
    for start, stop in days:
        indices[start:stop] = start + rng.permutation(stop - start)
    return indices


def day_constant_columns(source, days):
    constant = set()
    for column in range(source.shape[1]):
        for start, stop in days:
            first = source[start, column]
            values = source[start:stop, column]
            if not (np.isnan(values) if np.isnan(first) else values == first).all():
                break
        else:
            constant.add(column)
    return constant


def perturbation_drop(source, work, columns, donors, baseline_ap, score):
    """Score with selected columns swapped together; restore work even if scoring fails."""
    changed = []
    try:
        for column in columns:
            values = source[donors, column]
            if not np.array_equal(values, source[:, column], equal_nan=True):
                changed.append(column)
                work[:, column] = values
        return baseline_ap - score(work) if changed else 0.0
    finally:
        for column in changed:
            work[:, column] = source[:, column]


def score_fold(pipeline, source, y, days, year, reference_ap, targets):
    baseline, baseline_ap = baseline_probability(pipeline, source, y, year, reference_ap)
    classifier = pipeline["classifier"]
    work = np.array(source, dtype=np.float64, order="C", copy=True)
    if not np.array_equal(run.predict_chunks(classifier, work), baseline):
        raise ValueError(f"Fold {year} pristine classifier probabilities differ from pipeline baseline")
    del baseline
    print(f"{year}: baseline AP {baseline_ap!r}; classifier input verified", flush=True)
    constant = day_constant_columns(source, days)

    def score(matrix):
        return average_precision_score(y, run.predict_chunks(classifier, matrix))

    drops = {name: [] for name in targets}
    for repeat in range(REPEATS):
        donors = donor_indices(days, year, repeat)
        for name, columns in targets.items():
            # Never send shuffled history/flag pairs through the production validator.
            changing = tuple(column for column in columns if column not in constant)
            drops[name].append(perturbation_drop(source, work, changing, donors, baseline_ap, score))
        print(f"{year}: scored repeat {repeat + 1}/{REPEATS} ({len(targets)} targets)", flush=True)
    return baseline_ap, drops, constant


def summarize(baselines, drops, names):
    records = []
    years = sorted(baselines)
    for name in names:
        annual = {year: math.fsum(drops[year][name]) / len(drops[year][name]) for year in years}
        percent = {year: 100 * annual[year] / baselines[year] for year in years}
        low, high = min(years, key=annual.__getitem__), max(years, key=annual.__getitem__)
        low_pct, high_pct = min(years, key=percent.__getitem__), max(years, key=percent.__getitem__)
        row = {
            "name": name,
            "mean_ap_drop": math.fsum(annual.values()) / len(years),
            "mean_pct_baseline_ap": math.fsum(percent.values()) / len(years),
            "min_ap_drop": annual[low],
            "min_ap_drop_year": low,
            "max_ap_drop": annual[high],
            "max_ap_drop_year": high,
            "min_pct_baseline_ap": percent[low_pct],
            "min_pct_year": low_pct,
            "max_pct_baseline_ap": percent[high_pct],
            "max_pct_year": high_pct,
        }
        for year in years:
            row[f"baseline_ap_{year}"] = baselines[year]
            row[f"ap_drop_{year}"] = annual[year]
            row[f"pct_drop_{year}"] = percent[year]
        records.append(row)
    return sorted(records, key=lambda row: (-row["mean_pct_baseline_ap"], row["name"]))


def brackets_zero(row):
    return row["min_ap_drop"] <= 0 <= row["max_ap_drop"]


def plot_importance(path, rows):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 1.4 + 0.35 * len(rows)), layout="constrained")
    values = [row["mean_pct_baseline_ap"] for row in rows]
    ax.barh([row["name"] for row in rows], values,
            color=["#a74828" if value < 0 else "#276a94" for value in values])
    ax.axvline(0, color="0.25", linewidth=0.8)
    # Keep the zero line inside the plot even when every displayed drop is positive.
    scale = max(map(abs, values)) or 1
    left, right = ax.get_xlim()
    ax.set_xlim(min(left, -0.15 * scale), max(right, 0.15 * scale))
    ax.invert_yaxis()
    ax.set_xlabel("Mean within-day AP drop (% of validation-year baseline)")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def result_block(baselines, features, groups, constant):
    def formatted(rows):
        return ", ".join(f"`{row['name']}` ({row['mean_pct_baseline_ap']:.3f}%)"
                         for row in rows) or "none"

    baseline_text = ", ".join(f"{year}: {ap!r}" for year, ap in baselines.items())
    constants = ", ".join(f"`{name}`" for i, name in enumerate(FEATURES) if i in constant)
    return "\n".join((
        f"- Baseline AP: {baseline_text}.",
        f"- Top five predictors: {formatted(features[:5])}.",
        f"- Feature families: {formatted(groups)}.",
        f"- Negative mean percent drop: {formatted(row for row in features if row['mean_pct_baseline_ap'] < 0)}.",
        "- Negative mean raw AP drop: " + (", ".join(
            f"`{row['name']}`" for row in features if row["mean_ap_drop"] < 0) or "none") + ".",
        f"- Fold AP drops bracket zero (inclusive): {formatted(row for row in features if brackets_zero(row))}.",
        f"- Exactly constant within every validation day: {constants or 'none'}.",
    ))


def execute(cache, output):
    X, y, manifest = data.load_cache(cache)
    run.check_gate(manifest)
    folds = fold_slices(manifest)
    groups = feature_groups()
    features = {name: (i,) for i, name in enumerate(FEATURES)}
    targets = features | groups
    reference = json.loads(REFERENCE.read_text())["variants"]["coordinates_15"]["fold_average_precision"]
    output = prepare_output(output)
    baselines, drops = {}, {}
    constant_all_years = set(range(len(FEATURES)))
    with TemporaryDirectory(prefix="ignition-permutation-") as scratch, threadpool_limits(limits=2):
        for year, train, valid, days in folds:
            print(f"{year}: fitting retained HGB80 on {train.stop - train.start:,} rows", flush=True)
            pipeline = fit_fold(X[train], y[train], scratch)
            baselines[year], drops[year], constant = score_fold(
                pipeline, X[valid], y[valid], days, year, reference[str(year)], targets,
            )
            constant_all_years &= constant
            del pipeline

    feature_rows = summarize(baselines, drops, features)
    group_rows = summarize(baselines, drops, groups)
    run.write_csv(output / "feature_importance.csv", feature_rows)
    run.write_csv(output / "group_importance.csv", group_rows)
    plot_importance(output / "top_15_features.png", feature_rows[:15])
    plot_importance(output / "group_importance.png", group_rows)
    print(result_block(baselines, feature_rows, group_rows, constant_all_years), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    execute(args.cache, args.output)
