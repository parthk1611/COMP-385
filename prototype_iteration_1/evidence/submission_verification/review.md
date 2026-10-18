# Submission source review

This iteration packages the current reviewed source without changing model or application logic. Source copies, model bytes and prediction tables are checked against the working project. No new fit, calibration, final scoring or tuning is performed.

Reviewed the runtime dependency paths: capstone_app resolves ROOT from its copied source location; its served HTML, both prediction tables, model and predictor-contract hashes, first-day feature lookups, export geometry and saved readiness JSON are present. All 129 tests pass in the staged layout. Fourteen real HTTP requests pass using that layout. A bulk-read test initially encountered a macOS socket buffer error on the large historical HTML; streaming the client response in 64 KiB chunks completed all requests. No application change was made to hide that failure.

Reviewed inclusion boundaries: no .git, .venv, credentials or national raw archives; raw sample and pilot fixtures retained for tests; acquisition/model code retains source-specific input requirements. Dated old documents retain their historical statements and are superseded by this README and current acceptance record. Model bundles are local trusted project artifacts, not files from an unverified third party.

Independent review, clean-machine installation and live acceptance are not asserted.
