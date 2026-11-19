# Three-minute demonstration

## Before presenting

Launch `Start-IgnitionDemo.cmd`. Wait for the browser to display 9,673 scored
cells. Keep the server window open. Start on July 1, 2019, the fixed calendar
default. This date was not chosen for a favourable result.

## 0:00–0:30: Define the prediction

"This app explores the estimated probability of at least one recorded wildfire
ignition in an Ontario 10 km cell during a local calendar day. The retained
coordinate HGB uses 80 iterations and 39 inputs, fitted on 2010–2016.
This is a replay of 2019, not an operational forecast."

Point to the date selector, map, colour legend and historical-mode label.

## 0:30–1:15: Trace a cell

Select the highest-ranked cell. Read its percentage score. Show its prior-day
weather and station count, then open the full 39-input list. Explain that
terrain and cell coordinates stay static while weather/history depend on date.
The outline is the frozen grid footprint, not a substituted official boundary.

Move forward one day. The selected cell remains selected and receives its new
score and inputs. Explain that the saved model makes predictions without
retraining.

## 1:15–2:00: Demonstrate the decision

Show the illustrative default cutoff: 0.001, displayed as 0.1%. It was not
selected using validation or replay labels. Read the day's correct/false alerts
and missed ignitions; undefined precision or recall is shown as a dash.

Select a lower cutoff and observe the changed counts. Toggle recorded
ignitions. Explain that those observations are comparisons and never enter
the model inputs.

## 2:00–2:30: Explain evaluation

Point to the note that global reserved-year evaluation was not recomputed.
Restore the illustrative default cutoff.

"These counts describe the displayed day only. They do not establish future
performance. The old 40-iteration model's published metrics and F2 policy
are not performance evidence for this retained coordinate model."

## 2:30–3:00: Show reproducibility and limits

Download the full day's predictions. Point to the 80-iteration/39-input
verification message. Explain that the clean `1cff710d` model export matches
the experiment pickle on all 12,458,824 development inputs with zero difference.
That proves reproduction, not accuracy on unseen years or geography.

"The app demonstrates a complete historical ML workflow. Live forecasting
would require a current data pipeline, issue-time availability checks,
additional validation and an operationally justified alert policy."
