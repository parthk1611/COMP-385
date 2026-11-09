# Three-minute demonstration

## Before presenting

Launch `Start-IgnitionDemo.cmd`. Wait for the browser to display 9,673 scored
cells. Keep the server window open. Start on July 1, 2019, the fixed calendar
default. This date was not chosen for a favourable result.

## 0:00–0:30: Define the prediction

"This app explores the estimated probability of at least one recorded wildfire
ignition in an Ontario 10 km cell during a local calendar day. It uses a
historical model trained on 2010–2016 data. This is a replay of 2019."

Point to the date selector, map, colour legend and historical-mode label.

## 0:30–1:15: Trace a cell

Select the highest-ranked cell. Read its percentage score. Show its prior-day
weather and station count, then open the full 36-input list. Explain that
terrain remains static while weather and history depend on the date.

Move forward one day. The selected cell remains selected and receives its new
score and inputs. Explain that the saved model makes predictions without
retraining.

## 1:15–2:00: Demonstrate the decision

Show the default cutoff, selected by F2 using 2018 validation data. Read the
day's correct alerts, false alerts and missed ignitions. If a denominator is
zero, the interface uses a dash rather than inventing a precision or recall.

Select a lower cutoff and observe the changed counts. Toggle recorded
ignitions. Explain that those observations are comparisons and never enter
the model inputs.

## 2:00–2:30: Explain evaluation

Point to the separately labelled 2018 and 2019 rows. Restore the default F2
cutoff. Explain that 2018 selects the policy and 2019 evaluates it.

"For the whole 2019 season, this cutoff catches 15 of 509 positive cell-days,
with 1,871 false alerts. Ranking improves over the prevalence baseline, but
the absolute alert performance remains limited."

## 2:30–3:00: Show reproducibility and limits

Download the full day's predictions. Point to the reconstruction verification
message and explain that its published 2019 metrics and eight confusion tables
match the original report. State that the reconstruction is saved separately.

"The app demonstrates a complete historical ML workflow. Live forecasting
would require a current data pipeline, issue-time availability checks,
additional validation and an operationally justified alert policy."
