"""Connect current observations to existing research models and local region notices."""

from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from rasterio.features import shapes
from rasterio.transform import from_origin
from scipy.spatial import cKDTree
from shapely import make_valid
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from scripts.ignition_comparison import digest
from scripts.workflow_sources import collect, atomic_json, now_utc
from scripts.research_alerts import notice_key, save_notices


class DistrictIndex:
    def __init__(self, collection, projected=False):
        project = Transformer.from_crs(4326, 3978, always_xy=True).transform
        self.records = []
        self.geometries = []
        self.repaired = []
        for feature in collection["features"]:
            props = feature["properties"]
            geometry = shape(feature["geometry"])
            if (
                geometry.geom_type not in ("Polygon", "MultiPolygon")
                or geometry.is_empty
            ):
                raise ValueError("District source requires nonempty polygons")
            if not geometry.is_valid:
                geometry = make_valid(geometry)
                self.repaired.append(props["OBJECTID"])
            if not projected:
                geometry = transform(project, geometry)
            self.geometries.append(geometry)
            self.records.append(
                {
                    "district_id": str(props["OBJECTID"]),
                    "district": props["DISTRICT_NAME"],
                    "region": props.get("REGION_NAME"),
                }
            )
        self.tree = STRtree(self.geometries)

    def locate(self, longitude, latitude):
        x, y = Transformer.from_crs(4326, 3978, always_xy=True).transform(
            longitude, latitude
        )
        point = Point(x, y)
        return [
            self.records[int(i)] for i in self.tree.query(point, predicate="intersects")
        ]

    def overlaps(self, footprint):
        result = []
        for index in self.tree.query(footprint, predicate="intersects"):
            area = footprint.intersection(self.geometries[int(index)]).area
            if area > 0:
                result.append(
                    {**self.records[int(index)], "overlap_ha": float(area / 10000)}
                )
        return sorted(result, key=lambda r: r["district_id"])


def normalize_incidents(collection):
    result = []
    for feature in collection["features"]:
        p = feature["properties"]
        geometry = feature.get("geometry")
        if geometry is None or geometry.get("type") != "Point":
            raise ValueError("Expected active-fire point geometry")
        lon, lat = map(float, geometry["coordinates"][:2])
        if not np.isfinite([lon, lat]).all() or not (
            -180 <= lon <= 180 and -90 <= lat <= 90
        ):
            raise ValueError("Invalid reported coordinates")
        confirmed = p.get("CONFIRMED_DATE")
        confirmed = (
            pd.Timestamp(confirmed, unit="ms", tz="UTC").isoformat()
            if confirmed is not None
            else None
        )
        result.append(
            {
                "incident_id": str(p["FIREID"]),
                "name": p.get("FIRE_NAME"),
                "longitude": lon,
                "latitude": lat,
                "reported_condition": p.get("CONDITION_DESCRIPTION"),
                "reported_size_ha": p.get("CURRENT_SIZE"),
                "reported_district": p.get("DISTRICT_NAME"),
                "reported_cause": p.get("ESTIMATED_FIRE_CAUSE"),
                "confirmed_at_utc": confirmed,
                "state_observed_at_utc": None,
                "perimeter": None,
                "mode": "reported_observation",
            }
        )
    return result


def reconstruction_footprint(case, hours):
    if hours not in (1, 3, 6):
        raise ValueError("Only saved 1/3/6-hour reconstruction horizons are supported")
    rows, cols = int(case["rows"]), int(case["columns"])
    if not 0 < rows * cols <= 200000 or case["pixel"] != 90:
        raise ValueError("Unexpected saved reconstruction grid")
    event = case["ignition"]
    cells = np.frombuffer(base64.b64decode(event["cells"], validate=True), dtype="<u4")
    minutes = np.frombuffer(
        base64.b64decode(event["minutes"], validate=True), dtype="<u2"
    )
    if (
        len(cells) != len(minutes)
        or len(np.unique(cells)) != len(cells)
        or (cells >= rows * cols).any()
    ):
        raise ValueError("Invalid saved arrival arrays")
    mask = np.zeros(rows * cols, dtype="uint8")
    mask[cells[minutes <= hours * 60]] = 1
    mask = mask.reshape(rows, cols)
    affine = from_origin(case["west"], case["north"], 90, 90)
    polygons = [
        shape(g)
        for g, value in shapes(mask, mask=mask.astype(bool), transform=affine)
        if value == 1
    ]
    return unary_union(polygons)


def replay_regions(workspace, index):
    directory = workspace / "reports/week_5_completion_2026-10-16"
    source = directory / "corrected_spread_viewer.html"
    audit = json.loads((directory / "spread_viewer_audit.json").read_text())
    if digest(source) != audit["sha256"]:
        raise ValueError("Saved reconstruction viewer changed")
    payload = json.loads(
        source.read_text()
        .split("window.SPREAD_VIEWER_DATA = ", 1)[1]
        .split(";</script>", 1)[0]
    )
    if payload["settings"].get("forecastValidated") is not False:
        raise ValueError("Unexpected reconstruction mode")
    cases = []
    polygons = []
    project = Transformer.from_crs(3978, 4326, always_xy=True).transform
    for fire in payload["fires"]:
        if not fire.get("ignition"):
            continue
        for hours in (1, 3, 6):
            footprint = reconstruction_footprint(fire, hours)
            row = {
                "incident_id": fire["id"],
                "start_local": fire["ignition"]["startLocal"],
                "horizon_hours": hours,
                "footprint_ha": float(footprint.area / 10000),
                "districts": index.overlaps(footprint),
                "mode": "historical_reconstruction",
                "forecast_validated": False,
                "uncertainty": "not_estimated",
                "assumptions": "Final-perimeter-assisted inputs; approximate start clock and possible ignition-cell relocation",
                "ignition_relocation_m": fire["ignition"]["movedMetres"],
            }
            cases.append(row)
            polygons.append(
                {
                    "type": "Feature",
                    "properties": {k: v for k, v in row.items() if k != "districts"},
                    "geometry": mapping(transform(project, footprint)),
                }
            )
    return cases, {"type": "FeatureCollection", "features": polygons}, digest(source)


def weather_context(workspace, directory, incidents, current):
    manifest = json.loads((directory / "manifest.json").read_text())
    source = directory / "hourly_weather.parquet"
    expected = next(
        r["sha256"]
        for r in manifest["outputs"]
        if r["path"].endswith("/hourly_weather.parquet")
    )
    if digest(source) != expected:
        raise ValueError("Weather snapshot changed")
    available = pd.Timestamp(manifest["bundle"]["available_at_utc"])
    if available.tzinfo is None or available > current:
        raise ValueError("Invalid weather availability")
    weather = pd.read_parquet(source)
    if weather.duplicated(["grid_id", "valid_time_utc"]).any():
        raise ValueError("Duplicate weather cell-time")
    future = weather.loc[weather.valid_time_utc > current]
    required = pd.date_range(current.ceil("h"), periods=6, freq="h")
    usable = set(required).issubset(set(future.valid_time_utc))
    summary = {
        "available_at_utc": available.isoformat(),
        "run_time_utc": manifest["bundle"]["run_time_utc"],
        "age_hours": float((current - available).total_seconds() / 3600),
        "future_six_hours_covered": usable,
        "valid_until_utc": weather.valid_time_utc.max().isoformat(),
        "source": "HRDPS",
        "source_manifest_sha256": digest(directory / "manifest.json"),
        "mode": "forecast_weather_research",
        "fwi_state": "forecast-derived research state; not accepted observed state",
    }
    if not usable:
        return summary, {}
    grid_path = (
        workspace / "reports/week_4_data_2026-10-16/current_boundary_centroid_grid.csv"
    )
    seed_path = directory / "state_checkpoint.json"
    seed_hash = next(
        r["sha256"]
        for r in manifest["outputs"]
        if r["path"].endswith("/state_checkpoint.json")
    )
    if digest(seed_path) != seed_hash:
        raise ValueError("Weather grid checkpoint changed")
    if json.loads(seed_path.read_text())["_metadata"]["grid_sha256"] != digest(
        grid_path
    ):
        raise ValueError("Weather centroid grid changed")
    grid = pd.read_csv(grid_path)
    project = Transformer.from_crs(4326, 3978, always_xy=True)
    x, y = project.transform(
        grid.centroid_longitude.to_numpy(), grid.centroid_latitude.to_numpy()
    )
    tree = cKDTree(np.column_stack([x, y]))
    context = {}
    for incident in incidents:
        px, py = project.transform(incident["longitude"], incident["latitude"])
        distance, nearest = tree.query([px, py])
        if distance > 20000:
            continue
        key = grid.grid_id.iloc[int(nearest)]
        chosen = future.loc[future.grid_id.eq(key)]
        rows = []
        for row in chosen.itertuples():
            fields = {
                k: (float(getattr(row, k)) if np.isfinite(getattr(row, k)) else None)
                for k in [
                    "temp_c",
                    "rh_pct",
                    "wind_kmh",
                    "wind_from_degrees",
                    "precip_mm",
                ]
            }
            rows.append({"valid_time_utc": row.valid_time_utc.isoformat(), **fields})
        context[incident["incident_id"]] = {
            "grid_id": key,
            "centroid_distance_km": float(distance / 1000),
            "sampling": "Nearest 10 km model-grid centroid; not a measurement at the fire",
            "hours": rows,
        }
    return summary, context


def build_notices(incidents, scenarios):
    notices = []
    for incident in incidents:
        for district in incident["districts"]:
            notices.append(
                {
                    "id": notice_key(
                        "reported_fire",
                        incident["incident_id"],
                        district["district_id"],
                    ),
                    "kind": "reported_fire",
                    "incident_id": incident["incident_id"],
                    "district": district["district"],
                    "mode": "reported_observation",
                    "reported_condition": incident["reported_condition"],
                    "reported_size_ha": incident["reported_size_ha"],
                    "message": f"The active-fire feed reports {incident['name']} in {district['district']}. Current perimeter and observation time are unavailable.",
                    "actionable": False,
                    "delivery": "local_only",
                }
            )
    for scenario in scenarios:
        for district in scenario["districts"]:
            notices.append(
                {
                    "id": notice_key(
                        "reconstruction",
                        scenario["incident_id"],
                        district["district_id"],
                        scenario["horizon_hours"],
                    ),
                    "kind": "reconstruction_draft",
                    "incident_id": scenario["incident_id"],
                    "district": district["district"],
                    "horizon_hours": scenario["horizon_hours"],
                    "overlap_ha": district["overlap_ha"],
                    "mode": "historical_reconstruction",
                    "scenario_start_local": scenario["start_local"],
                    "message": f"Historical {scenario['horizon_hours']}-hour reconstruction overlaps {district['district']}. This is a demonstration draft.",
                    "actionable": False,
                    "delivery": "local_only",
                }
            )
    return notices


def refresh_weather_context(result, current):
    weather = result.get("weather")
    if weather:
        available = pd.Timestamp(weather["available_at_utc"])
        until = pd.Timestamp(weather["valid_until_utc"])
        if available.tzinfo is None or until.tzinfo is None or available > current:
            raise ValueError("Invalid weather clock")
        weather["age_hours"] = float((current - available).total_seconds() / 3600)
        required = pd.date_range(current.ceil("h"), periods=6, freq="h")
        weather["future_six_hours_covered"] = bool(
            weather["future_six_hours_covered"] and required[-1] <= until
        )
        for incident in result.get("incidents", []):
            context = incident.get("weather_context")
            if context:
                context["hours"] = [
                    r
                    for r in context["hours"]
                    if current < pd.Timestamp(r["valid_time_utc"]) <= required[-1]
                ]
                context["six_hours_covered"] = set(required).issubset(
                    {pd.Timestamp(r["valid_time_utc"]) for r in context["hours"]}
                )


def read_snapshot(path, now=None):
    result = json.loads(Path(path).read_text())
    if (
        result.get("schema_version") != 1
        or result.get("live_ignition_probability") is not None
        or result.get("live_spread") is not None
    ):
        raise ValueError("Unqualified live outputs are not accepted")
    if any(
        n.get("actionable") is not False or n.get("delivery") != "local_only"
        for n in result["notices"]
    ):
        raise ValueError("Public alert delivery is not configured")
    current = pd.Timestamp(now or now_utc())
    captured = pd.Timestamp(result["collected_at_utc"])
    if current.tzinfo is None or captured.tzinfo is None or captured > current:
        raise ValueError("Invalid snapshot clock")
    age = float((current - captured).total_seconds() / 3600)
    result["snapshot_age_hours"] = age
    result["freshness"] = "fresh" if age <= 6 else "stale"
    result["freshness_scope"] = (
        "Feed retrieval only; incident observation age is unknown"
    )
    refresh_weather_context(result, current)
    return result


def run(workspace, output, weather_dir, source_snapshot=None):
    if output.exists():
        raise FileExistsError("Use a new workflow snapshot directory")
    output.mkdir(parents=True)
    state = workspace / "data/processed/live_workflow"
    state.mkdir(exist_ok=True)
    try:
        if source_snapshot is None:
            collections, sources = collect(
                output / "raw", workspace / "data/raw/workflow_reference_districts"
            )
        else:
            sources = json.loads((source_snapshot / "sources.json").read_text())
            collections = {}
            for kind in ("fires", "districts"):
                path = source_snapshot / (kind + ".geojson")
                if digest(path) != sources[kind]["sha256"]:
                    raise ValueError("Source snapshot changed")
                collections[kind] = json.loads(path.read_text())
        index = DistrictIndex(collections["districts"])
        incidents = normalize_incidents(collections["fires"])
        for incident in incidents:
            incident["districts"] = index.locate(
                incident["longitude"], incident["latitude"]
            )
        current = pd.Timestamp(now_utc())
        weather, contexts = weather_context(workspace, weather_dir, incidents, current)
        for incident in incidents:
            incident["weather_context"] = contexts.get(incident["incident_id"])
        scenarios, footprints, viewer_hash = replay_regions(workspace, index)
        built = now_utc()
        captured = sources["fires"]["retrieved_at_utc"]
        notices = save_notices(
            state / "notices.sqlite", build_notices(incidents, scenarios), built
        )
        qualification = (
            workspace / "reports/live_qualification_2026-11-01/live_readiness.json"
        )
        readiness = json.loads(qualification.read_text())
        if (
            readiness.get("status") != "unavailable"
            or readiness.get("probability") is not None
        ):
            raise ValueError(
                "This workflow cannot activate a live model from a qualification flag"
            )
        snapshot = {
            "schema_version": 1,
            "collected_at_utc": captured,
            "built_at_utc": built,
            "sources": sources,
            "source_mode": (
                "collected" if source_snapshot is None else "reused_snapshot"
            ),
            "code_sha256": digest(Path(__file__)),
            "model_readiness": {
                **readiness,
                "assessment_sha256": digest(qualification),
            },
            "incidents": incidents,
            "weather": weather,
            "scenarios": scenarios,
            "notices": notices,
            "live_ignition_probability": None,
            "live_spread": None,
            "region_scope": "Dated MNR administrative reference districts, not community or evacuation boundaries",
            "live_blockers": [
                "Active feed supplies points, not a verified current perimeter/time.",
                "Observed/overwintered FWI state and matching model source/issue-time qualification remain incomplete.",
            ],
            "reconstruction_viewer_sha256": viewer_hash,
            "repaired_district_ids": index.repaired,
            "footprints": footprints,
        }
        atomic_json(output / "snapshot.json", snapshot)
        atomic_json(output / "footprints.geojson", footprints)
        atomic_json(state / "latest.json", snapshot)
        atomic_json(
            state / "refresh_status.json", {"status": "ok", "completed_at_utc": built}
        )
        return snapshot
    except Exception as error:
        atomic_json(
            state / "refresh_status.json",
            {
                "status": "failed",
                "attempted_at_utc": now_utc(),
                "error_type": type(error).__name__,
            },
        )
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--weather-dir", type=Path, required=True)
    p.add_argument("--source-snapshot", type=Path)
    a = p.parse_args()
    result = run(
        a.workspace.resolve(),
        a.output_dir.resolve(),
        a.weather_dir.resolve(),
        a.source_snapshot.resolve() if a.source_snapshot else None,
    )
    print(
        json.dumps(
            {
                "reported_incidents": len(result["incidents"]),
                "scenarios": len(result["scenarios"]),
                "local_notices": len(result["notices"]),
                "live_probability": None,
            },
            indent=2,
        )
    )
