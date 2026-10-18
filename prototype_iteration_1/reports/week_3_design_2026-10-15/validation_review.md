# Validation and critical review

Reviewed October 16, 2026. This is an implementer review with automated checks, not an independent reviewer sign-off. No independent agent or external-engine validation was run. The restricted research design is accepted locally; operational/live forecast acceptance is rejected.

## Checked outcomes

- Combined project/repository tests: **71 passed in 3.62 seconds**. The run covers 10 ignition-comparison contracts, four interface-schema checks, the existing weather/data tests, and 27 spread tests. `unit_tests.txt` preserves output. This is module verification, not application or scientific acceptance.
- Four new spread regressions failed on old propagation: one-cell horizontal/vertical water barriers, blocked diagonal contact, an empty active mask, and default repair policy. They pass after the scoped patch. Existing spread checks continue to pass.
- Replay/export CLI help executes. Corrected full replay is not run: raw landscape windows are absent. Old v1 replay scores/viewer remain unchanged and refer to old propagation.
- All eight fitted bundles pass save/load score parity. Maximum difference is 1.40e-9. Refit probe comparisons match exactly across both protocols (1,000 validation rows x four candidates each). This is a bounded repeatability check, not a full cross-platform result.
- Frozen reservation/selector/input hashes are checked before fitting. Calibration/final-test byte hashes match the materialization manifest; the final-test file remains read-only. The comparison entry point rejects reserved roles/years and does not parse their Parquet contents.
- Predictor allowlists, history exclusions for geographic fitting, source infinities, feature order, valid probabilities and completed-run overwrite protection have explicit guards. Model output is not treated as a calibrated or deployed forecast.
- Interface fixtures and negative cases check schema structure, failure/null handling, timestamps and forecast outcome-assistance restrictions. These schemas do not implement a serving endpoint or establish live availability.
- `pip check` reports no broken requirements. The complete environment snapshot, selected direct pins and hardware record are saved. Fitting uses four CPU threads on an 18 GiB Apple M3 Pro.

## Findings and disposition

| Finding | Action or retained restriction |
| --- | --- |
| Logistic save/load check originally demanded overly strict batch arithmetic agreement | Use rtol=1e-6 / atol=1e-8; observed reload error is below 1e-6 absolute requirement. No fitting hyperparameter was changed to improve validation scores. |
| Main script could overwrite a completed experiment | Reject existing comparison output or model directory; guard regression passes. Use a new output basename for each experiment. |
| Surface moves could skip barriers; empty active state restarted spread | Add touched-cell clearance and unconditional active masking; preserve 16 directions; regression tests pass. |
| Outcome-assisted repair was implicit | Default off; reconstruction drivers opt in and declare mode. Outcome-conditioned domain and retrospective daily weather still prevent forecast validation. |
| New code could be displayed beside old scores | Use a separate output directory and require matching propagation revision in exporter. Full v2 replay remains a later validation dependency. |
| Pooled candidate ranking could hide year/spatial weakness | Report both years, blocked results, natural prevalence and absolute alert performance. No robust/operational superiority is asserted. |
| Automated quality scan flags long orchestration/complexity | Preserve the scan results: ignition run() has 115 lines and estimated complexity 26; read_development estimated 16. These are maintainability debt in a bounded experiment, not passed quality gates. Its seed/magic-number and import-count heuristics include false positives (seed already has a named constant). No unrelated refactor was made after experiment source freeze. |
| Unpackaged partition exporter and absent live/map adapters | Mark implemented/materialized/planned states explicitly; no end-to-end portability or application latency claim. |

## Evidence limits and next work

Week 3 design deliverables and bounded comparison are complete locally. This does not complete Week 4 source preparation or Week 5 prototype acceptance. Station/mask corrections, compatible province-wide selected-source features, calibration/final evaluation, SHAP/map, corrected full spread replay and live causal weather remain unfinished. Independent team review and professor feedback are not claimed. Source hashes and a local patch/snapshot make the changes reviewable without merging or pushing branches.
