"""Small, independently testable contracts shared by reconstruction and serving."""
import json
from datetime import date
from pathlib import Path

import numpy as np

from scripts.ignition_modeling.contract import ROOT, FEATURE_NAMES

OUTPUT = ROOT / "artifacts/ignition_modeling/retained_coordinate_hgb"
CACHE = ROOT / "data/interim/ignition_modeling_cache"
WEB = ROOT / "ignition_demo/web"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def alert_policy():
    """Illustrative score cutoffs, never selected using replay-year labels."""
    thresholds = [1e-5, 5e-5, .0001, .0005, .001, .005, .01, .05]
    return {"selection_year": None, "metric": None, "default_index": 4,
            "threshold": thresholds[4],
            "choices": [{"index": index, "threshold": value, "f2": None, "validation": None}
                        for index, value in enumerate(thresholds)],
            "rule": "Illustrative fixed probability cutoffs; default 0.001; no labels-based tuning",
            "scope": "Not a validated operational policy; daily counts are descriptive replay only"}


def validate_date(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Use a local date in YYYY-MM-DD format") from None
    if value != parsed.isoformat() or not date(2019, 5, 1) <= parsed <= date(2019, 10, 31):
        raise ValueError("Supported dates are 2019-05-01 through 2019-10-31")
    return value


def checked_probabilities(values, rows):
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (rows,) or not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("Model must return one finite probability in [0, 1] per cell")
    return values


def confusion(labels, probabilities, threshold):
    labels = np.asarray(labels)
    probabilities = checked_probabilities(probabilities, len(labels))
    if labels.ndim != 1 or not np.isin(labels, [0, 1]).all():
        raise ValueError("Observed labels must be aligned binary values")
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be in [0, 1]")
    flagged, observed = probabilities >= threshold, labels == 1
    tp, fp = int((flagged & observed).sum()), int((flagged & ~observed).sum())
    fn, tn = int((~flagged & observed).sum()), int((~flagged & ~observed).sum())
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "true_negative": tn, "alerts": tp + fp, "observed": tp + fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def nullable(value):
    return float(value) if np.isfinite(value) else None
