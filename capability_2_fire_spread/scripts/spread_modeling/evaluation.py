"""Scores shared by training and the holdout comparison.

- `mean_step_ap`: how well scores rank the cells that will burn within each step, averaged over steps;
- `area_scale`: how many cells a model predicts in a step (scale x its summed probabilities);
- `predicted_mask`: a model's predicted new cells, the k most likely candidates;
- `simulator_score`: the simulator's ranking of cells, so it can be scored like a model;
- `bootstrap_difference`: a model's mean difference from the simulator with a 95% interval over fires;
- `matched_recall`: per step, the share of new cells reached when predicting as many cells as the simulator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from .contract import LABEL, TARGET_AREA_RATIO


BOOTSTRAP = 2000


def step_ap(labels: np.ndarray, scores: np.ndarray) -> float | None:
    """Average precision of one step's candidate cells; undefined when nothing newly burned."""
    return float(average_precision_score(labels, scores)) if labels.any() else None


def mean_step_ap(frame: pd.DataFrame, scores: np.ndarray) -> float:
    """Average precision within each step (ranking the step's candidate cells), averaged over steps."""
    values = [step_ap(frame[LABEL].values[index], scores[index]) for index in frame.groupby(["fire_id", "observation"]).indices.values()]
    return float(np.mean([value for value in values if value is not None]))


def area_scale(frame: pd.DataFrame, probability: np.ndarray) -> float:
    """Scale on the summed probabilities that makes the median predicted/observed new area equal the target (1.3)."""
    steps = frame.assign(p=probability).groupby(["fire_id", "observation"]).agg(expected=("p", "sum"), observed=(LABEL, "sum"))
    steps = steps[steps.observed > 0]
    return float(TARGET_AREA_RATIO / np.median(steps.expected / steps.observed))


def predicted_mask(n_cells: int, cells: np.ndarray, probability: np.ndarray, k: int) -> np.ndarray:
    """The k most likely candidate cells (ties broken by cell order)."""
    mask = np.zeros(n_cells, dtype=bool)
    if k > 0:
        order = np.lexsort((cells, -probability))[:k]
        mask[cells[order]] = True
    return mask


def matched_recall(frame: pd.DataFrame, scores: np.ndarray, steps: pd.DataFrame) -> pd.Series:
    """Per step: new cells among the k highest-scoring candidates, over all new cells, with k the simulator's count.

    `frame` holds a step's candidate cells and labels; `steps` is indexed by (fire_id, observation) and gives
    `simulated_new_cells` and `observed_new_cells` (which also counts new cells beyond the candidate radius).
    """
    out = {}
    cells, labels = frame.cell.to_numpy(), frame[LABEL].to_numpy()
    for key, index in frame.groupby(["fire_id", "observation"]).indices.items():
        k, observed = int(steps.loc[key, "simulated_new_cells"]), int(steps.loc[key, "observed_new_cells"])
        top = np.lexsort((cells[index], -scores[index]))[:k]
        out[key] = labels[index][top].sum() / observed
    return pd.Series(out)


def simulator_score(rows: pd.DataFrame) -> np.ndarray:
    """Rank cells by the simulator: reached share, then earliest arrival; unreached cells by distance from the fire."""
    arrival = rows.sim_arrival_fraction.fillna(2.0).to_numpy()
    return np.where(rows.sim_reached_share > 0, 2.0 + rows.sim_reached_share - arrival / 10, -rows.distance_to_burned_m / 1e5)


def bootstrap_difference(steps: pd.DataFrame, model: str, metric: str, rng: np.random.Generator) -> dict[str, float | None]:
    """Mean over steps of (model - simulator), with a 95% interval from resampling fires (steps of one fire are not independent)."""
    pair = steps[steps.model.isin([model, "simulator"])].pivot_table(index=["fire_id", "from_observation"], columns="model", values=metric).dropna()
    if pair.empty:
        return {"mean": None, "low": None, "high": None, "steps": 0}
    difference = (pair[model] - pair["simulator"]).groupby(level="fire_id")
    sums, counts = difference.sum().to_numpy(), difference.count().to_numpy()
    draws = rng.integers(0, len(sums), size=(BOOTSTRAP, len(sums)))
    means = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return {"mean": round(float(sums.sum() / counts.sum()), 4), "low": round(float(np.quantile(means, 0.025)), 4),
            "high": round(float(np.quantile(means, 0.975)), 4), "steps": int(counts.sum()), "fires": int(len(sums))}  # fmt: skip
