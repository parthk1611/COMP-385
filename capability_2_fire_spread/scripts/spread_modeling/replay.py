"""Replay real fires step by step and score a prediction against the satellite record.

For each fire, and each pair of consecutive satellite observations, a model
starts from the area burned up to the first observation and predicts the cells
newly seen burning at the second.  Scoring is on the satellite's own 375 m grid.

A satellite pass shows only where fire is active at that moment, so the cells
seen so far are a patchy under-count of what has burned.  The starting area is
therefore those cells with the gaps between them closed and holes filled.  For
the same reason the observed new cells are a lower bound: the fair questions
are whether a model reaches them (recall), how far its head runs against
theirs, and whether it runs the same way.  Every score is set beside a baseline
that grows the fire by the same area evenly from the active perimeter.

`iter_steps` yields the steps every model is scored on; `score_step` scores one
prediction; `replay_fire` runs the simulator through a fire.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.spatial import cKDTree

from scripts.spread_common import PROCESSED

from .simulator import CELL_375_M, Settings, load_case, simulate


MIN_HOURS, MAX_HOURS = 6.0, 30.0  # shorter steps move less than one 375 m cell
MIN_NEW_CELLS = 5
CLOSING_PASSES = 2  # each pass bridges gaps one cell wider between detections
DETECTABLE_SHARE = 0.25  # a 375 m cell counts as reached once fire covers this much of it
LONG_RUN_M = 1500.0  # steps whose observed head ran at least this far are also scored on their own
ACTIVE_PASSES = 1  # flames seen in this many most recent passes mark the perimeter as still alight
ACTIVE_REACH_CELLS = 1  # how far (in 375 m cells) from those detections the perimeter counts as alight
_shared: dict = {}


class Layout:
    """The case's 375 m cells arranged as a 2-D array, for neighbourhood operations."""

    def __init__(self, keys: list[tuple[int, int]]) -> None:
        array = np.array(keys, dtype=int)
        self.x, self.y = array[:, 0] - array[:, 0].min(), array[:, 1] - array[:, 1].min()
        self.shape = (int(self.x.max()) + 1, int(self.y.max()) + 1)

    def grid(self, mask: np.ndarray) -> np.ndarray:
        out = np.zeros(self.shape, dtype=bool)
        out[self.x[mask], self.y[mask]] = True
        return out

    def flat(self, grid: np.ndarray) -> np.ndarray:
        return grid[self.x, self.y]

    def burned_area(self, detected: np.ndarray) -> np.ndarray:
        """Detected cells with the gaps between them closed and holes filled."""
        closed = ndimage.binary_closing(self.grid(detected), structure=np.ones((3, 3), dtype=bool), iterations=CLOSING_PASSES)
        return self.flat(ndimage.binary_fill_holes(closed)) | detected


def _bearing(offsets: np.ndarray) -> float | None:
    east, north = offsets[:, 0].mean(), offsets[:, 1].mean()
    return None if np.hypot(east, north) < 1e-9 else float(np.degrees(np.arctan2(east, north)) % 360)


def _growth_shape(new_keys: np.ndarray, start_keys: np.ndarray) -> tuple[float, float | None]:
    """90th-percentile distance (m) and head bearing of new cells from the nearest starting cell."""
    distance, index = cKDTree(start_keys).query(new_keys)
    offsets = (new_keys - start_keys[index]) * CELL_375_M
    head = distance >= np.quantile(distance, 0.9)
    return float(np.quantile(distance, 0.9) * CELL_375_M), _bearing(offsets[head])


def score_step(case, layout: Layout, start: np.ndarray, active: np.ndarray, observed_new: np.ndarray, simulated_new: np.ndarray) -> dict[str, float | None]:
    """Compare predicted and observed new 375 m cells (boolean arrays over the case's 375 m cells)."""
    keys = np.array(case.cell375_keys, dtype=float)
    hits = int((simulated_new & observed_new).sum())
    union = int((simulated_new | observed_new).sum())
    result = {
        "observed_new_cells": int(observed_new.sum()),
        "simulated_new_cells": int(simulated_new.sum()),
        "iou": hits / union if union else None,
        "recall": hits / int(observed_new.sum()),
        "precision": hits / int(simulated_new.sum()) if simulated_new.any() else None,
        "area_ratio": float(simulated_new.sum() / observed_new.sum()),
    }
    observed_distance, observed_bearing = _growth_shape(keys[observed_new], keys[start])
    result["observed_distance_m"] = observed_distance
    # bearings are true bearings: grid bearing plus the grid's convergence at this fire
    result["observed_head_bearing_deg"] = None if observed_bearing is None else (observed_bearing + case.convergence_deg) % 360
    if simulated_new.any():
        simulated_distance, simulated_bearing = _growth_shape(keys[simulated_new], keys[start])
        result["simulated_distance_m"] = simulated_distance
        result["simulated_head_bearing_deg"] = None if simulated_bearing is None else (simulated_bearing + case.convergence_deg) % 360
        if observed_bearing is not None and simulated_bearing is not None:
            result["direction_error_deg"] = float(abs((simulated_bearing - observed_bearing + 180) % 360 - 180))
    # Baseline: the same number of new cells, taken evenly outward from the same active stretch of perimeter.
    distance = layout.flat(ndimage.distance_transform_edt(~layout.grid(active)))
    distance[start] = np.inf
    count = int(simulated_new.sum())
    if count:
        even = np.zeros(len(keys), dtype=bool)
        even[np.argsort(distance, kind="stable")[:count]] = True
        even_hits = int((even & observed_new).sum())
        result["even_growth_iou"] = even_hits / int((even | observed_new).sum())
        result["even_growth_recall"] = even_hits / int(observed_new.sum())
    return result


@dataclass
class Step:
    """One pair of consecutive satellite observations of a fire, as both the simulator and the learned models see it.

    Everything here is known at the first observation except `observed_new`, the cells first seen at the second.
    """

    case: object
    layout: Layout
    observation: int
    next_observation: int
    start_utc: pd.Timestamp
    hours: float
    start: np.ndarray  # 375 m cells burned by the first observation (gaps closed, holes filled)
    active: np.ndarray  # stretch of that perimeter where flames were seen at the latest pass
    observed_new: np.ndarray  # 375 m cells first seen burning at the second observation
    usable: bool  # inside the scored step length and with enough new cells


def iter_steps(fire_id: str, settings: Settings, include_unusable: bool = False, shared: dict | None = None):
    """Yield every consecutive-observation step of one fire; scored steps only unless `include_unusable`."""
    shared = _shared if shared is None else shared
    case = load_case(fire_id, settings, shared)
    lookup = {key: index for index, key in enumerate(case.cell375_keys)}
    cells = case.arrival[[key in lookup for key in zip(case.arrival.cell_x, case.arrival.cell_y)]]
    cell_index = np.array([lookup[key] for key in zip(cells.cell_x, cells.cell_y)], dtype=int)
    first_seen = cells.first_observation.values
    if "detections" not in shared:
        table = pd.read_csv(PROCESSED / "ontario_fire_spread_detections_v1.csv.gz", dtype={"fire_id": str}, usecols=["fire_id", "observation", "x", "y"])
        shared["detections"] = dict(tuple(table.groupby("fire_id")))
    seen = shared["detections"][fire_id]
    seen_keys = list(zip(np.floor(seen.x / CELL_375_M).astype(int), np.floor(seen.y / CELL_375_M).astype(int)))
    in_window = np.array([key in lookup for key in seen_keys])
    seen_index = np.array([lookup[key] for key, keep in zip(seen_keys, in_window) if keep], dtype=int)
    seen_pass = seen.observation.values[in_window]
    times = case.observation_times
    layout = Layout(case.cell375_keys)
    square = np.ones((3, 3), dtype=bool)
    for observation in times.index[:-1]:
        nxt = observation + 1
        if nxt not in times.index:
            continue
        hours = (times[nxt] - times[observation]).total_seconds() / 3600
        detected = np.zeros(len(case.cell375_keys), dtype=bool)
        detected[cell_index[first_seen <= observation]] = True
        start = layout.burned_area(detected)
        observed_new = np.zeros_like(start)
        observed_new[cell_index[first_seen == nxt]] = True
        observed_new &= ~start
        usable = bool(MIN_HOURS <= hours <= MAX_HOURS and observed_new.sum() >= MIN_NEW_CELLS and start.any())
        if not usable and not include_unusable:
            continue
        # Fire spreads from the stretch of perimeter near where the last passes saw flames, not from
        # edges that burned out days ago.
        recent = np.zeros_like(start)
        recent[seen_index[(seen_pass <= observation) & (seen_pass > observation - ACTIVE_PASSES)]] = True
        edge = start & ~layout.flat(ndimage.binary_erosion(layout.grid(start), structure=square))
        active = edge & layout.flat(ndimage.binary_dilation(layout.grid(recent), structure=square, iterations=ACTIVE_REACH_CELLS))
        if not active.any():
            active = edge
        yield Step(case, layout, int(observation), int(nxt), times[observation], hours, start, active, observed_new, usable)


def simulate_step(step: Step, settings: Settings) -> np.ndarray:
    """The simulator's arrival time (minutes, 90 m grid; infinity where not reached) over one step."""
    return simulate(step.case, step.start[step.case.cell375], step.start_utc, min(step.hours, MAX_HOURS), settings, active=step.active[step.case.cell375])


def replay_fire(fire_id: str, settings: Settings, keep_grids: bool = False):
    """Score every usable step of one fire.  With `keep_grids`, also return what the viewer needs."""
    rows = []
    case = stitched = origin = None
    for step in iter_steps(fire_id, settings, include_unusable=keep_grids):
        if case is None:
            case = step.case
            stitched = np.full(case.shape, np.inf, dtype=np.float32) if keep_grids else None
            origin = case.observation_times.iloc[0]
        arrival = simulate_step(step, settings)
        reached = np.isfinite(arrival)
        if keep_grids:
            since_origin = (step.start_utc - origin).total_seconds() / 3600 + arrival / 60.0
            stitched = np.minimum(stitched, np.where(reached, since_origin, np.inf).astype(np.float32))
        if step.usable:
            simulated_new = case.burned_375(reached, DETECTABLE_SHARE) & ~step.start
            rows.append({"fire_id": fire_id, "from_observation": step.observation, "to_observation": step.next_observation, "hours": round(step.hours, 2), **score_step(case, step.layout, step.start, step.active, step.observed_new, simulated_new)})
    if keep_grids and case is None:  # a fire with a single observation still needs its grids for the viewer
        case = load_case(fire_id, settings, _shared)
        stitched = np.full(case.shape, np.inf, dtype=np.float32)
    return (rows, case, stitched) if keep_grids else rows


def summarise(scores: pd.DataFrame) -> dict[str, float]:
    return {
        "steps": int(len(scores)),
        "fires": int(scores.fire_id.nunique()),
        "mean_recall": round(float(scores.recall.mean()), 4),
        "mean_even_growth_recall": round(float(scores.even_growth_recall.fillna(0).mean()), 4),
        "mean_iou": round(float(scores.iou.mean()), 4),
        "mean_even_growth_iou": round(float(scores.even_growth_iou.fillna(0).mean()), 4),
        "mean_precision": round(float(scores.precision.fillna(0).mean()), 4),
        "median_area_ratio": round(float(scores.area_ratio.median()), 3),
        "median_direction_error_deg": round(float(scores.direction_error_deg.median()), 1),
        "share_direction_within_45_deg": round(float((scores.direction_error_deg <= 45).mean()), 4),
        # a step where the simulator predicts no growth counts as a head distance of zero
        "median_distance_ratio": round(float((scores.simulated_distance_m.fillna(0) / scores.observed_distance_m).median()), 3),
        "distance_rank_correlation": round(float(scores.simulated_distance_m.fillna(0).corr(scores.observed_distance_m, method="spearman")), 3),
    }
