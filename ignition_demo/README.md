# Ontario Ignition Atlas

A local Windows demonstration of historical Ontario wildfire ignition scores.
It supports every date from **2019-05-01 to 2019-10-31**, with 9,673 cells per day.

## Launch the prepared demo

Double-click **Start-IgnitionDemo.cmd** in the repository root. Keep its window
open while using the app. Close the server with Ctrl+C.

Alternatively, from PowerShell in the repository root:

```powershell
.\Start-IgnitionDemo.ps1
# Another available port, or keep the browser closed:
.\Start-IgnitionDemo.ps1 -Port 8767 -NoBrowser
```

The default address is <http://127.0.0.1:8766>. Startup checks the retained
80-iteration model and current 39-column cache fingerprints before serving.
The app loads its scripts, map geometry, fonts and styles locally. It needs no
external map service. The Python server binds only to your computer.

The header's **Architecture** link opens the full interactive Archify diagram
at `/architecture` in a new tab. The same self-contained page is committed at
`docs/ignition_demo/architecture.html` and can be opened directly without
starting the prediction server.

## Setup on another Windows machine

Use Python **3.12**. The packages below match the reconstructed model. An
isolated environment keeps this project's dependencies separate.

```powershell
py -3.12 -m venv .venv-demo
.venv-demo\Scripts\python.exe -m pip install -r ignition_demo/requirements.txt
```

If using `uv`:

```powershell
uv venv --python 3.12 .venv-demo
uv pip install --python .venv-demo/Scripts/python.exe -r ignition_demo/requirements.txt
```

Large generated artifacts are intentionally ignored by Git. Transfer the
trusted `artifacts/ignition_modeling/retained_coordinate_hgb/` export and
`data/interim/ignition_modeling_cache/` together, or rebuild the current
51-column panel and 39-column cache using
[the main modelling guide](../docs/modeling/README.md).

The old downloadable 48-column CSV and v2 36-column cache are not accepted
by the current model. Recover the pinned NFDB, grid, terrain and CWFIS inputs
using `ABOUT.md`; do not bypass a weather archive checksum mismatch.
The map displays the existing frozen 10 km grid footprint, explicitly labelled
as such. The pinned Ontario boundary asset is unavailable; do not substitute a
different boundary file whose checksum does not match. No boundary download
is required for this grid-footprint view.

Once the current panel exists, reconstruction delegates to the same cache
builder and retained main trainer:

```powershell
.venv-demo\Scripts\python.exe -m scripts.ignition_demo.reconstruct
```

It fits the 80-iteration coordinate HGB on 2010–2016 only. It does not run the
old model search, fit a calibrator, tune thresholds or globally evaluate
2018/2019. Existing model output directories are rejected; choose a new
`--output` directory for another run. The default server consumes the main
retained export, not `artifacts/ignition_demo/reconstruction/`.

### Rebuilding from a fresh clone without the boundary

The pinned Ontario Fire Region boundary can no longer be downloaded with its
recorded checksum. The label build needs it only to choose the in-region NFDB
events and to lay out the grid. Both results are tracked in git:
`data/interim/ontario_fire_region_10km_grid.csv` (9,673 cells) and
`data/interim/ontario_fire_region_nfdb_ignitions_2010_2019.csv` (8,109 events).
`--from-frozen` rebuilds the daily labels from those two files alone. It
leaves them and the label audit untouched, and stops if any count differs
from the tracked audit. Every other input (terrain summary, NFDB events,
feature registry) is tracked as well, so only the weather archive needs
downloading. From the repository root, in the demo environment:

```powershell
.venv-demo\Scripts\python.exe scripts/download_cwfis_fwi.py                       # ~2 min; refuses a changed archive
.venv-demo\Scripts\python.exe scripts/build_cpa_daily_ignition_labels.py --from-frozen   # ~6 min; 17,798,320 label rows
.venv-demo\Scripts\python.exe scripts/build_ignition_feature_panel.py             # ~50 min; 0.8 GB gzip panel
.venv-demo\Scripts\python.exe -m scripts.ignition_demo.reconstruct                # validate, cache, train, export
```

These are one-off steps. The panel, cache and model stay on disk, so later
launches only check fingerprints and serve. The download rewrites the
timestamp in the tracked `data/raw/cwfis/manifest.json`; restore it with
`git checkout` when the checksum matched. Teammates can copy the export and
cache folders instead of rebuilding.

## Fire spread from a selected cell (capability 2)

Below the map, **What if a fire started here?** grows a fire from the
selected cell's centre with capability 2's FBP simulator. Choose a start hour
(local standard time, default 14:00) and a run length (6–72 h). The map plays
the fire smoothly, at about 60 frames a second: 12 s for a 24 h run, up to 20 s
for 72 h. It starts
zoomed in on the start point (2 km across) and pulls back as the burned area
grows. Panning or zooming yourself stops it following. The fire is drawn on
the simulator's own 90 m cells (375 m for runs over 80,000 cells), and the
ignition colours are faded so it stands out. Arrival times are interpolated
between neighbouring cells, so the front sweeps across each cell instead of
filling it all at once, and the outline is rounded rather than stair-stepped.
The fire is drawn as a glowing red-orange fog: a soft, blurred haze with a
tighter body on top. Each spot glows pale yellow as the fire arrives, cools
through orange and red, and fades over about 10 hours to a translucent
ember-red smoke over the burned ground. The burning edge shimmers slightly. When only the start cell burns, the page says why: usually the day
itself was too wet (FFMC below about 75). A bar on the map has play/pause
and a time slider to scrub through the run. It reads out the time since the
start, the local clock time, the area burned so far (from the 90 m grid) and
that hour's wind; an arrow on the map shows where the wind blows. Below the
map are the final burned area, head distance and direction, and the weather at
the start.

- The server runs `capability_2_fire_spread/scripts/spread_modeling/ignition_bridge.py`
  in its own process for each new request, and keeps the last 64 results in
  memory.
- **Internet is needed the first time at a place.** The fuel map, terrain and
  ERA5 weather are fetched for a window around the cell and cached in
  `capability_2_fire_spread/artifacts/ignition_bridge/`. The first run takes
  about 30 s; repeats take 3–5 s.
- **One extra file** is needed once: the Ontario fire perimeters used to
  repair burn scars of fires after the run date. From `capability_2_fire_spread/`,
  run `python scripts/download_fire_disturbance.py --layer area`.
- The FBP settings come from `capability_2_fire_spread/docs/modeling/bridge_simulator_tuning.json`.
  They were tuned on 2012–2016 fires and tested on 2017–2018 and 2020–2024;
  2019 was never used. See the capability 2 README.
- It is a hindcast: it uses the weather that actually followed. A high
  ignition score does not mean a fire started there.

## What is generated

| Location | Contents |
| --- | --- |
| `data/interim/ignition_modeling_cache/` | Corrected 39-feature memory-mapped inputs, labels, grid indices, date slices and weather index; v3 rejects old caches |
| `artifacts/ignition_modeling/retained_coordinate_hgb/` | Main joblib model, settings/ordered features/training scope/commit/checksums JSON, training diagnostics and verification |
| `docs/ignition_demo/` | Historical report, learning materials and presentation; their old 40-iteration performance is not attributed to the new model |

## Prediction interface

All JSON uses UTF-8, dates use local `America/Toronto` calendar days, and missing
numeric values are JSON `null`. Scores are fractions between 0 and 1.

| GET endpoint | Response |
| --- | --- |
| `/architecture` | Full interactive architecture of both AI capabilities |
| `/api/metadata` | Date range, 80-iteration model provenance, ordered 39 features, illustrative cutoffs and limitations |
| `/api/grid` | EPSG:3978 cell origins, geographic centroids and simplified study boundary |
| `/api/predictions?date=2019-07-01` | Scores, recorded labels, weather quality and all eight daily confusion tables |
| `/api/cell?date=2019-07-01&grid_id=...` | Score and exact ordered 39 inputs for a cell |
| `/api/download?date=2019-07-01` | Full-precision CSV containing all 9,673 cells |
| `/api/spread?date=2019-07-01&grid_id=...&start_hour=14&hours=24` | FBP spread from the cell's centre: reached 375 m cells with arrival minutes, summary, weather at start, FBP settings and their tuning years. 400 for bad hours, 404 for an unknown cell, 502 if the simulation cannot run (for example, no internet on a first run) |

Prediction arrays align with the cell order returned by `/api/grid`. The
service explicitly reorders the cache's daily rows by grid index. Missing or
duplicate dates and out-of-range dates return 400; unknown cells and routes
return 404. Missing startup artifacts produce a recovery instruction.

## Checks

```powershell
.venv-demo\Scripts\python.exe -m unittest discover -s tests -v
node --check ignition_demo/web/app.js
```

Real-artifact checks run when the main retained export exists. Otherwise,
isolated joblib/cache fixtures exercise the model-selection, HTTP and integrity
contracts without downloaded data. Demo cutoffs are illustrative, not the
previous model's validated policy; daily observed counts are descriptive.

## Learning materials

Read `docs/ignition_demo/learning_guide.md`, then follow
`docs/ignition_demo/demo_script.md`. The capstone report records both the
original results and this reconstruction's evidence.

The shared `docs/ignition_demo/architecture.html` map includes the API and
frontend connections, the separate ignition development branch, and the
learned fire-spread pipeline. Its source links open the exact 18 November 2026
code snapshot on GitHub. Generated model/data files still require local
rebuilding or transfer. The editable Archify specification and compact
verification record are beside the HTML as `architecture.json` and
`architecture-verification.json`.

The editable presentation is ready to use. Regenerating it with
`build_presentation.mjs` additionally requires the bundled Artifact Tool,
the captured app screenshot, and `IGNITION_PRESENTATION_SKILL_DIR` and
`IGNITION_PRESENTATION_RUNTIME_DIR` set to the installed presentation tools
and dependency directory. These authoring tools are separate from running
the app.
