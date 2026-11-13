"""Add only 1/7-day neighbourhood history to fixed coordinate HGB; development only."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
from collections import Counter, deque
from datetime import date
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from scripts.build_ignition_feature_panel import DEFAULT_EVENTS, FireHistory, load_events, load_grid
from experiments.ignition.common import (
    ROOT, GRID_PATH, DEFAULT_CACHE, FOLD_YEARS, PARAMS,
    RAW_FEATURES as BASE_RAW, TRANSFORMED_FEATURES as BASE_TRANSFORMED,
    load_data, prepare_output, fit_hgb, predict_hgb, evaluate_saved,
    fold_metrics, summarize, save_predictions,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json

FEATURE_VERSION = "ignition-weather-v2-cell-centres-recent-neighborhood-v1"
RECENT_NAMES = ("fire_history_neighborhood_1d", "fire_history_neighborhood_7d")
RAW_FEATURES = (*BASE_RAW, *RECENT_NAMES)
TRANSFORMED_FEATURES = (*BASE_TRANSFORMED, *RECENT_NAMES)


def history_days(grid, events, dates):
    """Reuse original event-count/3x3 semantics; snapshot state before each issue day."""
    if not dates or any(left >= right for left, right in zip(dates, dates[1:])):
        raise ValueError("History issue dates must be strictly increasing")
    history = FireHistory(grid)
    # Extend the original public window state, without changing the frozen builder.
    history.windows.update({days: (deque(), Counter(), Counter()) for days in (1, 7)})
    pending = deque((day, key) for day in sorted(events) for key in events[day])
    keys = list(grid)
    for issue in dates:
        history.advance(issue, pending)
        values = np.empty((len(keys), 2), dtype=np.float64)
        for column, days in enumerate((1, 7)):
            counter = history.windows[days][2]
            values[:, column] = np.fromiter((counter[key] for key in keys), dtype=np.float64, count=len(keys))
        yield issue, values


def build_recent_features(X, y, row_ids, manifest, grid, events):
    """Build strictly pre-issue development counts from the original event records."""
    development = year_slice(manifest, 2010, 2016)
    if development.start != 0:
        raise ValueError("Expected the unchanged 2010-start panel")
    date_rows = [(date.fromisoformat(day), start, stop) for day, (start, stop) in manifest["date_slices"].items()
                 if 2010 <= int(day[:4]) <= 2016]
    recent = np.empty((development.stop, 2), dtype=np.uint32)
    lookup = {key: index for index, key in enumerate(grid)}
    rows_checked = 0
    positive_rows = 0
    for (issue, start, stop), (computed_day, values) in zip(date_rows, history_days(grid, events, [item[0] for item in date_rows])):
        if computed_day != issue or start != rows_checked or stop-start != len(grid):
            raise ValueError("History date/grid row universe differs from cache")
        ids = row_ids[start:stop]
        if not np.array_equal(np.sort(ids), np.arange(len(grid))):
            raise ValueError("Each date must contain exactly the frozen grid")
        event_counts = np.zeros(len(grid), dtype=np.uint32)
        for key in events.get(issue, ()):
            event_counts[lookup[key]] += 1
        expected_labels = (event_counts[ids] > 0).astype(np.uint8)
        if not np.array_equal(expected_labels, y[start:stop]):
            raise ValueError(f"Event-source labels do not reproduce on {issue}; do not fit")
        current = values[ids]
        if np.any(current < 0) or np.any(current > np.iinfo(np.uint32).max):
            raise ValueError("Recent-history event count out of range")
        recent[start:stop] = current
        rows_checked = stop
        positive_rows += int(expected_labels.sum())
    if rows_checked != development.stop:
        raise ValueError("History features do not cover development rows")
    return recent, {
        "status": "PASS", "rows_checked": rows_checked, "dates_checked": len(date_rows),
        "positive_cell_days_checked": positive_rows,
        "source_records_in_development": sum(len(events.get(day, ())) for day, _, _ in date_rows),
        "recent_dtype": str(recent.dtype), "recent_maxima": recent.max(axis=0).tolist(),
        "source_semantics": "Counts individual selected ignition records, not binary positive cell-days; 3x3 includes own cell",
        "timing": "Only t-1 for 1d; t-7 through t-1 inclusive for 7d; advance after source day completes",
        "coverage": "Selected fire-season history starts in 2010; no fabricated pre-2010 or unselected off-season records",
        "availability": "Retrospective ignition dates; historical discovery/report available_at is unknown",
    }


def execute(cache, baseline, output):
    data = load_data(cache)
    X, y, manifest, row_ids, centres = data
    if Path(output).resolve() in (Path(cache).resolve(), Path(baseline).resolve()):
        raise ValueError("Recent-history output must be separate from baseline/cache")
    output = prepare_output(output)
    base_summary = {**evaluate_saved(data, baseline, PARAMS), "variant": "coordinates"}
    grid = load_grid(GRID_PATH)
    days = [date.fromisoformat(day) for day in manifest["date_slices"] if 2010 <= int(day[:4]) <= 2016]
    events = load_events(DEFAULT_EVENTS, grid, days)
    recent, history = build_recent_features(X, y, row_ids, manifest, grid, events)
    records = []
    for first, last, year in FOLD_YEARS:
        training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
        if training.stop > validation.start or last >= year or year > 2016:
            raise ValueError("Partitions overlap or access reserved years")
        print(f"Fitting recent-history fold {year}", flush=True)
        classifier, preprocessor = fit_hgb(
            X[training], y[training], row_ids[training], centres,
            scratch_dir=output / "scratch", params=PARAMS, extra=recent[training])
        probability = predict_hgb(classifier, preprocessor, X[validation], row_ids[validation], centres,
                                  extra=recent[validation])
        save_predictions(output, PARAMS, year, y[validation], probability)
        records.append({"fold": year, "params": PARAMS, "metrics": fold_metrics(data, year, probability)})
        del classifier, preprocessor, probability
    new_summary = {**summarize(PARAMS, records), "variant": "coordinates_and_recent_history"}
    results = {
        "status": "complete", "feature_set_version": FEATURE_VERSION,
        "raw_features": list(RAW_FEATURES), "transformed_features": list(TRANSFORMED_FEATURES),
        "history": history, "baseline": base_summary, "with_recent_history": new_summary,
        "relative_mean_ap_gain": new_summary["mean_fold_average_precision"] / base_summary["mean_fold_average_precision"] - 1,
        "year_ap_changes": {year: new_summary["fold_average_precision"][year] - value
                            for year, value in base_summary["fold_average_precision"].items()},
        "selected_variant": "with_recent_history" if new_summary["mean_fold_average_precision"] > base_summary["mean_fold_average_precision"] else "baseline",
        "scope": "Exactly two recent-history predictors; five development fits only; no 2017--2019 features, fits or scores",
    }
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_coordinates")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/recent_history")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.baseline, args.output)


if __name__ == "__main__":
    main()
