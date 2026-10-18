# Week 1-5 acceptance record

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
