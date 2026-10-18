# End-user use cases v1

Prepared October 15, 2026. Roles describe application interactions; this document does not reintroduce team administration or a stakeholder register. Requirements are defined in [the SRS](system_requirements.md).

## System use-case diagram

Parentheses denote use cases; each name begins with a verb. The boundary encloses the proposed Ontario wildfire application. Links indicate participation, not execution order.

```text
                           +------------------------------------------------+
                           | Ontario wildfire application                   |
                           |                                                |
  Analyst -----------------+-- (Select historical date and area)             |
     |                     +-- (Predict daily ignition risk)      UC-01      |
     |                     +-- (Explain a cell prediction)        UC-02      |
     |                     +-- (Simulate an existing fire)         UC-03      |
     |                     +-- (Compare historical replay)         UC-04      |
     +---------------------+-- (Export selected results)                     |
                           |                                                |
  Developer/operator ------+-- (Build and validate input data)                |
     |                     +-- (Train and evaluate candidate models)         |
     +---------------------+-- (Load a versioned model for scoring)           |
                           +------------------------------------------------+

  Weather services and source archives support the input-building use case.
  The deployed scoring model and spread engine are internal components.
  UC-02 requires an existing successful UC-01 prediction.
```

The complete templates below cover AI-related user actions. Data building and export remain visible in the diagram but do not need additional AI templates under the supplied course instructions.

## UC-01 — Predict daily ignition risk

| Field | Description |
| --- | --- |
| Description | The analyst requests a map of recorded-new-start probabilities for eligible 10 km cells on a supported historical date. |
| Primary actor | Analyst |
| Goal in context | Identify which cells the evaluated model ranks as higher risk and inspect input quality. |
| Trigger | Select date/area and press Predict. |
| Preconditions | A compatible evaluated model, pinned feature contract, eligible inputs and reserved evaluation policy exist. Historical mode is identified. |
| Priority / channel | High / web interface |
| Success postcondition | Versioned probabilities are displayed for the requested keys with quality information. |
| Requirements | FR-01–03, FR-05; NFR-01–06, NFR-08–09. |

| Step | Actor | System |
| --- | --- | --- |
| 1 | Select historical date and area. | Offer supported dates/areas and identify the 10 km unit. |
| 2 | Press Predict. | Validate request, model compatibility and input availability; show processing state. |
| 3 | | Load/build eligible features using the issue-time contract and trained preprocessing. |
| 4 | | Score requested cells; attach model/data/threshold versions and quality flags. |
| 5 | Inspect the map or choose a cell. | Display probabilities and missing-output states; offer UC-02/export. |

Exceptions: 2.1 unsupported date/area -> explain the supported range; 2.2 unavailable model/contract mismatch -> stop with a specific error; 3.1 missing required inputs -> distinguish incomplete scoring from low probability; 4.1 timeout -> identify failure and allow retry without presenting stale output as fresh.

## UC-02 — Explain a cell prediction

| Field | Description |
| --- | --- |
| Description | Show the factors and quality indicators behind a selected ignition probability. |
| Primary actor | Analyst |
| Goal in context | Understand the model's prediction and whether missing inputs affect interpretation. |
| Trigger | Click a scored cell and select Explain. |
| Preconditions | UC-01 succeeded; the selected prediction and compatible model/explanation method are available. |
| Priority / channel | High / web interface |
| Success postcondition | The cell details match the selected model/date and retain source/quality information. |
| Requirements | FR-04–06, FR-13; NFR-03, NFR-08–10. |

| Step | Actor | System |
| --- | --- | --- |
| 1 | Select a scored cell. | Retrieve the exact key, score and model version. |
| 2 | Select Explain. | Compute/load the model-compatible explanation and validate feature alignment. |
| 3 | Inspect the result. | Show contributing features, values/units, missingness, explanation method and calibration/quality information. |
| 4 | Export details or return to the map. | Export the selected record or retain current map selection. |

Exceptions: 1.1 cell has no score -> explain why; 2.1 explanation unavailable or incompatible -> retain the probability but explicitly state explanation unavailable; 2.2 computation failure -> show failure, never invented factor rankings. Contributions describe model behaviour, not established causation.

## UC-03 — Simulate an existing fire

| Field | Description |
| --- | --- |
| Description | Simulate progression from a known fire state using the separate spread engine and compatible weather/landscape inputs. |
| Primary actor | Analyst |
| Goal in context | Explore projected progression and distinguish it from observed fire detections. |
| Trigger | Choose a supported incident or initial location/mask, start time and horizon; press Simulate. |
| Preconditions | Eligible initial state, fuel/terrain, weather and required moisture-code state exist. Input mode/vintage is explicit. |
| Priority / channel | High / web interface |
| Success postcondition | Completed time-labelled simulations are displayed with source and validation limits. |
| Requirements | FR-07–08, FR-10; NFR-01–03, NFR-07–09. |

| Step | Actor | System |
| --- | --- | --- |
| 1 | Choose incident or enter location/mask and time. | Check study coverage, coordinates, non-burnable areas and initial state. |
| 2 | Select 1, 3 or 6 hours and press Simulate. | Check weather horizon, units, fuel support, timing and state initialization. |
| 3 | | Label historical reconstruction/fixed-landscape/forecast mode correctly and run the versioned 90 m engine. |
| 4 | Inspect the timeline. | Display simulated extents, elapsed times and whether matching validation observations exist. |
| 5 | Export or open comparison. | Retain run inputs, source versions and simulator settings; offer UC-04 when observations are suitable. |

Exceptions: 1.1 invalid/outside/non-burnable initial state -> reject; 2.1 insufficient weather or FWI state -> identify missing input; 3.1 timeout/failure -> return a named failure; 3.2 final-perimeter-assisted input -> label reconstruction and prevent it entering forecast-skill claims; 4.1 no matching 1-/3-hour observations -> show simulation without claiming validation. The reproduced barrier defect remains implementation work, not a completed use case.

## UC-04 — Compare historical replay

| Field | Description |
| --- | --- |
| Description | Compare a historical simulated progression with eligible satellite observations and a simple baseline under one scoring definition. |
| Primary actor | Analyst |
| Goal in context | Judge whether the spread model adds value beyond the baseline and understand observation gaps. |
| Trigger | Select a scoreable incident/observation interval and press Compare. |
| Preconditions | Timestamped matched observations, completed simulation and baseline outputs with common support exist; evaluation partition is known. |
| Priority / channel | High / web interface |
| Success postcondition | Comparison and metrics identify incident, target, interval, partition, baseline and coverage. |
| Requirements | FR-09–10, FR-12; NFR-03–05, NFR-08. |

| Step | Actor | System |
| --- | --- | --- |
| 1 | Select incident and interval. | List supported observed intervals, not arbitrary hourly truth. |
| 2 | Press Compare. | Verify target/mask/time alignment and permitted calibration/holdout role. |
| 3 | | Score candidate and baseline on identical targets; separate reconstruction-assisted runs. |
| 4 | Inspect reached/missed observations and metrics. | Show scores, coverage and baseline difference, including negative results. |
| 5 | Export comparison. | Include settings, source versions, observations and metric definitions. |

Exceptions: 1.1 no suitable observation -> mark unscoreable; 2.1 inconsistent target/mask/time -> stop comparison; 3.1 undefined metric -> report undefined rather than zero or a fabricated percentage. Repeated tuning on final-test incidents requires a new future evaluation set and cannot remain described as an untouched final test.
