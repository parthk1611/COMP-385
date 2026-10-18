# Week 3 architecture decisions

These are local development decisions, not professor sign-off or release approval.

## ADR-01: Keep ignition classification separate from spread reconstruction

Accepted. A shared ingestion/provenance convention is useful; one shared target/model is not. The ignition dataset is a 10 km local calendar-day panel; spread is incident-conditioned propagation on 90 m cells, evaluated against selected 375 m satellite observations. Separate modules prevent final outcomes from leaking into ignition features and prevent a simulated horizon from being mistaken for validated accuracy. A single undifferentiated model was rejected because its target and source-time requirements are incompatible.

## ADR-02: Use a modular local batch architecture

Accepted for the historical prototype. Existing Python/file-based builders and serialized models are cheaper to operate and easier to audit than a feature-store/microservice platform for this team-scale capstone. The trade-off is explicit file manifests, manual orchestration and a later serving adapter. Paid AI APIs, LLMs, distributed training and cloud deployment do not solve the current source/target problems and are not required. The planned app interfaces are versioned now; they are not described as running endpoints.

## ADR-03: Compare LightGBM with the existing shortlist, rather than replace it by assumption

Accepted. Both boosting candidates support missing values and nonlinear interactions. The local experiment fits historical rate, logistic regression, histogram boosting and LightGBM on the same weighted training selection and evaluates the same complete validation population. Histogram boosting is the provisional temporal candidate by the predeclared pooled AP rule. LightGBM is close and has slightly higher within-year AP in both validation years; there is no established robust superiority. Histogram boosting avoids an additional model-runtime dependency for the chosen path. Neither nonlinear candidate has demonstrated acceptable geographic transfer at the illustrative alert budget. Keep logistic as an interpretable comparator and do not promote a spatial/operational model on these results.

## ADR-04: Preserve final-test isolation through nested geographic development

Accepted. Scoring the outer 2019 geographic test to choose a model would spend the reserved final test. Inner blocked validation inside the frozen outer development area allows a geographic stress test while retaining that reservation. The separate all-geography temporal experiment keeps its original contract. The cost is less fitting/validation support in the inner experiment and only 156 inner validation positives. Development scores and bootstrap intervals are not independent final performance estimates.

## ADR-05: Treat v1 as a fixed retrospective benchmark

Accepted with restrictions. Preserve raw nulls, source versions, quality flags and the documented station/mask defects. Reject modern fuel/forest/weather substitution into 2010-2019 without a new contract. The alternative of silently repairing or enriching v1 would prevent reproducibility and mix incompatible vintages. Week 4 must version station/mask corrections and source joins; final conclusions must describe the actual dataset used.

## ADR-06: Separate corrected spread code from archived reconstruction scores

Accepted. Barrier/active-mask defects are fixed, perimeter repair becomes explicit, and new outputs have a separate revision directory. Old scores remain old-code reconstruction evidence. A new exporter refuses mismatched scores. Forecast acceptance is rejected until outcome-independent domains/fuels, causal weather state and suitable observations are available. This restriction prevents a completed design review from becoming an unsupported forecast-performance claim.

## Review and change procedure

Any change to target, grid, predictor list, source vintage, missingness interpretation, cutoff, calibration map, propagation or observation mask requires a new version and a linked decision. Re-run the checks affected by that change. Freeze the complete selected model/calibration/alert contract before final-test scoring. Mark a decision superseded when replaced; retain its original evidence. The current candidate artifacts remain development-only.
