# Executed verification

The reconstructed model's AP, ROC-AUC, Brier score and log loss have zero
numerical difference from the original published 2019 metrics. All eight
frozen-cutoff confusion tables match. The original model bytes were not
available; this is a separately saved reconstruction.

## Data and model

- Audited uncompressed source checksum and pinned CWFIS archive match.
- Independently scanned all 17,798,320 cache rows across 1,840 dates.
- Each date contains exactly one permutation of the 9,673 grid cells.
- The exact feature schema, binary labels, chronological slices, station and
  missing-weather consistency, seven-day rain coverage and annual counts pass.
- Fitted all 12,458,824 training rows from 2010–2016, using the frozen HGB
  settings and seed. Saved the model/policy freeze before test evaluation.
- Model reloads reproduce 512 fixed training examples within 1e-14.
- Compact fingerprints and metrics are in `reconstruction_evidence.json`.

## Automated checks

Executed `.venv-demo/Scripts/python.exe -m unittest discover -s tests -v`:
**44 tests passed**, including original modelling/feature regressions, the
existing coverage-diagnosis test, 14 new demo policy/HTTP/real-artifact checks.
HTTP checks require the test process to have permission to connect to its own
loopback server. The suite passed after enabling that access.

Real-artifact integration checks compare served May 1, July 1 and October 31
predictions against the frozen 2019 vector, check grid ordering and missing
weather, and verify full-precision CSV output. JavaScript syntax and Python
compilation checks passed.

The Windows PowerShell launcher also started the app on an alternate port;
its metadata response confirmed 9,673 cells and reconstruction status PASS.

## Browser checks

Executed the reproducible `ignition_demo/verify_browser.js` using a local
Chrome test browser:

- Date stepping and both fire-season boundaries passed.
- Cell inspection showed all 36 inputs and retained selection across dates.
- Lowering the cutoff increased or preserved alert counts.
- Observed-ignition and alert-only overlays, zoom and reset passed.
- Recorded-ignition ranking filter passed.
- The downloaded July 2 CSV contains 9,673 rows, 9,673 unique cells and the
  correct single date.
- Unsupported API dates returned 400.
- Widths of 1440, 1024 and 390 pixels showed no page-level horizontal overflow.
  Wide tables scroll within their own containers.
- No JavaScript page errors occurred. Desktop and phone screenshots were
  visually inspected. These checks use actual reconstructed predictions.

## Presentation

The seven-slide deck contains editable text, two native tables, one editable
chart with an embedded data workbook, and an actual app screenshot. Chart
values use six-decimal display precision; full-precision metrics remain in
the report/evidence. Package, geometry, fonts, chart data and import checks
passed. Each slide was rendered and visually reviewed. Native PowerPoint
opening/editing was not checked.

## Preserved state

The frozen modelling implementation and published modelling reports have no
diffs. Existing unrelated untracked files remain untouched. Generated model,
cache, environments and private browser/presentation build files stay ignored.
