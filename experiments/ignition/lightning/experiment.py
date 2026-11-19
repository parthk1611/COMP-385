"""Fixed coordinate HGB with two past-only CG-density predictors."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import gc
from pathlib import Path

from threadpoolctl import threadpool_limits

from experiments.ignition.common import (
    ROOT, PARAMS, FOLD_YEARS, DEFAULT_CACHE, RAW_FEATURES as BASE_RAW,
    TRANSFORMED_FEATURES as BASE_TRANSFORMED, load_data, fit_hgb, predict_hgb,
    evaluate_saved, fold_metrics, summarize, prepare_output, save_predictions,
)
from experiments.ignition.lightning.build_features import (
    FEATURE_VERSION, LIGHTNING_NAMES, source_inputs, build_features,
)
from scripts.ignition_modeling.data import year_slice
from scripts.ignition_modeling.run import write_json

RAW_FEATURES = (*BASE_RAW, *LIGHTNING_NAMES)
TRANSFORMED_FEATURES = (*BASE_TRANSFORMED, *LIGHTNING_NAMES)
DEFAULT_AUDIT = ROOT / "artifacts/ignition_modeling/lightning_coverage_audit"
DEFAULT_AREA = ROOT / "artifacts/ignition_modeling/hgb_lightning/source/cell_area_0.1-deg.nc"
DEFAULT_OUTPUT = ROOT / "artifacts/ignition_modeling/reruns/lightning"


def execute(cache, baseline, audit, area, output):
    data = load_data(cache)
    X, y, manifest, row_ids, centres = data
    control = evaluate_saved(data, baseline)
    inputs = source_inputs(audit, area)
    output = prepare_output(output)
    lightning, coverage = build_features(audit, area, row_ids, manifest, output, inputs)
    records = []
    for first, last, year in FOLD_YEARS:
        training, validation = year_slice(manifest, first, last), year_slice(manifest, year)
        if training.stop > validation.start or last >= year or year > 2016:
            raise ValueError("Training must precede development validation")
        print(f"Lightning fold {year}: fitting {len(y[training]):,} rows", flush=True)
        classifier, preprocessor = fit_hgb(
            X[training], y[training], row_ids[training], centres,
            scratch_dir=output / "scratch", extra=lightning[training])
        p = predict_hgb(classifier, preprocessor, X[validation], row_ids[validation],
                        centres, extra=lightning[validation])
        save_predictions(output, PARAMS, year, y[validation], p)
        records.append({"fold": year, "params": PARAMS, "metrics": fold_metrics(data, year, p)})
        del classifier, preprocessor, p
        gc.collect()
    combined = summarize(PARAMS, records)
    results = {
        "status": "complete", "feature_set_version": FEATURE_VERSION,
        "params": PARAMS, "raw_features": list(RAW_FEATURES),
        "transformed_features": list(TRANSFORMED_FEATURES),
        "baseline": control, "with_lightning": combined,
        "relative_mean_ap_gain": combined["mean_fold_average_precision"] / control["mean_fold_average_precision"] - 1,
        "year_ap_changes": {year: combined["fold_average_precision"][year] - value
                            for year, value in control["fold_average_precision"].items()},
        "selected_variant": "with_lightning" if combined["mean_fold_average_precision"] > control["mean_fold_average_precision"] else "baseline",
        "selection_rule": "Highest unweighted mean yearly AP; exact ties retain baseline",
        "scope": "All rows, five development folds; no 2017--2019 construction, fitting or scoring",
    }
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=ROOT / "artifacts/ignition_modeling/hgb_coordinates")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--area", type=Path, default=DEFAULT_AREA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        execute(args.cache, args.baseline, args.audit, args.area, args.output)


if __name__ == "__main__":
    main()
