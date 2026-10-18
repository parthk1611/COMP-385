# Data decisions and implementation handoff

This closes the Week 2 investigation of source suitability. It does not certify that every selected source is province-wide, historically eligible or operationally integrated. The original broad acquisition/integration item remains partial under Week4 until those builds exist.

## Decisions recorded now

| Decision | Evidence and action |
| --- | --- |
| Retain the 10 km historical baseline | Keep the 2010–2019 NFDB/CDEM/CWFIS panel as a reproducibility benchmark. The seven selected source groups remain the enrichment/live development scope, rather than silently replacing these historical inputs. |
| Preserve original fire labels | Cross-reference by normalized identifier/year, then require matching recorded date and 10 km cell for an unambiguous correspondence. Of 8,109 NFDB source rows, 8,107 have exactly one strict provincial match. Two conflicts are quarantined for review; no automatic label replacement occurs. |
| Preserve repeated identifier instances | The retained NFDB events have 8,105 distinct IDs and eight rows in repeated-ID groups, at different dates/locations. Do not deduplicate on ID alone. Provincial point identifier/year keys also repeat; preserve source OBJECTID and instance rows. |
| Treat agency perimeters as final outcomes | Full area input has 2,751 records: 2,673 IFR, 42 OFR and 36 PB. There are 27 invalid geometries. Keep raw geometries unchanged; any repaired geometry needs a derived version and repair flag. Perimeters cannot establish intermediate fire fronts or ignition predictors. |
| Keep dates as dates | There are 49 missing point start dates and 14 year/start-date disagreements. Preserve quality flags. UTC serialization of a provider date does not establish an ignition clock time or a historical availability timestamp. |
| Retain and disclose the v1 mask | Current official boundary covers all 8,109 retained event locations, but 25 retained grid-cell centres fall outside it. This is consistent with the edge-cell design needing review, not proof of exact agreement with the old boundary snapshot. Keep the v1 baseline; require a label-independent grid sensitivity experiment before generalization claims. |
| Do not substitute a changed boundary archive | Current official FIRERESP ZIP contains an OpenFileGDB, not the Shapefile expected by the older downloader. The current archive hash differs. It was decoded into a separate audit location, never represented as the old pinned file. |
| Preserve weather missingness | Rebuilding v1 is a reproducibility exercise, not a correction of its nearest-station candidate problem. Retain all weather/history quality flags; a corrected station-selection method requires a new feature version and comparison. |
| Restrict modern landscape use | FBP 2024 and SCANFI 2020 are not contemporaneous predictors for an unqualified 2010–2019 forecast. Use only in explicitly fixed-landscape retrospective studies or later eligible periods with publication/availability records. No source switch is authorized by this audit. |
| Keep satellite gaps explicit | The processed 300,601 VIIRS detections are matched observations, not all Ontario fires or continuous perimeter truth. Missing detections are not negative fire labels. |
| Separate live weather acceptance | A late-retrieved HRDPS sample proves decoding. It does not implement issue-time run selection, earth-relative wind verification, rolling rainfall or FWI state. Require those before live inference. |

## The two cross-source conflicts

- `ON-2012-PAR18`, June 19, 2012, NFDB cell `ofr10km_1130000_-240000`: the identifier/year candidate is provincial OBJECTID 33505, but recorded date/cell do not satisfy the strict rule.
- `ON-2015-THU5`, October 30, 2015, NFDB cell `ofr10km_410000_110000`: candidate OBJECTID 744625 does not satisfy the strict date/cell rule.

These two baseline records remain unchanged and flagged, pending source-specific adjudication. The [complete correspondence table](nfdb_ontario_adjudication.csv) accounts for every retained source row; [raw candidate pairs](nfdb_ontario_key_reconciliation.csv) retain one-to-many relationships. [Point/area keys](point_area_key_reconciliation.csv) and [full source profiles](ontario_point_area_full_profile.json) retain unmatched keys and quality results.

## Data-preparation work still required

1. Review and version the station-selection correction and label-independent mask; then rebuild and compare with reproducible v1.
2. Acquire the remaining province-wide selected-source coverage for a declared eligible modelling period. Keep the inspected sample extents distinct from whole-source coverage.
3. Scale and join the tested pilot ERA5 rain/RH/wind/FWI adapter, retaining its explicit standard-noon, startup, missing-state and cutoff rules. Pilot decoding/tests are complete; provincial execution and training/live parity remain open.
4. Build HRDPS available-run selection, wind rotation, sufficient forecast leads, recent-weather bridge and FWI state.
5. Enforce the reserved evaluation selectors inside fitting; fit preprocessing only on training partitions.

These are open Week 3–5 implementation/acceptance tasks, with the broad source-readiness item still visibly partial in the checklist. No model was trained or source defect fixed by producing this handoff.

## Data-adapter architecture review before implementation

The remaining adapter work uses existing rasterio/pandas and the repository's published-reference-tested FWI equations. Preserve raw files, fixed source versions, the existing 10 km grid and the original v1 benchmark. Write supplementary selected-source outputs to separate versioned paths. ERA5 rainfall must be decoded across file/month boundaries; weather remains retrospective. Use hourly ending timestamps, explicit standard-noon offset, past-only feature cutoffs, missingness propagation and declared seasonal startup. State-based FWI is invalid after a missing required update until a new declared startup or trusted persisted state. HRDPS must retain issue/retrieval/valid times and component orientation; run time alone cannot prove historical availability. No trained model or operational forecast will be claimed by adapter tests. The overall application/AI architecture review remains a separate Week 3 milestone.
