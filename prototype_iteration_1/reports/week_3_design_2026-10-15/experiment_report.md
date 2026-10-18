# Ignition model comparison

Historical development experiment; reviewed October 16, 2026.

## Decision

Histogram gradient boosting is the provisional temporal candidate under the recorded pooled-average-precision rule. This is a development ranking, not operational acceptance. LightGBM is close; it has slightly higher AP within each individual validation year. Neither boosting model demonstrates satisfactory geographic transfer at the illustrative alert budget. Keep logistic regression as the simpler comparator.

## Common evaluation contract

All models use the unchanged historical v1 NFDB/CDEM/CWFIS panel. No selected modern fuel/forest product is backfilled into this older dataset. The 52.482010% weather missingness, station-candidate limitation, outcome-dependent edge-cell eligibility and unknown publication timing remain disclosed.

| Protocol | Eligible training rows / positives | Fitted sample rows / positives | Full validation rows / positives | Predictors |
| --- | --- | --- | --- | --- |
| temporal | 10,678,992 / 4,717 | 111,459 / 4,717 | 3,559,664 / 1,309 | 36 |
| inner_spatial | 6,760,896 / 3,251 | 70,985 / 3,251 | 463,312 / 156 | 31 |

Fit years are 2010-2015; validation years are 2016-2017. All positives and deterministic hash-selected approximately 1% of negatives are retained in fitting, with inverse negative-selection weights and unit positive weights. These weights restore population loss proportions; sampled fitting is not equivalent to full-data fitting. No class balancing is added. All validation rows retain natural prevalence. Logistic medians/indicators are fitted on the selected training sample; its scaler and loss are weighted. Both tree models retain NaNs. No random early-stopping split is used.

The inner geographic experiment uses deterministic 100 km blocks within the frozen outer development region, with a 20 km centre buffer: 6,124 training cells, 1,259 validation, 384 buffer and 1,906 outer reserved cells. It excludes all five fire-history predictors. The all-geography temporal experiment follows its separate original protocol. Neither reads 2018 calibration or 2019 final-test content. Earlier descriptive EDA exposed 2019 and is disclosed.

## Measured results

AP means scikit-learn average_precision_score, not trapezoidal PR-AUC. Top-budget precision/recall select ceil(1% of eligible cells) separately each day with deterministic hash tie-breaking. This budget is illustrative and not stakeholder-approved.

### temporal

| Model | AP | ROC-AUC | Brier | Precision at daily budget | Recall at daily budget | False alerts / 1,000 cell-days |
| --- | --- | --- | --- | --- | --- | --- |
| historical_rate | 0.00036773 | 0.5000 | 0.000367602 | 0.048% | 1.299% | 10.023 |
| logistic | 0.00193402 | 0.8075 | 0.000367416 | 0.328% | 8.938% | 9.995 |
| histogram_boosting | 0.00576444 | 0.8438 | 0.000366655 | 0.373% | 10.160% | 9.991 |
| lightgbm | 0.00568383 | 0.8416 | 0.000366737 | 0.347% | 9.473% | 9.993 |

### inner_spatial

| Model | AP | ROC-AUC | Brier | Precision at daily budget | Recall at daily budget | False alerts / 1,000 cell-days |
| --- | --- | --- | --- | --- | --- | --- |
| historical_rate | 0.00033671 | 0.5000 | 0.000336614 | 0.063% | 1.923% | 10.319 |
| logistic | 0.00104272 | 0.7359 | 0.000336604 | 0.063% | 1.923% | 10.319 |
| histogram_boosting | 0.00105177 | 0.7710 | 0.000336684 | 0.021% | 0.641% | 10.323 |
| lightgbm | 0.00094312 | 0.7717 | 0.000336858 | 0.021% | 0.641% | 10.323 |

The temporal histogram candidate reaches 133 of 1,309 recorded positive cell-days at the budget: recall 10.160%, precision 0.373%. Most alerts are false positives. Its daily-resampling 95% recall interval is 8.477%-12.034% (1,000 replicates). This measures variation across validation days, not independent-fire uncertainty or calibrated model uncertainty. No statistical superiority over LightGBM is established.

Inner geographic validation has only 156 positive cell-days. Historical-rate and logistic selections each reach 3; each boosting model reaches 1. Histogram AP exceeds logistic by only 0.00000905, while its Brier score and budget recall are worse. These results do not support geographic promotion.

### Year-level temporal stability

| Model | 2016 AP | 2017 AP |
| --- | --- | --- |
| historical_rate | 0.00032194 | 0.00041352 |
| logistic | 0.00248569 | 0.00172332 |
| histogram_boosting | 0.00900364 | 0.00328002 |
| lightgbm | 0.00903379 | 0.00334013 |

Both boosting models degrade in the second year. Pooled AP depends on ranking across years as well as within each year; a pooled winner need not win either year separately. The small ordering difference is not evidence of robust model dominance.

## Algorithms, frameworks, cost and challenges

| Candidate | Fixed settings and framework | Fit time temporal / inner | Cost and main challenge |
| --- | --- | --- | --- |
| historical_rate | Weighted training prior; sklearn DummyClassifier | 0.015s / 0.002s | Minimal CPU/storage; cannot discriminate cells, tie-breaking controls alerts. |
| logistic | Median/indicator + weighted StandardScaler; C=1, max_iter=2000, tol=1e-5 | 0.442s / 0.177s | Small CPU model, interpretable coefficients; sample median is unweighted, nonlinear relationships omitted. |
| histogram_boosting | sklearn; 150 iterations, learning_rate=0.05, 15 leaves, depth 6, min_leaf=100, L2=2 | 4.029s / 1.942s | CPU-compatible native missingness; small pooled edge, weak transfer and nonlinear explanation burden. |
| lightgbm | LightGBM; 150 trees, learning_rate=0.05, 15 leaves, depth 6, min_child=100, L2=2 | 0.788s / 0.562s | Fast CPU fitting; compiled OpenMP dependency and sample-weight/binning effects; no demonstrated geographic edge. |

Eight fits and validation/reporting completed in 40.76s with peak process RSS 2863.0 MiB on Apple M3 Pro, 18 GiB RAM, four threads. This excludes data acquisition/rebuilding and Python import time. No paid model API or GPU was used. RAM/runtime are measured for this bounded comparison, not the full provincial selected-source build.

| Temporal model | p95 model-only daily score, first 20 validation dates |
| --- | --- |
| historical_rate | 0.546 ms |
| logistic | 3.889 ms |
| histogram_boosting | 10.874 ms |
| lightgbm | 10.394 ms |

Timings include the ordered-feature helper, exclude feature loading/map/server/export, and do not prove application latency. Sampling, versions, seeds, settings and input/source hashes are stored in experiment_config.json; all metrics, per-year measures, intervals and timings are in model_comparison.json. Eight trusted-local joblib bundles and two full validation-prediction Parquets are stored under data/processed/ignition_models_week3_v1/week_3_design_2026-10-15. Paths and SHA-256 hashes are recorded for every bundle.

## Reproducibility and next promotion gate

Every bundle passes save/load score agreement. Maximum reload difference is 1.40e-9, below the 1e-6 absolute requirement. Two refits with the same fitting settings agree on the first 1,000 validation rows across all four models in both protocols; repeatability.json records measured deltas and distinguishes reporting/guard source changes. Completed outputs and model directories reject overwrite by default.

Calibration remains unfitted and final evaluation remains unscored. Hash-only verification confirms the reserved calibration/final-test files are unchanged; the final-test file remains read-only. Before a final performance claim, freeze any source/mask correction, selected hyperparameters/features, refit policy, 2018 calibration and alert rules. Score the final 2019 temporal/geographic experiments separately, once. No map, SHAP explanation, live adapter, deployed endpoint or risk category was generated by this experiment.
