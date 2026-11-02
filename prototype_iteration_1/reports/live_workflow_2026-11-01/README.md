# Proposed workflow alignment — November 1, 2026

The local prototype now collects Ontario reported-fire locations and HRDPS forecast weather, joins reference districts, and records local notices. It also demonstrates regional intersections using the existing saved spread reconstructions. Live ignition and spread predictions remain unavailable; this implementation does not turn retrospective models into qualified live forecasts.

## What changed

| Proposed step | Implemented behavior | Remaining requirement |
| --- | --- | --- |
| Fetch Ontario active fires | Actual official feed collection: 9 reported incidents; exact source-ID reconciliation and retrieval provenance | Verified current perimeter and condition observation time; the feed used here supplies points |
| Fetch weather | Actual HRDPS 2026-11-01 18:00 UTC run; temperature, humidity, wind speed/from-bearing and preceding-hour rain | Accepted observed/overwintered FWI state and a trained/evaluated forecast-time feature contract |
| Combine vegetation, terrain and history | Existing model/data paths retained; 10 km ignition and separate 90 m spread grids | Current inputs must satisfy each model's contract before live inference |
| Predict ignition | Existing saved retrospective scores remain available and unchanged | Independent issue dates/seasons and accepted cross-source/model qualification; no cause classifier is implemented |
| Predict spread | Four historical fires at 1, 3 and 6 hours produce 12 saved reconstruction footprints | Current perimeter/time inputs and independently validated prospective spread performance |
| Identify affected regions | Geometry indexing and area intersections against 18 MNR reference districts | Current, appropriate community or response-area boundaries before operational interpretation |
| Generate alerts | 9 observation notices plus 12 reconstruction drafts; 21 unique local ledger records | Qualified forecasts, alert policy, recipient consent and authorized delivery integration |

The district archive is `LIO-2023-01-25`. It is a dated administrative reference, not verified current evacuation or community boundaries. Reported source districts are retained separately from spatial reference-district matches. Fire cause is a reported attribute, never a model prediction. No ember/spotting capability was added; the requested notification workflow is represented by local notices.

```text
Ontario reported fire points ----> reference-district lookup ----> local observation notices
                  |
HRDPS forecast --> nearest 10 km centroid weather context
                  |
          live model qualification gate
                  +---- incomplete: ignition = null, spread = null

Existing landscape/history ---> existing retrospective ignition studies
Saved 90 m spread reconstructions ---> 1/3/6 h footprints
                                  ---> district area intersections
                                  ---> local demonstration drafts
```

## Actual source evidence

The fire feed was retrieved at **2026-11-02 02:29:19 UTC** (November 1 in Toronto). This timestamp describes retrieval, not the last observation of an incident. All 9 records matched a reference district and a weather centroid within the explicit 20 km display cutoff. The hourly context is forecast weather at the nearest model-grid centroid, not a measurement at the fire. Six-hour availability is recalculated when the API is read; a snapshot does not remain fresh indefinitely.

Sources: [Ontario fire map service](https://ws.lioservices.lrc.gov.on.ca/arcgis3/rest/services/FFIM/Forest_Fire_Info_Map/MapServer/1), [official district catalogue](https://open.canada.ca/data/en/dataset/51dfb682-33e3-443b-b9ef-c683930bc44f), [official district ZIP](https://ws.gisetl.lrc.gov.on.ca/fmedatadownload/Packages/MNRDIST.zip). The district REST geometry request failed; the successful run uses the documented ZIP, with its package date and hash retained. Raw failed attempts remain local.

The new weather run was collected at 02:16:51 UTC and supports 9,111 research checkpoint cells. Those forecast-derived states remain untrusted for observed-state qualification. The prior measured source comparison still contains one archived run and 154,368 post-issue pairs; it is not independent live forecast-skill evidence.

See `sources.json`, `weather_manifest.json`, `sample_snapshot.json` and `runtime_inventory.json` for exact hashes, clocks and full local asset locations.

## Code and performance

`workflow_sources.py` collects fixed official endpoints, checks complete IDs and stores hashes. `live_workflow.py` validates inputs, indexes district geometry, builds footprints and publishes one complete JSON snapshot atomically. `research_alerts.py` uses deterministic identities and parameterized SQLite upserts; reruns preserve first-seen times and do not duplicate notices. Failures preserve the previous snapshot and publish a separate failed-refresh status. `workflow_view.py` displays the read-only result using text nodes for source strings.

`runtime_cache.py` removes repeated Parquet reads and full explanation-JSON parsing. Caches are bounded, keyed by file identity, invalidated after file changes and return copies to callers. Hash verification was already inexpensive and remains unchanged.

| Measured cell-detail lookup | Before | After |
| --- | ---: | ---: |
| Median of 12 repeated calls | 49.24 ms | 0.31 ms |
| First uncached call | 154.87 ms | 50.97 ms |

This is a small same-machine, repeated-key benchmark, not a production throughput or latency guarantee. Three existing historical/selected-source detail responses matched exactly. Raw timings and the baseline profile are retained. The legacy `p95_ms` evidence field is labelled as the maximum of 12 observations and should not be presented as a population p95.

## Verification and scope

- **197 tests passed**, including source errors/truncation, clock expiry, geometry areas, cache invalidation/copying, duplicate keys, notice revisions/idempotency, atomic failure preservation and API rejection of prohibited live values.
- **18 actual HTTP checks passed**, covering existing pages/scores/details/exports, live HTTP 503/null, the new workflow page/API/GeoJSON and invalid queries.
- New-page JavaScript passed syntax validation. Browser control was unavailable, so a fresh visual/accessibility rehearsal is still pending.
- Original final models/predictions/replay artifacts and the two prior qualification/weather audit reports were checked by hash; see `verification.json`.
- Static checks and direct code review were performed. The heuristic checker still reports medium complexity in validation/orchestration functions; its numerical grade is not a review certification. No independent human/agent review is claimed. New Python modules/tests were formatted with Black 26.10.0 without adding a runtime dependency.

No model was promoted or refit, no old final benchmark was rescored, no public notice was sent, and no recurring collector or cloud deployment was created. Current runtime deployment is a loopback process on the existing Mac. A clean-machine installation is not verified.

## Run locally

The full existing workspace and pinned assets are required. From the original CAPSTONE directory, refresh weather into a **new** output/report directory:

```sh
.venv/bin/python -m scripts.hrdps_live_weather --output-dir data/processed/hrdps_workflow_NEXT --report-dir reports/hrdps_workflow_NEXT --research-startup
.venv/bin/python -m scripts.live_workflow --workspace . --output-dir data/processed/workflow_NEXT --weather-dir data/processed/hrdps_workflow_NEXT
.venv/bin/python -m scripts.capstone_app serve --port 8771
```

Open `http://127.0.0.1:8771/workflow.html`. Collection is manual; restart a stopped server using the command above. A failed refresh does not change the original snapshot clock.

For repeatable assembly without refreshing the fire feed, add `--source-snapshot data/processed/live_workflow_2026-11-01_v3/raw` and use the pinned weather directory `data/processed/hrdps_live_workflow_2026-11-01`. This preserves the original source retrieval times and records `source_mode=reused_snapshot`; it is not a new live collection. Use a fresh output directory each time.

The Git folder contains code, tests and compact evidence. The approximately 387 MB weather download, district archive/shapes, SQLite ledger and full runtime assets remain local and are inventoried, not committed. The older submission ZIP has not been silently replaced with these additions. A Git-only clone needs those assets or a documented rebuild; copying this report alone does not install a runnable forecast service.
