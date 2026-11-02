"""Bounded read caches for local, keyed research artifacts."""

from functools import lru_cache
from copy import deepcopy
import json
from pathlib import Path
import pandas as pd


def identity(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@lru_cache(maxsize=256)
def _parquet(path, version, columns, day, grid):
    frame = pd.read_parquet(
        path,
        filters=[("ignition_date", "=", day), ("grid_id", "=", grid)],
        columns=list(columns),
    )
    if identity(path) != version:
        raise OSError("Artifact changed during read")
    return frame


def parquet_lookup(path, columns, day, grid):
    path = Path(path)
    if not path.exists():
        return pd.read_parquet(
            path,
            filters=[("ignition_date", "=", day), ("grid_id", "=", grid)],
            columns=list(columns),
        )
    return _parquet(path, identity(path), tuple(columns), day, grid).copy()


def index_explanations(path):
    document = json.loads(path.read_text())
    indexed = {r["grid_id"]: r for r in document["rows"]}
    if len(indexed) != len(document["rows"]):
        raise OSError("Duplicate explanation key")
    return document["date"], indexed


@lru_cache(maxsize=8)
def _explanations(path, version):
    result = index_explanations(path)
    if identity(path) != version:
        raise OSError("Artifact changed during read")
    return result


def explanation_lookup(path, grid):
    path = Path(path)
    date, indexed = (
        _explanations(path, identity(path))
        if path.exists()
        else index_explanations(path)
    )
    row = indexed.get(grid)
    return date, deepcopy(row) if row is not None else None
