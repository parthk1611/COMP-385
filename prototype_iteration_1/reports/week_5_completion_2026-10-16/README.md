# Week 5 local research completion

The corrected spread replay, selected-source 2025 study, live-readiness assessment and combined dashboard are implemented and verified locally. **126 tests pass. Live ignition acceptance fails and stays disabled**; this is a completed assessment, not an operational success claim.

Open [the dashboard](http://127.0.0.1:8767/) while its loopback server is running. Restart from CAPSTONE with `.venv/bin/python -m scripts.capstone_app serve`. The dashboard links both ignition studies, corrected incident reconstruction, exports and explicit live failure reasons. Start on a supported date, select a cell, inspect values/provenance, export that date, then switch to spread or live readiness.

- [Consolidated technical report](technical_report.md) and [PDF copy](Ontario_Wildfire_Technical_Report.pdf) document methods, actual results, limitations and appendices.
- [Corrected spread results](corrected_spread_results.json): 150 steps/22 fires, mean recall 0.3606 vs even growth 0.4018. Final-perimeter-assisted reconstruction only.
- [Selected 2025 study](selected_2025_results.json): within-season temporal test AP0.00049667, five/102 positives reached; separate geographic test one/14. Low precision; no cross-year/live qualification.
- [Live readiness](live_readiness.json): zero coincident ERA5/HRDPS reference days, zero trusted observed-state cells, and no accepted cross-source decision. Live endpoint returns503/probabilitynull.
- [Full test output](unit_tests_final.txt), actual HTTP/export/detail checks, browser observations, source snapshots, performance measurements and integrity/package ledgers support review.

The existing 2019 historical final evaluation remains frozen and unchanged. Original sources/older bundles and dated packages are preserved. No Git merge/push, production deployment, independent review/professor acceptance or external submission is claimed. Native Microsoft Project verification remains deferred. Unmet live M2 acceptance and optional research extensions remain explicitly outside the completed local research prototype.


```text
Historical model -> frozen 2019 scores -> historical map / exports
Selected 2025 sources -> within-season fit/calibration/test -> separate map
Pinned landscapes + incidents -> corrected reconstruction -> paired baseline
Recorded HRDPS + state -> readiness assessment FAILS -> live output unavailable
                          |
                          v
                  Combined local dashboard
```

Browser QA recorded a MutationObserver message on initial dashboard load. The captured stack ends in the desktop Electron sandbox, with no project-page URL; it is consistent with browser/host instrumentation. It persists in a fresh tab, so an empty console is not claimed. App flows pass, and the generated viewer also guards its optional theme observer. See browser_verification.json.
