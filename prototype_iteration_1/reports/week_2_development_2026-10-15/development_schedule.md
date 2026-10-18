# Provisional development schedule

Prepared October 15, 2026. The user requested completion without focusing on dates. Treat the dependencies, durations, two AI iterations and overlap below as the working plan. Calendar dates in the existing CSV/XML remain provisional placeholders; they are not an official deadline and do not block the technical work.

Files: [dated tasks and dependencies](development_schedule.csv), [Microsoft Project XML import candidate](development_schedule.xml), [validation record](schedule_validation.json).

## Sequence and overlap

| Work package | Provisional dates | Dependency / output |
| --- | --- | --- |
| Source-quality/coverage decisions; requirements review | Oct 15–21 | Current audit and specification; resolve remaining readiness decisions. |
| Formal architecture review | Oct 22–23 | Data and requirements; review alternatives, interfaces and outstanding issues before implementation changes. |
| Feature rebuild and selector enforcement | Oct 26–29 | Reviewed architecture; eligible reproducible table and verified partitions. |
| AI iteration 1 | Oct 30–Nov 5 | Baseline fitting, development evaluation and review. |
| AI iteration 2 | Nov 6–13 | Agreed boosting comparison, calibration, freeze and final held-out score. |
| Ignition application work | Nov 4–9 | Begin after baseline fitting; saved-model scoring and historical map overlap iteration 2. |
| Spread corrections and evaluation | Oct 26–Nov 3 | Separate track after architecture review; barrier/outcome-input corrections and replay. |
| Spread viewer update | Nov 4–6 | Use evaluated spread results and honest horizon limits. |
| Historical integration demonstration | Nov 16–18 | Evaluated ignition, scoring/map and spread viewer. |
| Later live increment | Nov 19–30 | HRDPS adapter, FWI-state bridge and compatibility checks, after historical integration. |
| Regression checks and report/demo preparation | Dec 1–10 | Integrated outputs and versioned evidence. |
| Contingency and readiness checkpoint | Dec 11–16 | Resolve remaining defects; this is not a confirmed submission date. |

These are high-level durations, not a promise that students work eight hours daily. The import calendar uses standard eight-hour weekdays only to express Project durations. Resource availability is not levelled, holiday/reading-week exceptions have not been entered, and team role assignments are intentionally omitted. The optional live increment can be deferred if the real deadline requires the historical prototype first.

## Microsoft Project handoff — deferred by user

The XML follows the documented Project task/calendar/dependency field structure. Checks passed for well-formed XML, valid predecessor IDs, weekday dates and finish-to-start ordering. **No native Microsoft Project import, automatic rescheduling or full XSD validation was performed.** An XML file is not evidence that the course's “use Microsoft Project” step has been completed inside that application.

The user explicitly set this verification aside on October 15. It is not a blocker to beginning Week 3. When Microsoft Project is available, open the XML as a new project, verify the calendar and 21 tasks, check dependencies/overlap, adjust the provisional calendar if needed, then save the reviewed native project. CSV is supplied as an alternate import/review source. Source: [Microsoft Project XML documentation](https://learn.microsoft.com/en-us/office-project/xml-data-interchange/project-element?view=project-client-2016).

All scheduled implementation tasks start at 0% complete. Generating this plan does not claim that training, fixes or integrations have occurred. The project checklist separately records completed research, audits and documentation.
