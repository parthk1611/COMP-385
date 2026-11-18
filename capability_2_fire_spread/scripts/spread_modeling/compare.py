"""Experiment 4: score every learned model against the simulator on holdout fires (2021-2024), once.

Every model is scored on the same steps, from the same start area and active
perimeter, by the same `score_step` the simulator was published with.  A
learned model turns its probabilities into a set of predicted new cells in two
ways:

- `matched`: the k most likely cells, with k the simulator's own count for that
  step.  Both predict the same area, so this compares only *where* they put it;
- `own`: k = the model's area scale x its summed probabilities, the scale set on
  calibration fires to the simulator's area target.  This also tests *how much*.

Ranking skill needs no cell count: the mean per-step average precision of each
model's scores, the simulator scored by earliest arrival (cells it never reaches
ranked by distance), and even growth by distance from the active perimeter.

Differences from the simulator are given with 95% intervals from a bootstrap
over fires, because steps of one fire are not independent.  Two holdout sets
are reported: the simulator's published 24 fires, and every scored holdout fire.
Writes `docs/modeling/comparison.json`; every model's score on every step goes to
`artifacts/spread_modeling/holdout_step_scores.csv`.

    python -m scripts.spread_modeling.compare
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd

from scripts.spread_common import DATASET_VERSION, action_log

from .contract import CELL_TABLE, COMPARISON, HOLDOUT_STEP_SCORES, LABEL, MODEL_DIR, SEED, SIMULATOR_SCORES
from .evaluation import bootstrap_difference, predicted_mask, simulator_score, step_ap
from .replay import LONG_RUN_M, iter_steps, score_step, summarise
from .simulator import Settings


COMPARED = ["recall", "iou", "precision", "direction_within_45", "step_ap"]


def summary(scores: pd.DataFrame) -> dict:
    result = summarise(scores)
    result["mean_step_ap"] = round(float(scores.step_ap.mean()), 4)
    return result


def report_for(steps: pd.DataFrame, models: list[str]) -> dict:
    rng = np.random.default_rng(SEED)
    out = {}
    for name, subset in [("all_steps", steps), (f"steps_with_observed_head_run_of_{LONG_RUN_M:.0f}_m_or_more", steps[steps.observed_distance_m >= LONG_RUN_M])]:
        out[name] = {
            "by_model": {model: summary(group) for model, group in subset.groupby("model")},
            "difference_from_simulator": {model: {metric: bootstrap_difference(subset, model, metric, rng) for metric in COMPARED} for model in models if model != "simulator"},
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    log = action_log("compare with the simulator")
    scores = json.loads(SIMULATOR_SCORES.read_text(encoding="utf-8"))
    settings = Settings(ros_scale=scores["chosen_ros_scale"], flank_scale=scores["chosen_flank_scale"])
    bundles = {path.stem: joblib.load(path) for path in sorted(MODEL_DIR.glob("*.joblib"))}
    # Models that score whole maps (the CNN) save their holdout predictions per candidate cell instead of a joblib.
    predicted = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(MODEL_DIR.glob("*.json")) if (MODEL_DIR / f"{path.stem}.predictions.parquet").exists()}
    table = pd.read_parquet(CELL_TABLE)
    table = table[table.split == "holdout"].reset_index(drop=True)
    if table.fire_year.min() < 2021:
        raise ValueError("Holdout rows must come from 2021-2024")
    probability = {}
    radius = table.in_radius.to_numpy()
    for variant, bundle in bundles.items():
        p = np.zeros(len(table))
        p[radius] = bundle["model"].predict_proba(table.loc[radius, bundle["features"]].to_numpy(np.float32))[:, 1]
        probability[variant] = p  # cells outside the radius (simulator-only rows) are never predicted by a learned model
    covered = {}  # steps each saved-prediction model was run on
    for variant, meta in predicted.items():
        saved = pd.read_parquet(MODEL_DIR / f"{variant}.predictions.parquet")
        merged = table[["fire_id", "observation", "cell"]].merge(saved, on=["fire_id", "observation", "cell"], how="left")
        # a model run on only some steps (FireSTARR on the published steps, say) is scored on those steps alone;
        # within a step it covers, every candidate cell must have a prediction
        steps_covered = set(zip(saved.fire_id, saved.observation))
        in_covered = np.array([key in steps_covered for key in zip(table.fire_id, table.observation)])
        if merged.p[radius & in_covered].isna().any():
            raise ValueError(f"{variant}: saved predictions miss candidate cells of steps it covers")
        covered[variant] = steps_covered
        probability[variant] = np.where(radius, merged.p.fillna(0.0).to_numpy(), 0.0)
        bundles[variant] = meta  # area scale, family and settings, as for the per-cell models
    table = table.assign(**{f"p_{variant}": p for variant, p in probability.items()})
    groups = table.groupby(["fire_id", "observation"]).indices
    rows = []
    fires = sorted(table.fire_id.unique())
    log.info(f"START: {len(fires)} holdout fires, {len(groups)} steps, models {['simulator', 'even_growth_rank'] + [f'{v}_{m}' for v in bundles for m in ['matched', 'own']]}")
    for number, fire_id in enumerate(fires, start=1):
        for step in iter_steps(fire_id, settings):
            index = groups.get((fire_id, step.observation))
            if index is None:
                raise ValueError(f"step {fire_id} {step.observation} is missing from the table")
            cells_rows = table.iloc[index]
            n = len(step.case.cell375_keys)
            cells = cells_rows.cell.to_numpy()
            in_radius = cells_rows.in_radius.to_numpy()
            labels = cells_rows[LABEL].to_numpy()[in_radius]
            simulated = np.zeros(n, dtype=bool)
            simulated[cells[cells_rows.sim_new.to_numpy() == 1]] = True
            k = int(simulated.sum())
            base = {"fire_id": fire_id, "from_observation": step.observation, "to_observation": step.next_observation, "hours": round(step.hours, 2),
                    "simulator_holdout_sample": bool(cells_rows.simulator_holdout_sample.iloc[0])}  # fmt: skip
            masks = {"simulator": (simulated, step_ap(labels, simulator_score(cells_rows)[in_radius]))}
            for variant, bundle in bundles.items():
                if variant in covered and (fire_id, step.observation) not in covered[variant]:
                    continue
                p = cells_rows[f"p_{variant}"].to_numpy()
                ap = step_ap(labels, p[in_radius])
                own = int(round(bundle["area_scale"] * p[in_radius].sum()))
                masks[f"{variant}_matched"] = (predicted_mask(n, cells[in_radius], p[in_radius], k), ap)
                masks[f"{variant}_own"] = (predicted_mask(n, cells[in_radius], p[in_radius], own), ap)
            for model, (mask, ap) in masks.items():
                result = score_step(step.case, step.layout, step.start, step.active, step.observed_new, mask)
                rows.append({**base, "model": model, **result, "step_ap": ap})
            rows.append({**base, "model": "even_growth_rank", "observed_new_cells": int(step.observed_new.sum()),
                         "step_ap": step_ap(labels, -cells_rows.distance_to_active_m.to_numpy()[in_radius])})  # fmt: skip
        if number % 10 == 0:
            log.info(f"{number} of {len(fires)} holdout fires scored")
    steps = pd.DataFrame(rows)
    steps["direction_within_45"] = np.where(steps.direction_error_deg.notna(), (steps.direction_error_deg <= 45).astype(float), np.nan)
    scored = steps[steps.model != "even_growth_rank"]
    models = sorted(scored.model.unique())
    ranking = steps.groupby(["simulator_holdout_sample", "model"]).step_ap.mean().round(4)
    report = {
        "dataset_version": DATASET_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "holdout_years": sorted(int(y) for y in table.fire_year.unique()),
        "simulator_settings": {"ros_scale": settings.ros_scale, "flank_scale": settings.flank_scale},
        "models": {name: {"family": bundle["family"], "feature_set": bundle["feature_set"], "area_scale": bundle["area_scale"], "params": bundle["params"]} for name, bundle in bundles.items()},
        "how_to_read": {
            "matched": "same number of cells as the simulator in each step: compares where, not how much",
            "own": "the model's own number of cells (area scale x summed probabilities): compares where and how much",
            "even_growth": "even_growth_recall / even_growth_iou: the published baseline, same count as each row's model, spread evenly from the active perimeter",
            "step_ap": "average precision of the model's ranking of candidate cells within 6 km, averaged over steps; needs no cell count",
            "difference_from_simulator": "mean over steps of (model - simulator), 95% interval from 2000 bootstrap resamples of fires",
        },
        "simulator_published_24_fires": report_for(scored[scored.simulator_holdout_sample], models),
        "all_scored_holdout_fires": report_for(scored, models),
        "mean_step_ap_including_even_growth": {("published_24" if sample else "other_holdout"): group.droplevel(0).to_dict() for sample, group in ranking.groupby(level=0)},
    }
    HOLDOUT_STEP_SCORES.parent.mkdir(parents=True, exist_ok=True)
    steps.round(4).to_csv(HOLDOUT_STEP_SCORES, index=False)
    COMPARISON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    published = report["simulator_published_24_fires"]["all_steps"]["by_model"]["simulator"]
    log.info(f"simulator check on its published 24 fires: {published['steps']} steps, recall {published['mean_recall']:.3f} (published {scores['holdout']['mean_recall']:.3f})")
    for model, values in report["all_scored_holdout_fires"]["all_steps"]["by_model"].items():
        log.info(f"all holdout, {model}: recall {values['mean_recall']:.3f}, IoU {values['mean_iou']:.3f}, step AP {values['mean_step_ap']:.3f}, direction within 45 deg {values['share_direction_within_45_deg']:.1%}")
    log.info(f"DONE: wrote {COMPARISON.name}; step scores in {HOLDOUT_STEP_SCORES}")


if __name__ == "__main__":
    main()
