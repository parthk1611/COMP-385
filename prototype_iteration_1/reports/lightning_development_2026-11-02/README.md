# Past lightning development comparison

Completed 18 fits under `protocol.json`, registered before fitting. The earlier-fold rule retained the reference for both temporal and geographic protocols. Geographic hits at the fixed daily 1% capacity: reference 2/92, past-24h lightning 2/92, past-24h plus 7d lightning 3/92. Temporal variants each find 66/734. No model is promoted. The 2017 diagnostic is previously exposed development data.

See `../demo_readiness_2026-11-02/README.md` for interpretation, limitations and UI/demo verification. `results.json`, `rolling_results.json`, `selection_freeze.json`, `feature_audit.json`, `source_receipts.json`, reliability/daily CSVs and positive-case ranks provide the evidence. Large panels/models live in `CAPSTONE/data/processed/lightning_development_2026-11-02`.

Reproduction from `CAPSTONE/github_iteration_1/prototype_iteration_1`, with the full original workspace and pinned dependencies restored, using fresh output paths:

```sh
../../.venv/bin/python -m scripts.lightning_experiment --workspace ../.. --output-dir ../../reports/lightning_repeat --cache-dir ../../data/processed/lightning_repeat
```

This uses the verified prior wildfire-target cache and eight fixed free ECCC annual archives. It does not access reserved final fitting/scoring partitions. Source processing in 2026 does not establish historical publication availability.
