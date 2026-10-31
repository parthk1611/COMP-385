# Professor and class demonstration

Prepared October 31, 2026. Assumption: **10 minutes, six slides and a local live walkthrough**. Adjust after the presentation duration/rubric is confirmed. The working prototype already exists; the first new work completed here is a missed-fire audit and an executable model-inference example.

## Main message

“Our research prototype estimates recorded fire-start risk on a 10 km Ontario grid and separately reconstructs incident spread at 90 m. We built a versioned data pipeline, compared four ignition model families, calibrated probabilities, tested interfaces and investigated failures. Current results support a research demonstration; live warning capability and forecast skill are not established.”

The four ignition families are historical fire rate, logistic regression, histogram gradient boosting and LightGBM. Existing calibrated LightGBM bundles remain the application defaults. The spread module is an empirical FBP-inspired simulator, not a fifth ignition classifier. There is no LLM or paid AI inference API.

## Recommended ten-minute order

| Time | Slide/action | What to say or demonstrate |
|---|---|---|
| 0:00–0:45 | 1: Problem and scope | A grid-cell/day risk estimate and incident spread answer different questions. State 10 km versus 90 m and historical research scope. |
| 0:45–1:45 | 2: Architecture | Sources → time/geometry/quality checks → offline fitting/simulation → stored outputs → Python API/browser. Name labels, weather and landscape inputs. Keep the two study contracts separate. |
| 1:45–2:45 | 3: Models and evidence | Four families; later-year and geographic evaluation; separate calibration. Explain recall at a fixed review budget and AP for rare events. |
| 2:45–3:30 | Terminal: actual inference | Run the command below. It executes the saved spatial development model on a known 2017 feature row now, without passing the target as an input. The expected calibrated result is about 0.3417%. |
| 3:30–5:45 | 4: Browser ignition | Open the 2019 view, select a cell on May 1, inspect details, export CSV. Briefly show the separate 2025 view. Describe browser maps as saved evaluations. |
| 5:45–7:00 | Browser spread | Select a supported incident, replay observations and move the first-six-hours slider. Call it final-perimeter-assisted reconstruction; the displayed horizons are not validated forecasts. |
| 7:00–7:30 | Browser live readiness | Show the explicit unavailable result. Explain why qualified historical inference does not automatically qualify a live forecast. |
| 7:30–9:00 | 5: Findings | At equal capacity, the temporal development reference found 64 of 736 positive cell-days; denser negative sampling found 56. Keep the reference. Explain the geographic audit and its limits. |
| 9:00–10:00 | 6: Next milestone | Version the wildfire-only label policy, test weather-history features and reserve genuinely new evaluation data before claiming improved generalization. Invite questions. |

For a five-minute slot: use slides 1–3 for 90 seconds, show one CLI prediction plus one map/cell/export for 90 seconds, spread for 45 seconds, and findings/next step for 75 seconds. Skip the second study and detailed live-readiness walkthrough; still state both limitations.

## Prepare this Mac

Full runtime workspace:

```text
/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE
```

The local server was started on port 8768 during preparation. First open http://127.0.0.1:8768/ . If it is no longer running, use a terminal:

```sh
cd /Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE
.venv/bin/python -m scripts.capstone_app serve --port 8768
```

Leave that terminal open. Stop with Ctrl+C when the demonstration is finished. Do not launch a second copy on the same port.

Open the six-slide PPTX, browser and a second terminal before class. Keep the model-refinement report and audit report as question-and-answer backups. No training or data download should run during the presentation.

## Actual inference command

In the second terminal:

```sh
cd /Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/github_iteration_1/prototype_iteration_1
../../.venv/bin/python -m scripts.demo_model_inference --workspace ../..
```

Expected stable fields:

```text
mode: retrospective development inference; not a current forecast
cell: ofr10km_470000_40000
date: 2017-08-09
features_passed_to_model: 31
target_passed_to_model: false
probability_percent: about 0.3417119
recorded_start: true
```

The timing field varies. It measures scoring only, excluding data/model loading. Do not present it as whole-application latency. The CLI uses an inner-spatial DEVELOPMENT bundle; the 2019 browser map uses a different frozen temporal bundle. Their probabilities are not interchangeable.

Suggested narration: “This executes predict_proba using a saved model and an archived feature row. The observed start is shown only for comparison. This case had positive risk but ranked 14th when the daily review budget was 13, so it was missed by the top-1% policy.”

This command needs the full local `ignition_weather_v2_development/validation.parquet`, its manifest, and the pinned development model under `ignition_refinement_2026-10-31`. Those are outside Git and are not supplied by a fresh clone. Model/input hashes are checked before scoring. The script restricts demonstration inputs to exposed 2017 data.

## Browser sequence and exact examples

1. Open **Historical ignition · 2019**. Use **2019-05-01**, click a cell and choose **Cell details and provenance**. First-day factor explanations are available; on later dates the app explicitly reports unavailable factors. Factors describe raw model log-odds contributions, not causal effects or contributions to calibrated probability.
2. Choose **Export selected date · CSV**, then optionally **GeoJSON**. A historical date export contains 9,673 grid rows. Demonstrate that a download exists and show a few rows; do not read the whole file on screen.
3. Optional exact browser API check for the cell `ofr10km_-10000_100000`:
   `http://127.0.0.1:8768/api/cell-details?study=historical&date=2019-05-01&grid_id=ofr10km_-10000_100000`
   Saved probability: 0.0017897933, or about **0.1790%**. This is a negative-label example, not a claimed successful fire detection.
4. Briefly open **Selected sources · 2025**, using **2025-09-01**. It is a separate population/model/source contract with 9,648 eligible grid cells. The same example cell has a saved probability of 0.0022899407, or about **0.2290%**. This is not a direct comparison of model quality across populations.
5. Open **Corrected spread reconstruction**. Use the incident dropdown, retain one supported case, choose **Replay between satellite passes**, and move time forward. Then choose **First 6 hours from ignition**. Its 0–200 slider maps to 0–6 hours: roughly 33≈1 hour, 100=3 hours, 200=6 hours. These are saved reconstruction displays, not a fresh simulation server call. Do not promise a basemap without network access; the embedded reconstruction/fuel view is the scientific content.
6. Open **Live readiness**. The unavailable response is expected. The API returns HTTP 503 with a null probability; null does not mean zero risk. No current wildfire warning is issued.

If no convenient map cell is selected during rehearsal, keep the exact API URL above open as a backup. UI clicks and animations still require a visual rehearsal; passing an HTTP route is not the same as confirming an interaction.

## Results worth presenting

| Evidence | Result and correct interpretation |
|---|---|
| Automated regression suite | 158 tests passed in the existing Mac environment. This is software evidence, not forecast accuracy. |
| Fresh server/API preflight | 14 checks passed: pages, scores, details, exports, invalid input and unavailable live output. HTTP validation is not a fresh visual click-through. |
| Temporal 2017 development | Reference AP 0.00434155; ROC AUC 0.866279; recall 8.70% (64/736) at 1% daily capacity. Candidate AP 0.00445058 but recall 7.61% (56/736), so no promotion. Both used 17,848 review slots. |
| Geographic 2017 development audit | 0/92 positives selected at 1% capacity. All 92 had declared weather support; no internal grid/label/date mismatch was found. This motivates model refinement. |
| Small-capacity context | Uniform random review at the same capacity expects about 0.95 hits and has about a 38.45% chance of zero, under the stated sampling assumptions. This is context, not a model significance test. |
| Preservation | Earlier final model/evaluation artifacts remain unchanged. These new checks use exposed development data and are not a new final test. |

The chart is a development comparison, not the frozen 2019 final evaluation. Do not call the 2017 results “accuracy,” and do not combine the 2019 and 2025 study populations. The spread refinement also did not justify replacement: its overlap gain interval included zero and recall fell. Keep current settings and qualify its reconstruction scope.

## What is ready and what remains

Ready: six-slide editable deck with notes, executable historical inference example, tested local API, existing dashboard, recorded evidence, dated screenshot backups, audit and a registered next-feature design.

Still required before presenting:

- [ ] Open the PPTX in the actual presentation application and test the projector/text size.
- [ ] Visually rehearse the map selection, date changes, details, export and spread controls on this Mac.
- [ ] Time the full talk and practice the switch between slides, terminal and browser.
- [ ] Confirm the real duration/rubric and divide speaking roles if this is a team presentation.

Browser control was disabled in Work settings during this preparation, so a new automated visual rehearsal could not be completed. The deck was structurally validated and all six exported final slides were inspected; opening it in native PowerPoint was not verified. Current screenshots in the backup folder are explicitly from **October 16, 2026**, not a new capture. A video recording and an offline visual rehearsal were not made.

Modelling work remains after the demo: implement the newly registered label/feature experiment, acquire/reserve fresh evaluation data, and qualify live weather and spread forecast horizons. These are not prerequisites for honestly demonstrating the existing research prototype. New frontend work is not the current priority.

## What I need from you

Only the presentation duration and any professor rubric/specific instructions are needed to tailor this package. The current 10-minute version is usable for rehearsal now. You can complete the manual visual rehearsal yourself, or enable browser control in Work settings for a fresh automated pass. No additional dataset/provider credentials are needed for this saved-data demonstration on the current Mac.

## Questions you may be asked

**Why 10 km?** It is the agreed common ignition data/model contract. Finer 2.5 km work was a separate pilot; finer cells do not automatically add reliable observations. The 90 m spread grid serves a different incident-scale task.

**Why LightGBM?** It is the existing calibrated application choice after model comparisons. Recent candidates did not pass all recall/AP/calibration safeguards. It is not established as universally best.

**Why not report only accuracy?** Positive cell-days are rare. A system predicting no starts can appear highly accurate. We examine AP, capacity recall/precision, probability losses and calibration, plus temporal/geographic performance.

**Does 0/92 mean zero risk everywhere?** No. It means no held positive made the daily top-1% review set. The best missed positive ranked 14th with 13 slots. The sample and small budget require cautious interpretation.

**Is this live?** The browser serves archived evaluations and saved spread reconstructions. The terminal recomputes a model score now on archived inputs. Operational live forecasting remains unqualified.

**Does the simulator predict a fire six hours ahead?** The viewer displays retrospective, final-perimeter-assisted reconstruction. Its one-, three- and six-hour controls do not establish validated future prediction.

**How do you prevent leakage?** Separate issue-day cutoffs, past-only histories, training-only fitted transforms and calibration partitions. Final perimeter data stays in the reconstruction path, not ignition predictors. Modern archive publication timing is still a limitation.

**What is next?** Version the prescribed-burn exclusion policy, test trailing weather features under the same pre-day cutoff, compare against a matching reference, and reserve genuinely untouched evaluation data. See the audit's registration draft.

## Code and diagrams to show if asked

- `prototype_iteration_1/scripts/demo_model_inference.py`: actual model invocation and input/target separation.
- `prototype_iteration_1/scripts/missed_fire_audit.py`: grid/label/time reconciliation and capacity diagnostics.
- `prototype_iteration_1/scripts/capstone_app.py`: local serving, stored scores, details and exports.
- `prototype_iteration_1/scripts/model_refinement.py`: temporal/geographic experiment protocol.
- `prototype_iteration_1/team_repository/capability_2_fire_spread/scripts`: separate spread methods.
- Existing [Lucid architecture/use-case/data-flow diagrams](https://lucid.app/lucidchart/24bb58c8-fb97-479c-a0a8-9434caf9e283/edit); local exports are under `prototype_iteration_1/docs/diagrams/lucid`. The new deck includes an editable simplified architecture flow.

## Backup and portability

`backup/` holds three dated screenshot copies and their provenance, the recorded inference JSON and one historical date export. If the UI fails, label the screenshot date and use these examples; do not imply a successful live interaction. `evidence/http_preflight.json` holds the fresh endpoint evidence.

The authoritative local output is in `CAPSTONE/reports/class_demo_2026-10-31/output`. A compact copy is tracked under `github_iteration_1/prototype_iteration_1/reports/class_demo_2026-10-31`. The Git folder alone does not restore large runtime panels or saved models. The original code submission ZIP supplies the old saved-map runtime; the new CLI additionally needs the development files specified above. This preparation is not a clean-machine installation certification.
