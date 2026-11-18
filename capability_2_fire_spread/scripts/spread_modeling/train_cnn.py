"""Experiment 3: train the two CNNs on calibration fires (2012-2020) and predict the holdout fires.

As for the per-cell models (`train.py`), settings are chosen and the area scale
set by leave-one-fire-year-out cross-validation within 2012-2020, on the mean
per-step average precision.  The final network is refitted on every calibration
patch, and its probability for every holdout candidate cell is saved for
`compare.py`.  Writes `docs/modeling/cnn_training.json`.  Needs the patches
(`cnn_patches.py`); uses the GPU when one is present.

    python -m scripts.spread_modeling.train_cnn
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from scripts.spread_common import DATASET_VERSION, action_log

from .cnn import CANDIDATES, CHANNELS, SIZE, VARIANT_CANDIDATES, VARIANTS, fit, predict, row_probabilities
from .contract import CELL_TABLE, CELL_TABLE_STEPS, CNN_PATCH_INDEX, CNN_PATCHES, CNN_TRAINING, LABEL, MODEL_DIR
from .evaluation import area_scale, matched_recall, mean_step_ap


def train(variants: list[str]) -> None:
    import torch

    log = action_log("train CNN")
    if not torch.cuda.is_available():
        log.info("no CUDA GPU found: training on the CPU, which is much slower")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = np.load(CNN_PATCHES, allow_pickle=True)
    x, y, mask, split, year = data["x"], data["y"], data["mask"], data["split"], data["year"]
    index = pd.read_parquet(CNN_PATCH_INDEX)
    table = pd.read_parquet(CELL_TABLE, columns=["fire_id", "observation", "cell", "in_radius", LABEL, "split", "fire_year"])
    calibration_rows = table[(table.split == "calibration") & table.in_radius].reset_index(drop=True)
    holdout_rows = table[(table.split == "holdout") & table.in_radius].reset_index(drop=True)
    steps = pd.read_csv(CELL_TABLE_STEPS, dtype={"fire_id": str}).set_index(["fire_id", "observation"])
    big = steps.observed_new_cells >= 31  # a big step: 31 or more new cells
    train_ids = np.flatnonzero(split == "calibration")
    holdout_ids = np.flatnonzero(split == "holdout")
    years = sorted(int(v) for v in np.unique(year[train_ids]))
    report = json.loads(CNN_TRAINING.read_text(encoding="utf-8")) if CNN_TRAINING.exists() else {}
    report.update({"dataset_version": DATASET_VERSION, "created_at_utc": datetime.now(UTC).isoformat(), "device": str(torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu"),
                   "torch": torch.__version__, "patch": f"{SIZE} x {SIZE} cells of 375 m", "channels": CHANNELS, "candidates": CANDIDATES,
                   "folds": "leave one fire year out", "selection_metric": "mean over folds of mean per-step average precision"})  # fmt: skip
    report.setdefault("models", {})
    log.info(f"START: {variants} on {len(train_ids)} calibration patches ({years}); {len(holdout_ids)} holdout patches predicted after selection")
    for name in variants:
        hybrid = VARIANTS[name]
        results, out_of_fold = [], {}
        for number, params in enumerate(VARIANT_CANDIDATES[name]):
            began, folds, oof = time.perf_counter(), {}, []
            for held in years:
                fit_ids, test_ids = train_ids[year[train_ids] != held], train_ids[year[train_ids] == held]
                network, channels, vectors = fit(x[fit_ids], y[fit_ids], mask[fit_ids], params, hybrid, device)
                maps = predict(network, channels, vectors, x[test_ids], device)
                oof.append(row_probabilities(maps, test_ids, index))
                fold_rows = calibration_rows[calibration_rows.fire_year == held]
                p = fold_rows.merge(oof[-1], on=["fire_id", "observation", "cell"], how="left").p.fillna(0).to_numpy()
                folds[held] = mean_step_ap(fold_rows, p)
            oof = calibration_rows.merge(pd.concat(oof), on=["fire_id", "observation", "cell"], how="left").p.fillna(0).to_numpy()
            recall = matched_recall(calibration_rows, oof, steps)  # secondary: not used to choose
            result = {"candidate": number, "params": params, "mean_step_ap": float(np.mean(list(folds.values()))), "fold_mean_step_ap": folds,
                      "matched_recall": round(float(recall.mean()), 4), "matched_recall_big_steps": round(float(recall[big.reindex(recall.index)].mean()), 4),
                      "seconds": round(time.perf_counter() - began, 1)}  # fmt: skip
            results.append(result)
            out_of_fold[number] = oof
            log.info(f"{name} candidate {number} {params}: mean per-step AP {result['mean_step_ap']:.4f}, matched recall {result['matched_recall']:.3f} (big steps {result['matched_recall_big_steps']:.3f}) ({result['seconds']}s)")
        best = max(results, key=lambda r: r["mean_step_ap"])
        scale = area_scale(calibration_rows, out_of_fold[best["candidate"]])
        network, channels, vectors = fit(x[train_ids], y[train_ids], mask[train_ids], best["params"], hybrid, device)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        torch.save(network.state_dict(), MODEL_DIR / f"{name}.pt")
        holdout = holdout_rows[["fire_id", "observation", "cell"]].merge(row_probabilities(predict(network, channels, vectors, x[holdout_ids], device), holdout_ids, index), how="left")
        holdout["p"] = holdout.p.fillna(0.0)
        holdout.to_parquet(MODEL_DIR / f"{name}.predictions.parquet", index=False)
        meta = {"name": name, "family": "cnn", "feature_set": "patch_with_simulator" if hybrid else "patch", "area_scale": scale, "params": best["params"]}
        (MODEL_DIR / f"{name}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        report["models"][name] = {**meta, "channels": [CHANNELS[c] for c in channels], "candidates": results, "selected": best["candidate"],
                                  "training_patches": int(len(train_ids)), "holdout_patches": int(len(holdout_ids))}  # fmt: skip
        CNN_TRAINING.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        log.info(f"{name}: chose candidate {best['candidate']}, area scale {scale:.3f}; refitted on all calibration fires and predicted the holdout fires")
    log.info(f"DONE: CNN models, holdout predictions and {CNN_TRAINING.name} written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    train(parser.parse_args().models)


if __name__ == "__main__":
    main()
