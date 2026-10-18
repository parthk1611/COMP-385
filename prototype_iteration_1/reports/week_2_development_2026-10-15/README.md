# Week 2 development package

Prepared October 15, 2026. This package advances the remaining development work using the chosen **10 km ignition grid**, existing repository and selected seven-source scope. The separate spread prototype remains at 90 m. No model was trained or simulator code changed.

## Completed in this continuation

- [Requirements specification](system_requirements.md): 16 functional requirements, 12 measurable quality requirements, acceptance criteria and traceability.
- [Use cases](use_cases.md): an ASCII system diagram and four detailed AI-related actor/system scenarios, including triggers and exceptions.
- [Evaluation reservation](evaluation_plan.md): frozen selectors, source/output hashes, four materialized Parquet partitions, separate temporal/spatial experiments and explicit prior-EDA limits.
- [Data audit](data_readiness.md): seven-source profiles, pinned source restorations, complete point/area/NFDB correspondence accounting and a fresh full historical v1 feature rebuild; five HRDPS sample files with provenance.
- [Provisional schedule](development_schedule.md): 21 dated tasks with dependencies, two AI iterations and overlapping application/spread work; CSV and XML import candidate.

The [research attachment](../research_review_2026-10-14/README.md) now completes both the minimum two-original-paper synthesis and the extended slide review, including full-text DPV/C2FK assessment through Centennial Library.

## Verified status and remaining boundaries

| Item | State |
| --- | --- |
| Minimum two-paper literature review | Complete locally, with synthesis and comparison to this project. |
| Use-case diagram and four AI templates | Complete as v1 documentation. |
| Functional/non-functional specification | Complete: 16 functional and 12 measurable quality requirements. Acceptance testing remains later work. |
| Temporal/geographic test reservation | Complete local reservation and physical export: four temporal Parquet files, frozen spatial roles, source/selector/output hashes and an explicit predictor allowlist. Training must enforce them. |
| Data investigation and representative-source EDA | Completed audits for all seven groups, with exact scope stated; full provincial fire sources, 20 VIIRS sensor-years and pinned legacy CWFIS restored. [Decisions](data_decisions.md) record compatibility limits and treatment of conflicts. |
| Later full selected-source training/live readiness | Partial implementation work, tracked in Week 4. Pilot weather transformations/state are tested; province-wide joins and live integration remain open. The completed Week 2 audit does not certify these. |
| High-level development plan | Prepared with 21 tasks, dependencies, two AI iterations and overlapping application work. Dates remain provisional at the user's request. Native Microsoft Project verification is explicitly deferred by the user; no native import/use result is claimed. |
| Extended research beyond the minimum | Complete. DPV/C2FK full publisher HTML was read through Centennial Library; methods, results, validation limits and future uses are documented. Burn-probability maps is resolved as a method/output, not an additional identified paper. |

**Week 2 development deliverables are complete locally, with native Microsoft Project verification deferred by the user.** This means research, source investigation/EDA, quality/coverage decisions, requirements/use cases, planning dependencies and evaluation reservation. It does not mean complete provincial feature preparation, trained models or live serving. The earlier broad training/live-readiness row is retained as partial under Week 4, where the supplied course places data preparation; it has not been marked done. Dates are not a blocker. No remote branches were merged or pushed.

## Newly restored local evidence

- 65,655 provincial fire points and 2,751 area records, both matching pinned source hashes.
- 1,037,059 raw VIIRS box detections across 20 pinned sensor-years, plus the existing 300,601 event-matched observations.
- 4,159,936 CWFIS records with the required source checksum.
- 17,798,320 reconstructed historical label rows and a fresh 48-column v1 feature rebuild using the unchanged grid/events and pinned CWFIS source. Weather remains missing on 52.482010% of rows, as explicitly recorded.
- Fire correspondence: 8,107 unique strict matches and two flagged conflicts; no automatic label replacements.
- Fresh spread validation: 18/18 structural checks passed; 3 ignition and 23 spread unit tests passed. These do not establish model accuracy or fix the known simulator defects.

The [data audit](data_readiness.md) now also includes all-grid-centre FBP/MRDEM coverage, a full January provincial ERA5 profile and tested pilot weather conversion. The [weather output audit](selected_weather_audit.json) records 18,704 daily rows and 13,664 valid research FWI rows. The combined local/repository checks pass **53 tests**. Province downloads beyond January are not counted as retrieved until their manifest entries and files exist.

## Review workflow

```text
Requirements + use cases + data evidence
                    |
                    v
Resolve coverage/source decisions + formal architecture review
                    |
                    v
Rebuild eligible panel -> enforce frozen selectors
                    |
                    v
Train/evaluate baselines -> chosen candidate -> historical map

Separate spread path: correct defects -> outcome-independent replay
                      -> reviewed viewer and horizon limits
```

Audit JSON/CSV files retain measured results. Raw HRDPS and branch point-source copies are under `../../data/raw/week_2_audit/`, with manifests. The evaluation manifest pins selectors and source grid; the validation summary records completed checks and their boundaries.
