# Ontario Wildfire Code Iteration 1

COMP 385 research prototype. This submission includes the team's data and spread modules plus the local ignition experiments, corrected replay integration and combined dashboard. It does not claim individual authorship of every collaborator's code.

## Runtime assets

This Git folder contains code, tests, bounded test fixtures and research evidence. Large generated predictions, model bundles, map pages and feature caches are omitted and listed with hashes in runtime_artifacts.json. Before demonstrating saved scores, maps or cell details, extract Code_Iteration_1.zip from the local submission delivery and copy its contents into this folder. The complete local package is at ../reports/submission_iteration_1/Code_Iteration_1.zip relative to the original CAPSTONE workspace, outside this Git checkout. Collaborators need that artifact package or must rebuild the pinned data using the included scripts and documented source access. No model was refit for this commit.

## Run the prototype

Use Python 3.13. From this extracted folder, run these commands one at a time:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m scripts.capstone_app serve --port 8768
```

Open http://127.0.0.1:8768/ . If another application uses that port, stop your previous prototype with Ctrl+C or choose another port. Stop the server with Ctrl+C.

On macOS, LightGBM can require the OpenMP runtime. If its import reports libomp missing, install the official Homebrew libomp package (`brew install libomp`) and retry. Dependency installation needs Internet access. Existing model artifacts were created with the exact versions in requirements-lock.txt. The saved-result demo does not require weather-provider credentials or downloads.

## What to demonstrate

1. Historical ignition: select a supported date from May to October 2019, click a 10 km cell and inspect the probability.
2. Request Cell details and provenance. Saved factor explanations cover the first evaluated day only; other dates explicitly say unavailable. Changing date or cell clears stale details.
3. Export that date as CSV or GeoJSON. Historical exports contain 9,673 cells; the selected-source study contains 9,648 cells.
4. Selected sources: inspect the separate September to October 2025 study. Do not treat it as the same training population as the historical study.
5. Spread: inspect one of four supported incidents, replay observations and the 1/3/6-hour simulation controls. These are saved retrospective reconstruction outputs, not a live simulation API.
6. Live readiness: verify the unavailable message and missing qualification evidence. HTTP 503 with probability null is the expected safe result.

## Run the tests

```sh
python -m pytest tests team_repository/tests team_repository/capability_2_fire_spread/tests -q
```

The submission layout passes all 129 tests in the current Mac environment. Fourteen HTTP checks cover all four pages, both saved-score paths, three detail cases, three exports, invalid input and fail-closed live output. See evidence/submission_verification. The archived final review contains browser and performance records with their original scope.

## Files to review

- scripts/capstone_app.py: loopback dashboard, request validation, saved-score/detail lookup, exports and readiness.
- scripts/ignition_comparison.py, week5_ignition.py, selected_2025_model.py: comparison, frozen refit/calibration and separate selected-source study.
- scripts/prepare_*.py, build_selected_2025_panel.py, refine_provincial_fuel.py, hrdps_live_weather.py: versioned preparation and weather paths.
- team_repository/scripts: team historical feature builders.
- team_repository/capability_2_fire_spread/scripts: empirical FBP-inspired simulator, fire-weather equations and replay tooling.
- tests and team_repository test folders: automated regression checks.
- docs/diagrams: original DOT, SVG and PNG diagrams. docs/diagrams/lucid contains the eight Lucid page exports, Draw.io import source and verified page inventory. Open the Lucid document at https://lucid.app/lucidchart/24bb58c8-fb97-479c-a0a8-9434caf9e283/edit .
- data/processed: frozen model bundles, saved predictions and runtime feature caches.
- reports: dated research evidence; later records supersede historical status statements in earlier reports.

## Boundaries and reproducibility

The separate full submission ZIP includes saved temporal/geographic prediction tables, calibrated model bundles, first-day explanations, the feature caches needed by detail lookups, grid geometry and study HTML files. This Git snapshot intentionally omits the runtime files listed in runtime_artifacts.json. Source and scientific runtime files are copied without model retuning. The manifest records hashes. The corrected spread viewer embeds saved supported-case output; running it does not rerun calibration or holdout scoring.

Full national raw rasters, full historical training/calibration partitions, ERA5/HRDPS acquisition archives and all corrected replay landscapes are intentionally excluded. Acquisition/training code and source registries are included for review, but a complete raw-to-model rebuild requires restoring those pinned archives, provider access where applicable, and the original documented protocols. Paths recorded inside old manifests remain historical provenance, not portable instructions. Do not rerun final-test selection to improve the reported result.

The 2.5 km sample rasters/pilot are included only as fixtures for existing tests and history; they do not replace the current 10 km ignition decision. Public-source metadata and credits are preserved in the source registries and dated evidence. No API keys, virtual environment, Git credentials, user identity forms or machine secrets are included.

This package was tested after relocation on the same Mac with the existing environment. A new operating-system/dependency installation is not certified. The spread viewer can request external basemap tiles; its embedded reconstruction and fuel view remain the scientific content. Live scoring, independent user/field/professor acceptance and public/cloud deployment are not complete. Native Microsoft Project verification remains deferred.
