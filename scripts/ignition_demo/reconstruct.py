"""Prepare the current canonical panel/cache and invoke the main retained-model export."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits

from scripts.ignition_modeling.contract import ROOT
from scripts.ignition_modeling.data import load_cache, prepare_cache
from scripts.ignition_modeling.run import execute
from scripts.ignition_modeling.validation import validate_dataset
from .common import CACHE, OUTPUT


def reconstruct(source, cache, output, reference_pickle=None):
    source, cache, output = Path(source), Path(cache), Path(output)
    # Revalidate the current panel before a new cache, without overwriting archives.
    if not (cache / "manifest.json").exists():
        audit_dir = cache / "panel_validation"
        report = validate_dataset(source, audit_dir)
        if report["status"] != "PASS":
            raise ValueError("Panel validation failed; inspect the generated audit before cache preparation")
        prepare_cache(source, cache, audit_path=audit_dir / "data_quality_report.json")
    else:
        load_cache(cache)
    return execute(cache, output, reference_pickle=reference_pickle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/processed/ontario_fire_region_10km_daily_ignition_features_v1.csv.gz")
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--reference-pickle", type=Path)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        reconstruct(args.input, args.cache, args.output, args.reference_pickle)
