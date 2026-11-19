# Executed verification: retained coordinate model

## Clean model export

The current joblib export was recreated from clean commit
`1cff710d4ea388acfeefa72cdbd7bd17696db61d` before editing the browser verifier
or documentation. `model_metadata.json` records `working_tree_dirty: false`.
The updated verifier and learning-material edits are later working-tree changes,
not part of that model-training commit.

- Settings: 80 iterations, learning rate 0.1, L2 1.0, 15 leaves,
  minimum leaf size 100, seed 385; no class weighting, early stopping or calibration.
- Inputs: the ordered 39 persisted fields from
  `data/metadata/ignition_feature_selection_v1.json`; no appended duplicates.
- Training: all 12,458,824 development rows from 2010–2016.
- Corrected-cache version: `ignition-v1-weather-asof-global-date-coordinates-v3`.
- Full experiment-pickle comparison: zero differing predictions across all
  12,458,824 development inputs; maximum absolute difference **0.0**.
- Joblib reload probe: 1,024 inputs, maximum absolute difference **0.0**.

| Record | SHA-256 |
| --- | --- |
| Joblib model | `5dd1c909a9d0ea4903567ee66f4831d9e687e62156b6288812888ec3e830cb89` |
| Clean export metadata | `8f9a276cdd7d06b6a2eb52ae8d300381ba867656e5aecf136db70ae51c795e52` |
| Corrected-cache manifest | `ebc13ce6b473eebe1696ce571bba884a4408a01e60176062894ff3297282f696` |
| Both development prediction streams | `96093ef5fcd34f494c864b09287b86170ecfc1a16fa2c64c20986b3118c4dc43` |

Settings, features, source/cache hashes and environment are recorded under
`artifacts/ignition_modeling/retained_coordinate_hgb/` in
`model_metadata.json`, `training.json` and `verification.json`.
Matching development predictions establish reproduction, not held-out quality.
No 2017–2019 fitting, calibration, policy tuning or global scoring was added.

## Data and serving contract

The completed main-pipeline rebuild validated all 17,798,320 rows and 1,840
dates in the 51-column panel, then preserved all 39 inputs in the corrected
cache. The main pipeline and demo reject old 36-column caches and mismatched
model feature order/version. Earlier independent fixture and real-artifact
tests cover cache persistence, missingness/censoring, model parameters,
grid ordering, API behavior and full-precision CSV output.

The browser run below used the actual clean-export model and full cache.
Its metadata response confirmed 80 iterations, 39 inputs, the clean commit,
and `model_metadata.working_tree_dirty: false`.

## Executed browser checks

Ran the updated `ignition_demo/verify_browser.js` against the local server
using Playwright with system Chromium. Result: **PASS**.

- Retained 80-iteration/39-input model and illustrative cutoff policy.
- All 39 inspector inputs; selected cell retained across date changes.
- Next-day navigation and both May/October fire-season limits.
- Lower cutoffs preserved or increased alert counts.
- Observed/alert-only overlays, zoom/reset and recorded-ignition filter.
- July 2 CSV: 9,673 rows, 9,673 unique cells and the correct date throughout.
- Invalid API date returned 400.
- No JavaScript page errors.

| Viewport width | Page width | Map width |
| ---: | ---: | ---: |
| 1440 | 1440 | 1000 |
| 1024 | 1024 | 684 |
| 390 | 390 | 352 |

No page-level horizontal overflow occurred. Desktop and mobile screenshots
were visually inspected. Generated evidence: `output/playwright/verification.json`,
`desktop.png`, `map-inspector.png`, `mobile.png` and the downloaded CSV.
These files are ignored generated artifacts.

## Known map limitation and historical evidence

The pinned Ontario boundary asset is unavailable. The map displays the
existing **frozen 10 km grid footprint**, explicitly labelled as such.
No checksum-mismatched boundary was substituted; the pinned manifest is unchanged.

`reconstruction_evidence.json`, the earlier presentation and the original
published 2019 metrics describe the historical 40-iteration reconstruction.
They are not current retained-model performance results. The current app
uses illustrative fixed cutoffs (default 0.001, or 0.1%), not the old F2 policy.
The old deck was not regenerated as part of this verification.
