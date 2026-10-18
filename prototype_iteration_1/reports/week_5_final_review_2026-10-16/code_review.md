# Final application code review

Review scope: scripts/capstone_app.py and tests/test_capstone_app.py, plus original requirements and HTTP/browser evidence. The engineering code-review skill guided correctness, performance, input/security and maintainability checks. This is an implementer review; no independent reviewer was used.

## Findings resolved

1. Missing saved assets closed an HTTP connection with FileNotFoundError. A fault-injection HTTP regression now requires JSON503/probability null, followed by a successful root request.
2. Duplicate saved keys were returned as not-found, and nonfinite raw probability could reach JSON serialization. Both now return explicit unavailable outputs. A synthetic regression covers both.
3. Dates without explanations omitted issue time and model/contract hashes. All-date cell details and keyed score APIs now preserve those fields. The regression checks a later date without SHAP data.
4. Browser requests had no visible rejection/network/timeout handling. Details, exports and readiness now show failures; the request timeout is 15 seconds. Actual API/browser normal paths and CSV download were checked; an exhaustive UI fault matrix was not run.
5. The outer details panel kept the prior day's factors after map selection changes. Date, next-day and cell events now clear it; a pending detail response is discarded if its date/cell/study is no longer selected. Actual browser date-change verification confirmed the cleared state.

The three new regression tests first failed on the old behavior; all eight app tests and 129 combined tests now pass. JavaScript syntax checks pass. No model fitting, final evaluation, thresholds or saved probabilities changed.

## Review disposition

Fixed request-path findings are closed for the tested local demo. File serving remains allowlisted and loopback-only; no path supplied by a request is opened directly. JSON data enter visible UI through textContent. Live probability remains unavailable even if isolated overlap/state flags are supplied. Model/source provenance hashes are returned with saved outputs.

Long orchestration/inline dashboard code remains maintenance debt. A malformed Parquet/schema may produce an explicit invalid-request/data failure rather than a highly specific diagnostic; exhaustive storage/race/accessibility fault handling is not certified. Independent scientific or professor acceptance is unverified. The existing low precision, geographic-transfer and reconstruction limitations are unchanged.
