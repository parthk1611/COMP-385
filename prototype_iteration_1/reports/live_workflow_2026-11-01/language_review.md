# Language and code review

Scope: new workflow code/UI/report and the prototype README addition. Frozen historical research reports and original source attributes were retained.

Claims checked against actual outputs:

- Use “reported active-fire feed”, not a claim that every record is independently verified currently burning.
- Display retrieval time separately from confirmation time; condition observation time and perimeter remain unavailable.
- Use “dated MNR reference districts” with the 2023 package date, not current evacuation/community areas.
- Use “historical reconstruction” and disclose final-perimeter assistance, approximate start clock and possible ignition relocation.
- Call the 21 records local notices/drafts. They are non-actionable and have no delivery integration.
- Keep “reported cause” separate from ignition likelihood; there is no trained cause classifier.
- Retain null live outputs and explicit scientific qualification blockers. A configuration flag cannot qualify a model.
- State the measured 12-call cache benchmark and cold-call limit; do not convert it into an SLA or model-accuracy improvement.
- Distinguish 197 automated tests/18 HTTP checks from visual rehearsal, field validation or independent approval.

Code reviewed for unnecessary services, invented AI features, repeated I/O, duplicate notice insertion, unsafe HTML insertion, silent source truncation and stale-time claims. The implementation reuses existing adapters and saved scientific artifacts, adds no LLM or frontend framework, and formats new Python modules/tests for readability. Remaining medium-complexity checker findings are disclosed rather than relabelled as a clean independent review.
