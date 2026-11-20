# Ignition → spread bridge (FBP)

Capability 1 scores whether a 10 km cell has an ignition on a local day.
`scripts/spread_modeling/ignition_bridge.py` takes a cell from it and grows a
fire from the cell's centre with the FBP simulator. The ignition demo calls it
through `/api/spread`. It is a **retrospective hindcast**: the run uses the
reanalysis weather that actually followed, which nobody had in advance.

## Keeping 2019 clean

The combined run is shown on 2019, so neither capability is fitted or tuned on
2019 or later, and 2019 is never used to test the FBP settings:

| Part | Fitted or tuned on | Tested on | Shown on |
| --- | --- | --- | --- |
| Ignition model (capability 1) | 2010–2016 | threshold 2018, test 2019 | 2019 |
| FBP settings for the bridge | 2012–2016 fires | 2017–2018 and 2020–2024 fires | 2019 |

The published FBP tuning (`tune_simulator.py`, rate × 0.8, flank × 0.25) drew 2
of its 24 tuning fires from 2019, so the bridge does not use it.
`tune_simulator_bridge.py` refuses tuning years from 2019 on and any split
containing 2019. The bridge refuses a settings file that breaks either rule.
Test fires after 2019 cannot change the chosen setting; they only measure it.

## How the FBP settings were re-tuned

`python -m scripts.spread_modeling.tune_simulator_bridge` (about 6 minutes on 12 cores)

- **What is tuned.** Two multipliers on the FBP equations: `ros_scale` on every
  rate of spread, and `flank_scale` on the flank and back rates only (below 1,
  the fire is narrower than the FBP ellipse).
- **Fires.** Every trackable (three or more growth steps), monitored (`MON`)
  fire of 500–30,000 ha, all of them rather than a sample:

  | Role | Years | Fires | Scored steps |
  | --- | --- | ---: | ---: |
  | Tune | 2012–2016 | 43 | 157 |
  | Test | 2017–2018 | 59 | 302 |
  | Test | 2020–2024 | 50 | 314 |
  | Never read | 2019 | — | — |

- **Replay.** Each fire is replayed pass by pass. Between two satellite passes
  6–30 h apart, the simulator starts from the area burned so far and spreads for
  the hours between them. It is compared with the 375 m cells first seen
  burning at the second pass.
- **Search.** An exhaustive grid of 15 rate scales (0.2–1.6, step 0.1) × 11
  flank scales (0.05–1.0) = 165 settings, each replayed on all 43 tuning fires.
  `bridge_simulator_grid.csv` holds every setting's tuning scores.
- **Objective (unchanged from the published tuning).** The simulated head
  should run as far as the observed head (median ratio 1). The simulated area
  should be 1.3 × the cells the satellite saw (median ratio 1.3), because
  satellites record about 77% of a fire's final area. Error =
  `|log(distance ratio)| + |log(area ratio / 1.3)|`, smallest wins; on an exact
  tie the higher mean IoU wins. Recall is reported but not used to choose,
  because a bigger area always raises it.
- **Test.** The chosen pair is scored once on each test period, beside the
  published 0.8 / 0.25 on the same steps. Every score comes with the
  even-growth baseline: the same area spread evenly outward, with no wind, fuel
  or terrain.

## Result

**Chosen: rate × 1.3, flank × 0.1** (tuning error 0.239; on 2012–2016, head
distance ratio 0.79 and area ratio 1.30).

| Test steps | Setting | Recall | Even-growth recall | IoU | Even-growth IoU | Head distance ratio | Area ratio | Direction within 45° |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2017–2018 (302) | **chosen 1.3 / 0.1** | 0.191 | 0.200 | 0.091 | 0.079 | 0.51 | 0.62 | 43% |
| | published 0.8 / 0.25 | 0.270 | 0.284 | 0.103 | 0.095 | 0.66 | 1.13 | 48% |
| 2020–2024 (314) | **chosen 1.3 / 0.1** | 0.264 | 0.268 | 0.109 | 0.104 | 0.69 | 1.00 | 54% |
| | published 0.8 / 0.25 | 0.354 | 0.373 | 0.114 | 0.114 | 0.91 | 1.78 | 56% |
| All test (616) | **chosen 1.3 / 0.1** | 0.229 | 0.235 | 0.100 | 0.092 | 0.59 | 0.79 | 49% |
| | published 0.8 / 0.25 | 0.313 | 0.329 | 0.108 | 0.105 | 0.77 | 1.50 | 52% |
| Long runs ≥ 1.5 km (232) | **chosen 1.3 / 0.1** | 0.181 | 0.150 | 0.093 | 0.073 | 0.30 | 0.51 | 59% |

What this shows:

- **The chosen setting burns too little on later fires.** It hit the area
  target on 2012–2016 but reaches only 0.79 of it on the test fires, so its
  recall is lower than the published setting's, which burns about twice the
  area.
- **Overlap (IoU) is the fairer comparison** because it does not reward a bigger
  area. The chosen setting beats even growth on IoU in both test periods
  (0.100 vs 0.092 pooled), and on long runs it beats even growth on recall
  too (0.181 vs 0.150). The published setting is still slightly ahead on IoU
  (0.108).
- **Why the choice is fragile.** The error surface is a long, flat valley: a
  faster head with a narrower flank, or a slower head with a wider flank, gives
  much the same fire. (1.3, 0.1) is an isolated dip in that valley on 43 fires,
  mostly from 2012. Tuning on all 102 fires from 2012–2018 instead would have
  chosen rate × 0.9, flank × 0.2 (or 1.2 / 0.15, which tied).
- **Every setting under-predicts long runs.** On steps where the head ran
  1.5 km or more, the simulated head reaches 0.30 of the observed distance.

## What the bridge does per run

1. **Start.** The 10 km cell's centre, at a chosen hour (default 14:00) in
   local standard time (CST west of 90° W, otherwise EST, as in the spread
   dataset). If that 90 m cell is water or non-fuel, the start moves to the
   nearest burnable cell within 1 km.
2. **Window.** A square around the start, 10–35 km half-width depending on
   run length, snapped to the fuel map's lattice.
3. **Fuel.** FBP Fuel Types 2024 at 90 m (CWFIS web coverage). The 2024 map
   shows burn scars of fires that happened after the start date. Inside the
   Ontario Fire Disturbance perimeters of fires that started on or after the
   start date (through 2024), land gets the fuel of the nearest burnable cell
   outside. Older scars are kept, because they were real at the start.
4. **Terrain.** MRDEM-30 DTM warped to the same 90 m grid.
5. **Weather.** Hourly ERA5 / ERA5-Land at the start point from Open-Meteo
   (`era5_seamless`), from 1 April (or 30 days earlier) so the FWI codes spin
   up. They go through the same `daily_fire_weather` and hourly FFMC code as
   the spread dataset.
6. **Spread.** `simulator.simulate` from the start cell for the chosen hours.
   Arrival times are aggregated to the 375 m satellite grid, with the earliest
   arrival per cell.

Fetched inputs are cached in `artifacts/ignition_bridge/` (not in git), so
only the first run at a place needs the internet.

## Limits

- The ignition model gives a day and a 10 km cell, not a time or a point.
  The start is an assumption the user controls.
- Most cells, even high-scoring ones, had no fire that day. A spread run
  answers "what if a fire started here", not "a fire started here".
- The FBP simulator under-predicts long runs. On test steps where the head
  ran 1.5 km or more, the simulated head reaches 0.30 of the observed distance,
  so spread maps will look small for blow-up days.
- One deterministic run; no crown fire, spotting or suppression.
