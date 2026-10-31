# Missed-fire audit: 2017 development geography

October 31, 2026. This diagnoses an already exposed development result. It neither fits a new model nor provides a new final evaluation. The existing serving models, alert capacity and prior final artifacts are unchanged.

## Finding and interpretation

The spatial development model put none of the 92 recorded positive cell-days in the held geography into its daily top 1% review set. This is **zero detections at that capacity**, not zero model probabilities. The best missed case ranked 14th on a day with 13 review slots; its calibrated probability was 0.341712%. The median positive rank was around the top 21.29% of eligible cells.

The audit found no internal grid, source-label or date alignment mismatch in the checked 2017 data. It does not establish that source coordinates, reported dates or archive completeness are error-free. All 92 held positive cell-days had declared station-weather support. Missing weather therefore does not explain these 92 misses. Coverage is not a guarantee of local measurement accuracy: station interpolation can smooth conditions between stations, but that remains a hypothesis to test.

| Check | Observed result |
|---|---:|
| Grid cells / fire-season dates | 9,673 / 184 |
| Total 2017 cell-days | 1,779,832 |
| Source event records / positive cell-days | 753 / 736 |
| Source keys absent from panel | 0 |
| Label / event-count mismatches | 0 / 0 |
| Independent event-to-cell projection mismatches | 0 of 753 |
| Duplicate cell-days / grid key-origin mismatches | 0 / 0 |
| Prior-day weather / Toronto-midnight UTC mismatches | 0 / 0 |
| Held geography cells / positive cell-days | 1,259 / 92 |
| Held review slots / detected positives | 2,392 / 0 |
| Held positives with declared weather support | 92 of 92 |

The same model found 25 of 442 positives in familiar training geography during 2017 (5.66% recall), versus 0 of 92 in the inner-validation geography. Neither group was fitted on 2017. Their populations differ, so this comparison describes geographic transfer rather than isolating its cause.

A uniform random selection reference at the same daily capacity expects about **0.95 hits**, with a **38.45% chance of zero hits**, assuming independent sampling without replacement within each day. This contextualizes the small number expected at 1% capacity. It is not a classifier significance test, evidence that the model equals random, or a reason to relax the acceptance rule.

## Label semantics

The 95 source event records behind the 92 held positive cell-days contain 79 N (natural) and 16 H (human) cause entries. No held record has the checked prescribed-burn flags. Two records elsewhere in the full 2017 legacy source have prescribed-burn flags. They cannot explain the held misses, but they motivate a separate, versioned wildfire-only target policy.

The [official NFDB point metadata](https://scifv.scf.rncan.gc.ca/downloads/nfdb/fire_pnt/current_version/NFDB_point_shapefile_metadata.pdf) defines CAUSE N, H and H-PB. FIRE_TYPE is agency-specific; the audit also checks the source's explicit `is_prescribed` and PB fields. Region/type codes must not be reinterpreted as causes. Unknown causes remain documented unknowns.

## Capacity sensitivity: diagnostic only

| Daily capacity | Positive cell-days found | Recall |
|---|---:|---:|
| 1% | 0 / 92 | 0.00% |
| 2% | 4 / 92 | 4.35% |
| 5% | 9 / 92 | 9.78% |
| 10% | 24 / 92 | 26.09% |
| 20% | 41 / 92 | 44.57% |

Increasing the budget uses more review slots. These rows are not a model improvement and do not replace the 1% primary policy.

## Evidence and scope

- `results.json`, `integrity.json`, `protocol.json`: counts, reconciliations, input/model hashes and fixed rules.
- `positive_case_audit.csv`: all 92 positive cell-days with rank, coverage and source-event attributes.
- `false_alerts.csv`: all 2,392 selected cell-days without a recorded positive label; absence of a record is not verified absence of fire.
- `monthly_diagnostics.csv`, `feature_distribution_comparison.csv`: descriptive checks, not causal explanations. Selected quality-feature ranges do not reveal an obvious extrapolation break; the sampled training ranges are not a full distribution-shift test.
- `tests.txt`: 158 combined prototype regression tests passed, including seven audit tests and three inference-demo tests.
- `code_review.json`: static checks; low-severity explicit-constant warnings remain. Direct local review is not independent approval.
- `source/`: exact audit and test snapshots. The protocol code hash identifies the executed script.
- `verification.json`: preservation checks against the earlier 31-file scientific snapshot.

The earlier audit directory without `_v2` predates the random-capacity reference. This v2 report is the current audit. Neither version changes the old benchmark.

## Reproduce locally

From `github_iteration_1/prototype_iteration_1`, with the pinned full development inputs restored:

```sh
../../.venv/bin/python -m scripts.missed_fire_audit --workspace ../.. --output-dir ../../reports/missed_fire_audit_repeat_01
```

Use a new output directory. The Git snapshot alone omits the full input panels and model binaries. Input hashes are checked before scoring; previously exposed 2017 development observations are used, not old final-period records. Date alignment does not prove that the modern archive was published at the historical issue time.

## Next step

Register a versioned target policy and weather-history feature experiment before fitting. Preserve current defaults and the legacy results. Compare improvements at the same capacity and on the same target; reserve genuinely new data before claiming independent final improvement. See `next_feature_experiment.md`.
