# Week 5 — historical ignition prototype increment

Completed locally October 16, 2026. The frozen final refit, 2018 calibration, one-time 2019 evaluation, first-day TreeSHAP explanations and interactive historical risk map have executed. **118 tests pass. Week 5 overall is still in progress:** corrected spread replay, compatible selected-source modelling and live acceptance remain open.

## Demonstration

Open [the self-contained map](historical_ignition_map.html). It contains 184 May–October 2019 days and all 9,673 historical 10 km cells. No external map service, account, paid API or internet connection is required by the HTML. The file is about 52 MB because its complete keyed daily predictions are embedded. A loopback-only server is currently serving it at [the local preview](http://127.0.0.1:8766/historical_ignition_map.html); that preview depends on the local server remaining running.

1. Start on May 1, 2019, chosen as the earliest final date before inspecting outcomes.
2. Select a cell, or focus the map and press the right arrow. Its probability and source-coverage status appear.
3. On May 1, inspect the three strongest local raw-log-odds TreeSHAP contributions. These explain the model, not causes or changes in calibrated probability. Contributions plus the baseline were checked against raw model margins for every first-day cell.
4. Choose a date or use Next day. Factor details are explicitly unavailable for later dates; they are not copied from May 1.
5. Optionally show recorded positive cells for retrospective comparison. Probability bands are numerical ranges, not invented approved danger categories.

Browser verification checked default/date navigation, cell selection, probability/factor rendering, the recorded-start toggle and captured console errors (none). This is a browser smoke test, not full accessibility/performance/field validation. [UI observations](browser_verification.json).

## Frozen experiment

The [protocol freeze](protocol_freeze.json) was written before new 2018/2019 partition reads. It locks the corrected Week 4 four-daily-valid-station/200 km source method, original 9,673-cell label universe, LightGBM hyperparameters, deterministic approximately 1% negative sampling with inverse population weights, predictor allowlists and illustrative 1% per-day alert budget. Current-boundary sensitivity remains a separate development result; no new boundary was selected from final labels.

The temporal model refits on all 14,238,656 development rows from 2010–2017 through a 148,407-row weighted fitting sample. The separate spatial model refits only on 11,433,024 spatial-development rows (119,558 sampled), excludes all fire-history features and never trains on the reserved geographic test cells or buffer. There are 36 temporal and 31 spatial predictors. No ordinary transform or base classifier fits on calibration/final years.

The identical frozen weather helper constructs separate corrected 2018 and 2019 partitions, preserving all original keys/labels and strict previous-day weather. Calibration has 1,779,832 rows (16.619% missing station support); final testing has 1,779,832 rows (5.883% missing). Original v1 files remain unchanged/read-only where applicable. The Week 4 data stays unchanged; no modern landscape or forecast weather is backfilled.

Calibration uses a prespecified positive-slope logistic map of clipped raw logits, fitted at natural 2018 prevalence. Slope is bounded [0.000001,20], intercept [−50,50], clipping 1e−12, with a fixed L-BFGS-B optimizer. Both fits converged. This is a declared custom recalibration, not a claim of identical sklearn internal Platt smoothing. The [official calibration guidance](https://scikit-learn.org/stable/modules/calibration.html) supports separate base-model/calibration data and describes sigmoid assumptions; severe imbalance/source shift can still limit calibration. The calibration-fit diagnostics are in-sample map-fitting diagnostics, not unbiased validation.

After base/calibrator artifacts were saved and passed reload parity, their hashes and all alert decisions were sealed in [the final-evaluation freeze](final_evaluation_freeze.json). Only then were 2019 content and targets used for final evaluation. A one-time marker prevents silent rescore/tuning. Existing broad descriptive EDA had previously exposed 2019; this is reserved from new training/tuning, **not a pristine never-inspected holdout**. Both actual read/scoring stages are now complete; earlier dated Week 4 statements about unopened content remain historical snapshots.

## Final 2019 results

AP is average precision, not ordinary accuracy or trapezoidal PR-AUC. Every variant uses the same eligible keys and fixed daily alert budget. The constant historical-rate baseline is the appropriate refit-training event prior for that protocol. “Raw” is the selected base model before the 2018 map.

| Protocol | Variant | Rows | Positive cell-days | AP | Brier | Recall at budget | Precision at budget |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| temporal | training_prior | 1,779,832 | 509 | 0.00028598 | 0.000285919 | 0.982% | 0.028% |
| temporal | uncalibrated | 1,779,832 | 509 | 0.00352195 | 0.000286241 | 12.377% | 0.353% |
| temporal | calibrated | 1,779,832 | 509 | 0.00352195 | 0.000285728 | 12.377% | 0.353% |
| spatial | training_prior | 255,208 | 74 | 0.00028996 | 0.000289893 | 0.000% | 0.000% |
| spatial | uncalibrated | 255,208 | 74 | 0.00134303 | 0.000290026 | 6.757% | 0.194% |
| spatial | calibrated | 255,208 | 74 | 0.00134303 | 0.000289967 | 6.757% | 0.194% |

The calibrated temporal model reaches **63 of 509** positive cell-days: **12.377% recall**, **0.353% precision** at the illustrative daily budget. Day-resampling 95% recall interval: **9.272%–15.821%**. Most alerts remain false positives. AP is about 12.3 times the constant-prior AP, but this is not an operational-readiness threshold. Calibration improves Brier versus raw and only slightly versus the constant prior; overall mean predictions still exceed 2019 prevalence. No strong probability reliability is claimed.

The separate geographic test reaches **five of 74** positives across 1,387 withheld cells: **6.757% recall**, **0.194% precision**; day-resampling recall interval **1.515%–12.500%**. Its calibrated Brier is worse than the constant prior. The 2018 map therefore does not demonstrate reliable geographic probability transfer. No model reselection or post-final recalibration was performed.

The intervals resample days, not independent fires, and do not capture every source of temporal/spatial dependence. Full ROC-AUC, log loss, fixed-bin counts, support subgroups and daily alerts are in [the measured final JSON](final_evaluation.json). The no-weather spatial subgroup contains zero positives, so class-sensitive metrics are explicitly undefined. This does not prove safety where weather is absent.

![Final fixed-bin diagnostics](final_calibration_diagnostics.png)

## Data flow

```text
Frozen Week4 source / feature / model choices
    -> refit separate temporal and geographic base models on 2010–2017
    -> corrected 2018 weather / unchanged labels
    -> fit two declared calibration maps, save/load check
    -> seal base + calibrator + alert policy hashes
    -> corrected 2019 weather / unchanged labels
    -> one-time temporal and withheld-geography evaluation
    -> saved keyed predictions + additive first-day explanations
    -> self-contained historical map / browser smoke test
```

## Files and repeatability

- `scripts/week5_ignition.py`: explicit role/year guards, frozen dependency checks, reserved weather join, final refit/calibration and one-time scoring.
- `scripts/build_ignition_map.py`: keyed map assembly; duplicate/missing/invalid scores reject rather than becoming zero risk.
- `tests/test_week5_ignition.py`, `tests/test_ignition_map.py`: eight new tests for role isolation, freeze requirement, monotonic finite calibration, bad joins/timing and keyed map integrity.
- `data/processed/ignition_weather_v2_reserved/`: versioned corrected calibration/final partitions and manifests.
- `data/processed/ignition_models_week5_v1/`: two calibrated bundles, two final-prediction Parquets and first-day explanation JSON.
- This directory: frozen protocols, configuration/code review, calibration/final results, map, plot, test logs, source snapshots and integrity/package ledgers.

The combined local and repository suites pass **118 tests**. Review was an implementer pass plus automated quality scanning; long functions/complexity remain debt, and independent sign-off is not claimed. The local `.venv` and pinned source files are required. A fresh workspace can execute `python -m scripts.week5_ignition calibrate`, then `python -m scripts.week5_ignition evaluate`, then `python -m scripts.build_ignition_map`; completed paths/final marker deliberately reject overwrites. Do not rerun/tune on 2019. Opening the retained map or inspecting already-saved predictions is a demonstration, not a new model-selection experiment.

## Remaining Week 5 work

- Restore the missing landscape windows and rerun the corrected spread reconstruction; archived old-code replay scores must remain labelled as such. An outcome-independent, causal-weather spread forecast is a further separate experiment.
- Freeze a suitable evaluation design/data sufficiency policy for the separate selected 2025 panel before modelling. The one-year panel is not made ready merely by calibrating the different historical benchmark.
- Validate ERA5/HRDPS source compatibility and trusted observed/overwintered FWI state before live ignition inference. Current research weather checkpoints cannot satisfy that gate.
- Integrate the separately evaluated capabilities and verify the remaining application requirements. No live-warning endpoint, approved danger labels, uncertainty model, independent team/professor acceptance or production deployment is claimed.

No Git merge/push, external submission or synced-source edit was performed. The user's native Microsoft Project verification remains deferred. This is a completed historical prototype increment, not a claim that every Week 5 acceptance item is done.
