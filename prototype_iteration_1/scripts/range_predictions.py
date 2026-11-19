"""Paginated daily Ontario estimates from a frozen seasonal model and saved forecast coverage."""
import csv
import calendar
from datetime import date, datetime, timedelta
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from scripts.week5_ignition import apply_calibration
import pandas as pd

PAGE_DAYS = 31
WEATHER_FEATURES = ['seasonal_probability', 'season_sin', 'season_cos', 'temp', 'rh', 'rain', 'wind', 'hours']
WEATHER_METHOD = 'HRDPS previous_day1 fixed offset, 12-21 UTC target window'
REGIONS = ('All Ontario', 'Northwest', 'Northeast', 'South (below 46 N)')


def today_in_ontario(now=None):
    clock = now or datetime.now(ZoneInfo('America/Toronto'))
    if clock.tzinfo is None:
        raise ValueError('A timezone-aware clock is required')
    return clock.astimezone(ZoneInfo('America/Toronto')).date()


def parse_request(query, now=None):
    if set(query) - {'days', 'offset', 'region', 'date', 'view', 'model'} or any(len(v) != 1 for v in query.values()):
        raise ValueError('One value per supported field is required')
    if query.get('view', ['day'])[0] not in ('day', 'range'):
        raise ValueError('Choose a daily or whole-range map')
    if query.get('model', ['seasonal'])[0] not in ('seasonal', 'weather'):
        raise ValueError('Choose weather or historical estimates')
    text = query.get('days', ['14'])[0]
    offset_text = query.get('offset', ['0'])[0]
    if not text.isascii() or not text.isdigit() or len(text) > 7:
        raise ValueError('Enter a positive whole number of days')
    if not offset_text.isascii() or not offset_text.isdigit() or len(offset_text) > 7:
        raise ValueError('Invalid page offset')
    days, offset = int(text), int(offset_text)
    start = today_in_ontario(now)
    if days < 1 or days > (date.max - start).days + 1 or offset >= days:
        raise ValueError('The date range or page is outside the supported calendar')
    region = query.get('region', ['All Ontario'])[0]
    if region not in REGIONS:
        raise ValueError('Unknown Ontario region')
    end = start + timedelta(days=days - 1)
    selected = date.fromisoformat(query.get('date', [start.isoformat()])[0])
    if not start <= selected <= end:
        raise ValueError('Choose a day within the requested range')
    return start, end, days, offset, region, selected


@lru_cache(maxsize=2)
def load_artifacts(workspace, manifest_mtime):
    folder = Path(workspace) / 'data/processed/ontario_range_v1'
    manifest = json.loads((folder / 'runtime_manifest.json').read_text())
    for name, expected in manifest['sha256'].items():
        if Path(name).name != name:
            raise ValueError('Invalid runtime artifact name')
        with (folder / name).open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                raise ValueError('Prediction artifacts differ from the saved model')
    grid = pd.read_parquet(folder / 'grid.parquet')
    rates = np.load(folder / 'seasonal_2026.npy', allow_pickle=False)
    if grid.grid_id.duplicated().any() or rates.shape != (366, len(grid)):
        raise ValueError('Model and grid do not align')
    if not np.isfinite(rates).all() or (rates < 0).any() or (rates > 1).any():
        raise ValueError('Model probabilities are invalid')
    return grid, rates, manifest


def artifacts(workspace):
    path = Path(workspace) / 'data/processed/ontario_range_v1/runtime_manifest.json'
    return load_artifacts(str(workspace), path.stat().st_mtime_ns)


def select_grid(grid, region):
    if region == 'All Ontario':
        return np.ones(len(grid), dtype=bool)
    return grid.region.eq(region).to_numpy()


def day_index(day):
    return (date(2000, day.month, day.day) - date(2000, 1, 1)).days


def weather_snapshot(workspace, now=None):
    folder = Path(workspace) / 'data/processed/ontario_range_v1'
    data_path, meta_path = folder / 'current_weather.parquet', folder / 'current_weather.json'
    if not data_path.exists() or not meta_path.exists():
        return pd.DataFrame(), {'status': 'not_collected', 'sites': 0}
    meta = json.loads(meta_path.read_text())
    frame = pd.read_parquet(data_path).copy()
    required = {'site', 'date', 'temp', 'rh', 'rain', 'wind', 'hours', 'received_at'}
    if not required <= set(frame.columns):
        raise OSError('Saved weather is missing required inputs')
    clock = pd.Timestamp(now or datetime.now(ZoneInfo('UTC')))
    receipt = pd.to_datetime(frame.received_at, utc=True)
    frame['date'] = pd.to_datetime(frame.date).dt.strftime('%Y-%m-%d')
    if frame[['site', 'date']].isna().any().any() or frame.duplicated(['site', 'date']).any():
        raise OSError('Saved weather contains invalid location/date keys')
    values = frame[['temp', 'rh', 'rain', 'wind']]
    frame['usable'] = (frame.hours.eq(10) & np.isfinite(values).all(axis=1)
                       & frame.temp.between(-90, 60) & frame.rh.between(0, 100)
                       & frame.rain.ge(0) & frame.wind.ge(0))
    frame['fresh'] = (clock - receipt).dt.total_seconds().between(0, 21600)
    if meta.get('method') != WEATHER_METHOD:
        return pd.DataFrame(), {**meta, 'status': 'incompatible_weather_source'}
    return frame, {**meta, 'status': 'loaded'}


def weather_coverage(snapshot, day):
    frame, meta = snapshot
    if frame.empty:
        return {'status': meta['status'], 'complete_sites': 0}
    part = frame[frame.date.eq(day.isoformat())]
    complete = int((part.usable & part.fresh).sum())
    if not part.empty and not part.fresh.any():
        status = 'expired'
    else:
        status = ('available' if complete == meta['sites'] else 'partial' if complete
                  else 'incomplete_weather' if not part.empty else 'beyond_saved_forecast')
    return {'status': status, 'complete_sites': complete, 'total_sites': meta['sites'],
            'collected_at': meta['collected_at']}


@lru_cache(maxsize=2)
def weather_bundle(workspace, manifest_mtime):
    folder = Path(workspace) / 'data/processed/ontario_range_v1'
    manifest = json.loads((folder / 'runtime_manifest.json').read_text())
    entry = manifest.get('weather_model')
    if entry is None:
        return None
    path = folder / 'weather_candidate.joblib'
    if not path.exists():
        return None
    with path.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != entry['sha256']:
            raise OSError('Saved weather model differs from its registered checksum')
    bundle = joblib.load(path)
    if bundle.get('features') != WEATHER_FEATURES or bundle.get('operationally_validated') is not False:
        raise OSError('Saved weather model has an incompatible input contract')
    return bundle


def forecast_updates(workspace, grid, rates, snapshot, dates):
    """Replace historical estimates only for cells with usable saved forecast inputs."""
    start, end = dates
    weather, _ = snapshot
    if weather.empty:
        return {}
    manifest_path = Path(workspace) / 'data/processed/ontario_range_v1/runtime_manifest.json'
    bundle = weather_bundle(str(workspace), manifest_path.stat().st_mtime_ns)
    if bundle is None:
        return {}
    site_ids = (grid.grid_x_m // 100000).astype(str) + '_' + (grid.grid_y_m // 100000).astype(str)
    updates = {}
    for text, part in weather.groupby('date', sort=True):
        day = date.fromisoformat(text)
        if not start <= day <= end:
            continue
        inputs = part.set_index('site').reindex(site_ids).reset_index(drop=True)
        used = inputs.usable.eq(True).to_numpy() & inputs.fresh.eq(True).to_numpy()
        if not used.any():
            continue
        baseline = rates[day_index(day)].astype(float)
        inputs['seasonal_probability'] = baseline
        doy = day.timetuple().tm_yday
        inputs['season_sin'] = np.sin(2 * np.pi * doy / 365.25)
        inputs['season_cos'] = np.cos(2 * np.pi * doy / 365.25)
        with threadpool_limits(limits=4):
            raw = bundle['model'].predict_proba(inputs.loc[used, WEATHER_FEATURES].astype('float32'))[:, 1]
            calibrated = apply_calibration(bundle['calibrator'], raw)
        if not np.isfinite(calibrated).all() or ((calibrated < 0) | (calibrated > 1)).any():
            raise OSError('Weather model returned invalid probabilities')
        probability = baseline.copy()
        probability[used] = calibrated
        updates[text] = {'probability': probability, 'used': used,
                         'outside_evaluated_season': day.month not in range(5, 11),
                         'site_ids': site_ids.to_numpy(), 'inputs': inputs}
    return updates


def method_for(used):
    if used.all():
        return 'weather_plus_history_research'
    return 'mixed_weather_and_history' if used.any() else 'historical_seasonal_estimate'


def range_response(workspace, query, now=None):
    start, end, days, offset, region, _ = parse_request(query, now)
    grid, rates, manifest = artifacts(workspace)
    mask = select_grid(grid, region)
    requested = query.get('model', ['seasonal'])[0]
    snapshot = weather_snapshot(workspace, now)
    updates = forecast_updates(workspace, grid, rates, snapshot, (start, end)) if requested == 'weather' else {}
    rows = []
    for delta in range(offset, min(days, offset + PAGE_DAYS)):
        day = start + timedelta(days=delta)
        baseline = rates[day_index(day), mask]
        update = updates.get(day.isoformat())
        used = update['used'][mask] if update else np.zeros(int(mask.sum()), dtype=bool)
        probability = update['probability'][mask] if update else baseline
        coverage = weather_coverage(snapshot, day)
        reason = ('historical_selected' if requested == 'seasonal' else coverage['status']
                  if coverage['status'] != 'available' else 'weather_model_or_mapping_unavailable')
        rows.append({'date': day.isoformat(), 'expected_positive_cell_days': float(probability.sum()),
                     'highest_cell_probability': float(probability.max()), 'cells': int(mask.sum()),
                     'historical_expected_positive_cell_days': float(baseline.sum()),
                     'weather_cells_used': int(used.sum()), 'method': method_for(used),
                     'outside_evaluated_season': bool(update and update['outside_evaluated_season']),
                     'weather': coverage, 'fallback_reason': None if used.any() else reason})
    scores = json.loads((Path(workspace) / 'reports/ontario_range_v1/weather_scores.json').read_text())
    summary = {'weather_days_used': sum(bool(item['used'][mask].any()) for item in updates.values()),
               'outside_evaluated_season': any(item['outside_evaluated_season'] and item['used'][mask].any()
                                               for item in updates.values())}
    return {'start': start.isoformat(), 'end': end.isoformat(), 'days': days, 'offset': offset,
            'page_days': PAGE_DAYS, 'has_next': offset + PAGE_DAYS < days, 'region': region,
            'rows': rows, 'model': manifest['model'], 'requested_model': requested,
            'estimate_summary': {k: bool(v) if isinstance(v, np.bool_) else v for k, v in summary.items()},
            'weather_candidate_comparison': scores, 'operationally_validated': False,
            'current_day_partly_elapsed': True,
            'scope': 'Recorded IFR starts in the pinned Ontario agency snapshot; other fire types are excluded.'}


def calendar_counts(start, end):
    """Count each month/day without expanding a long date range."""
    def leap_years_through(year):
        return year // 4 - year // 100 + year // 400

    counts = np.full(366, end.year - start.year + 1, dtype=np.int64)
    counts[59] = leap_years_through(end.year) - leap_years_through(start.year - 1)
    for index in range(366):
        exemplar = date(2000, 1, 1) + timedelta(days=index)
        month_day = (exemplar.month, exemplar.day)
        if month_day < (start.month, start.day) and (index != 59 or calendar.isleap(start.year)):
            counts[index] -= 1
        if month_day > (end.month, end.day) and (index != 59 or calendar.isleap(end.year)):
            counts[index] -= 1
    return counts


def cell_response(workspace, query, now=None):
    start, end, _, _, region, day = parse_request(query, now)
    grid, rates, _ = artifacts(workspace)
    mask = select_grid(grid, region)
    snapshot = weather_snapshot(workspace, now)
    requested = query.get('model', ['seasonal'])[0]
    whole_range = query.get('view', ['day'])[0] == 'range'
    first, last = (start, end) if whole_range else (day, day)
    updates = forecast_updates(workspace, grid, rates, snapshot, (first, last)) if requested == 'weather' else {}
    result = grid.loc[mask, ['grid_id', 'longitude', 'latitude', 'region', 'landscape_complete']].copy()
    used_days = np.zeros(int(mask.sum()), dtype=int)
    if whole_range:
        metric = 'expected_positive_days'
        baseline = np.einsum('i,ij->j', calendar_counts(start, end), rates[:, mask], dtype=np.float64)
        values = baseline.copy()
        for text, update in updates.items():
            values += update['probability'][mask] - rates[day_index(date.fromisoformat(text)), mask]
            used_days += update['used'][mask]
        result['start_date'], result['end_date'] = start.isoformat(), end.isoformat()
        result['historical_expected_positive_days'] = baseline
    else:
        metric = 'probability'
        baseline = rates[day_index(day), mask].astype(float)
        update = updates.get(day.isoformat())
        values = update['probability'][mask] if update else baseline
        used_days = update['used'][mask].astype(int) if update else used_days
        result['date'] = day.isoformat()
        result['historical_probability'] = baseline
        if update:
            result['weather_site'] = update['site_ids'][mask]
            for field in ['temp', 'rh', 'rain', 'wind']:
                inputs = update['inputs'].loc[mask, field].to_numpy()
                result[field] = np.where(used_days > 0, inputs, None)
    result[metric] = values
    result['weather_days_used'] = used_days
    outside = np.zeros(int(mask.sum()), dtype=bool)
    for update in updates.values():
        if update['outside_evaluated_season']:
            outside |= update['used'][mask]
    result['outside_evaluated_season'] = outside
    result['method'] = np.select([used_days == 0, used_days == (last - first).days + 1],
                                 ['historical_seasonal_estimate', 'weather_plus_history_research'],
                                 default='mixed_weather_and_history')
    return result.sort_values([metric, 'grid_id'], ascending=[False, True]).reset_index(drop=True)


def daily_csv(result):
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(['date', 'region', 'cells', 'expected_positive_cell_days', 'highest_cell_probability', 'method', 'weather_cells_used', 'historical_expected_positive_cell_days', 'outside_evaluated_season'])
    for row in result['rows']:
        writer.writerow([row['date'], result['region'], row['cells'], row['expected_positive_cell_days'],
                         row['highest_cell_probability'], row['method'], row['weather_cells_used'],
                         row['historical_expected_positive_cell_days'], row['outside_evaluated_season']])
    return text.getvalue().encode('utf-8')
