#!/usr/bin/env python3
"""A spatial neural network (CNN) for fire spread, trained on the GPU.

The per-cell models judge one candidate cell at a time.  This model looks at a
96 x 96 patch of 375 m cells (36 km) centred on the stretch of perimeter still
burning, and predicts the whole map of cells that will be newly seen burning at
the next satellite pass.  It is given the same information as the per-cell
models, as image channels: the area burned so far and the active perimeter,
fuel shares, the FBP head rate of spread, terrain, distance to the fire, the
step's wind (as an east/north arrow) and fire-weather codes, and how the fire
grew at the last pass.  `cnn_hybrid` also gets the simulator's reached share.

Training uses calibration fires (2012-2020) only.  Every patch is also seen
rotated and mirrored (the eight symmetries of the square), with the wind and
growth arrows turned to match, and predictions are averaged over those eight
views.  The loss is cross-entropy over the candidate cells within 6 km of the
burned area, exactly the cells the per-cell models are scored on.  Settings
are chosen, and each model's area scale set, by leave-one-fire-year-out
cross-validation, as in `train_spread_models.py`.  The final model's
predictions for every holdout candidate cell are written for
`compare_spread_models.py`.

    python scripts/spread_cnn.py build    # patches from the learned-model table and the fire grids
    python scripts/spread_cnn.py train    # cross-validate, fit, predict holdout fires
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, datetime
from multiprocessing import Pool

import numpy as np
import pandas as pd

from spread_common import DATASET_VERSION, PROCESSED, PROJECT_ROOT, action_log
from spread_ml import LABEL, fbp_head_ros, load_observation_history, static_cell_layers, step_weather


SIZE = 96
TABLE = PROCESSED / "ml/spread_ml_cells_v1.parquet"
PATCHES = PROCESSED / "ml/spread_cnn_patches_v1.npz"
INDEX = PROCESSED / "ml/spread_cnn_patch_index_v1.parquet"
MODEL_DIR = PROJECT_ROOT / "artifacts/spread_models"
REPORT = PROCESSED / "simulation/spread_cnn_v1_training.json"
SEED = 385
CHANNELS = [
    "burned", "active", "inside_window", "fuel_conifer_share", "fuel_mixedwood_share", "fuel_deciduous_share", "fuel_grass_share",
    "fuel_non_fuel_share", "fuel_water_share", "fbp_head_ros", "elevation_anomaly", "distance_to_burned", "distance_to_active",
    "wind_east", "wind_north", "wind_max", "ffmc", "bui", "isi", "step_hours", "night_share", "rh_min", "temp_mean", "precip_total",
    "previous_head_east", "previous_head_north", "previous_new_cells", "previous_known", "sim_reached_share",
]  # fmt: skip
VECTORS = [("wind_east", "wind_north"), ("previous_head_east", "previous_head_north")]
SIMULATOR_CHANNEL = CHANNELS.index("sim_reached_share")
VARIANTS = {"cnn": False, "cnn_hybrid": True}  # name -> sees the simulator channel
CANDIDATES = [{"width": 32, "epochs": epochs, "learning_rate": 1e-3, "weight_decay": 1e-4, "batch_size": 16} for epochs in [20, 40]]
_state: dict = {}


# --------------------------------------------------------------------------------------------- patches


def _patch_work(job: tuple[str, float, float]):
    from scipy import ndimage

    from run_spread_replay import iter_steps
    from simulate_spread import CELL_375_M, Settings

    fire_id, ros, flank = job
    if "history" not in _state:
        _state["history"] = load_observation_history()
        _state["shared"] = {}
        table = pd.read_parquet(TABLE, columns=["fire_id", "observation", "cell", "in_radius", LABEL, "sim_reached_share"])
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
    log = action_log("14 CNN patches")
    scores = json.loads((PROCESSED / "simulation/spread_simulator_v1_scores.json").read_text(encoding="utf-8"))
    steps = pd.read_csv(PROCESSED / "ml/spread_ml_steps_v1.csv", dtype={"fire_id": str})
    fires = steps.groupby("fire_id").window_cells.first().sort_values(ascending=False).index.tolist()
    log.info(f"START: {SIZE} x {SIZE} patches of 375 m cells for {len(steps)} steps of {len(fires)} fires; channels {CHANNELS}")
    patches, labels, masks, index, order = [], [], [], [], []
    with Pool(workers) as pool:
        for result in pool.imap_unordered(_patch_work, [(f, scores["chosen_ros_scale"], scores["chosen_flank_scale"]) for f in fires]):
            for patch, label, mask, rows in zip(*result):
                rows["patch"] = len(patches)
                patches.append(patch)
                labels.append(label)
                masks.append(mask)
                index.append(rows)
    index = pd.concat(index, ignore_index=True)
    meta = steps.set_index(["fire_id", "observation"])[["split", "fire_year", "simulator_holdout_sample"]]
    patch_meta = index.groupby("patch")[["fire_id", "observation"]].first().join(meta, on=["fire_id", "observation"])
    np.savez(PATCHES, x=np.stack(patches), y=np.stack(labels), mask=np.stack(masks), split=patch_meta.split.to_numpy(), year=patch_meta.fire_year.to_numpy(),
             fire_id=patch_meta.fire_id.to_numpy(), observation=patch_meta.observation.to_numpy())  # fmt: skip
    index.to_parquet(INDEX, index=False)
    candidates = pd.read_parquet(TABLE, columns=["fire_id", "observation", "cell", "in_radius", LABEL])
    joined = candidates[candidates.in_radius].merge(index, on=["fire_id", "observation", "cell"])
    covered = joined[(joined.px >= 0)]
    log.info(f"DONE: {len(patches)} patches; {len(covered) / len(joined):.1%} of candidate cells and {covered[LABEL].sum() / joined[LABEL].sum():.1%} of newly burning ones fall inside the patches")


# --------------------------------------------------------------------------------------------- model


def apply_symmetry(x, flip: bool, k: int, vectors: list[tuple[int, int]]):
    """Mirror (east-west) and then turn k quarter turns anticlockwise a [batch, channel, east, north] tensor.

    Arrow channels are turned with the map: a mirror changes the sign of the east part, and a quarter turn
    anticlockwise sends (east, north) to (-north, east).
    """
    import torch

    x = x.clone()
    if flip:
        x = torch.flip(x, dims=[2])
        for e, _ in vectors:
            x[:, e] = -x[:, e]
    for _ in range(k):
        x = torch.rot90(x, 1, dims=(2, 3))
        for e, n in vectors:
            east, north = x[:, e].clone(), x[:, n].clone()
            x[:, e], x[:, n] = -north, east
    return x


def symmetries(x, vectors: list[tuple[int, int]]):
    """The eight rotations/mirrors of a patch batch, as (flip, quarter turns, transformed batch)."""
    return [(flip, k, apply_symmetry(x, flip, k, vectors)) for flip in (False, True) for k in range(4)]


def undo(prediction, flip: bool, k: int):
    """Bring a prediction made on a transformed patch back to the original orientation."""
    import torch

    prediction = torch.rot90(prediction, -k, dims=(-2, -1))
    return torch.flip(prediction, dims=[-2]) if flip else prediction


def make_network(channels: int, width: int):
    import torch
    from torch import nn

    def block(a, b):
        return nn.Sequential(nn.Conv2d(a, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True), nn.Conv2d(b, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        """A small U-Net: three resolutions (375 m, 750 m, 1.5 km), so a cell sees about 20 km of context."""

        def __init__(self):
            super().__init__()
            self.down1, self.down2, self.down3 = block(channels, width), block(width, 2 * width), block(2 * width, 3 * width)
            self.up2, self.up1 = block(5 * width, 2 * width), block(3 * width, width)
            self.out = nn.Conv2d(width, 1, 1)
            self.pool = nn.MaxPool2d(2)

        def forward(self, x):
            a = self.down1(x)
            b = self.down2(self.pool(a))
            c = self.down3(self.pool(b))
            up = nn.functional.interpolate(c, scale_factor=2, mode="bilinear", align_corners=False)
            b = self.up2(torch.cat([up, b], dim=1))
            up = nn.functional.interpolate(b, scale_factor=2, mode="bilinear", align_corners=False)
            return self.out(self.up1(torch.cat([up, a], dim=1)))[:, 0]

    return UNet()


def _channels(hybrid: bool) -> list[int]:
    return [c for c in range(len(CHANNELS)) if hybrid or c != SIMULATOR_CHANNEL]


def fit(x: np.ndarray, y: np.ndarray, mask: np.ndarray, params: dict, hybrid: bool, device):
    import torch

    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    channels = _channels(hybrid)
    vectors = [(channels.index(CHANNELS.index(e)), channels.index(CHANNELS.index(n))) for e, n in VECTORS]
    network = make_network(len(channels), params["width"]).to(device)
    optimiser = torch.optim.AdamW(network.parameters(), lr=params["learning_rate"], weight_decay=params["weight_decay"])
    steps_per_epoch = math.ceil(len(x) / params["batch_size"])
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=params["learning_rate"], total_steps=params["epochs"] * steps_per_epoch)
    network.train()
    for _ in range(params["epochs"]):
        order = rng.permutation(len(x))
        for start in range(0, len(x), params["batch_size"]):
            batch = order[start : start + params["batch_size"]]
            xb = torch.from_numpy(x[batch][:, channels].astype(np.float32)).to(device)
            yb = torch.from_numpy(y[batch].astype(np.float32)).to(device)
            mb = torch.from_numpy(mask[batch]).to(device)
            choice = int(rng.integers(8))
            flip, k = bool(choice // 4), choice % 4
            xb = apply_symmetry(xb, flip, k, vectors)
            yb, mb = _transform(yb, flip, k), _transform(mb, flip, k)
            logits = network(xb)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits[mb], yb[mb]) if mb.any() else logits.sum() * 0
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            schedule.step()
    return network.eval(), channels, vectors


def _transform(t, flip: bool, k: int):
    import torch

    t = torch.flip(t, dims=[-2]) if flip else t
    return torch.rot90(t, k, dims=(-2, -1))


def predict(network, channels, vectors, x: np.ndarray, device, batch_size: int = 32) -> np.ndarray:
    """Probability maps averaged over the eight symmetries."""
    import torch

    out = np.zeros((len(x), SIZE, SIZE), dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(x), batch_size):
            xb = torch.from_numpy(x[start : start + batch_size][:, channels].astype(np.float32)).to(device)
            total = torch.zeros(xb.shape[0], SIZE, SIZE, device=device)
            for flip, k, view in symmetries(xb, vectors):
                total += undo(torch.sigmoid(network(view)), flip, k)
            out[start : start + batch_size] = (total / 8).cpu().numpy()
    return out


def row_probabilities(maps: np.ndarray, patch_ids: np.ndarray, index: pd.DataFrame) -> pd.DataFrame:
    """Each table row's probability from its step's map; rows outside the patch get zero."""
    rows = index[index.patch.isin(patch_ids)].copy()
    position = {p: i for i, p in enumerate(patch_ids)}
    inside = rows.px.to_numpy() >= 0
    probability = np.zeros(len(rows), dtype=np.float32)
    local = rows.patch.map(position).to_numpy()
    probability[inside] = maps[local[inside], rows.px.to_numpy()[inside], rows.py.to_numpy()[inside]]
    rows["p"] = probability
    return rows[["fire_id", "observation", "cell", "p"]]


def train(variants: list[str]) -> None:
    import torch

    from train_spread_models import area_scale, mean_step_ap

    log = action_log("15 train CNN")
    if not torch.cuda.is_available():
        log.info("no CUDA GPU found: training on the CPU, which is much slower")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = np.load(PATCHES, allow_pickle=True)
    x, y, mask, split, year = data["x"], data["y"], data["mask"], data["split"], data["year"]
    index = pd.read_parquet(INDEX)
    table = pd.read_parquet(TABLE, columns=["fire_id", "observation", "cell", "in_radius", LABEL, "split", "fire_year"])
    calibration_rows = table[(table.split == "calibration") & table.in_radius].reset_index(drop=True)
    holdout_rows = table[(table.split == "holdout") & table.in_radius].reset_index(drop=True)
    train_ids = np.flatnonzero(split == "calibration")
    holdout_ids = np.flatnonzero(split == "holdout")
    years = sorted(int(v) for v in np.unique(year[train_ids]))
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    report.update({"dataset_version": DATASET_VERSION, "created_at_utc": datetime.now(UTC).isoformat(), "device": str(torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu"),
                   "torch": torch.__version__, "patch": f"{SIZE} x {SIZE} cells of 375 m", "channels": CHANNELS, "candidates": CANDIDATES,
                   "folds": "leave one fire year out", "selection_metric": "mean over folds of mean per-step average precision"})  # fmt: skip
    report.setdefault("models", {})
    log.info(f"START: {variants} on {len(train_ids)} calibration patches ({years}); {len(holdout_ids)} holdout patches predicted after selection")
    for name in variants:
        hybrid = VARIANTS[name]
        results, out_of_fold = [], {}
        for number, params in enumerate(CANDIDATES):
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
            result = {"candidate": number, "params": params, "mean_step_ap": float(np.mean(list(folds.values()))), "fold_mean_step_ap": folds,
                      "seconds": round(time.perf_counter() - began, 1)}  # fmt: skip
            results.append(result)
            out_of_fold[number] = oof
            log.info(f"{name} candidate {number} {params}: mean per-step AP {result['mean_step_ap']:.4f} ({result['seconds']}s)")
        best = max(results, key=lambda r: r["mean_step_ap"])
        scale = area_scale(calibration_rows, out_of_fold[best["candidate"]])
        network, channels, vectors = fit(x[train_ids], y[train_ids], mask[train_ids], best["params"], hybrid, device)
        torch.save(network.state_dict(), MODEL_DIR / f"{name}.pt")
        holdout = holdout_rows[["fire_id", "observation", "cell"]].merge(row_probabilities(predict(network, channels, vectors, x[holdout_ids], device), holdout_ids, index), how="left")
        holdout["p"] = holdout.p.fillna(0.0)
        holdout.to_parquet(MODEL_DIR / f"{name}.predictions.parquet", index=False)
        meta = {"name": name, "family": "cnn", "feature_set": "patch_with_simulator" if hybrid else "patch", "area_scale": scale, "params": best["params"]}
        (MODEL_DIR / f"{name}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        report["models"][name] = {**meta, "channels": [CHANNELS[c] for c in channels], "candidates": results, "selected": best["candidate"],
                                  "training_patches": int(len(train_ids)), "holdout_patches": int(len(holdout_ids))}  # fmt: skip
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        log.info(f"{name}: chose candidate {best['candidate']}, area scale {scale:.3f}; refitted on all calibration fires and predicted the holdout fires")
    log.info("DONE: CNN models, holdout predictions and spread_cnn_v1_training.json written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["build", "train"])
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--models", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    args = parser.parse_args()
    if args.stage == "build":
        build(args.workers)
    else:
        train(args.models)


if __name__ == "__main__":
    main()
