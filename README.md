# COMP-385

Ontario wildfire ignition modelling data for COMP-385.

The established baseline is a 2010–2019 Ontario Fire Region 10 km fire-season
cell/day ignition label panel. The large label and feature panels are
reproducible build artifacts, while their compact inputs, manifests, audits, and
the v1 feature implementation are tracked. The feature build adds time-bounded
calendar, static CDEM terrain, prior-day CWFIS weather/FWI, and past-only
ignition-history features without changing that panel's row universe.

See [the ignition feature documentation](docs/ignition_features.md) for source
provenance, leakage boundaries, deferred feature families, and reproducible
build commands. This branch's work focuses on the ignition panel.

See [the completed model comparison](docs/modeling/final_report.md) for the
logistic regression and histogram gradient boosting results, independent
verification, threshold tradeoffs and reproduction commands. The modelling
cache corrects v1 weather station selection and source-date joins; the original
v1 EDA below describes the uncorrected download.

See [the ignition EDA](docs/eda/README.md) for full-panel counts and missingness,
feature explanations, figures, the notebook, and commands to reproduce the
analysis. Its 36 recommended source predictors are recorded in
`data/metadata/ignition_feature_selection_v1.json`.

The second AI capability, wind-driven fire spread, has its own folder:
[`capability_2_fire_spread/`](capability_2_fire_spread/README.md). It holds a
separate dataset of 752 Ontario fires from 2012–2025 with their growth rebuilt
from satellite passes, hourly wind and fire-weather codes, fuel and terrain.
It is a replay set for the spread simulator and is never an ignition input.

## Iteration 1 prototype

[Prototype code and setup](prototype_iteration_1/README.md) contains the local combined dashboard, corrected ignition experiments, selected-source study, regression tests, bounded test fixtures and research evidence. [Progress report](docs/progress/Iteration_1_Progress_Report.docx) includes the architecture, use cases, data relationships, interaction flows and local deployment. [Lucid diagrams](https://lucid.app/lucidchart/24bb58c8-fb97-479c-a0a8-9434caf9e283/edit) are exported under `prototype_iteration_1/docs/diagrams/lucid`.

This snapshot preserves the existing root modelling work. The prototype retains its own pinned experiment contracts under `prototype_iteration_1`; results from the two workflows must not be combined. Large generated runtime assets remain outside Git and are inventoried in `prototype_iteration_1/runtime_artifacts.json`. Restore those assets from the separate full code submission ZIP before demonstrating saved maps and predictions. The corrected spread propagation blocks one-cell water barriers and diagonal corners; final-perimeter assistance is explicit retrospective reconstruction. Live forecasting remains unqualified.
