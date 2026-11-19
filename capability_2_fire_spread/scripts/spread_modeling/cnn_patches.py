"""Map patches for the CNN: each replay step drawn as a 96 x 96 image of 375 m cells (36 km).

The patch is centred on the stretch of perimeter still burning.  Its channels carry
the same information the per-cell models get, as maps: the area burned so far and
the active perimeter, fuel shares, the FBP head rate of spread, terrain, distance to
the fire, the step's wind (as an east/north arrow) and fire-weather codes, how the
fire grew at the last pass, and the simulator's reached share (used only by
`cnn_hybrid`).  The label map marks the cells first seen burning at the next pass,
and the mask marks the candidate cells every model is scored on.  Needs the cell
table (`cell_table.py`).

    python -m scripts.spread_modeling.cnn_patches
"""

from __future__ import annotations

import argparse
import json
import math
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import ndimage

from scripts.spread_common import action_log

from .contract import CELL_TABLE, CELL_TABLE_STEPS, CNN_PATCH_INDEX, CNN_PATCHES, LABEL, SIMULATOR_SCORES
from .features import fbp_head_ros, load_observation_history, static_cell_layers, step_weather
from .replay import iter_steps
from .simulator import CELL_375_M, Settings


SIZE = 96
CHANNELS = [
    "burned", "active", "inside_window", "fuel_conifer_share", "fuel_mixedwood_share", "fuel_deciduous_share", "fuel_grass_share",
    "fuel_non_fuel_share", "fuel_water_share", "fbp_head_ros", "elevation_anomaly", "distance_to_burned", "distance_to_active",
    "wind_east", "wind_north", "wind_max", "ffmc", "bui", "isi", "step_hours", "night_share", "rh_min", "temp_mean", "precip_total",
    "previous_head_east", "previous_head_north", "previous_new_cells", "previous_known", "sim_reached_share",
]  # fmt: skip
VECTORS = [("wind_east", "wind_north"), ("previous_head_east", "previous_head_north")]  # arrows: turned when a patch is rotated
_state: dict = {}


def _patch_work(job: tuple[str, float, float]):
    fire_id, ros, flank = job
    if "history" not in _state:
        _state["history"] = load_observation_history()
        _state["shared"] = {}
        table = pd.read_parquet(CELL_TABLE, columns=["fire_id", "observation", "cell", "in_radius", LABEL, "sim_reached_share"])
        _state["rows"] = dict(tuple(table.groupby("fire_id")))
    rows_by_step = dict(tuple(_state["rows"][fire_id].groupby("observation")))
    patches, labels, masks, index = [], [], [], []
    static = None
    for step in iter_steps(fire_id, Settings(ros_scale=ros, flank_scale=flank), shared=_state["shared"]):
        rows = rows_by_step.get(step.observation)
        if rows is None:
            continue
        case, layout = step.case, step.layout
        if static is None:
            static = static_cell_layers(case)
            daily = _state["shared"]["daily"][fire_id].set_index("date")
        weather = step_weather(case, step.start_utc, step.hours, daily)
        ros_cell = fbp_head_ros(case, weather)
        nx, ny = layout.shape
        ax, ay = layout.x[step.active], layout.y[step.active]
        cx, cy = int(round(ax.mean())), int(round(ay.mean()))
        x0, y0 = cx - SIZE // 2, cy - SIZE // 2
        full = {}
        grid = lambda values: _grid(layout, values)  # noqa: E731
        full["burned"], full["active"] = layout.grid(step.start).astype(np.float32), layout.grid(step.active).astype(np.float32)
        full["inside_window"] = layout.grid(np.ones(len(layout.x), dtype=bool)).astype(np.float32)
        for name in ["fuel_conifer_share", "fuel_mixedwood_share", "fuel_deciduous_share", "fuel_grass_share", "fuel_non_fuel_share", "fuel_water_share"]:
            full[name] = grid(static[name])
        full["fbp_head_ros"] = grid(ros_cell / 10.0)
        elevation = static["elevation_m"]
        full["elevation_anomaly"] = grid((elevation - elevation[step.active].mean()) / 50.0)
        full["distance_to_burned"] = ndimage.distance_transform_edt(~layout.grid(step.start)).astype(np.float32) * CELL_375_M / 6000.0
        full["distance_to_active"] = ndimage.distance_transform_edt(~layout.grid(step.active)).astype(np.float32) * CELL_375_M / 6000.0
        sim = np.zeros(len(layout.x), dtype=np.float32)
        sim[rows.cell.to_numpy()] = rows.sim_reached_share.to_numpy()
        full["sim_reached_share"] = grid(sim)
        downwind = math.radians(weather["downwind_bearing_deg"] - case.convergence_deg)  # grid frame
        scalars = {
            "wind_east": weather["wind_mean_kmh"] * math.sin(downwind) / 20.0, "wind_north": weather["wind_mean_kmh"] * math.cos(downwind) / 20.0,
            "wind_max": weather["wind_max_kmh"] / 30.0, "ffmc": weather["ffmc"] / 100.0, "bui": weather["bui"] / 100.0, "isi": weather["isi"] / 20.0,
            "step_hours": weather["step_hours"] / 24.0, "night_share": weather["night_share"], "rh_min": weather["rh_min_pct"] / 100.0,
            "temp_mean": weather["temp_mean_c"] / 30.0, "precip_total": weather["precip_total_mm"] / 10.0,
        }  # fmt: skip
        history = _state["history"]
        previous = history.loc[(fire_id, step.observation)] if (fire_id, step.observation) in history.index else None
        known = previous is not None and pd.notna(previous.head_bearing_deg)
        heading = math.radians(previous.head_bearing_deg - case.convergence_deg) if known else 0.0
        reach = (previous.spread_distance_p90_m / 2000.0) if known and pd.notna(previous.spread_distance_p90_m) else 0.0
        scalars.update({"previous_head_east": reach * math.sin(heading), "previous_head_north": reach * math.cos(heading),
                        "previous_new_cells": (previous.new_cells / 50.0) if previous is not None else 0.0, "previous_known": float(known)})  # fmt: skip
        patch = np.zeros((len(CHANNELS), SIZE, SIZE), dtype=np.float16)
        sx = slice(max(x0, 0), min(x0 + SIZE, nx))
        sy = slice(max(y0, 0), min(y0 + SIZE, ny))
        px = slice(sx.start - x0, sx.stop - x0)
        py = slice(sy.start - y0, sy.stop - y0)
        for c, name in enumerate(CHANNELS):
            if name in full:
                patch[c, px, py] = full[name][sx, sy]
            else:
                patch[c, px, py] = scalars[name] * full["inside_window"][sx, sy]
        cells = rows.cell.to_numpy()
        rx, ry = layout.x[cells] - x0, layout.y[cells] - y0
        inside = (rx >= 0) & (rx < SIZE) & (ry >= 0) & (ry < SIZE)
        label, mask = np.zeros((SIZE, SIZE), dtype=np.uint8), np.zeros((SIZE, SIZE), dtype=bool)
        keep = inside & rows.in_radius.to_numpy()
        label[rx[keep], ry[keep]] = rows[LABEL].to_numpy()[keep]
        mask[rx[keep], ry[keep]] = True
        patches.append(patch)
        labels.append(label)
        masks.append(mask)
        index.append(pd.DataFrame({"fire_id": fire_id, "observation": step.observation, "cell": cells, "px": np.where(inside, rx, -1), "py": np.where(inside, ry, -1)}))
    return patches, labels, masks, index


def _grid(layout, values: np.ndarray) -> np.ndarray:
    out = np.zeros(layout.shape, dtype=np.float32)
    out[layout.x, layout.y] = values
    return out


def build(workers: int) -> None:
    log = action_log("CNN patches")
    scores = json.loads(SIMULATOR_SCORES.read_text(encoding="utf-8"))
    steps = pd.read_csv(CELL_TABLE_STEPS, dtype={"fire_id": str})
    fires = steps.groupby("fire_id").window_cells.first().sort_values(ascending=False).index.tolist()
    log.info(f"START: {SIZE} x {SIZE} patches of 375 m cells for {len(steps)} steps of {len(fires)} fires; channels {CHANNELS}")
    with Pool(workers) as pool:
        made = [item for result in pool.imap_unordered(_patch_work, [(f, scores["chosen_ros_scale"], scores["chosen_flank_scale"]) for f in fires]) for item in zip(*result)]
    made.sort(key=lambda item: (item[3].fire_id.iloc[0], int(item[3].observation.iloc[0])))  # same order on every run
    patches, labels, masks, index = [], [], [], []
    for number, (patch, label, mask, rows) in enumerate(made):
        rows["patch"] = number
        patches.append(patch)
        labels.append(label)
        masks.append(mask)
        index.append(rows)
    index = pd.concat(index, ignore_index=True)
    meta = steps.set_index(["fire_id", "observation"])[["split", "fire_year", "simulator_holdout_sample"]]
    patch_meta = index.groupby("patch")[["fire_id", "observation"]].first().join(meta, on=["fire_id", "observation"])
    CNN_PATCHES.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CNN_PATCHES, x=np.stack(patches), y=np.stack(labels), mask=np.stack(masks), split=patch_meta.split.to_numpy(), year=patch_meta.fire_year.to_numpy(),
             fire_id=patch_meta.fire_id.to_numpy(), observation=patch_meta.observation.to_numpy())  # fmt: skip
    index.to_parquet(CNN_PATCH_INDEX, index=False)
    candidates = pd.read_parquet(CELL_TABLE, columns=["fire_id", "observation", "cell", "in_radius", LABEL])
    joined = candidates[candidates.in_radius].merge(index, on=["fire_id", "observation", "cell"])
    covered = joined[(joined.px >= 0)]
    log.info(f"DONE: {len(patches)} patches; {len(covered) / len(joined):.1%} of candidate cells and {covered[LABEL].sum() / joined[LABEL].sum():.1%} of newly burning ones fall inside the patches")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=12)
    build(parser.parse_args().workers)


if __name__ == "__main__":
    main()
