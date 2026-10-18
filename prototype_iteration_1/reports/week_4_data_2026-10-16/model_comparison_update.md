# Corrected-weather model comparison

Completed October 16, 2026. Development validation only; 2018 calibration and 2019 final-test content remain unscored. All models were refitted with unchanged hyperparameters, sampling seed, negative weights and predictor allowlists.

| Model | v1 temporal AP | v2 temporal AP | v1 inner spatial AP | v2 inner spatial AP | v2 temporal recall at 1% daily budget |
| --- | --- | --- | --- | --- | --- |
| historical_rate | 0.00036773 | 0.00036773 | 0.00033671 | 0.00033671 | 1.299% |
| logistic | 0.00193402 | 0.00271247 | 0.00104272 | 0.00134612 | 9.015% |
| histogram_boosting | 0.00576444 | 0.00548892 | 0.00105177 | 0.00165749 | 9.549% |
| lightgbm | 0.00568383 | 0.00599798 | 0.00094312 | 0.00156264 | 9.778% |

The corrected source does not improve every candidate: histogram boosting pooled temporal AP falls, while LightGBM and logistic improve. LightGBM becomes the provisional temporal candidate under the existing pooled-AP rule. That is development selection, not a final-test or operational superiority claim. The same row-key sampling hashes make the unmasked v1/v2 comparison paired at the fitting-row level. Fixed model settings were not optimized for the new data.

| Model | v2 temporal precision / recall | v2 inner precision / recall | v2 temporal Brier | v2 inner Brier |
| --- | --- | --- | --- | --- |
| historical_rate | 0.048% / 1.299% | 0.063% / 1.923% | 0.000367602 | 0.000336614 |
| logistic | 0.331% / 9.015% | 0.084% / 2.564% | 0.000367632 | 0.000338897 |
| histogram_boosting | 0.350% / 9.549% | 0.063% / 1.923% | 0.000367426 | 0.000337553 |
| lightgbm | 0.359% / 9.778% | 0.021% / 0.641% | 0.000367290 | 0.000337403 |

The 1% budget remains illustrative and unapproved by an end user. Absolute precision, spatial stress results, daily bootstrap intervals and year-level metrics remain material limits; full values are in each model_comparison.json. No probability calibration, SHAP, risk categories, live ignition inference or model deployment is implied.

## Current-boundary sensitivity

| Model | Unmasked temporal AP | Boundary-only temporal AP | Unmasked inner AP | Boundary-only inner AP |
| --- | --- | --- | --- | --- |
| historical_rate | 0.00036773 | 0.00036699 | 0.00033671 | 0.00033724 |
| logistic | 0.00271247 | 0.00271486 | 0.00134612 | 0.00134934 |
| histogram_boosting | 0.00548892 | 0.00554706 | 0.00165749 | 0.00161986 |
| lightgbm | 0.00599798 | 0.00639386 | 0.00156264 | 0.00168435 |

This is an intersection with an independently constructed current-boundary centroid scenario. It changes the eligible population and removes some positive cell-days; differences are sensitivity results, not a directly paired performance gain or proof of historical eligibility. Outer geographic selectors remain fixed, with their roles intersected by eligibility. The current geometry is not the absent old pinned boundary snapshot.

## Source/feature decision

Retain v1 as the immutable published benchmark. Accept daily-available-station v2 as the corrected **development** weather method, with the declared 200 km cap and quality rules, and keep its own feature contract. Coverage sensitivity at 100/200/300 km is reported in the data audit; model results shown here use 200 km only, so no radius-optimality claim is made. Keep the current-boundary scenario distinct rather than silently replacing the original target population. Freeze any final refit/calibration/alert choices before final evaluation.

All sixteen new bundles pass save/load parity. Source, selector, sample/config hashes and full validation predictions are recorded separately. Existing Week 3 bundles/results remain unchanged. The updated comparison CLI accepts explicit data/contract paths and an optional boundary-only flag; no reserved-role access was added.
