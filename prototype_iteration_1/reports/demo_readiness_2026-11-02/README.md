# November 2 model work and demonstration readiness

The dashboard and presentation are updated. Universal wildfire detection is **not achieved**. A new constrained LightGBM candidate finds **5 of 92** positive cell-days at the registered daily 1% review budget, compared with **2 of 92** for the matching reference. It fails the earlier selection folds, so existing serving models remain unchanged. These are previously exposed geographic development results, not a new independent evaluation or a live forecast.

## Completed modelling

Two protocols were written before their respective fits. The lightning ablation completed 18 fits; the physical-feature geographic comparison completed 9. Both use the existing wildfire-only target, fixed 10 km grid, deterministic negative sampling, population-corrected weights, original spatial blocks/buffer and separate calibration. No old final model was retrained and no protected final predictions were regenerated.

| Geographic candidate | Found at 1% | Missed | Recall | Average precision | Brier | Log loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Reference | 2/92 | 90 | 2.17% | 0.0023242605 | 0.0003967059 | 0.0031854008 |
| Reference + past 24h lightning | 2/92 | 90 | 2.17% | 0.0024014289 | 0.0003967329 | 0.0031839446 |
| Reference + past 24h/7d lightning | 3/92 | 89 | 3.26% | 0.0023086058 | 0.0003967038 | 0.0031787210 |
| Physical features, logistic regression | 2/92 | 90 | 2.17% | 0.0022394170 | 0.0003966994 | 0.0032256662 |
| Physical features, constrained LightGBM | 5/92 | 87 | 5.43% | 0.0035090156 | 0.0003965471 | 0.0031454606 |

The 92 examples are positive **cell-days**, not 92% accuracy. In this subgroup, 95 retained archive event records map onto those 92 cell-days. The older 0/92 audit used a different target/refit and is not a matched comparator for today’s results.

The constrained model found 0 and 4 positives on the earlier 2014/2015 geographic folds; the reference found 0 and 7. Its improved 2017 result cannot override the frozen earlier-fold decision. The conditional paired seven-day bootstrap interval for its recall change is [0, 6.90] percentage points; this does not adjust for prior exploratory choices or establish independent generalization. The physical model removes station/reporting quality fields from learned risk predictors while preserving source-quality metadata upstream. Logistic imputation/scaling use training data only. Constrained boosting imposes nondecreasing effects for FFMC/DMC/DC and past CG densities, with other features unconstrained.

## Lightning data and boundaries

Eight annual [ECCC CanCPLD cloud-to-ground archives](https://crd-data-donnees-rdc.ec.gc.ca/CDAS/products/CanCPLD/CLDN/cg/) support **14,238,656 cell-days** across 2010–2017. Intersections between the native 0.1-degree cells and existing 10 km cells produce area-weighted flash densities. The builder reads bounded 64-band chunks and reuses a sparse spatial-weight matrix across years. Full windows preserve missing coverage; zero flashes and missing observations remain distinct.

Every 24h/168h window ends at the last complete three-hour interval before local midnight. All eight feature audits report zero future-interval violations. The original 30-row pilot matches the full-grid output within recorded numerical tolerance. Only 12 of the 92 positive cell-days have nonzero past-24h CG density; 59 have nonzero past-seven-day density. These are post-fit support diagnostics and were not used to revise candidates.

The archive was processed/retrieved in 2026. Earlier observation timestamps do not prove historical issue-time publication. Detector/classification changes across source years and the source’s spatial resolution remain limitations. No same-day future strikes, current vegetation backfill, final fire size or final perimeter enters ignition predictors. Method source: [Cannon et al. (2025), CanCPLD](https://doi.org/10.1038/s41597-025-05924-7).

Exact protocols, folds, calibrations, capacity curves, reliability tables, positive-case ranks and model hashes live in:

- `../lightning_development_2026-11-02/`
- `../geographic_transfer_2026-11-02/`

Large derived panels, prediction tables, models and raw archives remain local under `CAPSTONE/data/`. The Git copy contains code and compact evidence.

## Dashboard and source refresh

Open **http://127.0.0.1:8771/**. The home page now opens Geographic performance. It provides five candidate choices, exact found/missed counts, recall, precision, review workload, a dated geographic replay and recorded-start overlay. Capacity choices of 2%, 5%, 10% and 20% are explicitly diagnostic; increasing the list size is not a skill gain. The default remains the registered 1% reference.

Navigation retains the 2019 and 2025 study maps, cell explanations, CSV/GeoJSON exports, separate spread reconstruction, reported-fire/weather context and unavailable live readiness. The dashboard template is separate from request/model handling. A date change in the geographic replay no longer emits an irrelevant historical cell-detail prompt. The workflow’s home link returns to the top-level dashboard.

Fresh Ontario collection at **2026-11-02 15:07:12 UTC** contains 9 source-reported incidents, 12 historical scenarios and 21 local notices/drafts. Weather uses the **November 2 06 UTC HRDPS run**, acquired at 15:02 UTC. Snapshot age and valid forecast hours remain dynamic. Source retrieval is not proof of an incident’s latest observation or current perimeter. Live model outputs remain null and no public notice is sent.

The weather collection initially wrote valid payloads but failed its final report export because a new report directory did not exist. Payload hashes were verified, the report was recovered from the completed manifest, and `hrdps_live_weather.run` now creates that directory before collection. The source was not downloaded again to hide the failure.

## Verification

- **212 tests passed** across prototype, feature and spread suites. These check software, not model accuracy.
- **29 HTTP checks passed**, including five candidate/date APIs, malformed/reserved queries, exports, workflow and expected live 503/null.
- Five classroom launcher commands completed successfully with saved outputs.
- Actual Chrome checks verified candidate switching (2/92 to 5/92), capacity switching (1% to 5%), date navigation, recorded-start toggle, historical page, completed CSV download, refreshed fire/weather display, live-unavailable view and six-hour reconstruction controls. The corrected date interaction was rechecked after the final fix.
- **31 protected scientific artifacts** match their pre-experiment hashes. Both matched reference refits reproduce prior metrics.
- Five-slide PPTX structural/layout/native-chart checks passed. The changed results slide was visually inspected; the other four slides render pixel-identically to the source. Native PowerPoint/projector operation and the timed five-person rehearsal remain unverified.

Files: `regression_tests.txt`, `http_preflight.json`, `lightning_pilot_parity.json`, `presentation_commands.json`, `verification.json`, `code_review.json`, `source/`. The heuristic code checker reports style/complexity findings; it is not an independent correctness or security certification.

## Today’s demonstration

Use `../class_demo_2026-10-31/output/DEMO_GUIDE.md` and the updated five-slide PPTX in that folder. Preserve the 10-minute demonstration, 5-minute Q&A and 120 seconds per person. Do not train or collect new data while presenting.

For the results segment, show the 1% reference, switch to the constrained model and say: “This candidate finds five of the 92 known positive cell-days, compared with two for the reference. It still misses 87 and fails our earlier-fold selection rule. We kept the existing model and made the limitation visible.” If changing capacity, explain the additional false-positive review slots.

The next research priority is a source audit for historically dated fuel/vegetation and human-access data, including reporting coverage. Register the next feature/model comparison before fitting, use development geography for selection, and obtain genuinely untouched data before a generalization claim. Live qualification separately needs issue-time forecast features, observed-state lineage and horizon evaluation. A larger UI review list cannot solve missing predictive information or guarantee every future wildfire.

This development snapshot is packaged on `parth/iteration-1-prototype`. The dated verification record describes the pre-publication checks. No coursework submission or production deployment was performed.


## Access review and user assistance

The user reports no existing college/partner data access. No new API key, subscription or paid data is required to continue the public-source investigation. Existing CDS configuration is present; its presence alone does not verify a current authenticated session. Credentials were not read or printed.

The next candidate source families are historically dated forest cover/fuels, human access and stronger fire-record timing/quality. They are hypotheses, not assured improvements. We need coverage over the training geography as well as evaluation geography, with source vintages and observation/publication dates. Current maps must not be substituted into 2010–2017.

| Source/access | Current conclusion | Action |
| --- | --- | --- |
| ECCC CanCPLD CG density | Already acquired for the development years and tested; no key needed for those downloads | Reuse. A new generic weather API does not replace historical lightning or improve the tested model automatically |
| NRCan EOSD circa-2000 forest cover | Official description confirms Landsat land-cover classes around 2000, a possible older source candidate | Locate actual tiles, release/provenance and Ontario coverage before feature construction. Land-cover class is not an exact FBP fuel type |
| Statistics Canada 2009 Road Network File | Official catalogue confirms June 3, 2009 release and reference guide describes free download | Resolve the archived payload, licence and northern/forest-road completeness. Use only as a dated access proxy |
| Detailed provincial fire records | Public national records have variable completeness, approximate locations and reporting limitations | If the professor can obtain agency data, request discovery/reported-start times, coordinate accuracy, cause/status, prescribed-burn flags and reporting/observation coverage. Do not use final size/perimeters as ignition predictors |
| Raw CLDN lightning | ECCC directs access enquiries to its CLDN contact; charges can apply and academic terms are not verified | Optional only after a clear specification and access/price review. Do not purchase merely to pursue 92/92 |
| Forecast thunderstorm inputs | ECCC documents experimental outlook products with explicit issue/valid times | Investigate archived coverage and future availability separately. A current outlook cannot be backfilled into 2017 |

Public source references checked November 2:

- https://natural-resources.canada.ca/forests-forestry/sustainable-forest-management/forest-cover-map
- https://www150.statcan.gc.ca/n1/en/catalogue/92-500-X2009001
- https://www12.statcan.gc.ca/census-recensement/2011/geo/ref/2006/92-500-G2009001-eng.pdf
- https://cwfis.cfs.nrcan.gc.ca/en/fire-history
- https://eccc-msc.github.io/open-data/faq/readme_en/

`all_positive_capacity_diagnostic.json` uses only saved positive ranks, with no new fitting or final-test scoring. At whole-percent budgets, the reference requires 94% and the constrained candidate 96% daily review capacity to include all 92 known positive cell-days. This quantifies workload; it does not establish forecasting skill, acceptable precision, or detection of every future wildfire. The registered comparison remains at 1%.

If external access becomes available, share the provider/dataset name and its permitted use first. Configure any necessary secret locally rather than pasting it into chat. No provider was contacted, paid account opened or credential requested in this review.
