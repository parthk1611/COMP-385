# Presenter handoff — Monday November 2, 2026

Five presenters, **120 seconds each**, ten minutes total. Q&A follows separately for five minutes. These are proposed demonstration responsibilities assigned for this presentation; they do not establish original code authorship. Each person must understand the actual module and accurately describe their own contribution.

| Presenter | Clock | Operate and explain | Handoff sentence |
| --- | --- | --- | --- |
| Parth | 0:00–0:45, then 8:45–10:00 | Introduce the problem on slide 1. At the end run `./RUN_DEMO.sh research`, explain slide 5's actual model comparison and completed lightning experiments | Opening: “Harsh will show how we check the input data.” Closing: “We retained the existing models; the next research step audits dated fuel/access inputs and new evaluation evidence.” |
| Harsh | 0:45–2:45 | Slide 2, `./RUN_DEMO.sh data`; show the data reader, time/key checks and predictor contract | “These are the checked inputs. Rishi will run the saved ignition model.” |
| Rishi | 2:45–4:45 | Slide 3, `./RUN_DEMO.sh ignition`; point to `predict_proba`/calibration, show one historical cell/detail/export | “This was a score on archived inputs. Manav will show the separate spread reconstruction.” |
| Manav | 4:45–6:45 | Slide 4, `./RUN_DEMO.sh spread`; show the reconstruction decoder and 1/3/6-hour area outputs, then spread controls | “These are historical reconstructions. Jasdish will show the reported-fire view and why live scoring stays unavailable.” |
| Jasdish | 6:45–8:45 | Keep slide 4 available, `./RUN_DEMO.sh workflow`; show `read_snapshot`, local notices and live HTTP 503/null | “The source connections work, but forecasting is not qualified. Parth will explain the measured results and next experiment.” |

Time accounting: Parth 45 + 75 = 120 seconds; each other presenter 120 seconds. Handoffs and switching windows are inside these slots. Do not transfer an overrun to another member. At 20 seconds remaining, finish the current output and use the handoff sentence. If a UI interaction takes more than 15 seconds, move to the exact API/recorded backup in the guide.

## Code anchors to prepare

- Harsh: `source/presentation_steps.py::show_data` and `github_iteration_1/prototype_iteration_1/scripts/demo_model_inference.py` input selection; source contracts in `data/processed/ignition_weather_v2_development/predictor_contract.json`.
- Rishi: `prototype_iteration_1/scripts/demo_model_inference.py::run`, `ignition_comparison.py::predict_bundle`, `week5_ignition.py::apply_calibration`.
- Manav: `prototype_iteration_1/scripts/live_workflow.py::reconstruction_footprint`; simulator implementation in `team_repository/capability_2_fire_spread/scripts`. Be explicit that the demonstration decodes saved arrival times, rather than running a prospective simulation.
- Jasdish: `prototype_iteration_1/scripts/live_workflow.py::read_snapshot`, `capstone_app.py::live_readiness_response`, `research_alerts.py::save_notices`.
- Parth: `source/presentation_steps.py::show_research`, the saved `geographic_transfer_2026-11-02/results.json` and `lightning_development_2026-11-02/results.json`, `prototype_iteration_1/scripts/lightning_pilot.py::completed_window` and `density_summary`.

`prototype_iteration_1` above is inside `CAPSTONE/github_iteration_1`. This package's `code/presentation_steps.py` is the copied read-only helper. A shared module is split by responsibility: Harsh covers input validation and Rishi covers inference; Manav covers reconstruction geometry and Jasdish covers source freshness/qualification. Their 120-second slots are equal, and both must operate the assigned code. If the team changes shared-module assignments, split that module's allotted time equally between its two presenters.

## Team acceptance and rehearsal — complete together

| Presenter | Can explain code and own contribution | Ran assigned command | Rehearsed within 120 seconds | Attending |
| --- | --- | --- | --- | --- |
| Parth | Pending | Pending | Pending | Unconfirmed |
| Harsh | Pending | Pending | Pending | Unconfirmed |
| Rishi | Pending | Pending | Pending | Unconfirmed |
| Manav | Pending | Pending | Pending | Unconfirmed |
| Jasdish | Pending | Pending | Pending | Unconfirmed |

The automated command checks in `evidence/` were performed during package preparation; they do not fill in this team rehearsal table. Each presenter should identify a concrete line or function they can discuss and state original authorship truthfully. No team attendance or rehearsal has been confirmed.

Professor Mayy's notice requires all members to illustrate/run code, equal presentation time, attendance at peers' demonstrations and rehearsal. It states that absent members lose the presentation grade. Agree on one laptop, a keyboard handoff order, projector setup and a timer before class. Attend the other teams' demonstrations.
