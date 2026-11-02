# Physical-feature geographic development comparison

Completed 9 fits under `protocol.json`, registered before fitting. All fitting and calibration exclude the inner-validation geography and buffer. The exact matching reference reproduces the preceding lightning experiment.

At fixed daily 1% capacity on the exposed 2017 diagnostic: reference 2/92, physical logistic 2/92, constrained LightGBM 5/92. The constrained model improves diagnostic AP from 0.0023242605 to 0.0035090156, but it finds only 0 and 4 positives on the earlier 2014/2015 folds versus the reference’s 0 and 7. The frozen selection retains the reference. No independent generalization or live qualification is established.

See `../demo_readiness_2026-11-02/README.md` for the combined table, sources, limitations and demonstration instructions. `results.json`, `rolling_results.json`, `selection_freeze.json`, `support_diagnostic.json`, daily/reliability CSVs and positive-case ranks preserve the evidence. Large models/predictions remain in `CAPSTONE/data/processed/geographic_transfer_2026-11-02`.

From `CAPSTONE/github_iteration_1/prototype_iteration_1` with the full workspace and completed lightning cache, use fresh output paths:

```sh
../../.venv/bin/python -m scripts.geographic_transfer --workspace ../.. --output-dir ../../reports/geographic_transfer_repeat --cache-dir ../../data/processed/geographic_transfer_repeat
```
