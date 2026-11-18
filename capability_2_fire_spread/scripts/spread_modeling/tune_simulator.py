"""Experiment 1: tune the FBP simulator on calibration fires and score it once on holdout fires.

Two settings are tuned on a seeded sample of 24 calibration fires (2012-2020):
a scale on every rate of spread, and a further scale on the flank and back
rates.  The chosen pair is the one whose simulated head runs as far as the
observed one and whose simulated area is 1.3 times the cells the satellite saw
(satellites record a median 77% of a fire's final area).  The tuned simulator is
then scored once on a seeded sample of 24 holdout fires (2021-2024), beside the
even-growth baseline.  Writes `docs/modeling/simulator_scores.json` and the
chosen setting's step scores.

    python -m scripts.spread_modeling.tune_simulator
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from multiprocessing import Pool

import pandas as pd

from scripts.spread_common import DATASET_VERSION, PROCESSED, action_log

from .contract import SEED, SIMULATOR_CALIBRATION_STEPS, SIMULATOR_HOLDOUT_STEPS, SIMULATOR_SCORES, TARGET_AREA_RATIO
from .replay import LONG_RUN_M, MAX_HOURS, MIN_HOURS, MIN_NEW_CELLS, replay_fire, summarise
from .simulator import Settings


SCALES = [0.3, 0.5, 0.8, 1.2]
FLANK_SCALES = [0.1, 0.25, 0.5, 1.0]


def _worker(job: tuple[str, float, float]) -> list[dict]:
    fire_id, ros_scale, flank_scale = job
    rows = replay_fire(fire_id, Settings(ros_scale=ros_scale, flank_scale=flank_scale))
    for row in rows:
        row["ros_scale"], row["flank_scale"] = ros_scale, flank_scale
    return rows


def pick_fires(split: str, count: int, seed: int) -> list[str]:
    """A seeded sample of trackable, monitored fires small enough to replay quickly."""
    fires = pd.read_csv(PROCESSED / "ontario_fire_spread_fires_v1.csv", dtype={"fire_id": str})
    pool = fires[(fires.split == split) & fires.trackable & (fires.response_code == "MON") & fires.reported_size_ha.between(500, 30_000)]
    return sorted(pool.sample(min(count, len(pool)), random_state=seed).fire_id)


def tuning_error(summary: dict[str, float]) -> float:
    """How far a setting is from running the head as far as observed and burning the target area."""
    distance = abs(math.log(max(summary["median_distance_ratio"], 1e-6)))
    area = abs(math.log(max(summary["median_area_ratio"], 1e-6) / TARGET_AREA_RATIO))
    return distance + area


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calibration-fires", type=int, default=24)
    parser.add_argument("--holdout-fires", type=int, default=24)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    log = action_log("simulator tuning")
    calibration, holdout = pick_fires("calibration", args.calibration_fires, SEED), pick_fires("holdout", args.holdout_fires, SEED)
    log.info(
        f"START: tuning rate-of-spread scale {SCALES} and flank scale {FLANK_SCALES} on {len(calibration)} calibration fires, then scoring on {len(holdout)} holdout fires; "
        f"steps of {MIN_HOURS}-{MAX_HOURS} h with at least {MIN_NEW_CELLS} new cells; targets: head distance ratio 1, area ratio {TARGET_AREA_RATIO}"
    )
    with Pool(args.workers) as pool:
        jobs = [(fire, ros, flank) for fire in calibration for ros in SCALES for flank in FLANK_SCALES]
        tuning = pd.DataFrame([row for rows in pool.imap_unordered(_worker, jobs) for row in rows])
        by_setting = {setting: summarise(group) for setting, group in tuning.groupby(["ros_scale", "flank_scale"])}
        for (ros, flank), summary in by_setting.items():
            log.info(f"calibration rate {ros}, flank {flank}: head distance ratio {summary['median_distance_ratio']:.2f}, area ratio {summary['median_area_ratio']:.2f}, recall {summary['mean_recall']:.3f} (even growth {summary['mean_even_growth_recall']:.3f})")
        best = min(by_setting, key=lambda setting: tuning_error(by_setting[setting]))
        log.info(f"chosen rate-of-spread scale {best[0]} and flank scale {best[1]} (closest to the head-distance and area targets on calibration fires)")
        test = pd.DataFrame([row for rows in pool.imap_unordered(_worker, [(fire, best[0], best[1]) for fire in holdout]) for row in rows])
    holdout_summary = summarise(test)
    long_runs = summarise(test[test.observed_distance_m >= LONG_RUN_M])
    SIMULATOR_SCORES.parent.mkdir(parents=True, exist_ok=True)
    chosen = tuning[(tuning.ros_scale == best[0]) & (tuning.flank_scale == best[1])]
    chosen.sort_values(["fire_id", "from_observation"]).round(4).to_csv(SIMULATOR_CALIBRATION_STEPS, index=False)
    test.sort_values(["fire_id", "from_observation"]).round(4).to_csv(SIMULATOR_HOLDOUT_STEPS, index=False)
    report = {
        "dataset_version": DATASET_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "simulator": "FBP rate of spread, wind ellipse, slope, shortest travel time on a 90 m grid; burn scar in the 2024 fuel map repaired from surrounding fuel",
        "scoring": f"new 375 m cells between consecutive satellite observations {MIN_HOURS}-{MAX_HOURS} h apart with at least {MIN_NEW_CELLS} observed new cells",
        "fire_selection": "seeded sample of trackable, monitored fires of 500-30,000 ha",
        "calibration_fires": calibration,
        "holdout_fires": holdout,
        "tuning_targets": {"median_head_distance_ratio": 1.0, "median_area_ratio": TARGET_AREA_RATIO, "why_this_area": "satellite cells cover a median 77% of a fire's final perimeter area, so true growth is about 1.3 times the cells seen"},
        "calibration_by_setting": {f"rate {ros}, flank {flank}": summary for (ros, flank), summary in by_setting.items()},
        "chosen_ros_scale": best[0],
        "chosen_flank_scale": best[1],
        "holdout": holdout_summary,
        f"holdout_steps_with_observed_head_run_of_{LONG_RUN_M:.0f}_m_or_more": long_runs,
        "direction_chance_level": 0.25,
        "note": "Satellites see only where fire is active at a pass, so observed new cells are a lower bound on what burned; recall is the fairer of the two rates.",
    }
    SIMULATOR_SCORES.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log.info(
        f"DONE: holdout {holdout_summary['steps']} steps from {holdout_summary['fires']} fires: recall {holdout_summary['mean_recall']:.3f} "
        f"(even-growth baseline {holdout_summary['mean_even_growth_recall']:.3f}), head distance ratio {holdout_summary['median_distance_ratio']:.2f}, "
        f"area ratio {holdout_summary['median_area_ratio']:.2f}, direction within 45 deg {holdout_summary['share_direction_within_45_deg']:.1%}"
    )


if __name__ == "__main__":
    main()
