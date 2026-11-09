"""Publish compact demo evidence and a source-backed capstone report."""
from pathlib import Path
from .common import OUTPUT, ROOT, read_json, write_json


def publish():
    destination = ROOT / "docs/ignition_demo"
    destination.mkdir(parents=True, exist_ok=True)
    verification = read_json(OUTPUT / "verification.json")
    freeze = read_json(OUTPUT / "freeze.json")
    cache = read_json(OUTPUT / "cache_verification.json")
    training = read_json(OUTPUT / "training.json")
    policy = read_json(OUTPUT / "alert_policy.json")
    results = {str(year): read_json(OUTPUT / f"results_{year}.json") for year in (2018, 2019)}
    original = read_json(ROOT / "docs/modeling/final_test.json")
    index = policy["default_index"]
    selected = results["2019"]["thresholds"][index]
    evidence = {"reconstruction": verification, "source_sha256": freeze["source_sha256"],
                "weather_sha256": cache["weather_checksum"], "model_sha256": freeze["system_sha256"],
                "cache_sha256": cache["cache_sha256"], "frozen_at_utc": freeze["frozen_at_utc"],
                "rows": cache["rows"], "dates": cache["dates"], "cells": cache["cells"],
                "training_rows": training["n_rows"], "cache_checks": cache["checks"],
                "python": freeze["python"], "packages": freeze["packages"],
                "policy": policy, "results": results}
    write_json(destination / "reconstruction_evidence.json", evidence)
    table = "\n".join(f"| {label} | {original[key]:.12f} | {results['2019'][key]:.12f} | {verification['metric_differences'][key]:.3g} |"
                       for key, label in [("average_precision", "Average precision"), ("roc_auc", "ROC-AUC"),
                                          ("brier_score", "Brier score"), ("log_loss", "Log loss")])
    report = f"""# Ontario Ignition Atlas: capstone implementation report

## Result

The project now includes a complete local historical ignition demonstration:
a reconstructed trained model, date-based prediction service, interactive
Ontario risk grid, selectable alert cutoffs, full-day exports and learning
materials. It supports all 184 dates from May 1 through October 31, 2019,
with 9,673 cells per date. This report supplements the original completed
model comparison in `docs/modeling/final_report.md`.

## Prediction problem and inputs

The target is at least one recorded wildfire ignition in an existing 10 km
Ontario Fire Region cell during one local calendar day. The original full
panel contains 17,798,320 rows across 2010–2019. The 36 approved inputs describe
calendar/solar conditions, static terrain, prior-day CWFIS weather/FWI and
strictly earlier ignition history. Dates, identifiers and outcome labels are
excluded from the model matrix. Native missing values and the explicit
history-censor indicator preserve distinct source-coverage states.

The corrected cache fixes the original station-selection and unsorted-date
join problems. Daily weather is based on t−1, and seven-day rainfall requires
all seven completed dates. Historical archive publication times remain unknown.

## Reconstruction and separation from the original experiment

The original saved model bytes were absent locally. We recovered the exact
audited CSV from the supplied gzip file, verified its checksum and the pinned
weather archive, then rebuilt the corrected cache with the existing builder.
An independent scan checked the complete daily grid, date ordering, label and
quality consistency, and all annual counts against the published audit.

Only the selected HGB configuration was refitted, on {training['n_rows']:,}
rows from 2010–2016: 40 iterations, learning rate 0.1, 15 leaf nodes,
minimum leaf size 100, L2 regularisation 1.0, no class weighting, seed 385,
and no internal random early stopping. The recorded calibration decision
retains raw scores. The model and policy were frozen before 2019 evaluation.
Original training code and published experiment records were preserved.

| Measure | Original published 2019 | Reconstructed 2019 | Difference |
| --- | ---: | ---: | ---: |
{table}

Reconstruction status: **{verification['status']}**. All eight frozen-cutoff
confusion tables also match. Reloaded predictions agree within absolute
tolerance 1e-14. Matching numerical results establish this reconstruction's
agreement with the reference evaluation; the model was not recovered as the
original byte-for-byte artifact.

The 2019 prevalence baseline is {original['prevalence']:.9f}, compared with AP
{results['2019']['average_precision']:.9f}. ROC-AUC measures ranking and must
not be presented as the percentage of correct alerts.

## Prediction service and interface

A Python HTTP server binds to 127.0.0.1. It verifies model and cache
fingerprints, loads the trained pipeline once, and reads each requested day's
inputs from memory-mapped files. It explicitly reorders the daily cache rows
to match the map grid and caches recently requested days.

The browser uses plain JavaScript and a canvas. The map includes the actual
study grid and a simplified Ontario fire-region boundary in EPSG:3978. Its
fixed score colours come from 2018 cutoffs. Date controls, panning/zooming,
cell inspection, a keyboard-accessible ranked table, observed-ignition and
alert-only overlays, and full-precision CSV downloads support exploration.
Observed labels remain separate from model inputs. Missing weather and
censored fire history remain explicit in cell details.

The endpoints are `/api/metadata`, `/api/grid`, `/api/predictions`, `/api/cell`
and `/api/download`. Dates use America/Toronto local calendar dates, invalid
inputs receive clear errors, and missing numeric values use JSON null.

## Alert policy and its consequences

The demonstration policy maximises F2 among the eight existing cutoffs using
2018 validation counts only. F2 is `5 TP / (5 TP + 4 FN + FP)` and gives recall
more weight than precision. Its cutoff is **{policy['threshold']:.17g}**
({100*policy['threshold']:.4f}% as a displayed probability). Scores equal to
the cutoff are included. Higher cutoffs win any exact F2 ties.

This policy is a learning default, not an operational optimum. On 2018 it
produced approximately 48.37 alerts per day, 1.44% precision and 10.24% recall.
The unchanged rule gives the following reconstructed 2019 results:

| Outcome | Cell-days |
| --- | ---: |
| Correct alerts | {selected['true_positive']:,} |
| False alerts | {selected['false_positive']:,} |
| Missed ignitions | {selected['false_negative']:,} |
| Correct non-alerts | {selected['true_negative']:,} |

Precision is {100*selected['precision']:.4f}%, recall {100*selected['recall']:.4f}%,
and alert volume {selected['alerts']/184:.2f} cells per day. These weak absolute
alert results remain visible alongside the improvement in ranking. Users may
compare other frozen cutoffs; their selections do not modify the fitted model
or the recorded default policy.

## Validation and reproduction

Compact source/model/cache fingerprints, numerical results and reconstruction
checks are in `reconstruction_evidence.json`. The large binary artifacts stay
under the ignored reconstruction/cache directories. Setup, launch commands
and API details are in `ignition_demo/README.md`. The small-fixture regression
suite and real-artifact checks verify policy arithmetic, date/schema handling,
cache alignment, score persistence, missingness and CSV precision.

Browser verification covers date changes and boundaries, 36-input inspection,
selection retention, cutoff changes, observed/alert-only overlays, zoom/reset,
ranking filters, downloads, invalid API dates and widths of 1440, 1024 and
390 pixels. The verification summary records the executed results separately.

## Limits and future development

This remains a retrospective hindcast on a frozen grid whose edge selection
uses study-period events. Archive publication and revision times are unknown.
Terrain is a retrospective static approximation, history starts in 2010,
spatial generalisation and date-dependent uncertainty remain untested, and
false alerts dominate at the demonstrated cutoffs. The interface cannot
establish current conditions or provide emergency guidance.

Live forecasting would require an issue-time-available current data pipeline,
an appropriate current grid and model evaluation, temporal and spatial
validation, monitoring of coverage and score drift, and an alert policy tied
to actual response capacity and error costs. Fire spread is a separate
prediction problem and does not supply ignition predictors.
"""
    (destination / "report.md").write_text(report, encoding="utf-8")
    print(f"Published report and compact evidence to {destination}")


if __name__ == "__main__":
    publish()
