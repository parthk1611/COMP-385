# The FBP spread simulator (the baseline)

A wind-driven simulator that grows a fire across a 90 m grid, replayed against
real Ontario fires from the spread dataset. It is the physics baseline every
learned model is compared with. This note says how it works and how it was
tuned and scored; its results are in the [README](../../README.md#results).

## What it does

`scripts/spread_modeling/simulator.py` spreads fire from burning cells to their
neighbours. The time to cross to a neighbour comes from:

- the Canadian FBP rate-of-spread equations for the two cells' fuel types
  (`scripts/spread_modeling/fbp.py`; constants checked against the `cffdrs` R
  package);
- that hour's 10 m wind, the day's Fine Fuel Moisture Code and Buildup Index;
- an ellipse that stretches the fire downwind (FBP length-to-breadth ratio);
- the slope between the two cells (faster uphill).

Each cell's arrival time is the earliest time fire can reach it by any path
(shortest travel time over sixteen neighbours), so fire goes around lakes and
runs ahead through faster fuels. Water and non-fuel never burn.

Inputs per fire are the dataset's 90 m fuel and elevation windows and its
hourly weather. The fuel map is the 2024 edition, which shows regrowth or
non-fuel where older fires burned; inside each fire's perimeter the land is
given the fuel of the nearest burnable cell outside it (lakes are kept).

## Departure from the proposal

The proposal calls the simulator "Rothermel-based". This version uses the
Canadian FBP System instead: Rothermel needs the US fuel models, and the
national fuel map for Ontario is in FBP fuel types. The rest of the design
(physics-based, wind u/v, fuel moisture, fuel type, slope, replay against
time-stamped fire growth) follows the proposal.

## How it is replayed and scored

`scripts/spread_modeling/replay.py` replays fires between consecutive
satellite observations 6 to 30 hours apart with at least 5 newly burning 375 m
cells. Each step starts from the area burned so far, spreads only from the
stretch of perimeter where flames were seen at the latest pass, and is compared
with the cells first seen burning at the next pass. Every learned model is
scored on exactly these steps by the same `score_step`.

The baseline, "even growth", burns the same area as the simulator but spreads
it evenly outward from the same stretch of perimeter, with no wind, fuel or
terrain.

## How it is tuned

`scripts/spread_modeling/tune_simulator.py` tunes two settings on a seeded
sample of 24 calibration fires (2012–2020) only:

| Setting | Meaning | Grid | Chosen |
| --- | --- | --- | --- |
| `ros_scale` | multiplies every rate of spread | 0.3, 0.5, 0.8, 1.2 | 0.8 |
| `flank_scale` | further multiplies the flank and back rates | 0.1, 0.25, 0.5, 1.0 | 0.25 |

They are chosen so that the simulated head runs as far as the observed one
(distance ratio 1) and the simulated area is 1.3 times the cells seen
(satellites record a median 77% of a fire's final area). No single pair meets
both: the chosen pair gives 0.65 and 1.25 on the calibration fires. The tuned
simulator is then scored once on a seeded sample of 24 holdout fires
(2021–2024).

## Limits

- Satellites pass about twice a day, so the 1- and 3-hour horizons in the
  proposal cannot be scored; only steps of 6 hours or more are.
- Satellites see only where fire is active at a pass. Observed cells are a
  lower bound on what burned, which is why recall is reported ahead of overlap.
- Weather is reanalysis on a coarse grid (one series per fire), not the wind
  at the fire front.
- Fuel is the 2024 map with a repair inside the perimeter, not the fuel on the
  day of the fire.
- No crown-fire transition, spotting or suppression. Repeated runs for
  confidence bands are not built yet.

## Interface

`viewer/fire_spread_viewer.html` is a self-contained page that shows the best
learned model (the CNN) beside this simulator on three holdout fires. It plays
through each fire's steps as an animation: the area burned so far and the cells
the chosen model predicts (both predict the same number), then the cells the
next pass actually saw, marked as predicted or missed. A line chart below gives,
for every step, the share of the actual new burning each model predicted; click
a step to show it on the map. The fires are the simulator's published holdout
fires with the most scored steps whose grid has 130,000 cells or fewer, chosen
by rule, not by how either model did.

The map can be dragged and zoomed. The ground is the Canada Base Map –
Transportation from Natural Resources Canada, used under the Open Government
Licence – Canada and credited on the map. It is drawn in EPSG:3978, the
simulator's own grid, so it lines up with the cells. `scripts/spread_viewer/basemap.py`
fetches one image per fire the first time the viewer is exported;
`data/raw/basemap/manifest.json` records each request and checksum.

## Run it

Needs the dataset build's local fuel and terrain windows (`data/raw/fuel_terrain/windows/`).
From `capability_2_fire_spread/`:

```sh
python -m scripts.spread_modeling.tune_simulator   # tune, score, write docs/modeling/simulator_*.{json,csv}
python -m scripts.spread_viewer.export             # rebuild the viewer (needs the cell table and CNN predictions)
```
