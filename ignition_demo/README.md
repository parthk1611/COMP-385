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

## What is generated

| Location | Contents |
| --- | --- |
| `data/interim/ignition_modeling_cache/` | Corrected 39-feature memory-mapped inputs, labels, grid indices, date slices and weather index; v3 rejects old caches |
| `artifacts/ignition_modeling/retained_coordinate_hgb/` | Main joblib model, settings/ordered features/training scope/commit/checksums JSON, training diagnostics and verification |
| `docs/ignition_demo/` | Current 80-iteration/39-input report, learning guide, walkthrough and verification plan; presentation files and `reconstruction_evidence.json` are historical 40-iteration materials |

## Prediction interface

All JSON uses UTF-8, dates use local `America/Toronto` calendar days, and missing
numeric values are JSON `null`. Scores are fractions between 0 and 1.

| GET endpoint | Response |
| --- | --- |
| `/architecture` | Full interactive architecture of both AI capabilities |
| `/api/metadata` | Date range, 80-iteration model provenance, ordered 39 features, illustrative cutoffs and limitations |
| `/api/grid` | EPSG:3978 cell origins, geographic centroids and the frozen 10 km grid footprint (not an official boundary) |
| `/api/predictions?date=2019-07-01` | Scores, recorded labels, weather quality and all eight daily confusion tables |
| `/api/cell?date=2019-07-01&grid_id=...` | Score and exact ordered 39 inputs for a cell |
| `/api/download?date=2019-07-01` | Full-precision CSV containing all 9,673 cells |

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
`docs/ignition_demo/demo_script.md`. The current report and verification plan
describe the retained 80-iteration, 39-input model and clean export provenance.
The existing presentation and its generator remain historical materials, not
current-model performance evidence.

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
