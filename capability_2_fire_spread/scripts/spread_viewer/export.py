"""Export the viewer: the best learned model (the CNN) beside the FBP simulator, on test fires.

Writes `viewer/fire_spread_viewer.html`: the page in `viewer/viewer_template.html`
with the data written into it, so the one file opens anywhere.  Only holdout
fires (2021-2024) are shown, because the CNN was trained on the others.  For
each scored step of a fire it keeps the area burned so far, the cells each model
predicts, the cells the next satellite pass saw, the step's wind and both
models' scores.

The predictions are exactly those of the holdout comparison (`compare.py`): the
simulator's cells from the cell table, and the CNN's most likely cells, as many
as the simulator predicts in that step, so only where they are placed differs.
Needs the cell table (`cell_table.py`) and the CNN's holdout predictions
(`train_cnn.py`).

The ground is the Canada Base Map (see `basemap.py`), one image per fire,
downloaded the first time it is needed and kept in `data/raw/basemap/`.
Fires are chosen by rule, not by how well they turned out: the simulator's
published holdout fires with the most scored steps whose grid is small enough.

    python -m scripts.spread_viewer.export
"""

from __future__ import annotations

import argparse
import base64
import json

import numpy as np
import pandas as pd

from scripts.spread_common import PROCESSED, PROJECT_ROOT, RAW, action_log
from scripts.spread_modeling import replay
from scripts.spread_modeling.contract import CELL_TABLE, COMPARISON, MODEL_DIR, SIMULATOR_HOLDOUT_STEPS, SIMULATOR_SCORES
from scripts.spread_modeling.evaluation import predicted_mask
from scripts.spread_modeling.features import step_weather
from scripts.spread_modeling.simulator import CELL_375_M, FireCase, Settings

from . import basemap


OUTPUT = PROJECT_ROOT / "viewer/spread_viewer_data.js"
TEMPLATE = PROJECT_ROOT / "viewer/viewer_template.html"
PAGE = PROJECT_ROOT / "viewer/fire_spread_viewer.html"
DATA_TAG = '<script src="spread_viewer_data.js"></script>'
# the learned model shown, by its key in the page: the CNN, which does not take the simulator's output as an input
SHOWN = {"cnn": "cnn"}
MAX_GRID_CELLS = 130_000
WINDOW_MAP_PX = 1800  # longest side of the base-map image


def b64(array: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode("ascii")


def cells(mask: np.ndarray) -> str:
    return b64(np.flatnonzero(mask).astype(np.uint32))


def window_map_box(shape: tuple[int, int]) -> dict[str, int]:
    """A 3:2 box of 90 m cells around the fire's window, reaching past it, so the map fills the viewer."""
    rows = round(max(shape) * 1.1)
    columns = round(rows * 1.5)
    return {"r0": round((shape[0] - rows) / 2), "c0": round((shape[1] - columns) / 2), "rows": rows, "columns": columns}


def map_image(name: str, case: FireCase, box: dict[str, int], log) -> dict[str, object] | None:
    """The base map for a box of cells, ready to write into the page; None if the map service cannot be reached."""
    west, north = case.west + box["c0"] * case.pixel, case.north - box["r0"] * case.pixel
    try:
        path, fresh = basemap.fetch(name, west, north - box["rows"] * case.pixel, west + box["columns"] * case.pixel, north, WINDOW_MAP_PX)
    except (OSError, RuntimeError) as error:
        log.info(f"WARNING: no base map for {name} ({error}); the viewer shows a plain ground there")
        return None
    if fresh:
        log.info(f"downloaded base map {path.name} from {basemap.SERVICE}, {path.stat().st_size / 1024:.0f} KB")
    return {"src": basemap.data_uri(path), **box}


def export_fire(fire_id: str, settings: Settings, fire_row, rows: pd.DataFrame, log, with_map: bool) -> dict[str, object]:
    """Every scored step of one fire: burned area, both models' predicted cells, the next pass's new cells, scores."""
    steps, case = [], None
    by_step = dict(tuple(rows.groupby("observation")))
    for step in replay.iter_steps(fire_id, settings):
        case, layout = step.case, step.layout
        here = by_step[step.observation]
        n = len(case.cell375_keys)
        candidates = here.cell.to_numpy()
        in_radius = here.in_radius.to_numpy()
        fbp = np.zeros(n, dtype=bool)
        fbp[candidates[here.sim_new.to_numpy() == 1]] = True
        masks = {"fbp": fbp, **{key: predicted_mask(n, candidates[in_radius], here[f"p_{key}"].to_numpy()[in_radius], int(fbp.sum())) for key in SHOWN}}
        recall = {key: replay.score_step(case, layout, step.start, step.active, step.observed_new, mask)["recall"] for key, mask in masks.items()}
        weather = step_weather(case, step.start_utc, step.hours, replay._shared["daily"][fire_id].set_index("date"))
        steps.append({
            "from": step.observation, "to": step.next_observation, "hours": round(step.hours, 1),
            "startLocal": (step.start_utc + pd.Timedelta(hours=int(fire_row.utc_offset_hours))).strftime("%Y-%m-%d %H:%M"),
            "windKmh": round(weather["wind_mean_kmh"]), "windFrom": round((weather["downwind_bearing_deg"] + 180) % 360),
            "burned": cells(step.start), "observed": cells(step.observed_new), **{key: cells(mask) for key, mask in masks.items()},
            "score": {"observed": int(step.observed_new.sum()), "predicted": int(fbp.sum()), **{key + "Recall": round(value, 3) for key, value in recall.items()}},
        })  # fmt: skip
    keys = np.array(case.cell375_keys, dtype=np.int32)
    return {
        "id": fire_id, "year": int(fire_row.fire_year), "sizeHa": float(fire_row.reported_size_ha), "cause": fire_row.cause,
        "rows": int(case.shape[0]), "columns": int(case.shape[1]), "pixel": float(case.pixel), "west": float(case.west), "north": float(case.north),
        "convergence": round(float(case.convergence_deg), 2), "cellX": b64(keys[:, 0]), "cellY": b64(keys[:, 1]),
        "basemap": map_image(fire_id, case, window_map_box(case.shape), log) if with_map else None,
        "steps": steps,
    }  # fmt: skip


def write_page(data_script: str) -> None:
    """One self-contained page: the template with the data written into it."""
    template = TEMPLATE.read_text(encoding="utf-8")
    if DATA_TAG not in template:
        raise ValueError(f"{TEMPLATE.name} no longer contains {DATA_TAG}")
    PAGE.write_text(template.replace(DATA_TAG, "<script>" + data_script + "</script>"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fires", type=int, default=3)
    parser.add_argument("--page-only", action="store_true", help="rebuild the page from the template and the data already exported")
    parser.add_argument("--no-base-map", action="store_true", help="leave out the Canada Base Map images")
    args = parser.parse_args()
    log = action_log("viewer export")
    if args.page_only:
        write_page(OUTPUT.read_text(encoding="utf-8").strip())
        log.info(f"DONE: rebuilt {PAGE.name} from {TEMPLATE.name} and the existing {OUTPUT.name}")
        return
    scores = json.loads(SIMULATOR_SCORES.read_text(encoding="utf-8"))
    settings = Settings(ros_scale=scores["chosen_ros_scale"], flank_scale=scores["chosen_flank_scale"])
    fires = pd.read_csv(PROCESSED / "ontario_fire_spread_fires_v1.csv", dtype={"fire_id": str}).set_index("fire_id")
    windows = {w["fire_id"]: w["rows"] * w["columns"] for w in json.loads((RAW / "fuel_terrain/fuel_windows_manifest.json").read_text(encoding="utf-8"))["windows"]}
    counts = pd.read_csv(SIMULATOR_HOLDOUT_STEPS, dtype={"fire_id": str}).groupby("fire_id").size()
    counts = counts[[windows[fire_id] <= MAX_GRID_CELLS for fire_id in counts.index]].sort_values(ascending=False, kind="stable")
    chosen = list(counts.index[: args.fires])
    log.info(f"START: {list(SHOWN.values())} beside the FBP simulator on holdout fires {chosen}")
    table = pd.read_parquet(CELL_TABLE, columns=["fire_id", "observation", "cell", "in_radius", "sim_new"], filters=[("fire_id", "in", chosen)])
    for key, model in SHOWN.items():
        predictions = pd.read_parquet(MODEL_DIR / f"{model}.predictions.parquet").rename(columns={"p": f"p_{key}"})
        table = table.merge(predictions, on=["fire_id", "observation", "cell"], how="left")
        table[f"p_{key}"] = table[f"p_{key}"].fillna(0.0)  # cells outside the candidate radius are never predicted by a CNN
    overall = json.loads(COMPARISON.read_text(encoding="utf-8"))["all_scored_holdout_fires"]["all_steps"]["by_model"]
    summary = {name: {"recall": overall[key]["mean_recall"], "iou": overall[key]["mean_iou"], "direction45": overall[key]["share_direction_within_45_deg"]}
               for name, key in [*((k, f"{m}_matched") for k, m in SHOWN.items()), ("fbp", "simulator")]}  # fmt: skip
    summary.update(steps=overall["simulator"]["steps"], fires=overall["simulator"]["fires"])
    payload = {
        "settings": {"cell375": CELL_375_M, "basemapCredit": basemap.CREDIT},
        "summary": summary,
        "fires": [export_fire(fire_id, settings, fires.loc[fire_id], table[table.fire_id == fire_id], log, not args.no_base_map) for fire_id in chosen],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    data_script = "window.SPREAD_VIEWER_DATA = " + json.dumps(payload, separators=(",", ":")) + ";"
    OUTPUT.write_text(data_script + "\n", encoding="utf-8")
    write_page(data_script)
    log.info(f"DONE: wrote {PAGE.name}, {PAGE.stat().st_size / 1_048_576:.2f} MB, {sum(len(f['steps']) for f in payload['fires'])} steps from {len(chosen)} fires")


if __name__ == "__main__":
    main()
