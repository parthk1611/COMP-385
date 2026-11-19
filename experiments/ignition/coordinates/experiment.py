"""Fixed HGB comparison adding two static EPSG:3978 cell-centre coordinates."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import gc
from pathlib import Path

from threadpoolctl import threadpool_limits
from experiments.ignition.common import (
    ROOT, DEFAULT_CACHE, PARAMS, FOLD_YEARS, load_data, fit_hgb, predict_hgb,
    save_predictions, fold_metrics, summarize, evaluate_saved, prepare_output,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json


def execute(cache, baseline, output):
    data = load_data(cache)
    X, y, manifest, grid, centres = data
    base = {**evaluate_saved(data, baseline), "variant": "baseline"}
    output = Path(output)
    prepare_output(output)
    records = []
    for first, last, year in FOLD_YEARS:
        training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
        classifier, preprocessor = fit_hgb(X[training], y[training], grid[training], centres,
                                         scratch_dir=output / "scratch", params=PARAMS)
        p = predict_hgb(classifier, preprocessor, X[validation], grid[validation], centres)
        save_predictions(output, PARAMS, year, y[validation], p)
        records.append({"fold": year, "params": PARAMS, "metrics": fold_metrics(data, year, p)})
        del classifier, preprocessor, p
        gc.collect()
    coordinates = {**summarize(PARAMS, records), "variant": "with_coordinates"}
    results = {
        "status": "complete", "feature_set_version": "ignition-weather-v2-cell-centres-v1",
        "baseline": base, "with_coordinates": coordinates,
        "relative_mean_ap_gain": coordinates["mean_fold_average_precision"] / base["mean_fold_average_precision"] - 1,
        "year_ap_changes": {year: coordinates["fold_average_precision"][year] - ap for year, ap in base["fold_average_precision"].items()},
        "selected_variant": max([base, coordinates], key=lambda row: row["mean_fold_average_precision"])["variant"],
        "scope": "Fixed-parameter development comparison; no 2017--2019 fitting or evaluation",
    }
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_tuning")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ignition_modeling/reruns/coordinates")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.baseline, args.output)


if __name__ == "__main__":
    main()
