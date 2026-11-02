"""Read-only, bounded presentation API for the lightning development experiment."""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

CANDIDATES = ("reference", "lightning_24h", "lightning_24h_168h", "physical_logistic", "physical_monotonic")
EXPERIMENT = "lightning_development_2026-11-02"
TRANSFER_EXPERIMENT = "geographic_transfer_2026-11-02"


def evidence_response(workspace):
    source = Path(workspace) / "reports" / EXPERIMENT / "results.json"
    result = json.loads(source.read_text())
    if (result.get("operational") is not False or result.get("promoted") is not False
            or result.get("protected_artifacts_unchanged") is not True):
        raise OSError("Development evidence is incomplete or invalid")
    result["experiments"] = [EXPERIMENT]
    transfer_path = Path(workspace) / "reports" / TRANSFER_EXPERIMENT / "results.json"
    if transfer_path.exists():
        transfer = json.loads(transfer_path.read_text())
        if (transfer.get("operational") is not False or transfer.get("promoted") is not False
                or transfer.get("reference_parity") is not True
                or transfer.get("protected_artifacts_unchanged") is not True):
            raise OSError("Geographic transfer evidence is invalid")
        original = next(row for row in result["results"] if row["candidate"] == "reference" and row["protocol"] == "inner_spatial")
        repeated = next(row for row in transfer["results"] if row["candidate"] == "reference")
        if any(not np.isclose(original[key], repeated[key], rtol=1e-12, atol=0) for key in ("hits", "positives", "average_precision", "brier", "log_loss")):
            raise OSError("The two development comparisons have different references")
        result["results"].extend(row for row in transfer["results"] if row["candidate"] != "reference")
        result["capacity_curves"]["inner_spatial"].update({key: value for key, value in transfer["capacity_curves"]["inner_spatial"].items() if key != "reference"})
        result["selected"].update(transfer["selected"])
        result["development_gates_pass"].update(transfer["development_gates_pass"])
        result["model_fits"] += transfer["model_fits"]
        result["created_at_utc"] = transfer["created_at_utc"]
        result["experiments"].append(TRANSFER_EXPERIMENT)
    for row in result["results"]:
        if row["candidate"] not in CANDIDATES or not 0 <= row["hits"] <= row["positives"]:
            raise OSError("Invalid model evidence")
    result["dates"] = pd.date_range("2017-05-01", "2017-10-31").strftime("%Y-%m-%d").tolist()
    result["default_budget_percent"] = 1
    result["target"] = "Recorded wildfire-positive 10 km cell-days, explicit prescribed burns excluded"
    result["live_probability"] = None
    return result


@lru_cache(maxsize=12)
def _date_rows(path, modified_ns, size, day):
    return pd.read_parquet(path, filters=[("ignition_date", "==", day)])


def geographic_cells(workspace, candidate, day):
    if candidate not in CANDIDATES:
        raise ValueError("Unsupported candidate")
    if day not in pd.date_range("2017-05-01", "2017-10-31").strftime("%Y-%m-%d"):
        raise ValueError("Only exposed development dates are available")
    experiment = TRANSFER_EXPERIMENT if candidate.startswith("physical_") else EXPERIMENT
    path = Path(workspace) / "data/processed" / experiment / f"inner_spatial_{candidate}_predictions.parquet"
    identity = path.stat()
    frame = _date_rows(str(path), identity.st_mtime_ns, identity.st_size, day).copy()
    if frame.empty or frame.grid_id.duplicated().any() or not frame.ignition.isin([0, 1]).all():
        raise OSError("Incomplete geographic evidence")
    probabilities = frame.probability.to_numpy()
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise OSError("Invalid saved probability")
    parts = frame.grid_id.str.split("_", expand=True)
    frame["x"] = parts[1].astype(int)
    frame["y"] = parts[2].astype(int)
    rows = frame[["grid_id", "probability", "rank", "ignition", "x", "y"]].to_dict(orient="records")
    return {"mode": "exposed_development_replay", "live": False, "candidate": candidate,
            "date": day, "grid_cell_km": 10, "geometry_crs": "EPSG:3978",
            "rows": rows, "cells": len(rows), "positives": int(frame.ignition.sum()),
            "recorded_labels_are_predictors": False}
