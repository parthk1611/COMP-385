"""Fixed seven-day research outlook, forecast receipts and refresh worker."""
from datetime import date, timedelta
from functools import lru_cache
import json
from pathlib import Path
from threading import Event, Thread

import joblib
import numpy as np
import pandas as pd
import requests
from threadpoolctl import threadpool_limits

from scripts.range_predictions import REGIONS, artifacts, day_index, today_in_ontario
from scripts.seven_day_training import FEATURES, calibrated, enrich_grid, feature_frame, fingerprint, run, save_json, with_rain_history
from scripts.seven_day_weather import MODEL, VERSION, collect_archive, collect_current, digest


def parse_query(query, now=None):
    if set(query) - {'region', 'view', 'date'} or any(len(v) != 1 for v in query.values()):
        raise ValueError('The outlook always covers seven days; only area and map view can change')
    region = query.get('region', ['All Ontario'])[0]
    if region not in REGIONS or query.get('view', ['range'])[0] not in ('range', 'day'):
        raise ValueError('Unknown area or map view')
    start = today_in_ontario(now)
    end = start + timedelta(days=6)
    selected = date.fromisoformat(query.get('date', [start.isoformat()])[0])
    if not start <= selected <= end:
        raise ValueError('Choose one of the seven outlook days')
    return start, end, region, selected


@lru_cache(maxsize=4)
def checked_file(folder, manifest_text, model=False):
    meta = json.loads(manifest_text)
    if meta['contract'] != VERSION or Path(meta['file']).name != meta['file']:
        raise OSError('Seven-day artifact contract changed')
    path = Path(folder) / meta['file']
    if digest(path) != meta['sha256']:
        raise OSError('Seven-day artifact checksum differs from its receipt')
    value = joblib.load(path) if model else pd.read_parquet(path)
    if model and (value.get('features') != FEATURES or value.get('contract') != VERSION
                  or value.get('operationally_validated') is not False):
        raise OSError('Seven-day model input contract changed')
    return value


def saved_inputs(workspace, now):
    folder = Path(workspace) / 'data/processed/ontario_7day_v1'
    current = folder / 'current.json'
    weather, meta = pd.DataFrame(), {'sites': 0, 'status': 'not_collected'}
    if current.exists():
        text = current.read_text()
        meta = json.loads(text)
        weather = checked_file(str(folder), text).copy()
        required = {'site', 'date', 'lead', 'hours', 'expected_hours', 'time_safe', 'received_at',
                    'temp', 'rh', 'rain', 'wind', 'model', 'contract'}
        if (not required <= set(weather) or weather.duplicated(['site', 'date', 'lead']).any()
                or not weather.model.eq(MODEL).all() or not weather.contract.eq(VERSION).all()):
            raise OSError('Saved seven-day weather is incompatible')
        receipt = pd.to_datetime(weather.received_at, utc=True)
        fresh = (now - receipt).dt.total_seconds().between(0, 21600)
        valid = (np.isfinite(weather[['temp', 'rh', 'rain', 'wind']]).all(axis=1)
                 & weather.temp.between(-90, 60) & weather.rh.between(0, 100)
                 & weather.rain.ge(0) & weather.wind.ge(0) & weather.time_safe.eq(True))
        weather.loc[~(fresh & valid), 'hours'] = 0
        weather = with_rain_history(weather)
    bundle, model_meta = None, {'model': 'historical seasonal baseline', 'ranking_improved': False}
    model_path = folder / 'model.json'
    if model_path.exists():
        text = model_path.read_text()
        model_meta = json.loads(text)
        expected_terrain = model_meta.get('terrain_sha256')
        if expected_terrain:
            terrain = Path(workspace) / 'team_repository/data/interim/cdem_terrain_10km_summary.csv'
            if not terrain.exists() or digest(terrain) != expected_terrain:
                raise OSError('Static terrain differs from the trained model checksum')
        # Check integrity even when a candidate did not pass the ranking gate.
        bundle = checked_file(str(folder), text, model=True)
    return weather, meta, bundle, model_meta


def shortlist(frame, metric):
    frame = frame.sort_values([metric, 'grid_id'], ascending=[False, True]).reset_index(drop=True)
    frame['priority'] = np.arange(len(frame)) < max(1, int(np.ceil(len(frame) * .01)))
    return frame


def predict_cells(grid, rates, weather, bundle, start):
    frames = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        baseline = rates[day_index(day)].astype(float)
        probability, used = baseline.copy(), np.zeros(len(grid), dtype=bool)
        x = None
        if not weather.empty:
            x = feature_frame(grid, baseline, weather, str(day), offset + 1)
            if bundle is not None:
                used = x.weather_complete.eq(1).to_numpy()
                if used.any():
                    with threadpool_limits(limits=4):
                        probability[used] = calibrated(bundle['model'], bundle['calibrator'], x.loc[used], bundle['blend'])
        part = grid[['grid_id', 'longitude', 'latitude', 'region', 'landscape_complete']].copy()
        part['probability'], part['historical_probability'], part['weather_days_used'] = probability, baseline, used.astype(int)
        part['date'], part['lead'] = str(day), offset + 1
        part['method'] = np.where(used, 'weather_plus_history_research', 'historical_seasonal_estimate')
        for field in ['temp', 'rh', 'rain', 'wind', 'prior_rain_7d_mm', 'prior_rain_coverage_days']:
            part[field] = x[field].to_numpy() if x is not None else np.nan
        frames.append(shortlist(part, 'probability'))
    return pd.concat(frames, ignore_index=True)


def daily_summary(cells, weather, meta, region):
    selected = cells[cells.region.eq(region)] if region != 'All Ontario' else cells
    rows = []
    for text, part in selected.groupby('date', sort=True):
        day, lead = date.fromisoformat(text), int(part.lead.iloc[0])
        used = int(part.weather_days_used.sum())
        weather_part = weather[weather.date.eq(text) & weather.lead.eq(lead)] if not weather.empty else weather
        complete = int((weather_part.hours.eq(weather_part.expected_hours) & weather_part.time_safe.eq(True)).sum()) if len(weather_part) else 0
        status = 'available' if complete == meta['sites'] and complete else 'partial' if complete else 'unavailable'
        rows.append({'date': text, 'cells': len(part), 'expected_positive_cell_days': float(part.probability.sum()),
                     'highest_cell_probability': float(part.probability.max()), 'weather_cells_used': used,
                     'historical_expected_positive_cell_days': float(part.historical_probability.sum()),
                     'method': 'weather_plus_history_research' if used else 'historical_seasonal_estimate',
                     'outside_evaluated_season': bool(used and day.month not in range(5, 11)),
                     'fallback_reason': None if used else 'Matching weather model unavailable' if complete else 'Weather missing or stale',
                     'weather': {'status': status, 'complete_sites': complete, 'total_sites': meta['sites']}})
    return rows


def range_cells(grid, combined):
    cells = grid[['grid_id', 'longitude', 'latitude', 'region', 'landscape_complete']].copy()
    totals = combined.groupby('grid_id').agg(expected_positive_days=('probability', 'sum'),
        weather_days_used=('weather_days_used', 'sum'), historical_expected_positive_days=('historical_probability', 'sum'),
        candidate_expected_positive_days=('candidate_probability', 'sum'),
        candidate_weather_days_used=('candidate_weather_days_used', 'sum'))
    cells = cells.join(totals, on='grid_id', validate='one_to_one')
    cells['method'] = np.where(cells.weather_days_used.gt(0), 'weather_plus_history_research', 'historical_seasonal_estimate')
    return shortlist(cells, 'expected_positive_days')


def model_notice(rows, model):
    weather_days = sum(row['weather_cells_used'] > 0 for row in rows)
    ready = sum(row['weather']['status'] == 'available' for row in rows)
    note = f'Weather ready on {ready} of 7 days; used in estimates on {weather_days} of 7. '
    if weather_days:
        note += 'Experimental weather + history estimates are active. '
        if not model['ranking_improved']:
            note += 'Development replacement checks did not pass; an accuracy improvement is not established. '
        elif not model.get('all_metrics_improved'):
            note += 'Probability accuracy has not passed all development checks. '
    if weather_days < 7:
        note += 'Cells and days without usable weather or a matching model use historical estimates. '
    if any(row['outside_evaluated_season'] for row in rows):
        note += 'These dates are outside the May–October evaluation season. '
    note += 'Higher rank does not mean a fire is likely. Research estimates; live accuracy is unmeasured. Today includes hours already elapsed.'
    return note


def outlook(workspace, query, now=None, *, all_days=False):
    start, end, region, selected = parse_query(query, now)
    clock = pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    grid, rates, _ = artifacts(workspace)
    grid = enrich_grid(grid, workspace)
    weather, meta, bundle, model = saved_inputs(workspace, clock)
    combined = predict_cells(grid, rates, weather, bundle, start)
    combined['candidate_probability'] = combined.probability
    combined['candidate_weather_days_used'] = combined.weather_days_used
    combined['candidate_outside_evaluated_season'] = (combined.candidate_weather_days_used.gt(0)
        & ~pd.to_datetime(combined.date).dt.month.between(5, 10))
    rows = daily_summary(combined, weather, meta, region)
    if all_days:
        cells = combined
    elif query.get('view', ['range'])[0] == 'day':
        cells = combined[combined.date.eq(str(selected))].copy()
    else:
        cells = range_cells(grid, combined)
    cells = cells[cells.region.eq(region)] if region != 'All Ontario' else cells
    identity = model.get('training_fingerprint', '')
    result_path = Path(workspace) / 'reports/ontario_7day_v1/experiments' / identity[:12] / 'results.json'
    results = json.loads(result_path.read_text()) if result_path.exists() else None
    daily = {'start': str(start), 'end': str(end), 'days': 7, 'offset': 0, 'page_days': 7,
             'has_next': False, 'region': region, 'rows': rows, 'requested_model': 'weather',
             'model': model, 'model_notice': model_notice(rows, model), 'weather_source': 'Open-Meteo GFS',
             'forecast_received_at': meta.get('received_at'), 'comparison': results,
             'estimate_summary': {'weather_days_used': sum(row['weather_cells_used'] > 0 for row in rows),
                                  'outside_evaluated_season': any(row['outside_evaluated_season'] for row in rows)},
             'selection_policy': 'experimental_weather_plus_history',
             'operationally_validated': False, 'current_day_partly_elapsed': True,
             'priority_definition': 'Highest 1% of Ontario cells by estimated score, relative ranking only'}
    return daily, cells.reset_index(drop=True)


def save_prospective(workspace):
    folder = Path(workspace) / 'data/processed/ontario_7day_v1'
    daily, frame = outlook(workspace, {}, all_days=True)
    frame['schema_version'] = 2
    frame['selection_policy'] = daily['selection_policy']
    frame['issued_at'] = pd.Timestamp.now(tz='UTC').isoformat()
    target_start = pd.to_datetime(frame.date).dt.tz_localize('America/Toronto').dt.tz_convert('UTC')
    frame['eligible_for_prospective_evaluation'] = target_start > pd.Timestamp(frame.issued_at.iloc[0])
    frame['forecast_received_at'] = daily['forecast_received_at']
    candidate_sha = daily['model'].get('sha256')
    _, _, baseline = artifacts(workspace)
    frame['candidate_model_sha256'] = candidate_sha
    frame['model_sha256'] = np.where(frame.weather_days_used.gt(0), candidate_sha,
                                     baseline['sha256']['seasonal_2026.npy'])
    dest = folder / 'prospective'
    dest.mkdir(exist_ok=True)
    path = dest / (pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%fZ') + '.parquet')
    frame.to_parquet(path, index=False)
    return str(path)


def refresh_loop(workspace, stop):
    folder = Path(workspace) / 'data/processed/ontario_7day_v1'
    folder.mkdir(parents=True, exist_ok=True)
    while not stop.is_set():
        status = {'checked_at': pd.Timestamp.now(tz='UTC').isoformat()}
        try:
            path = folder / 'current.json'
            meta = json.loads(path.read_text()) if path.exists() else {}
            age = (pd.Timestamp.now(tz='UTC') - pd.Timestamp(meta['received_at'])).total_seconds() if meta else float('inf')
            refreshed = meta.get('start') != str(today_in_ontario()) or age >= 10800 or meta.get('past_days') != 7
            try:
                try:
                    identity, _ = fingerprint(workspace)
                except FileNotFoundError:
                    identity, _ = fingerprint(workspace, diagnostic=False)
                model_path = folder / 'model.json'
                model = json.loads(model_path.read_text()) if model_path.exists() else {}
                attempt_path = folder / 'training_attempt.json'
                attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else {}
                if attempt.get('fingerprint') == identity and attempt.get('status') == 'failed':
                    status['training'] = 'failed_awaiting_new_data_or_code'
                elif attempt.get('fingerprint') == identity and attempt.get('status') == 'complete':
                    status['training'] = 'comparison_complete_no_new_training_data'
                elif model.get('training_fingerprint') != identity:
                    status['training'] = 'running'
                    save_json(folder / 'worker.json', status)
                    save_json(attempt_path, {'fingerprint': identity, 'status': 'running'})
                    try:
                        run(workspace)
                    except FileNotFoundError:
                        save_json(attempt_path, {'fingerprint': identity, 'status': 'waiting_for_diagnostic_archive'})
                        raise
                    except (OSError, ValueError, RuntimeError) as error:
                        save_json(attempt_path, {'fingerprint': identity, 'status': 'failed', 'message': str(error)})
                        raise
                    save_json(attempt_path, {'fingerprint': identity, 'status': 'complete'})
                    refreshed = True
                else:
                    status['training'] = 'unchanged_data_no_retraining'
            except FileNotFoundError:
                status['training'] = 'waiting_for_complete_training_archive'
            if refreshed:
                collect_current(workspace)
            prospective = folder / 'prospective'
            if refreshed or not prospective.exists():
                status['prospective_file'] = save_prospective(workspace)
            status['status'] = 'ready'
        except (OSError, ValueError, RuntimeError) as error:
            status.update(status='failed', message=str(error))
        temporary = folder / 'worker.tmp.json'
        temporary.write_text(json.dumps(status, indent=2))
        temporary.replace(folder / 'worker.json')
        stop.wait(60)


def archive_loop(workspace, stop):
    path = Path(workspace) / 'data/processed/ontario_7day_v1/archive_status.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    while not stop.is_set():
        try:
            save_json(path, {'status': 'downloading_or_waiting_for_provider_quota'})
            collect_archive(workspace)
            save_json(path, {'status': 'complete'})
            return
        except requests.RequestException as error:
            save_json(path, {'status': 'retrying', 'message': str(error)})
            stop.wait(61)
        except (OSError, ValueError) as error:
            save_json(path, {'status': 'failed', 'message': str(error)})
            return


def start_worker(workspace):
    from scripts.forecast_overview import refresh_incidents_loop
    stop = Event()
    workers = [Thread(target=target, args=(workspace, stop), daemon=True, name=name)
               for target, name in [(refresh_loop, 'seven-day-outlook'), (archive_loop, 'ignition-training-archive'),
                                    (refresh_incidents_loop, 'reported-fire-refresh')]]
    for worker in workers:
        worker.start()
    return stop, workers
