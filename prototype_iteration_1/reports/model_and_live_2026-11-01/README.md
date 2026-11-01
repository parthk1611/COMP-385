# Model and live-forecast development update

November 1, 2026. Both requested workstreams were implemented and tested. The serving-model decision remains **retain defaults**; the live decision remains **unavailable**.

| Workstream | Completed work | Result | Decision |
|---|---|---|---|
| Geographic generalization | New wildfire-only target, rebuilt history, dated 3-/7-day FWI/DMC features, 12 forward-fold fits and six calibrated development refits | Spatial AP 0.00232426→0.00284508; detections remain 2/92 at the same 1% capacity. Temporal detections remain 66/734. | No replacement passed the required development rule; no new final generalization claim. |
| Live qualification | Downloaded matched ERA5-Land and CWFIS reports, checked exact cell-time/source clocks, measured weather differences, inspected station-code consistency, hardened state and API guards | 154,368 post-issue pairs from one archived run; trusted issue-verified grid state remains 0 | Weather-overlap blocker narrowed; live ignition stays HTTP 503/null. |

Read the [full feature experiment](../weather_history_2026-11-01/README.md) and [live qualification report](../live_qualification_2026-11-01/README.md). The latter states the exact remaining data and protocol requirements. Evidence includes fixed-capacity metrics, calibration tables/plot, conditional uncertainty, source manifests, tests, static/direct review and HTTP checks. All 31 previously protected scientific files retain their hashes.

The 2/92 reference is from a new target/refit and must not be presented as a weather-feature improvement over the older 0/92 result. Within this new comparison, history finds **2 versus 2**. Similarly, the new reference has 734 temporal positives while the older target had 736. Keep the denominators and study versions together.

## Next action

Keep the simpler weather-history candidate for further registered development. The first priority is geographic detection at the agreed review capacity, not a larger frontend. The prospective 2027 evaluation is reserved but not acquired or scored; previously exposed periods remain development evidence.

For live work, obtain authoritative grid/noon state lineage and receipt timing, preserve observed versus forecast state, build the intended source/issue/target contract, and collect repeated source-matched cases before a model acceptance decision. One matched weather episode does not establish live ignition skill.

## Professor update

“We implemented a time-safe weather-history experiment and a versioned wildfire-only target, tested them with forward-year and geographic development splits, and retained the existing models because fixed-capacity detection did not improve. We also obtained actual forecast/reference overlap and added strict state and API checks. The prototype has 180 automated tests and 14 fresh HTTP checks passing. Live forecasting remains unavailable until state lineage and source/issue-time model validation pass.”

The historical-demo deck remains a dated October 31 artifact. Use this update alongside it when presenting new progress. No cloud/production deployment, external approval, fresh visual rehearsal or new independent final test is claimed. Native Microsoft Project verification remains deferred.
