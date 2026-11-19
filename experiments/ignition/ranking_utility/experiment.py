"""Recompute development daily screening budgets from saved predictions only."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.ignition.common import DEFAULT_CACHE, FEATURE_NAMES, PARAMS, load_data, load_predictions, prepare_output
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json, write_csv

BUDGETS = (1, 2, 5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--predictions', type=Path, default=ROOT / 'artifacts/ignition_modeling/hgb_coordinates')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/ignition_modeling/reruns/ranking_utility')
    args = parser.parse_args(argv)
    X, y, manifest, _, _ = load_data(args.cache)
    prepare_output(args.output)
    with (ROOT / "data/interim/ontario_fire_region_10km_grid.csv").open() as stream:
        grid_names = [row["grid_id"] for row in csv.DictReader(stream)]
    assert len(grid_names) == len(set(grid_names)) == 9673
    priority = np.empty(len(grid_names), dtype=np.int64)
    for rank, index in enumerate(sorted(range(len(grid_names)), key=grid_names.__getitem__)):
        priority[index] = rank
    grid = np.memmap(args.cache / "grid.u16", dtype="uint16", mode="r", shape=(len(y),))
    weather_index = FEATURE_NAMES.index("cwfis_missing")

    counts = defaultdict(lambda: defaultdict(float))
    daily = []

    def add(key, labels, selected, group):
        item = counts[key]
        size = int(group.sum())
        positive = int(np.count_nonzero(labels & group))
        alerts = int(np.count_nonzero(selected & group))
        true_positive = int(np.count_nonzero(selected & labels & group))
        item["n_samples"] += size
        item["n_positive"] += positive
        item["n_alerts"] += alerts
        item["true_positive"] += true_positive
        item["n_dates"] += 1
        item["days_with_rows"] += int(size > 0)

    for year in range(2012, 2017):
        validation = year_slice(manifest, year)
        probability = load_predictions(args.predictions, PARAMS, year, y[validation])
        dates = [(day, start, stop) for day, (start, stop) in manifest["date_slices"].items() if int(day[:4]) == year]
        assert len(dates) == 184 and dates == sorted(dates)
        assert dates[0][1] == validation.start and dates[-1][2] == validation.stop
        assert all(left[2] == right[1] for left, right in zip(dates, dates[1:]))
        for day, start, stop in dates:
            assert validation.start <= start < stop <= validation.stop and stop-start == 9673
            ids = grid[start:stop]
            assert np.array_equal(np.sort(ids), np.arange(9673))
            labels = y[start:stop].astype(bool)
            score = probability[start-validation.start:stop-validation.start]
            weather = X[start:stop, weather_index]
            assert np.all((weather == 0) | (weather == 1))
            order = np.lexsort((priority[ids], -score))
            for percent in BUDGETS:
                k = (len(score)*percent + 99)//100
                selected = np.zeros(len(score), dtype=bool)
                selected[order[:k]] = True
                threshold = score[order[k-1]]
                above, tied = score > threshold, score == threshold
                slots, tie_count = k-int(above.sum()), int(tied.sum())
                tp_above, tp_tied = int(labels[above].sum()), int(labels[tied].sum())
                minimum = tp_above + max(0, slots - (tie_count - tp_tied))
                maximum = tp_above + min(slots, tp_tied)
                expected = tp_above + slots*tp_tied/tie_count
                tp = int(np.count_nonzero(selected & labels))
                assert minimum <= tp <= maximum and minimum <= expected <= maximum
                random_tp = k*int(labels.sum())/len(labels)
                for period in (str(year), "pooled"):
                    for group_name, group in (("all", np.ones(len(score), dtype=bool)), ("covered", weather == 0), ("missing", weather == 1)):
                        add((period, percent, group_name), labels, selected, group)
                    total = counts[(period, percent, "all")]
                    total["tie_minimum_true_positive"] += minimum
                    total["tie_maximum_true_positive"] += maximum
                    total["tie_expected_true_positive"] += expected
                    total["ambiguous_cutoff_days"] += int(tie_count > slots)
                    total["cutoff_tie_cells"] += tie_count
                    total["random_expected_true_positive"] += random_tp
                digest = hashlib.sha256(np.sort(ids[selected]).astype("<u2").tobytes()).hexdigest()
                daily.append({"date": day, "year": year, "budget_percent": percent, "n_samples": len(score),
                              "n_positive": int(labels.sum()), "n_alerts": k, "true_positive": tp, "false_positive": k-tp,
                              "cutoff_score": float(threshold), "cutoff_tie_cells": tie_count, "tie_slots": slots,
                              "tie_minimum_true_positive": minimum, "tie_maximum_true_positive": maximum,
                              "tie_expected_true_positive": expected, "selected_grid_codes_sha256": digest})
        del probability

    rows = []
    integer_fields = ("n_samples", "n_positive", "n_alerts", "true_positive", "n_dates", "days_with_rows",
                      "tie_minimum_true_positive", "tie_maximum_true_positive", "ambiguous_cutoff_days", "cutoff_tie_cells")
    for (period, percent, group), raw in sorted(counts.items()):
        item = dict(raw)
        for field in integer_fields:
            if field in item:
                item[field] = int(item[field])
        n, positive, alerts, tp, days = (item[key] for key in ("n_samples", "n_positive", "n_alerts", "true_positive", "n_dates"))
        negative, fp, fn = n-positive, alerts-tp, positive-tp
        item.update(period=period, budget_percent=percent, weather_group=group, n_negative=negative,
                    false_positive=fp, false_negative=fn, true_negative=negative-fp,
                    prevalence=positive/n if n else None, precision=tp/alerts if alerts else None,
                    recall=tp/positive if positive else None, alerts_per_day=alerts/days,
                    true_positives_per_day=tp/days, false_alerts_per_day=fp/days,
                    false_positive_rate=fp/negative if negative else None,
                    false_alerts_per_10000_cell_days=10000*fp/n if n else None)
        if group == "all":
            item.update(random_expected_recall=item["random_expected_true_positive"]/positive,
                        recall_lift_vs_random=tp/item["random_expected_true_positive"],
                        tie_expected_precision=item["tie_expected_true_positive"]/alerts,
                        tie_expected_recall=item["tie_expected_true_positive"]/positive,
                        tie_minimum_recall=item["tie_minimum_true_positive"]/positive,
                        tie_maximum_recall=item["tie_maximum_true_positive"]/positive)
        rows.append(item)
    assert len(rows) == 54
    for period in [str(year) for year in range(2012,2017)]+["pooled"]:
        for budget in BUDGETS:
            groups = {row["weather_group"]:row for row in rows if row["period"]==period and row["budget_percent"]==budget}
            for field in ("n_samples","n_positive","n_alerts","true_positive","false_positive","false_negative"):
                assert groups["all"][field] == groups["covered"][field]+groups["missing"][field]


    configuration = dict(analysis='development-daily-ranking-utility-v1', model_params=PARAMS,
                         validation_years=list(range(2012, 2017)), budgets_percent=list(BUDGETS),
                         cells_per_day=9673, predictions=str(args.predictions), cache=str(args.cache),
                         scope='Saved coordinate-HGB development predictions only; no fits or 2017--2019 evaluation')
    write_json(args.output / 'configuration.json', configuration)
    write_json(args.output / 'results.json', dict(status='complete', rows=rows, model_params=PARAMS, scope=configuration['scope']))
    fields = sorted({key for row in rows for key in row})
    write_csv(args.output / 'budget_metrics.csv', [{field: row.get(field) for field in fields} for row in rows])
    write_csv(args.output / 'daily_metrics.csv', daily)
    print(json.dumps(dict(daily_rows=len(daily), aggregate_rows=len(rows)), indent=2))


if __name__ == '__main__':
    main()
