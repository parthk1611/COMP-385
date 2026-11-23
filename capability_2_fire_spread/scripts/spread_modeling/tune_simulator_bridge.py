"""Re-tune the FBP simulator for the ignition -> spread bridge, without any 2019 fire.

The published tuning (`tune_simulator.py`) drew its fires from 2012-2020, which
includes 2019, the year the combined ignition + spread run is shown on.  This
script tunes on earlier fires only and tests on every other year:

- tune: every eligible fire from 2012-2016 (grid search, below);
- test: every eligible fire from 2017-2018 and from 2020-2024, scored once
  with the chosen pair and reported for each period and pooled;
- 2019 is never read: it is the combined run's year.

Test fires never influence the chosen pair, so testing on years after 2019 does
not put later knowledge into the setting.

Eligible fires are the same as the published tuning's: trackable (three or more
growth steps), monitored (response code MON, so suppression shapes them less)
and 500-30,000 ha.  All of them are used, not a sample.

Grid search.  Every pair of `ROS_SCALES` x `FLANK_SCALES` replays every tuning
fire step by step (`replay.replay_fire`).  The objective is the published one
(`tune_simulator.tuning_error`): the simulated head should run as far as the
observed head (median distance ratio 1) and burn 1.3 times the cells the
satellite saw (median area ratio 1.3); the error is the sum of the two absolute
log deviations, so 2x too far and 2x too short count the same.  The pair with
the smallest error is chosen; on an exact tie (the medians can coincide), the
higher mean IoU wins.  Recall is reported but not used to choose, because more
area always raises recall.  Beside the chosen pair, each test period is also
scored with the published setting (0.8 / 0.25) for comparison; the even-growth
baseline comes with every score.

Writes `docs/modeling/bridge_simulator_tuning.json`, the full grid and the
chosen pair's step scores beside it; `ignition_bridge.py` reads the chosen pair
from there.

    python -m scripts.spread_modeling.tune_simulator_bridge
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from multiprocessing import Pool

import numpy as np
import pandas as pd

from scripts.spread_common import DATASET_VERSION, MODELING_DOCS, PROCESSED, action_log

from .contract import TARGET_AREA_RATIO
from .replay import LONG_RUN_M, MAX_HOURS, MIN_HOURS, MIN_NEW_CELLS, summarise
from .tune_simulator import _worker, tuning_error


RESERVED_YEAR = 2019  # the combined run's year: never used to tune or test
TUNE_YEARS = (2012, 2016)
TEST_PERIODS = ((2017, 2018), (2020, 2024))
PUBLISHED_SETTING = (0.8, 0.25)
ROS_SCALES = [round(v, 2) for v in np.arange(0.2, 1.61, 0.1)]  # 15 values
FLANK_SCALES = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0]  # 11 values
REPORT = MODELING_DOCS / "bridge_simulator_tuning.json"  # what ignition_bridge.py reads


def outputs(tag: str = "") -> tuple:
    """Report, grid, tuning-step and test-step files; an empty tag writes the files the bridge reads."""
    stem = "bridge_simulator" + (f"_{tag}" if tag else "")
    return tuple(MODELING_DOCS / f"{stem}{suffix}" for suffix in ("_tuning.json", "_grid.csv", "_tune_steps.csv", "_test_steps.csv"))


def eligible_fires(first_year: int, last_year: int, tuning: bool = True) -> list[str]:
    """Every trackable, monitored fire of 500-30,000 ha in the given years, never from 2019.

    Tuning years must all be before 2019; test years may come after it.
    """
    if tuning and last_year >= RESERVED_YEAR:
        raise ValueError(f"tuning years must end before {RESERVED_YEAR}")
    if first_year <= RESERVED_YEAR <= last_year:
        raise ValueError(f"{RESERVED_YEAR} is reserved for the combined run")
    fires = pd.read_csv(PROCESSED / "ontario_fire_spread_fires_v1.csv", dtype={"fire_id": str})
    pool = fires[fires.fire_year.between(first_year, last_year) & fires.trackable & (fires.response_code == "MON") & fires.reported_size_ha.between(500, 30_000)]
    return sorted(pool.fire_id)


def choose(grid: pd.DataFrame) -> pd.DataFrame:
    """Order the grid best first: smallest tuning error, then the higher mean IoU on an exact tie."""
    return grid.sort_values(["error", "mean_iou"], ascending=[True, False], kind="mergesort").reset_index(drop=True)


def replay_all(pool: Pool, fires: list[str], setting: tuple[float, float]) -> pd.DataFrame:
    return pd.DataFrame([row for rows in pool.imap_unordered(_worker, [(fire, *setting) for fire in fires]) for row in rows])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--tune-years", type=int, nargs=2, default=TUNE_YEARS, metavar=("FIRST", "LAST"))
    parser.add_argument("--test-years", type=int, nargs=2, action="append", metavar=("FIRST", "LAST"),
                        help="a test period; repeat for several (default: 2017-2018 and 2020-2024)")
    parser.add_argument("--tag", default="", help="suffix for the output files; empty writes the files the bridge reads")
    args = parser.parse_args()
    log = action_log("bridge simulator tuning")
    tune_years = tuple(args.tune_years)
    test_periods = tuple(tuple(p) for p in args.test_years) if args.test_years else TEST_PERIODS
    report_path, grid_path, tune_steps_path, test_steps_path = outputs(args.tag)
    tune_fires = eligible_fires(*tune_years)
    test_fires = {period: eligible_fires(*period, tuning=False) for period in test_periods}
    if any(first <= tune_years[1] for first, _ in test_periods):
        raise ValueError("test periods must come after the tuning years")
    log.info(f"START: grid of {len(ROS_SCALES)} rate scales x {len(FLANK_SCALES)} flank scales on {len(tune_fires)} fires from {tune_years}; "
             f"then one test on {', '.join(f'{len(f)} fires from {p}' for p, f in test_fires.items())}; {RESERVED_YEAR} never read")  # fmt: skip
    began = time.perf_counter()
    with Pool(args.workers) as pool:
        jobs = [(fire, ros, flank) for fire in tune_fires for ros in ROS_SCALES for flank in FLANK_SCALES]
        tuning = pd.DataFrame([row for rows in pool.imap_unordered(_worker, jobs, chunksize=4) for row in rows])
        grid = []
        for (ros, flank), group in tuning.groupby(["ros_scale", "flank_scale"]):
            summary = summarise(group)
            grid.append({"ros_scale": ros, "flank_scale": flank, "error": round(tuning_error(summary), 4), **summary})
        grid = choose(pd.DataFrame(grid))
        best = grid.iloc[0]
        chosen = (float(best.ros_scale), float(best.flank_scale))
        log.info(f"chose rate scale {chosen[0]}, flank scale {chosen[1]}: head distance ratio {best.median_distance_ratio}, area ratio {best.median_area_ratio}, recall {best.mean_recall} ({time.perf_counter() - began:.0f}s)")
        tested = {period: (replay_all(pool, fires, chosen), replay_all(pool, fires, PUBLISHED_SETTING)) for period, fires in test_fires.items()}
    test = pd.concat([chosen_scores for chosen_scores, _ in tested.values()], ignore_index=True)
    published = pd.concat([published_scores for _, published_scores in tested.values()], ignore_index=True)

    MODELING_DOCS.mkdir(parents=True, exist_ok=True)
    grid.round(4).to_csv(grid_path, index=False)
    tuning[(tuning.ros_scale == chosen[0]) & (tuning.flank_scale == chosen[1])].sort_values(["fire_id", "from_observation"]).round(4).to_csv(tune_steps_path, index=False)
    test.sort_values(["fire_id", "from_observation"]).round(4).to_csv(test_steps_path, index=False)

    def label(period: tuple[int, int]) -> str:
        return f"{period[0]}-{period[1]}"

    report = {
        "dataset_version": DATASET_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "purpose": f"FBP settings for the ignition -> spread bridge; no {RESERVED_YEAR} fire is read",
        "tune_years": list(tune_years),
        "test_years": [list(period) for period in test_periods],
        "reserved_year": RESERVED_YEAR,
        "fire_selection": "every trackable, monitored (MON) fire of 500-30,000 ha in those years",
        "scoring": f"new 375 m cells between consecutive satellite passes {MIN_HOURS}-{MAX_HOURS} h apart with at least {MIN_NEW_CELLS} observed new cells",
        "search": {"method": "exhaustive grid search", "ros_scales": ROS_SCALES, "flank_scales": FLANK_SCALES, "settings": int(len(grid))},
        "objective": f"|log(median head distance ratio)| + |log(median area ratio / {TARGET_AREA_RATIO})|, smallest wins; exact ties go to the higher mean IoU",
        "tune_fires": tune_fires,
        "test_fires": {label(period): fires for period, fires in test_fires.items()},
        "chosen_ros_scale": chosen[0],
        "chosen_flank_scale": chosen[1],
        "tune": {"error": float(best.error), **summarise(tuning[(tuning.ros_scale == chosen[0]) & (tuning.flank_scale == chosen[1])])},
        "top_settings": grid.head(10).round(4).to_dict(orient="records"),
        "test": {
            "pooled": {"chosen": summarise(test), "published_0.8_0.25": summarise(published),
                       f"chosen_head_runs_of_{LONG_RUN_M:.0f}_m_or_more": summarise(test[test.observed_distance_m >= LONG_RUN_M])},
            **{label(period): {"chosen": summarise(c), "published_0.8_0.25": summarise(p)} for period, (c, p) in tested.items()},
        },  # fmt: skip
        "seconds": round(time.perf_counter() - began, 1),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pooled = report["test"]["pooled"]
    log.info(f"DONE: test {pooled['chosen']['steps']} steps of {pooled['chosen']['fires']} fires: recall {pooled['chosen']['mean_recall']} "
             f"(published setting {pooled['published_0.8_0.25']['mean_recall']}, even growth {pooled['chosen']['mean_even_growth_recall']}); wrote {report_path.name}")  # fmt: skip


if __name__ == "__main__":
    main()
