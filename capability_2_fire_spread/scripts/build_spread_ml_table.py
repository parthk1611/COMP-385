#!/usr/bin/env python3
"""Build the per-cell table the learned spread models train and are scored on.

For every scored replay step (the same steps, start areas and active
perimeters as `run_spread_replay.py`) this writes one row per candidate 375 m
cell with the features in `spread_ml.py`, whether the cell was first seen
burning at the next pass, and the tuned simulator's prediction for it.  The
simulator is run once per step at the settings chosen in
`data/processed/simulation/spread_simulator_v1_scores.json`.

Fires: every trackable fire whose 90 m window has at most `--max-window-cells`
cells (the simulator is pure Python, so the largest windows are left out by
that size rule, not by how they burned).  Calibration fires (2012-2020) are for
training; holdout fires (2021-2024) are only scored.  The simulator's own 24
holdout fires are always included and flagged, so the comparison can be made
on exactly the steps the simulator was published on.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from multiprocessing import Pool

import pandas as pd

from run_spread_replay import DETECTABLE_SHARE, iter_steps, simulate_step
from simulate_spread import Settings
from spread_common import DATASET_VERSION, PROCESSED, RAW, action_log
from spread_ml import RADIUS_M, load_observation_history, static_cell_layers, step_rows


OUT = PROCESSED / "ml"
SCORES = PROCESSED / "simulation/spread_simulator_v1_scores.json"
_state: dict = {}


def _work(job: tuple[str, float, float]) -> tuple[list[pd.DataFrame], list[dict], float]:
    fire_id, ros_scale, flank_scale = job
    began = time.perf_counter()
    if "history" not in _state:
        _state["history"] = load_observation_history()
        _state["shared"] = {}
    settings = Settings(ros_scale=ros_scale, flank_scale=flank_scale)
    frames, summaries, static = [], [], None
    for step in iter_steps(fire_id, settings, shared=_state["shared"]):
        if static is None:
            static = static_cell_layers(step.case)
            daily = _state["shared"]["daily"][fire_id].set_index("date")
        frame, summary = step_rows(step, static, daily, _state["history"], simulate_step(step, settings), DETECTABLE_SHARE)
        frames.append(frame)
        summaries.append(summary)
    return frames, summaries, time.perf_counter() - began


def select_fires(max_cells: int) -> pd.DataFrame:
    fires = pd.read_csv(PROCESSED / "ontario_fire_spread_fires_v1.csv", dtype={"fire_id": str})
    windows = {w["fire_id"]: w["rows"] * w["columns"] for w in json.loads((RAW / "fuel_terrain/fuel_windows_manifest.json").read_text(encoding="utf-8"))["windows"]}
    fires["window_cells"] = fires.fire_id.map(windows)
    simulator_holdout = set(json.loads(SCORES.read_text(encoding="utf-8"))["holdout_fires"])
    fires["simulator_holdout_sample"] = fires.fire_id.isin(simulator_holdout)
    keep = fires.split.isin(["calibration", "holdout"]) & fires.trackable & ((fires.window_cells <= max_cells) | fires.simulator_holdout_sample)
    return fires[keep].sort_values("window_cells", ascending=False)  # largest first, so the pool finishes evenly


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-window-cells", type=int, default=150_000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, help="Only this many fires per split, for a trial run (writes to ml/trial/).")
    args = parser.parse_args()
    log = action_log("11 learned-model table")
    scores = json.loads(SCORES.read_text(encoding="utf-8"))
    ros, flank = scores["chosen_ros_scale"], scores["chosen_flank_scale"]
    fires = select_fires(args.max_window_cells)
    if args.limit:
        fires = pd.concat([group.tail(args.limit) for _, group in fires.groupby("split")])
    out = OUT / "trial" if args.limit else OUT
    out.mkdir(parents=True, exist_ok=True)
    log.info(f"START: per-cell table for {len(fires)} fires ({fires.split.value_counts().to_dict()}); candidates within {RADIUS_M:.0f} m of the burned area; simulator at rate {ros}, flank {flank}")
    frames, summaries, timing = [], [], {}
    with Pool(args.workers) as pool:
        for number, (fire_frames, fire_summaries, seconds) in enumerate(pool.imap_unordered(_work, [(f, ros, flank) for f in fires.fire_id]), start=1):
            frames += fire_frames
            summaries += fire_summaries
            if fire_summaries:
                timing[fire_summaries[0]["fire_id"]] = round(seconds, 1)
            if number % 20 == 0:
                log.info(f"{number} of {len(fires)} fires done")
    attributes = fires.set_index("fire_id")[["split", "fire_year", "simulator_holdout_sample", "window_cells"]]
    table = pd.concat(frames, ignore_index=True).join(attributes[["split", "fire_year", "simulator_holdout_sample"]], on="fire_id")
    steps = pd.DataFrame(summaries).join(attributes, on="fire_id")
    table.to_parquet(out / "spread_ml_cells_v1.parquet", index=False)
    steps.to_csv(out / "spread_ml_steps_v1.csv", index=False)
    audit = {
        "dataset_version": DATASET_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "candidate_rule": f"unburned 375 m cells within {RADIUS_M:.0f} m of the area burned by the first pass, plus any cell the simulator predicts",
        "simulator_settings": {"ros_scale": ros, "flank_scale": flank},
        "fire_rule": f"trackable fires with a 90 m window of at most {args.max_window_cells:,} cells, plus the simulator's 24 holdout fires",
        "fires_by_split": {k: int(v) for k, v in steps.groupby("split").fire_id.nunique().items()},
        "fires_without_scored_steps": sorted(set(fires.fire_id) - set(steps.fire_id)),
        "steps_by_split": {k: int(v) for k, v in steps.split.value_counts().items()},
        "rows_by_split": {k: int(v) for k, v in table.split.value_counts().items()},
        "positive_rows_by_split": {k: int(v) for k, v in table.groupby("split").label.sum().items()},
        "observed_new_cells_within_radius_share": round(float(steps.observed_new_in_radius.sum() / steps.observed_new_cells.sum()), 4),
        "simulated_new_cells_outside_radius": int(steps.simulated_new_outside_radius.sum()),
        "seconds_per_fire": timing,
    }
    (out / "spread_ml_table_v1_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    log.info(f"DONE: {len(steps)} steps, {len(table):,} rows; {audit['observed_new_cells_within_radius_share']:.1%} of observed new cells lie within the candidate radius")


if __name__ == "__main__":
    main()
