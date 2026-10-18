# Ontario Wildfire Ignition and Spread Research Prototype

COMP 385, Section 001 | Final local research review | October 16, 2026

## 1. Executive result

The local research prototype now combines historical ignition predictions, a separately trained selected-source 2025 study, corrected incident spread reconstruction, exports and an explicit live-readiness decision. All four requested development activities have been executed. This is not a declaration that live forecasting passed acceptance: the measured evidence rejects live ignition scoring, and the application deliberately returns unavailable rather than a probability.

The historical temporal final test reaches 63 of 509 recorded positive cell-days at a fixed illustrative 1% daily alert budget. The selected 2025 temporal study reaches five of 102 positives. Both have low absolute precision. The corrected spread simulator scores 150 steps from 22 fires and achieves lower overall recall than even growth. These failures are findings, not reasons to retune on held-out outcomes or conceal limitations. The complete software suite passes 129 tests; actual HTTP, export, browser and bounded performance checks are separately recorded.

## 2. Problem and scope

A daily ignition product estimates the probability of at least one recorded new start in an existing 10 km Ontario cell on a local calendar date. A separate 90 m incident simulator estimates progression conditional on an existing fire state, weather and landscape. Daily ignition probability is not burn probability, and a high-risk cell is not itself an observed fire state.

The seven-source development scope remains Ontario Fire Disturbance Point/Area, VIIRS, ERA5-Land, HRDPS, FBP Fuel Types 2024, SCANFI v1.2/2020 and MRDEM. Areas and VIIRS are separate spread/evaluation inputs, not ignition predictors. The legacy NFDB/CDEM/CWFIS benchmark is retained under its historical contract; it is not silently relabelled as the modern seven-source panel. The user's 10 km ignition decision and separate spread grid are unchanged.

The delivered application is a loopback-only research dashboard, not an emergency service. No approved categorical fire-danger thresholds, treatment optimizer, suppression model, crown-fire validation or operational uncertainty model is claimed. Native Microsoft Project verification remains explicitly deferred by the user; professor/team acceptance and submission are outside the verified local development result.


```text
Historical NFDB/CDEM/CWFIS -> corrected weather -> frozen model -> 2019 map
Selected 2025 sources     -> separate model     -> Sep-Oct 2025 map
Existing incident state  -> corrected simulator -> reconstruction + baseline
HRDPS + research state   -> readiness fails     -> no live probability
                                   |
                                   v
                    Local dashboard / details / exports
```

## 3. Data engineering and provenance

The historical benchmark contains 17,798,320 cell-days over 9,673 cells in May-October 2010-2019. Its corrected daily-station weather method selects up to four currently valid reporting stations within 200 km, uses declared physical/range rules and variable-specific valid weights, and requires seven complete consecutive days for recent rain. It uses only previous-date observations. The 2010-2017 development coverage improvement, paired-key checks and boundary sensitivity are recorded in Week 4. Original labels, selectors, v1 files and 24 development bundles remain preserved.

The selected-source panel contains 1,775,232 May-October 2025 rows over 9,648 independent current-boundary cells. It retains 624 source instances in 600 positive cell-days, with 25 explicitly excluded instances. Provider calendar dates are preserved; exact ignition clocks are not invented. A negative means no IFR start recorded in the selected source/date/cell. The separate current boundary is not recovery of the missing old pinned geometry.

Final FBP2024 features are native-pixel intersection-area categorical shares, retaining raw codes and partial support. Six cells have no native fuel support. SCANFI closure/composition and MRDEM terrain are 100 deterministic 1 km strata-centre estimates, not complete native-area means; closure is conditional on joint species validity and slope is a coarse sample gradient. Source CRSs are transformed explicitly, including MRDEM EPSG:3979. Forest source files retain the selected v1.2/2020 vintage rather than the earlier EDA's newer products.

ERA5-Land transforms 8,016 hours from eleven pinned Jan-Nov 2025 provincial files to 3,222,432 daily records. Local standard noon is mapped per cell, accumulated precipitation is decoded with reset/interval rules and FWI uses an explicit research startup. Missing updates invalidate state. The modelling table joins only the previous standard-noon day and has 1,773,024 valid research FWI rows. It does not establish observed or overwintered state, retrospective publication availability or operational weather quality.

## 4. Literature and design basis

Pais et al.'s Cell2Fire study supports cell-based growth simulation and landscape-management research. Our simulator differs: it uses a sixteen-neighbour shortest-travel-time algorithm with a restricted FBP-inspired rate subset and simplified processes. Its published performance cannot be transferred to this implementation. (Pais et al., 2021).

Kim, Pais and Gonzalez compare Cell2Fire with other simulators and demonstrate calibration and sensitivity on synthetic and real landscapes. This supports reporting calibration separately from independently evaluated forecasting; fitting a historical scar does not establish future incident accuracy (Kim et al., 2025).

The existing research attachment reviews the wider slide list, including tools, benchmark datasets and the DPV/C2FK studies. No external engine was silently substituted or claimed integrated. Module boundaries separate acquisition, feature preparation, model fitting, calibration, saved scoring, spread simulation, evaluation and display. Week 3 architecture decisions and the Week 4 pre-implementation/source reviews remain preserved appendices.

## 5. Historical ignition experiment

Four candidate families were compared on common development protocols: historical rate, logistic regression, histogram gradient boosting and LightGBM. Fixed source/model/alert choices selected LightGBM provisionally from corrected-weather pooled temporal AP. All choices were frozen before new reserved-year reads. The final temporal model refits 2010-2017 using all positives and deterministic approximately 1% sampled negatives with weights restoring population class proportions. A separate geographic model fits spatial-development cells only and excludes history features.

The prespecified monotone logistic map of clipped raw logits fits only natural-prevalence 2018 calibration rows. Completed base/calibrator artifacts pass reload parity and were sealed before one-time 2019 scoring. The final primary temporal test has 1,779,832 rows and 509 positives; the separate geographic test has 255,208 rows and 74 positives. Earlier broad descriptive EDA exposed 2019, so this is reserved from new fitting/tuning, not a pristine never-inspected holdout. [E1]

| Historical final protocol | AP | Calibrated Brier | Recall at budget | Precision at budget |
| --- | --- | --- | --- | --- |
| Temporal, 2019 | 0.00352195 | 0.000285728 | 12.377% (63/509) | 0.353% |
| Withheld geography, 2019 | 0.00134303 | 0.000289967 | 6.757% (5/74) | 0.194% |

The temporal AP exceeds constant-prior AP, but most alerts are false positives. Geographic calibrated Brier is worse than its constant prior. Day-resampling recall intervals, fixed-bin diagnostics and weather-support subgroups are retained. Resampling days does not account for all incident/spatial dependence. No post-final hyperparameter, threshold or calibrator selection was performed.

## 6. Selected-source 2025 experiment

A separate protocol was frozen before role-specific fitting: May-June initial training, July validation, May-July final refit, August calibration and September-October final testing. The LightGBM family/settings and sampling/alert/calibration rules were already fixed. The secondary geographic experiment intersects the original label-independent geographic selectors with the current grid; only development geography fits/refits/calibrates, and September-October reserved cells form its final test. All predictors follow the separate selected-source contract; no historical CWFIS model is applied to these inputs. [E2]

This one-season study uses only eligible date roles and natural final prevalence. Minimum class-support guards were declared for fitting and evaluation; both final protocols have positive support, although the secondary sample is small. The original panel's old readiness flag remains an immutable construction snapshot. The active result qualifies only a within-season research experiment, not cross-year robustness or live compatibility. Prior 2025 source/EDA exposure is disclosed.

| Selected-source final protocol | Rows / positives | AP | Calibrated Brier | Recall / precision at budget |
| --- | --- | --- | --- | --- |
| Temporal, Sep-Oct 2025 | 588,528 / 102 | 0.00049667 | 0.000173328 | 4.902% / 0.0845% |
| Withheld geography, Sep-Oct 2025 | 84,363 / 14 | 0.00057686 | 0.000165930 | 7.143% / 0.1171% |

The temporal model reaches five positives and the secondary reaches one. These are weak research results. Calibrated temporal Brier is only marginally better than the constant prior; no strong probabilistic reliability or geographic generalization follows. Two separately fitted bundles pass reload parity, and selected-study first-day TreeSHAP contributions pass raw-margin additivity checks. Explanations are raw-log-odds attributions, not causes or additive changes in calibrated probability.

## 7. Corrected spread reconstruction

All 48 frozen replay incidents now have regenerated 90 m fuel and terrain landscapes from the pinned local FBP2024/MRDEM products. Native source hashes, resampling, grids, nodata coverage and output hashes are recorded. These are new versioned derived inputs, not a claim of byte-identical recovery of missing TIFFs. The cleaned 48-perimeter subset was rebuilt from the pinned raw area layer using the original buffer-zero repair rule; its outcome assistance is explicit. [E3]

Across regenerated grids the minimum valid support is 95.69%; per-source/per-case fractions are retained. Unsupported fuel remains non-spreading. The inherited reconstruction loader replaces missing terrain with its case mean; this is a disclosed research heuristic, not a validated operational unknown-input policy.

The corrected simulator enforces touched-cell water/diagonal clearance and respects an explicitly empty active mask. Scar repair defaults off in the general engine. This replay opts into scar repair and uses archived final-perimeter domains and retrospective weather, so it remains reconstruction. The previously published holdout was already inspected; the rerun is a corrected-revision regression evaluation, not pristine forecast validation.

The same 24 calibration incidents and 4 x 4 scale grid select ROS scale 1.2 and flank scale 0.25 before the 24 holdout incidents are replayed. Twenty-two holdout incidents have scoreable observations, yielding 150 steps of 6-30 hours with at least five observed new cells. The area-ratio 1.3 heuristic is retained and disclosed rather than presented as an independently validated target.

| Corrected held-out reconstruction metric | Simulator | Even growth |
| --- | --- | --- |
| Mean recall | 0.3606 | 0.4018 |
| Mean IoU | 0.1019 | 0.1039 |

The simulator does not beat even growth overall. Mean precision is 0.1835, median predicted/observed area ratio 2.076 and median head-distance ratio 0.984. No new performance is attributed solely to the barrier patch because regenerated landscape lineage also differs. A new four-incident viewer uses corrected arrivals/scores and clearly labels final-perimeter-assisted reconstruction. Its 1-, 3- and 6-hour controls demonstrate completed simulations; suitable horizon-specific forecasting observations are absent.

## 8. Live readiness: measured rejection

The HRDPS research adapter is implemented: actual available-run selection, downloaded/hash-verified files, rotated-grid wind conversion, accumulation-aware precipitation, standard-noon extraction and date/clock/provenance checks on FWI seeds. Its recorded run has 231,552 hourly rows, 8,526 valid research FWI updates and 1,122 incomplete-weather cells. Forecast-derived checkpoints remain untrusted when reused.

The readiness assessment finds zero common ERA5/HRDPS reference dates in the available archives and zero trusted observed-state cells. The selected model has only within-season retrospective qualification. Equivalent variable names/units and shared equations do not establish forecast-source interchangeability. There is therefore no accepted empirical parity or observed/overwintered-state decision. [E4]

The combined app presents these reasons. Its live ignition endpoint returns HTTP 503 with status unavailable and probability null; a failure is never turned into zero risk. Tests show that merely supplying coincident dates or a trusted label cannot bypass the missing accepted validation decision. Completing this assessment is not passing live acceptance: operational live ignition remains an unmet M2 requirement. Resolving it needs independent matched forecast/reference data and verified observed/state provenance, not another code toggle.

## 9. Application and interfaces

The local dashboard at http://127.0.0.1:8768 provides four explicit modes: historical 2019 ignition, selected-source 2025 ignition, corrected spread reconstruction and live readiness. The daily probability maps and incident reconstruction remain separate. The host binds only loopback, serves an explicit file allowlist and accepts read-only requests. Keys, dates, studies and export formats are validated; arbitrary paths cannot be requested.

The two ignition maps retain 184 and 61 final-evaluation dates respectively, exact keyed scores, source-quality flags and first-day factor details. The cell-details API/UI adds feature values, units, missingness and raw-log-odds contributions when explanations exist. All supported dates retain source versions, issue time and model/contract hashes. Selection changes clear old factors; pending responses cannot overwrite a different selected date/cell/study. Missing local files return JSON503 and the browser displays request failures/timeouts. Other dates explicitly report unavailable explanations instead of reusing the first day's factors. CSV/GeoJSON exports preserve model/contract hashes, keys, full probabilities, issue time, quality flags and numerical-band version. GeoJSON uses transformed EPSG:4326 polygons; native EPSG:3978 grid metadata is retained.

Browser verification covered mode navigation, selected cell values/factors, downloaded selected-date CSV, spread reconstruction banner, 1/3/6-hour controls and the live rejection panel. The default narrow app viewport was inspected. Transport tests compare real CSV and GeoJSON keys/values/provenance against saved predictions. These checks do not establish independent first-time-user usability or a full accessibility certification.

## 10. Validation and performance

The complete combined suite passes 129 tests. New tests cover categorical resampling, source/role boundaries, live-failure invariants, request validation, keyed scores, units and unsupported study rejection. Existing weather, FWI, calibration, model-contract and barrier/corner/empty-mask tests remain passing. Software checks are distinct from the empirical model/simulator results and cannot validate emergency or field accuracy.

Across twenty local HTTP requests per route, p95 body-transfer response times were 0.038 seconds for the 51.6 MB historical map, 0.014 seconds for the selected map and 0.023 seconds for keyed historical details. These timings include transport/lookup but exclude browser rendering, data rebuilding and cold source downloads. They are not a complete end-to-end NFR-06 certification. Twenty supported <=100,000-cell reconstruction cases each completed a six-hour simulation; p95 simulation-only time was 0.0067 seconds, excluding landscape loading. The small elapsed time says nothing about forecast correctness. [E5]

The measured host is Apple M3 Pro with 19,327,352,832 bytes RAM (18 GiB). Earlier bounded historical comparison RSS/runtime and full-data preparation audits remain in their dated packages; no unmeasured peak memory for the entire new sequence is invented. Code review used implementer, security/input-path and automated complexity passes; independent reviewer/professor sign-off is not claimed. Long orchestration functions remain maintenance debt.

## 11. Requirement disposition and completion boundary

FR-01 to FR-03: supported studies/dates, keyed scores and maps are demonstrated. FR-04/05: first-day factors with values/units/provenance and explicit unavailable states are demonstrated. FR-06: CSV/GeoJSON export is measured. FR-07 to FR-10: supported incident reconstruction, simulated horizons, paired baseline comparison and mode separation are demonstrated; arbitrary live initial-state forecasting is excluded. FR-11 to FR-13: versioned builds, explicit selectors, comparisons, bundles/reload and contracts are demonstrated. [E6]

FR-14/15 remain unmet for accepted live ignition: the weather adapter runs, but source/state qualification fails. FR-16 ensembles/DPV treatment ranking remain later research options. Independent user/field acceptance, operational source qualification, approved danger categories and deployment are not represented as completed. The native Project audit remains user-deferred. Thus local Week 5 research implementation and its requested assessments are complete, while live-operational acceptance has a documented failed decision rather than a fabricated success.

## 12. Reproduction and evidence

From the CAPSTONE directory, use the retained .venv and pinned inputs. Start this reviewed revision with `.venv/bin/python -m scripts.capstone_app serve --port 8768`. Rebuild its static dashboard/readiness snapshot with `python -m scripts.capstone_app build`. The frozen model/replay outputs reject overwrites; do not retune or rerun final tests to improve reported numbers. Source snapshots, selected final freeze, completion protocol, input/output hashes, environment lock and package verification support review. No Git merge/push, external submission or synced-source edit was performed.

The first spread replay attempt failed before scoring because the ignored cleaned-perimeter cache was absent. Its empty output directory/log and source revision were retained; the pinned perimeter cache was then reconstructed and the corrected run completed. A legacy HTML fragment omitted an explicit body tag, so the reconstruction banner renderer was corrected; the replay source used for the scientific result is separately hash-preserved. No scientific score changed in that display correction.

## 13. References and appendices

Pais, C., Carrasco, J., Martell, D. L., Weintraub, A., & Woodruff, D. L. (2021). Cell2Fire: A cell-based forest fire growth model to support strategic landscape management planning. Frontiers in Forests and Global Change, 4, 692706. https://doi.org/10.3389/ffgc.2021.692706

Kim, M., Pais, C., & Gonzalez, M. C. (2025). Fire spread simulations using Cell2Fire on synthetic and real landscapes. Scientific Reports, 15, 25173. https://doi.org/10.1038/s41598-025-05706-6

Additional reviewed literature and primary data/tool references are in reports/research_review_2026-10-14/README.md. The cited findings guide research design, not transferred accuracy claims.

[E1] Historical protocol/calibration/final results: reports/week_5_prototype_2026-10-16/. [E2] Selected-source protocol/results: completion_protocol.json, selected_final_freeze.json, selected_2025_results.json. [E3] Landscape/perimeter ledgers: data/processed/spread_landscapes_restored_v2/; corrected_spread_results.json and corrected spread viewer. [E4] live_readiness.json and API rejection tests. [E5] http_performance.json, spread_performance.json, HTTP/export/cell-detail integration evidence. [E6] Original SRS/use cases/evaluation plan: reports/week_2_development_2026-10-15/; architecture/component contracts and decisions: reports/week_3_design_2026-10-15/; seven-source transforms and dictionary: reports/week_4_data_2026-10-16/.

These referenced local appendices remain part of the review package. Older dated documents are snapshots; current status is the updated checklist and this report. Checksums and the compact completion ZIP identify the delivered revision. Large raw rasters and full tables remain local and are excluded from the review ZIP.

## 14. Final software review and measured acceptance

The final application review corrected missing-file connection drops, duplicate/nonfinite saved-score handling, metadata omission on dates without explanations, browser failure messages and stale factors after selection changes. Three new regression tests failed before the fixes and passed afterwards; the complete suite now has 129 passing tests. Dependency checks and dashboard JavaScript syntax checks pass. These are software changes, not model reselection or a new evaluation.

Twenty warm historical-map reloads waited for the initialized 9,673-cell/date summary. P95 was 0.4078 seconds including browser-control overhead; this is initialized-view timing, not pixel-paint or cold-download certification. Twenty requests to the current first-day cell-details route had p95 0.1142 seconds including feature lookup and JSON body. Both satisfy the declared local warm targets. The earlier 20-case spread timing evidence gives load-plus-simulation p95 0.1143 seconds and maximum 0.4990 seconds for windows up to 73,688 cells. These derived timing totals do not rerun or validate scientific forecast skill.

The acceptance record below distinguishes local implementation, tested bounds, unmet M2 qualification and external quality/approval limits. The older six-page report and research packages remain immutable snapshots. This report and the new review bundle identify the current application revision; all frozen scientific results remain unchanged.

## 15. Requirement-by-requirement acceptance

Reviewed October 16, 2026. Requirement IDs retain the original Week 2 SRS. Implemented describes local software; it does not mean every quality or operational acceptance gate passed.

| Week | Development status | Boundary |
| --- | --- | --- |
| 1 | Complete locally | Scope, 10 km ignition contract and incremental plan recorded. |
| 2 | Complete locally | Source audits, research, SRS/use cases and evaluation roles; native Project verification user-deferred. |
| 3 | Complete locally | Designs, candidates, schemas, decisions and technical evidence; independent/professor approval unverified. |
| 4 | Complete locally | Corrected weather, selected-source join, live research adapter and architecture review; research FWI is untrusted operationally. |
| 5 | Local research implementation complete | App, tests, reports and measured assessments complete; live M2 acceptance remains unmet. |

## Functional requirements

| ID | Disposition | Evidence and limit |
| --- | --- | --- |
| FR-01 | Implemented | Historical/selected studies and supported date selectors; actual browser navigation. |
| FR-02 | Implemented | Unique saved scores, bounded probabilities, all-date issue/model/contract metadata; duplicate and nonfinite score failures tested. |
| FR-03 | Implemented | Separate 10 km grids, transformed map polygons, numeric probability bands; no approved danger categories. |
| FR-04 | Implemented with explicit limits | First-day TreeSHAP factors and values/units; other dates say unavailable. Date/cell changes clear stale details. No causal or probability-additive claim. |
| FR-05 | Implemented | Source and issue/model metadata retained even without explanations; missing weather remains flagged. |
| FR-06 | Implemented | CSV/GeoJSON API and actual browser CSV download; 9,648 unique selected-date keys verified. |
| FR-07 | Implemented for supported reconstruction | Four supported incidents and existing fire-state workflow. Arbitrary live-state forecasting is outside accepted scope. |
| FR-08 | Implemented simulation outputs | 1/3/6-hour controls demonstrate simulated progression. Horizon-specific forecasting accuracy remains unestablished. |
| FR-09 | Implemented retrospective comparison | Corrected 150-step/22-fire reconstruction and paired even-growth baseline; below-baseline results retained. |
| FR-10 | Implemented | Final-perimeter assistance, modern fuel vintage and reconstruction banner explicit. |
| FR-11 | Implemented locally | Seven-source audits, versioned transformations, quality/exclusion ledgers and dataset hashes; raw caches retained locally. |
| FR-12 | Implemented | Four candidate comparisons and frozen temporal/geographic protocols; no new final scoring in this closeout. |
| FR-13 | Implemented | Calibrated temporal/geographic model bundles, predictor contracts and reload parity; hashes preserved. |
| FR-14 | M2 acceptance unmet | HRDPS adapter implemented, but no qualified live ignition source/issue compatibility. |
| FR-15 | M2 acceptance unmet | Research FWI state/checkpoint path implemented; zero trusted observed/overwintered-state cells in recorded evidence. |
| FR-16 | Optional later research | Ensembles/DPV are reviewed options; no uncertainty or treatment-priority output invented. |

## Quality requirements

| ID | Disposition | Evidence and limit |
| --- | --- | --- |
| NFR-01 | Verified in retrospective scope | Key/time/availability guards and frozen role checks; unknown historical publication times remain labelled hindcast. |
| NFR-02 | Verified software contracts | CRS, categorical fuel, wind and unit checks; no independent canonical or field FWI validation claimed. |
| NFR-03 | Verified bounded reproducibility | Hashes, settings, source snapshots and saved/reloaded score checks; no new real-data fit in this closeout. |
| NFR-04 | Reported | Natural final prevalence, AP implementation, precision/recall and Brier retained; previous EDA exposure disclosed. |
| NFR-05 | Reported | Same-target baselines and weak/negative empirical results retained. |
| NFR-06 | Warm local targets passed | 20 initialized historical-map reloads: p95 0.4078 s; 20 current cell-detail HTTP requests: p95 0.1142 s. Includes control overhead for map; excludes cold build/download and pixel-paint certification. |
| NFR-07 | Bounded timing target passed | 20 existing supported cases <=73,688 cells: load plus six-hour simulation p95 0.1143 s; maximum 0.4990 s. Derived from sequential saved timing evidence, not a new scientific replay. |
| NFR-08 | Tested failure paths | Missing result file now gives JSON503; duplicate/nonfinite score outputs unavailable. Browser request/network errors and a 15 s timeout produce visible messages. Exhaustive fault certification is not claimed. |
| NFR-09 | External acceptance unverified | Implementer completed date/cell/export/reconstruction/live tasks; no independent first-time-user or accessibility acceptance is claimed. |
| NFR-10 | Documented local provenance | Public-source credits, loopback binding and path allowlist retained; no new credential collection or external transmission. |
| NFR-11 | Implemented with maintenance debt | Acquisition/transform/fit/score/simulate/display modules and 129 tests; orchestration and inline dashboard remain long. This is implementer review. |
| NFR-12 | Reproduction documented; broader portability unverified | Existing Mac environment passes pip check; source/environment and start/test commands supplied. Large data remain outside the compact ZIP. No clean-machine or full-pipeline peak-RSS certification claimed. |

## Remaining gates

Live qualification requires independently matched forecast/reference inputs over a justified evaluation period, observed/overwintered state with date/clock/availability provenance, a frozen source-compatible modelling protocol and acceptance evidence. Available local archives have no paired reference dates and no trusted observed-state cells. Downloading unrelated weather or changing a trusted flag would not resolve this. No new qualification is inferred.

Independent team/professor/field/user acceptance requires the relevant reviewers or observations; it is not supplied by this implementer audit. Native Microsoft Project verification remains explicitly deferred. Optional ensembles/DPV remain later research. No external submission or production deployment has occurred.

The supplied Module 1-5 content is the course basis. No separate final-marking rubric, signature, institutional approval or deadline has been assumed. This is a technical review package; administrative cover-page/student-signature requirements were excluded from the development checklist at the user's request.
