"""Read-only dashboard summary of dated research and forecast-weather evidence."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree

from scripts.live_workflow import normalize_incidents
from scripts.prepare_historical_weather_v2 import EARTH_RADIUS_KM, sphere
from scripts.range_predictions import artifacts
from scripts.seven_day_ignition import parse_query, saved_inputs
from scripts.seven_day_weather import locations, digest
from scripts.workflow_sources import atomic_json, collect_layer, now_utc


def refresh_reported_fires(workspace):
    workspace = Path(workspace)
    state = workspace / 'data/processed/overview_current'
    raw = workspace / 'data/raw/overview_current' / pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%fZ')
    raw.mkdir(parents=True)
    with requests.Session() as session:
        collection, source = collect_layer('fires', raw, session)
    incidents = normalize_incidents(collection)
    if len({row['incident_id'] for row in incidents}) != len(incidents):
        raise ValueError('Duplicate reported-fire identity')
    atomic_json(raw / 'sources.json', source)
    atomic_json(state / 'latest.json', {'incidents': incidents, 'source': source,
                                       'collected_at_utc': source['retrieved_at_utc']})
    completed = pd.Timestamp.now(tz='UTC')
    atomic_json(state / 'refresh_status.json', {'status': 'ok', 'completed_at_utc': completed.isoformat(),
        'next_refresh_at_utc': (completed + pd.Timedelta(minutes=15)).isoformat()})


def refresh_incidents_loop(workspace, stop):
    next_refresh = pd.Timestamp(0, tz='UTC')
    while not stop.is_set():
        if pd.Timestamp(now_utc()) < next_refresh:
            stop.wait(60)
            continue
        try:
            refresh_reported_fires(workspace)
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as error:
            clock = pd.Timestamp.now(tz='UTC')
            atomic_json(Path(workspace) / 'data/processed/overview_current/refresh_status.json',
                        {'status': 'failed', 'attempted_at_utc': clock.isoformat(),
                         'error_type': type(error).__name__,
                         'next_refresh_at_utc': (clock + pd.Timedelta(minutes=15)).isoformat()})
        next_refresh = pd.Timestamp(now_utc()) + pd.Timedelta(minutes=15)
        stop.wait(60)


def forecast_context(workspace, incidents, now):
    folder = Path(workspace) / 'data/processed/ontario_7day_v1'
    if not (folder / 'current.json').exists():
        return None, incidents
    weather, meta, _, _ = saved_inputs(workspace, now)
    grid, _, _ = artifacts(workspace)
    _, points = locations(grid)
    start, end, _, _ = parse_query({}, now)
    parts = []
    coverage = []
    for lead in range(1, 8):
        day = (pd.Timestamp(start) + pd.Timedelta(days=lead - 1)).strftime('%Y-%m-%d')
        part = weather[weather.date.eq(day) & weather.lead.eq(lead)].set_index('site').reindex(points.site)
        complete = part.hours.eq(part.expected_hours) & part.time_safe.eq(True)
        part.loc[~complete, ['temp', 'rh', 'rain', 'wind']] = np.nan
        parts.append(part)
        coverage.append({'date': day, 'complete_sites': int(complete.sum()), 'total_sites': len(points)})
    age = (now - pd.Timestamp(meta['received_at'])).total_seconds() / 3600
    summary = {'source': 'Open-Meteo GFS', 'mode': 'daily_forecast_weather_research',
               'available_at_utc': meta['received_at'], 'run_time_utc': None, 'age_hours': age,
               'forecast_days_complete': sum(row['complete_sites'] == len(points) for row in coverage),
               'forecast_days': 7, 'coverage': coverage, 'start': str(start), 'end': str(end),
               'valid_until_utc': (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize('America/Toronto').tz_convert('UTC').isoformat(),
               'source_manifest_sha256': digest(folder / 'current.json')}
    tree = cKDTree(sphere(points.longitude, points.latitude))
    result = []
    for incident in incidents:
        chord, nearest = tree.query(sphere([incident['longitude']], [incident['latitude']])[0])
        distance = float(2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1)))
        rows = []
        if distance <= 100:
            for support, part in zip(coverage, parts):
                row = part.iloc[int(nearest)]
                rows.append({'date': support['date'], **{name: float(row[field]) if np.isfinite(row[field]) else None
                    for name, field in [('temp_c', 'temp'), ('rh_pct', 'rh'), ('wind_kmh', 'wind'), ('precip_mm', 'rain')]}})
        result.append({**incident, 'weather_context': {'site': points.site.iloc[int(nearest)],
            'centroid_distance_km': distance, 'days': rows,
            'sampling': 'Nearest forecast sampling point within 100 km; daily maximum temperature/wind, minimum humidity, total precipitation'}})
    return summary, result


def study_metrics(workspace):
    root = Path(workspace) / "reports"
    historical = json.loads((root / "week_5_prototype_2026-10-16/final_evaluation.json").read_text())
    selected = json.loads((root / "week_5_completion_2026-10-16/selected_2025_results.json").read_text())
    rows = []
    for item in historical["results"]:
        if item["variant"] == "calibrated":
            rows.append({"study": "2019 historical", "protocol": item["protocol"], **summary(item)})
    for item in selected["final"]:
        rows.append({"study": "2025 within-season", "protocol": item["protocol"], **summary(item["calibrated"])})
    if len(rows) != 4:
        raise ValueError("Expected two protocols for each evaluated study")
    return rows


def summary(row):
    return {key: row[key] for key in (
        "rows", "positives", "average_precision", "brier",
        "daily_budget_recall", "daily_budget_precision",
    )}


def current_feed(workspace, workflow, now):
    current_path = Path(workspace) / 'data/processed/overview_current/latest.json'
    if current_path.exists():
        current = json.loads(current_path.read_text())
        age = (now - pd.Timestamp(current['collected_at_utc'])).total_seconds() / 3600
        if age < 0:
            raise ValueError('Reported fire collection time is in the future')
        status = current_path.with_name('refresh_status.json')
        workflow = {**workflow, 'incidents': current['incidents'], 'collected_at_utc': current['collected_at_utc'],
                    'snapshot_age_hours': age, 'freshness': 'fresh' if age <= .5 else 'stale',
                    'last_refresh': json.loads(status.read_text()) if status.exists() else {'status': 'unknown'}}
    return workflow


def forecast_status(weather):
    if not weather:
        return 'unavailable'
    if 'forecast_days_complete' in weather:
        if weather['forecast_days_complete'] == 7:
            return 'available'
        return 'partial' if weather['forecast_days_complete'] else 'unavailable'
    return 'available' if weather.get('future_six_hours_covered') else 'unavailable'


def build_overview(workspace, workflow, readiness):
    if (readiness.get("status") != "unavailable"
            or readiness.get("probability") is not None
            or workflow.get("live_ignition_probability") is not None
            or workflow.get("live_spread") is not None):
        raise ValueError("Unqualified wildfire predictions cannot be published")
    now = pd.Timestamp(now_utc())
    workflow = current_feed(workspace, workflow, now)
    weather, incidents = forecast_context(workspace, workflow['incidents'], now)
    weather = weather if weather is not None else workflow.get('weather')
    return {
        "mode": "research_dashboard",
        "operational": False,
        "live_ignition_probability": None,
        "live_spread": None,
        "forecast_weather_status": forecast_status(weather),
        "weather": weather,
        "feed_collected_at_utc": workflow["collected_at_utc"],
        "feed_freshness": workflow["freshness"],
        "feed_age_hours": workflow["snapshot_age_hours"],
        "freshness_scope": workflow["freshness_scope"],
        "incidents": incidents,
        "automatic_refresh": {"fire_feed_minutes": 15, "weather_hours": 3, "view_seconds": 60,
                              "requires_running_server": True},
        "last_refresh": workflow.get("last_refresh", {"status": "unknown"}),
        "qualification": readiness,
        "spread_blockers": workflow["live_blockers"],
        "study_metrics": study_metrics(workspace),
        "metric_scope": "Saved retrospective evaluations; 1% daily review capacity, not forecasting accuracy.",
        "spread_scope": "90 m historical reconstruction with final-perimeter assistance; 1/3/6-hour controls are not validated forecast horizons.",
    }
