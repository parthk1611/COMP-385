# Ontario wildfire AI capability design

COMP 385 | Week 3 | Reviewed October 16, 2026

## 1. Purpose and design decision

The project answers two different questions. The ignition classifier estimates whether a recorded fire starts in an existing 10 km Ontario Fire Region cell on a local calendar day. The spread simulator estimates how an already burning incident can progress across a separate 90 m landscape. An ignition score is not a fire-front prediction, and a simulated burned cell is not a new ignition.

The AI pattern is supervised predictive analytics with analyst decision support. The ignition target is binary classification. The spread prototype combines empirical rate equations with grid propagation; it is not a trained ignition classifier. No LLM or paid AI API is needed. The optional treatment-prioritization and ensemble work from the literature remains a later research extension.

The accepted Week 3 design is a local, modular research workflow. It supports versioned historical experiments and preserves the later application interfaces. It does not approve operational forecasting, the corrected spread engine's real-fire accuracy, or automatic treatment decisions.

## 2. Data boundary

The initial ignition experiment retains the repository's v1 NFDB/CDEM/CWFIS dataset: 9,673 cells, 1,840 May-October dates during 2010-2019, and 17,798,320 rows. The key is `(grid_id, ignition_date)`. The issue instant is midnight in America/Toronto, with daylight-saving conversion to UTC. Dynamic features use strictly earlier observations or recorded starts. CWFIS uses the previous source calendar day; its archive does not establish an exact historical publication time.

The selected development sources remain Ontario fire points/areas, VIIRS, CDS ERA5-Land, HRDPS, FBP Fuel Types 2024, selected SCANFI v1.2/2020 and MRDEM. They are not silently inserted into the older benchmark. VIIRS is an observation source for spread evaluation, not an ignition predictor. Final size, final perimeter, future detections, labels and identifier/provenance fields are excluded from ignition predictors.

Weather is missing in 52.482010% of the full v1 panel. The experiment retains those rows and quality fields. Logistic regression fits imputation/scaling on its training sample only; the tree candidates use native missing-value handling. The blank days-since-fire field represents censored observed history, not zero elapsed days. A learned imputation used inside a model does not alter raw source values.

The known station-candidate selection issue and label-dependent edge-cell mask remain limitations of this benchmark. Results describe this retained hindcast, not an unbiased claim about all Ontario cells or a replay of information known in real time. Their corrected feature/mask sensitivity studies remain Week 4 preparation work.

## 3. Training architecture

```text
Pinned NFDB + CDEM + CWFIS
          |
          v
Label / historical feature builders [implemented in team_repository]
          |
          v
48-column v1 panel -> frozen role export [materialized snapshot]
          |
          +--> 2018 calibration ------------------ reserved
          +--> 2019 final test ------------------- reserved
          |
          +--> 2010-2015 training + 2016-2017 validation
                        |
                        v
              Verify file / selector hashes and years
                        |
              Common training sample + sampling weights
                        |
            +-----------+-----------+--------------+
            |           |           |              |
      Historical rate Logistic   Histogram      LightGBM
                                  boosting
            +-----------+-----------+--------------+
                        |
                        v
             Full development evaluation
             + inner geographic experiment
                        |
                        v
             Candidate bundles + run records
                        |
             Later: refit / 2018 calibration / freeze
                        |
             Later: one reserved 2019 final score
```

`scripts/ignition_comparison.py` implements the comparison, role checks, training-only transformations, scoring helper, metrics, candidate serialization and run records. The materialized Week 2 partitions exist; a general-purpose partition-export command has not been packaged. Their source/selector/output manifest is therefore part of the experiment input contract.

The comparison includes every training positive and approximately 1% of training negatives, selected by deterministic row-key hash. Inverse sampling weights restore the eligible training population's event fraction in the loss. This controls memory on the 18 GiB Mac; it is not equivalent to fitting every training row. Validation is never downsampled. The experiment report gives actual population/sample counts, settings and results.

There are two separate fitted experiments. Temporal validation uses 36 permitted predictors and all geography. Inner geographic validation uses 31 predictors, excluding every fire-history field, with deterministic 100 km blocks inside the frozen outer spatial-development region and a 20 km centre buffer. It also moves forward in time. Outer geographic test cells do not enter this inner experiment. The separate temporal protocol still uses all cells in its permitted development years. Neither experiment reads 2018 calibration or 2019 test content.

## 4. Daily scoring architecture

```text
Analyst selects date + cells + mode [application planned]
                     |
                     v
Request / capability / source-time checks [adapter planned]
                     |
             Historical feature selection
                     |
             Model + manifest hash verification
                     |
             Exact predictor order and preprocessing
                     |
             predict_bundle [implemented helper]
                     |
             Keyed score + mode + quality metadata
                     |
        Map / cell explanation / export [planned]

Later live path:
Available HRDPS run + trusted recent weather/FWI state
 -> compatible versioned feature adapter -> reviewed live model
 -> same response contract
```

The current saved bundles produce uncalibrated development scores. They must not be presented as validated operational probabilities or assigned unsupported high/medium/low risk categories. The application, model-serving endpoint, explanation service and map remain unimplemented. Model-only scoring timings in the experiment are not web-response or map-load tests.

The historical adapter must require the recorded issue time and source contract. A same-date noon weather value cannot predict a day issued at midnight. Archive availability remains unknown in hindcast mode. Forecast mode must reject unknown or late availability and incomplete weather/FWI state. The existing CDS pilot converter and the spread Open-Meteo workflow have different source and startup contracts; an equal column name does not make their outputs interchangeable.

## 5. Spread architecture

```text
Observed incident state + explicit source/mode metadata
                     |
                     v
Initial-mask / raster / clock / wind checks [adapter planned]
                     |
             load_case [implemented historical loader]
                     |
       Mapped fuel / terrain / archived hourly weather
                     |
       FBP-inspired directional rates + 90 m graph search
                     |
       Arrival minutes / completed horizon masks
                     |
       375 m observation support + comparison scorer
                     |
       Archived replay viewer [existing v1 snapshot]

Reconstruction only:
Final perimeter -> optional fuel repair / outcome-based domain
               -> explicit reconstruction label
               -> excluded from forecast-validation claims
```

The engine keeps sixteen move directions but now checks crossed cells and diagonal corner contacts before propagation. Surface fire cannot jump a one-cell water barrier without an explicit spotting model. An empty active mask no longer restarts the whole burned edge. Final-perimeter fuel repair defaults to off; the historical reconstruction drivers opt in explicitly. New reconstruction reports declare their mode and propagation revision.

The engine is a subset inspired by Canadian FBP, not a complete implementation of FBP or Cell2Fire. The separate spread review records its missing processes, weather-time approximations and outcome-assisted data. One-, three- and six-hour grids can be computed; computation does not validate those horizons. Existing observational scoring is limited to selected gaps of 6-30 hours.

The corrected real-fire replay has not been run because its ignored raw fuel/terrain windows are absent locally. New replay outputs default to a separate revision directory. The exporter rejects old scores for the corrected propagation revision. The stored v1 scores and viewer remain archived evidence for the previous code.

## 6. Components and exchanged contracts

| Component | Actual module or artifact | Input / output | State |
| --- | --- | --- | --- |
| Labels and features | team_repository/scripts/build_cpa_daily_ignition_labels.py; build_ignition_feature_panel.py | Pinned source tables to keyed 48-column historical panel and audit | Implemented |
| Evaluation reservation | Week 2 selectors and ignition_evaluation_v1 manifest/Parquet | Frozen dates/cells and 49-column partitions including spatial role | Materialized; exporter not packaged |
| Comparison and registry | scripts/ignition_comparison.py | Training/validation only to eight fitted bundles, metrics, hashes and environment | Implemented |
| Fitted scoring | predict_bundle in that module | Exactly ordered permitted numeric predictors to probabilities | Implemented helper; no service |
| Calibration and promotion | Defined evaluation procedure | Selected/refitted development model plus 2018 data to calibrated frozen model | Planned |
| Selected CDS transformation | scripts/prepare_selected_weather.py | Five hourly variables to explicit-noon rain/RH/wind/research-FWI pilot table | Implemented pilot; no province join |
| Spread loading/propagation | simulate_spread.py; fbp_spread.py | FireCase, mask, start, horizon, settings to arrival-minute raster | Implemented; research restrictions |
| Spread replay/scoring | run_spread_replay.py | Incident observations to development tuning and separate replay results | Implemented; corrected full replay not run |
| Viewer export | export_spread_viewer_data.py | Matching-revision replay results to static viewer | Implemented exporter; old saved viewer archived |
| Analyst/live adapters | interfaces.schema.json and examples | Requests, provenance, status, quality and output records | Designed and schema-tested; no endpoint |

`interfaces.schema.json` defines RiskRequest, IgnitionScore, WeatherObservation, SpreadRequest and SpreadResult. Examples are labelled fixtures, not actual prediction responses. Failure records contain a null probability and an explicit error; failure cannot look like zero risk. Date-only observations retain a null clock. Forecast requests cannot contain final-perimeter assistance, outcome-conditioned domains or unknown availability. Syntactic validity does not authorize forecast execution: capability and eligibility checks must still reject unsupported modes.

Exchange rules:

- Geographic cells use EPSG:3978 and metre units; browser coordinates require a declared transformation. A 10 km ignition cell is never substituted for a 90 m simulation cell or 375 m observation cell.
- Weather fields carry Celsius, percent RH, km/h wind and mm rain. Bearings are meteorological **from** true north; the spread engine converts to downwind grid bearing using convergence. The ignition terrain slope is in degrees, while the spread slope term uses elevation rise divided by distance. Neither is a percent without conversion.
- Transport timestamps use UTC with an explicit zone; calendar-day keys retain their named local timezone. The legacy spread module uses naive datetime values that represent UTC, so an adapter must normalize them explicitly rather than assume local time.
- Arrays preserve shape, affine transform, resolution and nodata. Unreached arrival cells become null/masked values in a wire format, not non-standard JSON infinity.
- Quality metadata travels beside predictors. Identifiers, labels and provenance are never automatically included in the numeric matrix.

## 7. Requirements traceability

This table traces the design, not completion of every application requirement.

| Requirement | Design responsibility and evidence | Implementation boundary |
| --- | --- | --- |
| FR-01 | RiskRequest, fixed grid/date rules | Analyst selector planned |
| FR-02 | IgnitionScore; fitted scoring helper; bundle parity | Offline helper only |
| FR-03 | Daily scoring diagram and keyed geometry contract | Map planned |
| FR-04 | Explanation interface and model-specific methods | Explanation service planned; no causal claim |
| FR-05 | Source/feature/run hashes, observation precision and flags | Experiment evidence exists; analyst display planned |
| FR-06 | Keyed CSV/GeoJSON output contract | App export planned |
| FR-07 | SpreadRequest and explicit initial state/mode | Historical engine exists; validated public adapter planned |
| FR-08 | Horizon/output support and validation-status distinction | Synthetic propagation tested; horizon skill not established |
| FR-09 | Separate 375 m scoring support and baseline | Old replay evidence exists; corrected replay pending |
| FR-10 | Default-off repair, explicit reconstruction drivers and mode | Implemented safeguards; outcome-independent rebuild remains |
| FR-11 | Panel/partition manifests and source ledger | Historical artifacts exist; full selected-source build remains |
| FR-12 | Four fitted candidates, common temporal/inner-spatial evaluation | Completed development experiment |
| FR-13 | Ordered bundles, environment/feature hashes and reload tests | Development bundles exist; calibration/promotion remains |
| FR-14 | Availability/run/lead requirements in live diagram | HRDPS ingestion planned |
| FR-15 | Stateful weather contract with startup and invalidation | Pilot adapter exists; live state bridge planned |
| FR-16 | Ensemble/DPV separated from ignition and spread core | Future research only |

NFR-01 maps to year/role/cutoff guards; NFR-02 to unit/CRS/wind contracts and cardinal/barrier tests; NFR-03 to hashes, seeds, repeatability and version records; NFR-04/05 to full-prevalence validation, AP/Brier/baseline/alert metrics; NFR-06/07 to separately specified application/spread performance tests; NFR-08 to explicit failure/null outputs; NFR-09 to the future analyst workflow; NFR-10 to private credentials and source attribution; NFR-11 to the component split; NFR-12 to bounded sampling, measured memory/runtime and the environment lock. Application usability, end-to-end response times and emergency use are not established by module tests.

## 8. Evaluation, tracking and release rules

Average precision is the primary development metric, specifically sklearn.metrics.average_precision_score, not trapezoidal PR-AUC. Report natural validation prevalence, ROC-AUC, Brier score, log loss, false alerts and fixed-budget precision/recall. The 1% daily alert budget is an illustrative capacity choice; it has not been approved by an end user. Daily bootstrap intervals describe development recall variation, not model probability uncertainty or independent-fire confidence bounds.

Choose hyperparameters/features using development data only. Refit the selected temporal candidate on 2010-2017 only after the development design is frozen; fit a declared calibration map on 2018; freeze model, predictor order, calibration and alert rules before scoring 2019 once. Keep the outer geographic experiment separate: no outer test geography or history features in its fitting. Do not reuse the all-geography temporal model for geographic scoring. Earlier descriptive EDA exposed 2019, so it is not called a pristine untouched dataset.

Each run records source and selector hashes, code hash, predictor order, seed, versions, configuration, sample/population counts, metrics, runtime, memory and model hashes. Completed comparison files and their model directory are protected against default overwrite; a new experiment requires a new output version. Load only locally produced trusted joblib artifacts after hash/version verification. They are not a safe interchange format for untrusted uploads.

Promotion requires reviewed source/time eligibility, accepted mask/station corrections or explicit benchmark restrictions, completed calibration/final evaluation, matching loader/scorer versions, and user-facing mode/coverage labels. Source, feature, model and propagation revisions are independent. A source or propagation change invalidates reuse of old evaluation scores. No trained model is automatically deployed.

## 9. Evidence and references

The companion experiment report, spread review, decisions, validation review, schemas and manifests support this design. The course mapping is the supplied Module 3 shortlist and AI-capability-design guidance: relevant algorithms/frameworks with costs/challenges; AI/API/LLM/external-data identification; training/inference modules; component interactions; and textual explanation. No grading rubric or professor approval beyond those supplied requirements was available.

Technical references: [scikit-learn histogram boosting](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html), [SimpleImputer](https://scikit-learn.org/stable/modules/generated/sklearn.impute.SimpleImputer.html), [LightGBM parameters](https://lightgbm.readthedocs.io/en/stable/Parameters.html), [Canadian FBP revisions](https://publications.gc.ca/site/eng/9.565261/publication.html), [CFFDRS reference implementation](https://github.com/cffdrs/cffdrs_r). The [research attachment](../research_review_2026-10-14/README.md) supplies the peer-reviewed literature synthesis and its limits. Source/requirement details are retained in the [Week 2 specification](../week_2_development_2026-10-15/system_requirements.md).
