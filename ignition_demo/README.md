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

The default address is <http://127.0.0.1:8766>. Startup checks the model and
approximately 5 GB of cache fingerprints before serving; allow time for this.
The app loads its scripts, map geometry, fonts and styles locally. It needs no
external map service. The Python server binds only to your computer.

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

The large generated artifacts are intentionally ignored by Git. Either copy
the trusted reconstruction directory and corrected cache from the machine that
built them, or rebuild from the pinned sources:

1. Obtain version 1 of the [original feature dataset](https://www.kaggle.com/datasets/harsheary/ontario-fire-region-10km-daily-ignition-features).
   The uncompressed CSV must have SHA-256
   `8791c96e460e6294791bbbf1ad0d6aad68e31a98be28dbcc6060463f94ccfc9d`.
   The supplied local `.csv.gz` expands to those exact bytes.
2. Recover the weather archive with `python scripts/download_cwfis_fwi.py` in
   the demo environment. The pinned archive checksum is
   `67e706160316e2b1e496bc3b316d17d5c1623954f29231d5cb71e618f0329246`.
   Stop if the downloader reports an upstream change.
3. For the offline map, also recover the Ontario boundary with
   `.venv-demo\Scripts\python.exe scripts/download_ontario_fire_region.py`.
   If transferring artifacts from the prepared machine, include
   `data/raw/ontario_fire_region/fire_response_plan_sectors.geojson` and its
   source manifest.
4. Reconstruct using the uncompressed file or its gzip copy:

```powershell
.venv-demo\Scripts\python.exe -m scripts.ignition_demo.reconstruct --input 'C:\path\to\features.csv.gz'
```

Reconstruction requires roughly 20 GB of free disk for sources, numerical
caches and temporary model inputs; allow at least 8 GB of available RAM.
It preserves every original row, rebuilds the corrected past-only weather,
checks the cache, fits the selected model on 2010–2016 only, freezes it, and
then evaluates 2018 and 2019. It does not run the original 40-candidate search.
The original modelling modules and published reports remain intact.

Completed reconstruction directories are not overwritten. To deliberately
create another reproduction, choose a new `--output` directory. The default
server reads the original demo reconstruction path; use the normal default
path for a first build. A failed/incomplete cache without a manifest must be
investigated before restarting, particularly if archive indexing was interrupted.

## What is generated

| Location | Contents |
| --- | --- |
| `data/interim/ignition_modeling_cache/` | Corrected 36-feature memory-mapped inputs, labels, grid indices, date slices and weather index |
| `artifacts/ignition_demo/reconstruction/` | Model, training diagnostics, freeze, source/cache fingerprints, policy, prediction vectors and verification |
| `docs/ignition_demo/` | Report, learning guide, demo script, compact verification evidence and presentation |

## Prediction interface

All JSON uses UTF-8, dates use local `America/Toronto` calendar days, and missing
numeric values are JSON `null`. Scores are fractions between 0 and 1.

| GET endpoint | Response |
| --- | --- |
| `/api/metadata` | Date range, model provenance, eight cutoffs, validation/test results and limitations |
| `/api/grid` | EPSG:3978 cell origins, geographic centroids and simplified study boundary |
| `/api/predictions?date=2019-07-01` | Scores, recorded labels, weather quality and all eight daily confusion tables |
| `/api/cell?date=2019-07-01&grid_id=...` | Score and exact ordered 36 inputs for a cell |
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

Real-artifact checks run when reconstruction exists. Without it, small policy
and HTTP fixtures still run and the real-artifact checks report skipped.
Browser verification is described in the compact verification report.

## Learning materials

Read `docs/ignition_demo/learning_guide.md`, then follow
`docs/ignition_demo/demo_script.md`. The capstone report records both the
original results and this reconstruction's evidence.

The shared `docs/ignition_demo/architecture.html` map includes the API and
frontend connections. Its code links open the feature branch on GitHub;
generated model/data files are marked for local rebuilding. The original
local Archify map retains its Cursor links.

The editable presentation is ready to use. Regenerating it with
`build_presentation.mjs` additionally requires the bundled Artifact Tool,
the captured app screenshot, and `IGNITION_PRESENTATION_SKILL_DIR` and
`IGNITION_PRESENTATION_RUNTIME_DIR` set to the installed presentation tools
and dependency directory. These authoring tools are separate from running
the app.
