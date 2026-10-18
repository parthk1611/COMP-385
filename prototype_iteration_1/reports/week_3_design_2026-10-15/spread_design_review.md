# Spread design review

Review outcome: accept the module boundary and corrected surface-propagation design for restricted research. Reject operational forecast acceptance. This is a completed design review with explicit restrictions, not evidence that the simulator is ready for emergency use.

| Finding | Evidence in current source | Disposition |
| --- | --- | --- |
| Implemented physics is narrower than the name FBP suggests | fbp_spread.py implements a selected surface ROS/fuel subset, simplified seasonal grass/aspen/mixedwood assumptions and an ellipse. It does not calculate the full set of FBP behaviour outputs. | Call it FBP-inspired; no claim of full canonical equivalence. Existing C-2/ISI reference checks do not validate every fuel and process. |
| Geometry differs from Cell2Fire | simulate_spread.py uses sixteen neighbours and shortest travel time, average endpoint fuel rates, an uphill exponential and calibrated ROS/flank scales. | Describe the actual algorithm. Do not transfer Cell2Fire's published validation to this code. |
| Water could be skipped between endpoints | A full-width one-cell water barrier and a blocked diagonal corner failed new tests before the patch. | Fixed by checking touched intermediate cells/corner contacts, including non-spreading intermediate fuel. No spotting is implied. |
| An explicitly empty active mask restarted the whole edge | The old conditional only applied active when it intersected the edge. | Fixed: a supplied active mask always restricts the edge. Regression test passes. |
| Final perimeter changes predictors | _repair_burn_scar replaces mapped land fuel inside the known final scar using surrounding fuel. | Default off. Reconstruction drivers opt in and label their mode. This repair is forbidden as a forecast input. |
| The domain also uses the final outcome | download_spread_fuel_windows.window_for uses the final perimeter bounding box plus 3 km margin. | Disabling repair alone does not create an outcome-independent forecast. Future forecast domains must be chosen from issue-time information and a declared horizon. |
| Weather timing is retrospective | load_case maps same-date daily BUI/FFMC to hourly rows, fills forward/backward, and can use daily values before their observation time. The optional hourly FFMC re-seeding also uses a fixed 16:00 rule. | Reconstruction only. A causal weather/FWI adapter must preserve observed/available timestamps and trusted state; no future backfill in forecast mode. |
| Travel-time integration is approximate | A move uses rates from its departure hour even if traversal extends across later weather changes. | Document this approximation. A future forecast revision must integrate across hourly boundaries and test missing/out-of-range weather. |
| Unknown fuels and missing terrain are not a validated live-input policy | Unlisted codes do not spread; missing elevation is filled with a case mean. | Preserve unknown/filled flags; a public adapter must distinguish unsupported data from genuine non-fuel. Do not claim this failure policy is implemented for the app. |
| Observation targets are imperfect | VIIRS first-seen 375 m cells and morphological filling approximate active/burned state. Steps are filtered to 6-30 h and at least five new cells. | Report selection/observation masks and unchanged spatial support. Missing detections do not prove unburned land. No 1-/3-hour skill claim. |
| The 1.3 area target is a heuristic | run_spread_replay uses a target based on the 0.77 satellite/perimeter share described in broader EDA. | Audit the heuristic's population before claiming a fully isolated holdout; recompute any future tuning statistic on development incidents only. |
| Old replay scores predate these fixes | Stored v1 scores cover 150 steps from 22 scoreable holdout fires. Overall recall/IoU do not beat even growth. | Preserve as old-code reconstruction evidence. Do not attach them to the corrected revision. |

## Implemented safeguards and test evidence

Four new regression tests failed before modification; the spread suite now passes 27 tests. The patch keeps the existing move directions and adds conservative clearance checks. All touched cells must allow propagation; diagonal corner contacts cannot bypass a barrier. This may change both arrival times and aggregate skill, so a real-fire replay must be recomputed before reporting new performance.

New replay output defaults to `data/processed/simulation_surface_v2`, preserving archived results in `simulation`. Reports declare `surface-barrier-clearance-v2`, reconstruction mode and false forecast-validation status. The viewer exporter requires the matching revision. Its page-only path can still reconstruct an archived page; that is not a new simulator experiment.

## Remaining implementation work

The local ignored raw fuel/terrain windows required by load_case are absent. Therefore no corrected real-fire replay or new viewer was generated. That is a genuine Week 5 validation dependency, not a passed check. Restore/version the inputs, rebuild separate research results, and compare both engines/baselines on the same selected incidents without reusing old scores. An outcome-independent forecasting experiment additionally needs a causal weather bridge, issue-time initial state and domain, eligible fuels, explicit unknown-input handling, and reference/incident validation. Crown transition, spotting, suppression and ensembles remain outside the implemented model.

Sources: current simulator/loader/replay code, the frozen v1 result files, regression outputs in this package, and the government FBP/reference sources linked in the technical design. No external simulator was installed or benchmarked in this review.
