# Week 3 - AI capability design and evidence

Completed locally October 16, 2026; the folder retains its October 15 start date. The design addresses the supplied COMP 385 algorithm/framework shortlist and AI capability design requirements. It does not claim course submission, professor approval, independent sign-off or operational readiness.

## Open first

- `week_3_design_report.pdf`: integrated design, measured comparison, critical spread review, decisions and validation limits.
- `technical_design.md`: editable architecture, three ASCII workflows, module/component table, input/output/time/unit contracts and requirements traceability.
- `experiment_report.md`: common fitted comparison, actual counts/settings, natural-prevalence metrics, costs, yearly stability and interpretation.
- `spread_design_review.md`: implemented-model departures, corrected defects, outcome/time restrictions and unperformed real-fire validation.
- `decisions.md`: six architecture decisions, alternatives and version/change policy.
- `validation_review.md`: 71 passing tests, repeatability, review findings and explicit acceptance limits.

The development checklist is `../week_1_to_5_checklist.md`. Week 3 technical deliverables are complete locally. Week 2's native Microsoft Project verification remains explicitly deferred by the user. Week 4/5 implementation and validation remain visibly open rather than being treated as design completion.

## Evidence ledger

| Evidence | Location / meaning |
| --- | --- |
| Pre-implementation constraints | `preimplementation_review.md`; bounded historical review before source changes |
| Model settings and input/source hashes | `experiment_config.json` |
| All eight fitted results and model hashes | `model_comparison.json` |
| Schema and example fixtures | `interfaces.schema.json`, `interface_examples.json`; examples are illustrative, not actual app responses |
| Full geographic development selector | `inner_spatial_partition_v1.csv`; outer reservation preserved |
| Per-day alert results | Eight `*_daily_alerts.csv` files; fixed illustrative 1% capacity |
| Refit/reload verification | `repeatability.json`, model comparison model records; first 1,000 rows per protocol for refit check |
| Reserved-file integrity | `reserved_integrity.json`; hash-only check, not content parsing |
| Test/regression output | `unit_tests.txt`, `spread_regressions_before.txt`, `spread_regressions_after.txt` |
| Runtime / portability | `hardware.json`, `environment.lock.txt`, source-snapshot requirements |
| Critical code scan | `code_quality_ignition.json`, `code_quality_spread.json`; heuristic findings are disclosed, not a clean quality sign-off |
| Version evidence | `branch_snapshot.json`, `team_repository_changes.patch`, `source_snapshot/`, `artifact_manifest.json` |
| Model directory | `../../data/processed/ignition_models_week3_v1/week_3_design_2026-10-15/`; eight bundles and two full validation-prediction Parquets |
| Distribution | `week_3_review_bundle.zip`; report, editable evidence, source snapshot/patch and eight bundles; excludes large raw/partition/prediction data |

The `model_comparison_first_run.json`, first-prediction probes and `development_run_before_review/` preserve earlier reporting/review evidence; the root `model_comparison.json` is the final primary result.

Only trusted locally produced joblib bundles should be loaded. Hash/version checking is required; arbitrary uploaded joblib files are unsafe. The bundle preserves source changes without committing, merging or pushing branches. Root-project source and team-repository edits are also retained in place.

## Reproduce on this Mac

Run one command at a time in Terminal. The local `.venv` and inputs already exist. Download/acquisition and the one-off Week 2 partition export are separate prerequisites; this is not a clean-machine one-command build.

```sh
cd /Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE
.venv/bin/python -m pip check
.venv/bin/python -m pytest tests team_repository/tests team_repository/capability_2_fire_spread/tests -q
.venv/bin/python -m scripts.ignition_comparison --output-dir reports/week_3_repeat_v2
```

The last command deliberately requires a new, unused output basename and corresponding model directory. It validates manifests and reads only 2010-2015 training and 2016-2017 validation. It does not fit calibration or score final testing. Existing published results must not be overwritten. To recreate the comparison environment elsewhere, use Python 3.13 and `environment.lock.txt`; native geospatial/OpenMP dependencies may require matching platform packages. See the hardware record and known unpackaged partition-export limitation.

The spread replay/export `--help` commands were exercised. A full corrected replay is intentionally not listed as a runnable demonstration until the manifest-pinned ignored fuel/terrain windows are restored. Its new default output is `simulation_surface_v2`; old archived scores must not be copied into it.

## Result and next development gate

Histogram boosting leads pooled temporal AP (0.005764 versus historical-rate 0.000368) but has only 0.373% precision and 10.160% recall at the illustrative daily capacity. LightGBM is close and slightly stronger within each year. Inner geographic tail-alert performance is weak. There is no operational or geographic promotion.

Next: version station/mask corrections and compatible selected-source feature joins; freeze a refit/calibration/alert protocol; perform reserved final evaluation; build the historical map/explanation workflow. Separately restore landscape windows, recompute corrected spread replay and review its viewer. Live HRDPS/FWI availability/state and outcome-independent forecasting require their own accepted adapter/design. No LLM, paid AI API or alternative spread engine was integrated.
