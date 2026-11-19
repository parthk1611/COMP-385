"""Loopback-only, dependency-light HTTP service for the historical ignition demo."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import argparse
import csv
import io
import json
import logging
import threading
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import joblib
import numpy as np
import pandas as pd
from shapely import box, union_all
from shapely.geometry import mapping
from threadpoolctl import threadpool_limits

from scripts.ignition_modeling.contract import CACHE_VERSION, FEATURE_NAMES, RETAINED_HGB_PARAMS, ROOT, SEED
from scripts.ignition_modeling.data import load_cache
from scripts.ignition_modeling.run import predict_bundle
from scripts.ignition_modeling.weather import sha256
from .common import CACHE, OUTPUT, WEB, alert_policy, checked_probabilities, confusion, nullable, read_json, validate_date


class DemoStore:
    def __init__(self, output=OUTPUT, cache=CACHE, grid_path=None):
        from pathlib import Path
        output, cache = Path(output), Path(cache)
        self.output = output
        required = [output / name for name in ("selected_system.joblib", "model_metadata.json", "verification.json")]
        required.append(cache / "manifest.json")
        missing = [str(p) for p in required if not p.exists()]
        if missing:
            raise FileNotFoundError("Missing demo artifacts: " + ", ".join(missing) + ". Run python -m scripts.ignition_demo.reconstruct first.")
        self.model_metadata = read_json(output / "model_metadata.json")
        metadata = self.model_metadata
        self.verification = read_json(output / "verification.json")
        if self.verification["status"] != "PASS":
            raise ValueError("Main model export verification did not pass")
        if sha256(output / "model_metadata.json") != self.verification["metadata_sha256"]:
            raise ValueError("Model metadata checksum mismatch")
        digest = sha256(output / "selected_system.joblib")
        if digest != metadata["model_sha256"] or digest != self.verification["model_sha256"]:
            raise ValueError("Model checksum mismatch")
        if (metadata["artifact_version"] != "retained-coordinate-hgb-v1"
                or metadata["features"] != list(FEATURE_NAMES)
                or metadata["cache_version"] != CACHE_VERSION
                or metadata["fit_years"] != [2010, 2016]
                or metadata["training"]["years"] != list(range(2010, 2017))
                or metadata["params"].get("random_state") != SEED
                or metadata["params"].get("early_stopping") is not False
                or metadata["params"].get("categorical_features") is not None
                or any(metadata["params"].get(key) != value for key, value in RETAINED_HGB_PARAMS.items())):
            raise ValueError("Model feature schema/version or retained training configuration mismatch")
        fingerprints = metadata["cache_sha256"]
        if set(fingerprints) != {"manifest.json", "X.f64", "y.u8", "grid.u16"}:
            raise ValueError("Incomplete cache fingerprints")
        for name, checksum in fingerprints.items():
            if sha256(cache / name) != checksum:
                raise ValueError(f"Cache fingerprint mismatch: {name}; reconstruct before serving")
        if (fingerprints["manifest.json"] != metadata["cache_manifest_sha256"]
                or fingerprints["manifest.json"] != self.verification["cache_manifest_sha256"]):
            raise ValueError("Cache manifest checksum mismatch")
        self.X, self.y, self.manifest = load_cache(cache)
        if self.manifest["original_panel_sha256"] != metadata["source_panel_sha256"]:
            raise ValueError("Cache and model use different source panels")
        self.bundle = joblib.load(output / "selected_system.joblib")
        if (self.bundle["features"] != list(FEATURE_NAMES)
                or self.bundle["cache_version"] != CACHE_VERSION
                or self.bundle["calibrator"] is not None):
            raise ValueError("Model feature schema/version mismatch")
        classifier = self.bundle["pipeline"].steps[-1][1]
        if (any(classifier.get_params().get(key) != value for key, value in metadata["params"].items())
                or classifier.n_iter_ != RETAINED_HGB_PARAMS["max_iter"]
                or classifier.n_features_in_ != len(FEATURE_NAMES)
                or self.bundle["training"] != metadata["training"]):
            raise ValueError("Model parameters or training disagree with exported metadata")
        self.policy = alert_policy()
        self.grid = pd.read_csv(grid_path or ROOT / "data/interim/ontario_fire_region_10km_grid.csv")
        self.lookup = {value: i for i, value in enumerate(self.grid.grid_id)}
        if len(self.lookup) != len(self.grid):
            raise ValueError("Duplicate reference grid IDs")
        self.ids = np.memmap(cache / "grid.u16", dtype="uint16", mode="r", shape=(len(self.y),))
        self.lock = threading.RLock()
        self.results = {}
        self.metadata = {
            "title": "Ontario Ignition Atlas", "first_date": "2019-05-01", "last_date": "2019-10-31",
            "default_date": "2019-07-01", "timezone": "America/Toronto", "cells": len(self.grid),
            "model": f"Histogram gradient boosting · {metadata['params']['max_iter']} iterations",
            "fit_years": metadata["fit_years"], "feature_count": len(FEATURE_NAMES),
            "features": metadata["features"], "params": metadata["params"],
            "model_metadata": metadata, "policy": self.policy, "verification": self.verification,
            "results": self.results, "published_2019": None,
            "performance_note": "No global reserved-year evaluation was recomputed for this export. Historical 40-iteration results do not describe this model.",
            "colour_breaks": [self.policy["choices"][i]["threshold"] for i in (0, 1, 3, 4, 6)],
            "limitations": ["Historical hindcast on a frozen study grid, May–October 2019.",
                            "Archive publication times are unknown; this is not a live forecast.",
                            "The study grid includes event-informed edge cells; province-wide generalisation is unverified.",
                            "Cutoffs are illustrative, not validated operational decisions.",
                            "Daily observed counts are descriptive, not global test performance.",
                            "Shown inputs provide context, not causal explanations."]}

    @lru_cache(maxsize=1)
    def map_grid(self):
        footprint = union_all([
            box(row.grid_x_m, row.grid_y_m, row.grid_x_m + 10000, row.grid_y_m + 10000)
            for row in self.grid.itertuples()
        ])
        return {"crs": "EPSG:3978", "cell_size_m": 10000,
                "cells": [{"id": row.grid_id, "x": int(row.grid_x_m), "y": int(row.grid_y_m),
                           "longitude": row.centroid_longitude, "latitude": row.centroid_latitude}
                          for row in self.grid.itertuples()],
                "boundary": mapping(footprint),
                "boundary_kind": "frozen_10km_grid_footprint",
                "attribution": "Map outline: frozen 10 km grid footprint, not an official sector boundary. Terrain: NRCan CDEM. Weather: CWFIS. Ignitions: NFDB."}

    @lru_cache(maxsize=8)
    def _day(self, day):
        validate_date(day)
        start, stop = self.manifest["date_slices"][day]
        ids = self.ids[start:stop]
        if not np.array_equal(np.sort(ids), np.arange(len(self.grid))):
            raise ValueError("Incomplete daily grid")
        order = np.argsort(ids)
        X = np.asarray(self.X[start:stop])[order]
        y = np.asarray(self.y[start:stop])[order]
        p = checked_probabilities(predict_bundle(self.bundle, X), len(self.grid))
        return X, y, p

    def day(self, day):
        # Serialise inference and cache population; the HTTP server remains responsive.
        with self.lock:
            return self._day(day)

    def predictions(self, day):
        X, y, p = self.day(day)
        missing = X[:, FEATURE_NAMES.index("cwfis_missing")].astype(int)
        counts = X[:, FEATURE_NAMES.index("cwfis_station_count")].astype(int)
        return {"date": day, "timezone": "America/Toronto", "scores": p.tolist(),
                "observed": y.astype(int).tolist(), "weather_missing": missing.tolist(),
                "station_counts": counts.tolist(),
                "summary": {"cells": len(p), "weather_missing": int(missing.sum()),
                            "maximum_score": float(p.max()), "mean_score": float(p.mean())},
                "tradeoffs": [confusion(y, p, item["threshold"]) for item in self.policy["choices"]]}

    def cell(self, day, grid_id):
        if grid_id not in self.lookup:
            raise KeyError("Unknown grid cell")
        X, y, p = self.day(day)
        i = self.lookup[grid_id]
        return {"date": day, "grid_id": grid_id, "score": float(p[i]), "observed": int(y[i]),
                "features": {name: nullable(X[i, j]) for j, name in enumerate(FEATURE_NAMES)},
                "context_note": "Inputs are context, not causal explanations of this score."}

    def download(self, day):
        X, y, p = self.day(day)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["grid_id", "ignition_date", "longitude", "latitude", "score", "observed_ignition", "weather_missing", "station_count"])
        for i, row in enumerate(self.grid.itertuples()):
            writer.writerow([row.grid_id, day, row.centroid_longitude, row.centroid_latitude, repr(float(p[i])),
                             int(y[i]), int(X[i, FEATURE_NAMES.index("cwfis_missing")]),
                             int(X[i, FEATURE_NAMES.index("cwfis_station_count")])])
        return stream.getvalue().encode("utf-8")


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type="application/json; charset=utf-8", download=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            request = urlsplit(self.path)
            params = parse_qs(request.query, keep_blank_values=True)
            try:
                if request.path == "/api/metadata":
                    self.reply(200, store.metadata)
                elif request.path == "/api/grid":
                    self.reply(200, store.map_grid())
                elif request.path in ("/api/predictions", "/api/cell", "/api/download"):
                    if len(params.get("date", [])) != 1:
                        raise ValueError("Supply exactly one date")
                    day = validate_date(params["date"][0])
                    if request.path == "/api/predictions":
                        self.reply(200, store.predictions(day))
                    elif request.path == "/api/cell":
                        if len(params.get("grid_id", [])) != 1:
                            raise ValueError("Supply exactly one grid_id")
                        self.reply(200, store.cell(day, params["grid_id"][0]))
                    else:
                        self.reply(200, store.download(day), "text/csv; charset=utf-8", f"ignition_{day}.csv")
                elif request.path in ("/", "/app.js", "/style.css"):
                    filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[request.path]
                    kind = {"/": "text/html", "/app.js": "text/javascript", "/style.css": "text/css"}[request.path]
                    self.reply(200, (WEB / filename).read_bytes(), kind + "; charset=utf-8")
                elif request.path == "/architecture":
                    self.reply(200, (ROOT / "docs/ignition_demo/architecture.html").read_bytes(),
                               "text/html; charset=utf-8")
                elif request.path == "/favicon.ico":
                    self.reply(204, b"", "image/x-icon")
                else:
                    self.reply(404, {"error": "Route not found"})
            except ValueError as error:
                self.reply(400, {"error": str(error)})
            except KeyError as error:
                self.reply(404, {"error": str(error).strip("'")})
            except FileNotFoundError:
                self.reply(503, {"error": "Required local artifact is unavailable; rebuild the demo"})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                logging.exception("Prediction request failed")
                self.reply(500, {"error": "Prediction failed; see the local server window for details"})

        def log_message(self, format, *args):
            logging.info(format, *args)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open", action="store_true", help="Open the demo in your browser")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        with threadpool_limits(limits=2):
            store = DemoStore()
            server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
            url = f"http://127.0.0.1:{args.port}"
            print(f"Ignition demo ready: {url}\nPress Ctrl+C to stop.", flush=True)
            if args.open:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except (FileNotFoundError, ValueError, OSError) as error:
        parser.exit(1, f"Cannot start ignition demo: {error}\n")


if __name__ == "__main__":
    main()
