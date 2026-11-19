# COMP-385

Ontario wildfire ignition modelling data for COMP-385.

The established baseline is a 2010–2019 Ontario Fire Region 10 km fire-season
cell/day ignition label panel. The large label and feature panels are
reproducible build artifacts, while their compact inputs, manifests, audits, and
the v1 feature implementation are tracked. The current `ignition-feature-v1.1.0`
build has 51 columns and 39 selected predictors: calendar, static CDEM terrain,
prior-day CWFIS weather/FWI, past-only ignition history with its explicit
censor flag, and two static cell-centre coordinates, without changing the panel's row universe. The
coordinates are `grid_x_m + 5000` and `grid_y_m + 5000` in EPSG:3978 metres,
fixed per full 10 km cell, not ignition locations or clipped centroids.

See [the ignition feature documentation](docs/ignition_features.md) for source
provenance, leakage boundaries, deferred feature families, and reproducible
build commands. This branch's work focuses on the ignition panel.

See [the completed model comparison](docs/modeling/final_report.md) for the
logistic regression and histogram gradient boosting results, independent
verification, threshold tradeoffs and reproduction commands. The modelling
cache corrects v1 weather station selection and source-date joins; the original
v1 EDA below describes the uncorrected download.
The [development-only HGB tuning guide](docs/modeling/README.md#development-only-hgb-tuning)
describes the bounded follow-up experiments without reusing the 2019 test.

The [Ontario Ignition Atlas](ignition_demo/README.md) turns the verified model
into a local historical risk-map demo. Double-click `Start-IgnitionDemo.cmd`
on a prepared Windows checkout. It includes date-based predictions, cell
inspection, validation-selected alert controls and CSV exports. Read the
[implementation report](docs/ignition_demo/report.md),
[learning guide](docs/ignition_demo/learning_guide.md), and
[presentation](docs/ignition_demo/presentation.pptx).
The [interactive architecture map](docs/ignition_demo/architecture.html) also
shows both AI capabilities, the ignition demo API, the separate ignition
development branch, and the learned fire-spread pipeline. Open **Architecture**
in the demo site's header, or open the standalone HTML directly. Component
source links point to the verified 18 November 2026 code snapshot.

See [the ignition EDA](docs/eda/README.md) for historical v1.0.0 (48-column)
full-panel counts and missingness from the 2026-10-05 rebuild, feature
explanations, figures, the notebook, and reproduction commands. The current
`data/metadata/ignition_feature_selection_v1.json` is the only authoritative
39-predictor list: 36 original fields, history-censor flag, then coordinates.
The main corrected-weather cache, HGB and demo all consume these persisted
fields without appending duplicates; old 36-column caches are rejected.

The 2026-11-19 main-pipeline rebuild completed the 51-column panel and
39-column corrected-weather cache. Its retained 80-iteration joblib model
matches the experiment pickle bit-for-bit on all 2010–2016 development rows.
The demo serves that export and displays the frozen 10 km grid footprint.
See `docs/modeling/README.md` for commands, provenance and verification.
Static geometry adds no dynamic source or operational forecasting claim.

The second AI capability, wind-driven fire spread, has its own folder:
[`capability_2_fire_spread/`](capability_2_fire_spread/README.md). It holds a
separate dataset of 752 Ontario fires from 2012–2025 with their growth rebuilt
from satellite passes, hourly wind and fire-weather codes, fuel and terrain,
the Canadian FBP spread simulator, and ten learned models compared with it on
2021–2024 fires. Its README gives the results of every experiment. It is never
an ignition input.
