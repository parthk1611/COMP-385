# Lightning diagnosis: development validation, 2012–2016

## Scope

Analysis of existing coordinate-HGB predictions: baseline, 24-hour lightning, seven-day lightning, and both windows. No new model fitting, predictions, reserved-year scoring, or changes to training data. This is a retrospective development-data diagnosis, not an operational forecast or an independent confirmation of generalisation.

All 8,899,160 validation cell-days remain in the ranking universe: 9,673 cells on each of 920 days. Source ignition records collapse to 3,384 positive cell-days. Pure natural and pure human subsets exclude the three mixed N/H cell-days and 73 unknown-involved cell-days; those remain in the full analysis. Source cause codes are outcome descriptors, never model inputs.

## 1. Permitted lightning exposure is limited and nonspecific

| Cell-day group | Cell-days | Detected in 24h window | Detected in 7d window |
|---|---:|---:|---:|
| Natural-only positives | 1,748 | 300 (17.16%) | 921 (52.69%) |
| Human-only positives | 1,560 | 68 (4.36%) | 456 (29.23%) |
| Negative cell-days | 8,895,776 | 621,424 (6.99%) | 3,135,103 (35.24%) |

The seven-day window includes the 24-hour window. Both end at 03:00 UTC, one hour before local-midnight issue time during this fire-season panel. No target-day lightning is included.

Of the natural-only positives, 621 have seven-day exposure but none in the recent 24 hours; 827 (47.31%) have neither. Thus a physically relevant predictor does not mean that its usable pre-issue version covers every natural ignition. Natural-only positives have more detected exposure than negative cell-days, but millions of negatives also have exposure, especially over seven days.

These features contain no missing values on this validation slice. Nevertheless, zero means no detected exposure in the supplied source/window, not proven absence of physical lightning or proven sensor uptime. Density is spatially aggregated native-grid support, not a matched causative flash or necessarily an exact within-cell strike. Same-target-day lightning, detection limitations, holdover timing, and location/date errors remain possible explanations; this diagnosis cannot apportion them.

## 2. Existing models show a small recent-exposure ranking effect, not a large hidden benefit

For the 300 natural-only positive cell-days with recent 24-hour exposure:

| Model | Mean global daily rank (lower better) | Captured in daily top 1% | Captured in daily top 5% |
|---|---:|---:|---:|
| Coordinate baseline | 1,904.4 | 32 | 93 |
| +24h lightning | 1,856.8 | 35 | 92 |
| +7d lightning | 1,913.3 | 33 | 92 |
| +both windows | 1,856.2 | 40 | 94 |

The 24-hour model improves paired ranks for 183 of these cell-days, worsens 112, and ties five; its mean improvement is 47.6 positions among 9,673 cells. Mean rank improves in four of five years, but top-5% captures do not improve overall. This is a modest descriptive shift, not evidence of a reliable performance improvement.

Seven-day exposure without recent exposure is not rescued by the seven-day model: among those 621 natural positives, mean rank worsens by 26.2 positions, and top-5% captures fall from 167 to 165.

The apparent gains are not a large natural-fire improvement cancelled by human-fire losses. Across all natural-only positives, daily top-5% captures fall from 490 with the baseline to 479 with the 24-hour model. Human-only captures rise from 553 to 563. With both windows, the corresponding counts are 481 natural and 570 human. These are counts within the same full-grid budget, not cause-specific rerankings.

Budgets are 97, 194, and 484 cells per day for top 1%, 2%, and 5%. Fixed-budget captures use descending score, then ascending immutable grid ID. Mean ranks use the midpoint of score ties; full outputs also give capture expectations under random tie-breaking. No positive-only precision or AP is reported.

## 3. Interpretation and proportionate next steps

1. Keep the coordinate baseline as the default. These results do not justify promoting the lightning variants or doing more blind parameter searches.
2. For a further small investigation, inspect a bounded sample of natural positives with zero permitted exposure: distinguish the source's flash/discovery-date and location conventions where documentation permits. Never move the window into the target day just to make coverage look better.
3. If another feature experiment is wanted, audit a historically appropriate human-access layer such as roads or campsites before building features. That targets a different missing mechanism; historical coverage and availability must be established first. No such work was done here.
4. Cause-specific models would add complexity and need an agreed evaluation design. They are not an automatic remedy, and cause labels must not be supplied as predictors for unseen cell-days.

The checks here address cause/label/exposure alignment and saved-prediction ranking. They do not prove the absence of every modelling or source-data bug. This is post-hoc analysis of reused development years; it does not establish causality or statistical significance.

## Verification

Independent verification passed: all 3,384 positive cell-day source joins, 13,536 model/positive global-rank records, 48 exposure summaries, and 744 ranking summaries agree. Negative exposure counts were independently checked across 8,895,776 cell-days. All 103 protected existing files remained unchanged. No models were fitted and no new predictions or reserved-year scores were produced. Full evidence and output hashes are in the historical verification summary in this report; machine-readable results and aggregate tie-aware tables are retained in `results.json`; per-positive CSV/NPZ evidence remains generated-only and is not archived here.

## Archive layout

This report preserves the historical scientific account. `results.json` retains
all original primary fields, the original run configuration under
`recorded_configuration`, scientific JSON documents under `supporting_results`
(keyed by original filename), and CSV records under `tables` (original filenames;
all cells remain strings). Standalone execution-verification, resume, boundary,
and optional-dependency logs are omitted; the historical checks are summarized
above and were not rerun for this move.

## Recomputing the diagnosis

From the repository root, with this folder's requirements installed:

```sh
python -m experiments.ignition.lightning_diagnosis.experiment --help
python -m experiments.ignition.lightning_diagnosis.experiment \
  --cache data/interim/ignition_modeling_cache \
  --baseline-predictions artifacts/ignition_modeling/hgb_coordinates \
  --window-predictions artifacts/ignition_modeling/hgb_lightning_windows \
  --both-predictions artifacts/ignition_modeling/hgb_lightning \
  --features artifacts/ignition_modeling/hgb_lightning/lightning_features/ignition-weather-v2-cell-centres-lightning-cg-v1/features.npy \
  --events data/interim/ontario_fire_region_nfdb_ignitions_2010_2019.csv \
  --output artifacts/ignition_modeling/reruns/lightning_diagnosis
```

Requires the corrected cache and frozen grid, original saved fold NPZs for all
four variants, the existing cache-row-aligned two-column 24h/7d feature array,
and source ignition records. The window directory contains `24h_only` and
`7d_only` subdirectories. Fold filenames remain
`fold_<year>_iter_80_l2_1p0_leaves_15_min_100.npz`.

The program checks labels/probabilities, daily grid/date alignment, exact source
record-to-positive-cell-day reproduction, and exposure window containment. It
recomputes all 744 ranking and 48 exposure summaries without archived result
or verification inputs. Negative exposures use aggregate counts rather than
millions of Python strings. Import and help do not execute analysis. Outputs
include results/configuration JSON, aggregate CSVs and positive-cell-day CSV/NPZ;
the output directory must be new. No source manifests, protected-file hashes,
resume machinery, fitting, feature rebuilding, or reserved-year scoring is used.
Historical results and verification above predate this runtime refactor and
have not been rerun here; existing archived artifacts are not overwritten.

The [original modelling guide](../../../docs/modeling/README.md) retains the
core dataset and frozen-evaluation context.
