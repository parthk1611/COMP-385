# Prototype presentation — Monday November 2, 2026

**10-minute demonstration, then 5-minute Q&A. Five slides total, including the introduction.** PowerPoint is optional. The live code and prototype are the main demonstration. The schedule below gives Parth, Harsh, Rishi, Manav and Jasdish exactly 120 seconds each. Roles are proposed presentation assignments, not claims of original authorship.

## Begin with the problem in plain language

“Ontario has many locations to review for wildfire risk. We are testing whether past fire records, weather and landscape data can help rank 10 km cells for a recorded fire start on a day. We also have a separate 90 m research simulator for the spread of a known historical fire. We will run code and show actual outputs. Our current prototype does not issue operational fire warnings.”

Explain a **cell-day** as one grid square on one date. Explain **1% review capacity** as inspecting the highest-ranked 1% of eligible cells each day. A high probability and selection into that small review list are different things. The ignition classifier estimates recorded-start likelihood; it does not infer whether lightning or a person caused a fire. Source-reported cause is a separate attribute.

## Exact ten-minute order

Switching screens and handing over the keyboard are included. Keep a visible timer. Do not let one member's overrun consume the next member's slot. Each person opens the indicated source function and runs their assigned command. Stop at 10:00 and begin Q&A.

| Clock | Presenter | Live action and explanation |
| --- | --- | --- |
| 0:00–0:45 | Parth | Slide 1; introduce the problem, cell-day output and separate spread task using the paragraph above. Hand over to Harsh. |
| 0:45–1:15 | Harsh | Slide 2; identify recorded-start labels, dated weather, terrain and landscape inputs. Explain the checks in the architecture. |
| 1:15–1:45 | Harsh | Open `show_data` in `code/presentation_steps.py`; show the exact grid/date filter and target exclusion. |
| 1:45–2:20 | Harsh | Run `./RUN_DEMO.sh data`. Read the 10 km grid key, midnight issue, 31 allowed spatial predictors and `target_is_predictor: false`. |
| 2:20–2:45 | Harsh | Explain why future weather, final fire size and final perimeters are excluded from ignition inputs. Hand over. |
| 2:45–3:05 | Rishi | Slide 3; name historical fire rate, logistic regression, histogram gradient boosting and LightGBM. Explain separate temporal/geographic evaluation and calibration. |
| 3:05–3:20 | Rishi | Show `demo_model_inference.py::run`, specifically the feature selection and `predict_bundle`/calibration calls. |
| 3:20–3:45 | Rishi | Run `./RUN_DEMO.sh ignition`. Explain the actual historical inference: 0.3417119%, 31 inputs, target excluded. |
| 3:45–4:35 | Rishi | In the browser show the stored 2019 map, one first-day cell detail and CSV export. Use the exact detail API as fallback. |
| 4:35–4:45 | Rishi | State that the CLI development model and browser temporal model are different bundles, then hand over. |
| 4:45–5:05 | Manav | Slide 4; explain why incident spread is a separate 90 m task. |
| 5:05–5:30 | Manav | Show `live_workflow.py::reconstruction_footprint`: saved arrival times, horizon filtering, raster-to-polygon area. |
| 5:30–5:55 | Manav | Run `./RUN_DEMO.sh spread`. Read the 1/3/6-hour reconstructed areas for `2023_COC38`. |
| 5:55–6:35 | Manav | Open the spread viewer, select the same supported incident and move between the recorded replay and 1/3/6-hour controls. |
| 6:35–6:45 | Manav | State “final-perimeter-assisted historical reconstruction; future forecast skill is unproven”, then hand over. |
| 6:45–7:00 | Jasdish | Introduce the reported-fire/weather view as a separate observation pipeline. |
| 7:00–7:20 | Jasdish | Show `read_snapshot` and `live_readiness_response`: clock checks and rejection of unqualified live probabilities. |
| 7:20–7:45 | Jasdish | Run `./RUN_DEMO.sh workflow`. Read the source retrieval clock, 9 reported incidents, 12 historical scenarios, 21 local notices, and null live outputs. |
| 7:45–8:20 | Jasdish | Open `/workflow.html`; point out observation versus reconstruction labels, source age, weather context and local-only drafts. |
| 8:20–8:35 | Jasdish | Open `/api/live-ignition` and show expected HTTP 503/null; this is unavailable, not zero risk. |
| 8:35–8:45 | Jasdish | Name missing current perimeter/state/model qualification and hand over. |
| 8:45–9:00 | Parth | Run `./RUN_DEMO.sh research`. This reads both completed development experiments; it does not train or score a new test. |
| 9:00–9:10 | Parth | Show `show_research` and the lightning `completed_window` function. Explain the past-only time cutoff. |
| 9:10–9:35 | Parth | Slide 5 and Geographic performance; reference found 2/92, constrained boosting found 5/92 at 1%. The constrained candidate failed the earlier selection folds; defaults retained. |
| 9:35–9:50 | Parth | Next: historically dated fuel/access data and an untouched evaluation. Lightning features and two model comparisons are complete; universal detection remains unachieved. |
| 9:50–10:00 | Parth | State the remaining live/spread validation limits and invite questions. |

Total: **Parth 45 + 75 = 120 seconds; Harsh/Rishi/Manav/Jasdish 120 seconds each.** See `TEAM_HANDOFF.md` for source anchors and proposed responsibilities. A pair sharing a module must split that module's illustration equally. The main content can be presented without the slides using this same schedule.

## Prepare this Mac before class

Use the original full workspace. A Git-only clone lacks required saved panels/models. Do not install dependencies, train models or download data while presenting.

Terminal 1 (keep it open):

```sh
cd /Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE
.venv/bin/python -m scripts.capstone_app serve --port 8771
```

If port 8771 is already serving this prototype, reuse that process; do not start a duplicate or stop another application. Check `http://127.0.0.1:8771/` first. Ctrl+C stops a server launched in that terminal.

Terminal 2 (presenters share the keyboard in schedule order):

```sh
cd /Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/class_demo_2026-10-31/output
```

The commands below were executed during package preparation. Run each again in the team rehearsal:

```sh
./RUN_DEMO.sh data
./RUN_DEMO.sh ignition
./RUN_DEMO.sh spread
./RUN_DEMO.sh workflow
./RUN_DEMO.sh research
```

`RUN_DEMO.sh` resolves the original workspace and invokes the local Python environment. `code/presentation_steps.py` is a short read-only helper that calls existing project functions. Open the actual implementation beside it. The ignition step calls the existing inference function; other steps inspect real archived inputs, compute footprint areas or read saved research evidence. No step trains, retunes, changes state trust or contacts an external provider.

Have five browser tabs ready: home, exact historical detail API, spread, workflow and live readiness. Open the source functions in the editor and use one command per presenter. Keep the five-slide deck in presentation mode only when explaining a slide.

## Stable outputs and browser actions

| Step | Expected output and interpretation |
| --- | --- |
| Data | `ofr10km_470000_40000`, `2017-08-09`, issue `2017-08-09T04:00:00Z`, 31 allowed spatial predictors; target excluded |
| Ignition | Calibrated probability **0.0034171191**, or **0.3417119%**, recorded start true. This is an exposed legacy 2017 development example, not a current forecast or the new wildfire-only comparison |
| Spread | `2023_COC38`; **1.62 / 4.86 / 17.01 ha** at 1/3/6 hours; `forecast_validated: false`. Code computes areas now from saved reconstruction arrival times |
| Workflow | Captured 9 incidents / 12 historical scenarios / 21 local records; live ignition and spread null. Freshness/remaining weather hours change with the clock |
| Research | Five matched geographic candidates: reference **2/92**, lightning 24h **2/92**, lightning 24h+7d **3/92**, physical logistic **2/92**, constrained boosting **5/92**. Both registered studies retained the reference; **27 fits** total |

Do not describe a console output as proof of an actual team member's prior code authorship. Do not compare the CLI probability to another study's probability as if they were the same model.

In the earlier development audit, the CLI example ranked 14th with 13 daily review slots. It was missed by that top-1% policy; presenting its nonzero probability is not a claim of successful detection.

Browser sequence:

1. Home now opens **Geographic performance**. Show the fixed 1% reference and constrained-model comparison during Parth’s results segment; widening capacity is sensitivity only. For Rishi’s segment choose **Historical ignition · 2019**. Use **2019-05-01** and click one cell. Choose **Cell details and provenance** and export CSV. This date has saved factor explanations; later dates explicitly report unavailable factors. Explain factors as raw log-odds contributions, not causes.
2. Deterministic detail backup: `http://127.0.0.1:8771/api/cell-details?study=historical&date=2019-05-01&grid_id=ofr10km_-10000_100000`. Saved probability is **0.0017897933**, or **0.1790%**, for a negative-label example. A historical daily CSV contains **9,673 rows**.
3. Spread: `http://127.0.0.1:8771/spread.html`. Select the supported `2023_COC38` case using its displayed incident label. Choose the first-six-hour mode; its 0–200 slider maps approximately **33→1 hour, 100→3 hours, 200→6 hours**. The replay and first-six-hour reconstruction modes answer different retrospective questions. They do not run a fresh prospective simulation API.
4. Workflow: `http://127.0.0.1:8771/workflow.html`. The refreshed feed was retrieved **2026-11-02 15:07:12 UTC** (10:07 Toronto); weather uses the November 2 06 UTC run acquired at 15:02 UTC. Read the actual retrieval/freshness label. The feed has points, not verified current perimeters. Districts use a dated 2023 reference. By class, the snapshot/weather context may be stale or expired; that should remain visible. Do not refresh sources during the demo just to remove the label.
5. Live API: `http://127.0.0.1:8771/api/live-ignition`. **HTTP 503 and null are expected.** No source connection or trusted flag can by itself qualify a model. No public alerts are sent.

Skip the separate 2025 model tab in the core ten minutes. It is a different source/population contract with 9,648 eligible cells and is available only if asked. The historical 2019 map, legacy 2017 inference example and latest wildfire-only 2017 comparison must retain their separate study labels.

## Measured results to explain honestly

The updated slide 5 chart compares reference AP **0.0023242605** with constrained-model AP **0.0035090156** on the same exposed 2017 geographic diagnostic. At the fixed daily 1% capacity they find **2/92** and **5/92**, respectively. The constrained model still misses **87/92**. Earlier 2014/2015 folds found reference **0 and 7**, constrained **0 and 4**, so the registered selection rule retained the reference before 2017 scoring. This diagnostic gain does not establish unseen generalization or qualify a replacement. The older **0/92** audit used a different target/refit and remains separate.

Today’s lightning study completed **18 fits**, and the simpler geographic-transfer comparison completed **9 fits**. Lightning features cover **14,238,656 cell-days** in 2010–2017 with zero future-interval violations. The original 30-row pilot matches the full-grid output. At 1%, the two lightning variants find **2/92** and **3/92**; neither passes earlier-fold selection. Old final artifacts and serving defaults remain unchanged. The older weather-history study and its 2/92 versus 2/92 result remain valid as a separate experiment. Station-to-grid observed FWI startup and operational source timing remain unresolved.

The spread simulator has not demonstrated improvement over its baseline overall; supported replay displays are retrospective. No validated 1/3/6-hour future skill or current perimeter prediction is claimed. There is no LLM, paid inference API, cause classifier or public warning delivery in this demonstration.

The latest combined suite passed **212 tests** in this Mac environment. Those are software checks, not model accuracy or field acceptance. Fresh presentation preflight records verify code/HTTP behavior separately. No full team or native PowerPoint/projector rehearsal has been completed by this preparation.

## Five-minute Q&A, 10:00–15:00

Keep slide 5 visible. Answer the question first in about 20–30 seconds, then offer the relevant function or evidence file. Route questions to the assigned module presenter; let another member answer when they have already spoken. A separate five-minute Q&A does not extend the ten-minute demonstration.

| Likely question | Short answer | Suggested first responder |
| --- | --- | --- |
| What does the ignition output mean? | Probability of a recorded start in one 10 km cell on a calendar day, under that study's archived inputs. It does not identify the cause | Rishi |
| Why 10 km instead of 2.5 km? | Ten kilometres is the agreed ignition data/model contract. Finer pixels do not create reliable observations. The 90 m incident spread task is separate | Harsh |
| Which models did you compare? | Historical fire rate, logistic regression, histogram gradient boosting and LightGBM. Calibrated LightGBM bundles remain the existing app defaults; the spread simulator is separate | Rishi |
| Why did a higher AP not replace the model? | At the agreed daily 1% review capacity, the constrained model found 5/92 on the exposed diagnostic but had lower recall on earlier selection folds. The full adoption rule did not pass | Parth |
| Does 2/92 mean zero risk elsewhere? | No. It describes selection into a small review list, not zero predicted risk or guaranteed absence of fire | Parth |
| Is this live forecasting? | Reported-fire/weather collection works, but live model probabilities remain unavailable. Current perimeters, accepted state mapping and exact source/issue-time qualification are incomplete | Jasdish |
| Are those six-hour spread forecasts? | They are final-perimeter-assisted historical reconstructions. The controls do not establish future forecast accuracy | Manav |
| How is future information excluded? | Past-only input windows, training-only transforms, separate calibration and preserved evaluation partitions. Final perimeter/size stays out of ignition predictors; archive receipt timing remains a limitation | Harsh |
| What is new after the earlier demo? | Full development lightning features, 27 model fits, an interactive geographic-results dashboard and refreshed fire/weather observations. No candidate qualified for promotion | Jasdish or Parth |
| What will you do next? | Audit historically dated fuel/access sources and reporting coverage, then register the next development study and obtain an untouched evaluation. Qualify issue-time live inputs before live predictions | Parth |
| Why no accuracy headline? | Fire-positive cell-days are rare; always predicting no fire can look accurate. AP, calibration and recall at a fixed review capacity are more informative | Rishi |
| What did each person contribute? | State the member's actual work and point to the function/commit they can substantiate. The proposed presentation roles alone do not prove original contributions | Each member |

If asked for the exact model/refinement evidence, open `CAPSTONE/reports/geographic_transfer_2026-11-02/results.json` and `CAPSTONE/reports/lightning_development_2026-11-02/results.json`. The full source/access matrix is `CAPSTONE/reports/zero_cost_sources_2026-11-01/README.md`. Existing Lucid diagrams remain available at `https://lucid.app/lucidchart/24bb58c8-fb97-479c-a0a8-9434caf9e283/edit`; do not depend on online Lucid during the ten minutes.

## Rehearsal and fallback

- [ ] All five members accept their proposed roles and can explain their own contribution accurately.
- [ ] Each person opens the assigned function and runs the assigned command on the actual demo Mac.
- [ ] Run the whole sequence with a timer: 10:00 total and exactly 2:00 per person, including keyboard/window handoffs.
- [ ] Open the five-slide PPTX in the actual presentation application and test projector readability and speaker notes.
- [ ] Visually check map selection, date, cell details, CSV download and spread controls. Individual Chrome interaction checks were completed on November 2. The team still needs its timed end-to-end rehearsal and projector check.
- [ ] Rehearse an offline/failed-UI fallback without changing source freshness or model results.
- [ ] Confirm all members' attendance and remain for peers' demonstrations. Professor Mayy's notice says absent members lose the presentation grade.

If a command or UI takes longer than 15 seconds, stop troubleshooting in front of the class. Use the corresponding JSON/text output under `backup/`, say it is recorded evidence, and continue within the same member's slot. Use `backup/ignition_ui.png`, `spread_ui.png` and `live_ui.png` only as dated **October 16** screenshots; their live-status text may describe that older build. They are not fresh captures of today's workflow. `backup/RESULTS.txt` contains the latest small verified outputs, and `backup/model_inference_current.json` is the rerun historical inference. The old backup JSON/CSV provenance remains intact.

If the server is stopped, restart it with the command above before the timed demo. If Python/model assets are missing, use recorded evidence and clearly state the failure; do not improvise a prediction. If PowerPoint fails, use the inspected PNG slide exports and the guide. No internet connection or paid API is required for the saved local code examples. Static inspection found no external `src`/`href` URLs in the two main map/reconstruction pages, but an offline browser rehearsal remains unverified.

## Package and verification boundary

Authoritative folder: `/Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE/reports/class_demo_2026-10-31/output`.

The existing deck has been updated to five slides. Today’s code steps, HTTP checks and browser interaction scope are recorded in `evidence/verification_2026-11-02.json`. The November 1 preflight remains historical. Current slide validation is `evidence/slide_validation_2026-11-02.json`. The presentation and code/evidence snapshot are packaged on `parth/iteration-1-prototype`; dated verification records retain their original pre-publication scope. Large runtime data remains outside the presentation folder and Git. This is not a clean-machine installation certification or proof of completed team rehearsal. Today’s development work completed 27 model fits in separate new experiment directories. Protected final results remain unchanged. No public alert, submission, production deployment or paid service was performed. See `CAPSTONE/reports/demo_readiness_2026-11-02/README.md` for today’s evidence.
