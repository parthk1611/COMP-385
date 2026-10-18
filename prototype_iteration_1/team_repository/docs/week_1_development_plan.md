# Week 1 — Development scope and process

Recorded October 14, 2026. The user selected **10 km ignition grid cells** and asked that implementation, branch retrieval and stored artifacts remain on the local machine. This document completes the development-only Week 1 planning items. It does not claim data readiness, model performance, final architecture approval or completion of later weeks.

## Problem and intended result

Wildfire analysis requires combining fire records, weather and landscape information that differ in location, time and quality. This project will evaluate whether those inputs support useful daily ignition-risk estimates across Ontario's Fire Region, and separately investigate how an existing fire spreads. Results will be presented through maps with explanations and explicit data limitations.

Two capabilities remain separate:

1. **Ignition:** estimate the probability of at least one recorded new fire start in an eligible 10 km cell on a target day.
2. **Spread:** simulate progression from an existing fire state. The implemented historical simulator uses a separate 90 m grid; selecting 10 km for ignition does not resample spread to 10 km. Requested 1-, 3- and 6-hour outputs still require horizon-appropriate validation.

## Initial historical benchmark contract

The grid decision is explicitly user-confirmed. The remaining benchmark settings below retain the existing repository contract rather than introducing a new dataset design.

| Item | Working contract |
| --- | --- |
| Ignition unit | One existing 10 km EPSG:3978 grid cell on one local calendar day. |
| Geography | Repository Ontario Fire Region study mask and existing grid. The label-dependent edge-cell rule is preserved for reproducibility and flagged for a later design sensitivity review. |
| Period | 2010–2019; May 1–October 31 in each year. |
| Issue time | 00:00 America/Toronto on the target calendar date. |
| Target | `ignition = 1` if at least one selected NFDB ignition is recorded in the cell on that target date; otherwise `0` means none recorded in the selected archive. |
| Join key | `(grid_id, ignition_date)`. |
| Size | 9,673 cells × 1,840 dates = 17,798,320 rows in the existing label universe. These counts describe the established product, not a newly rebuilt feature file. |
| Existing inputs | Calendar/solar, static CDEM terrain, prior-day CWFIS weather/FWI and strictly earlier NFDB ignition history, with coverage/quality metadata. |
| Time boundary | Dynamic observations must precede the issue day. Fitted transformations belong inside training partitions. |
| Forecast claim | Retrospective calendar-day benchmark. Date-only fire labels and retrospective archives do not establish exact rolling-24-hour or operational forecast truth. A local calendar day is not always exactly 24 hours because of daylight saving. |
| First output | Evaluated historical ignition probabilities and a small risk-map demonstration; no guaranteed risk thresholds or measured improvement are claimed yet. |

Final fire size, final perimeter, management response and future satellite observations stay out of ignition predictors. Keep missing weather distinct from physical zero and censored fire history. Preserve the existing schemas while reviewing identified defects; any changed grid/feature product needs a new version and audit.

## Existing baseline versus selected-source development

The existing historical baseline uses NFDB/CDEM/CWFIS. The selected seven-source development scope remains Ontario Fire Disturbance Point + Area, VIIRS, ERA5-Land, HRDPS, FBP 2024, selected SCANFI 2020 and MRDEM. Choosing a 10 km grid does not make those sources identical to the baseline or authorize backfilling modern fuel/forest maps into 2010–2019.

Use the historical implementation for the first benchmark. Treat selected-source additions and the historical-to-live weather bridge as separately versioned development work with source-date, unit, aggregation and availability checks. Keep VIIRS on the separate spread-validation/replay path.

The older 2.5 km Thunder Bay pilot remains outside this repository at `../data/processed/`. It is retained as evidence of spatial joining and feature engineering, not the active ignition grid and not a sufficient performance dataset.

## Development process

Use an **iterative, incremental process with explicit design review**. Each increment follows:

```text
Define the input/output and acceptance evidence
                    |
                    v
Review design and unresolved assumptions
                    |
                    v
Build one reproducible increment locally
                    |
                    v
Test modules and the integrated path
                    |
                    v
Evaluate results, document limits and choose the next increment
```

| Increment | Deliverable | Evidence required before calling it complete |
| --- | --- | --- |
| Week 1: scope and local setup | This contract/process document; persistent local repository. | User's 10 km decision recorded, source/time boundaries explicit, repository origin and eight remote branches verified. |
| Data readiness | Audited chosen historical label/feature inputs and reproducible environment/build paths. | Source/version registry, coverage/missingness profile, station-selection and edge-grid sensitivity decisions, partition plan. |
| Architecture milestone | Requirements-linked components, interfaces and decision records. | **Review Architectural designs for software** completed before expanding/changing implementation. A diagram alone is insufficient. |
| AI iteration 1 | Historical-rate and interpretable ignition baseline, followed by the agreed boosting candidate. | Chronological fit/validation/calibration/test separation; separate spatial experiment; training-only preprocessing; rare-event and calibration metrics. |
| AI iteration 2 | Measured improvement or justified retention of the simpler method. | Same evaluation contract, versioned experiments and documented limits. LightGBM remains a candidate alongside the repository's histogram-boosting plan; no choice is treated as an achieved result. |
| Application increment, overlapping AI work | Saved-model historical scoring and a small risk map; separate reviewed spread demonstration. | Repeatable inputs → features → saved model → predictions → display, integration checks and visible timestamps/limitations. |
| Later live increment | Compatible HRDPS input adapter and maintained weather/FWI history. | Issue/availability/valid-time rules, 10 km aggregation, variable/unit compatibility, state initialization and end-to-end live validation. |

Spread development proceeds alongside ignition work. It starts from the existing simulator/viewer, addresses the reproduced water-barrier crossing and final-perimeter-assisted fuel reconstruction, and then reruns replay evaluation. Overall saved results currently do not beat the simple baseline. Unit-test success does not close those scientific/design issues.

## Local work arrangement

- Active checkout: this `team_repository` folder, cloned from the shared GitHub repository.
- Local working branch: `codex/week-one-plan`, based on the reviewed main commit.
- All eight remote branches are available as local remote-tracking references. No remote branches were merged or modified by setup.
- Bring in only reviewed files needed for a task, or use a separate local branch/worktree; compare provenance and contracts before combining artifacts.
- Keep raw source downloads and deterministic large panels in their ignored paths; commit compact source registries, audits and documentation as appropriate.
- The existing Centennial pilot's files are preserved. The clone is independent of the temporary review mirror.
- The Week 1 changes stay local; no push or remote publication occurred.

## Week 1 completion checklist

- [x] Define the development problem and the ignition/spread split.
- [x] Record the input/output workflow and research-purpose limits.
- [x] Record the 10 km ignition decision and first historical benchmark contract.
- [x] Document the iterative process, increments and architecture-review milestone.
- [x] Store a persistent version-controlled local checkout and verify branch availability.
- [x] Update the development checklist and project context to point to this decision.

No development-only Week 1 item remains undocumented. Data audits, requirements elaboration, architecture review, training, fixes and application implementation belong to later increments and remain open. See the [all-branch review](../../reports/repository_review_2026-10-14/README.md) and [Weeks 1–5 checklist](../../reports/week_1_to_5_checklist.md) for their evidence/status.
