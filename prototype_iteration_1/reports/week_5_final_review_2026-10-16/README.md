# Ontario Wildfire - final local technical package

Weeks 1-4 development and the Week 5 local research prototype are complete. The final review adds concrete request/provenance/selection fixes, 129 passing tests, warm browser/API timing and a requirement-by-requirement acceptance record. Live M2 qualification remains unmet. Independent team/professor/field/user approval is unverified; native Microsoft Project verification remains user-deferred.

Read `final_technical_report.pdf` or editable `final_technical_report.md`, then `acceptance_record.md`. Exact results and open scientific limits are retained. `code_review.md`, test/HTTP/browser/performance evidence, source patches and hashes support the final application revision. No new real-data fitting, final scoring or retuning took place in this closeout.

## Run on this Mac

1. In Terminal, enter: `cd /Users/parthkevadiya/Desktop/Centennial/sem-6/CAPSTONE`
2. Start: `.venv/bin/python -m scripts.capstone_app serve --port 8768`
3. Open http://127.0.0.1:8768/ . If that port is already serving this reviewed revision, use it directly.
4. Choose Historical or Selected sources, click a grid cell, then request details. Change the date and verify old factors clear. The first evaluated day has saved factors; other days explicitly show unavailable factors.
5. Export a date as CSV/GeoJSON. Switch to corrected spread reconstruction and inspect its banner and 1/3/6-hour controls. Open Live readiness to see why live scoring is unavailable.
6. Run tests: `.venv/bin/python -m pytest tests team_repository/tests team_repository/capability_2_fire_spread/tests -q`

The compact review ZIP is an evidence/source delivery, not a complete redistribution of national raw rasters or full prediction/feature Parquets. Those pinned caches are retained in this local CAPSTONE workspace and are required for API/export reproduction. Self-contained study HTML maps remain in the original research evidence. A clean-machine demo requires restoring the listed caches and pinned environment; clean-machine portability has not been certified. Do not rerun frozen training/final evaluation to improve results.

## Remaining gates

- Live scoring: no paired ERA5/HRDPS reference dates, no trusted observed/overwintered FWI state, and no accepted source/issue-time qualification.
- Scientific performance: low ignition precision/weak geographic transfer; corrected reconstruction remains below the baseline. Changing code or relabelling outcomes cannot establish forecasting skill.
- External checks: independent user/field/team/professor acceptance; native Project verification deliberately deferred.
- Optional research: spread ensembles, DPV treatment planning and new outcome-independent forecasting experiments.

The supplied course content was checked. No separate unseen marking rubric, signature, professor approval, external submission, production deployment or Git push/merge is claimed. See the acceptance record for every FR/NFR and each week's development status.
