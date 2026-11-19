"""Matched GFS forecast offsets for seven-day Ontario ignition research."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from threading import BoundedSemaphore, Lock
import time

import numpy as np
import pandas as pd
import requests

MODEL = 'gfs_seamless'
ENDPOINT = 'https://previous-runs-api.open-meteo.com/v1/forecast'
VERSION = 'gfs-seven-local-days-v1'
FIELDS = {'temperature_2m': ('temp', '°C'), 'relative_humidity_2m': ('rh', '%'),
          'precipitation': ('rain', 'mm'), 'wind_speed_10m': ('wind', 'km/h')}
ZONE = 'America/Toronto'
WEATHER_COLUMNS = ('temp', 'rh', 'rain', 'wind')
_REQUEST_LOCK = Lock()
_REQUEST_TIMES = []
_DOWNLOAD_SLOTS = BoundedSemaphore(2)


def wait_for_budget(cost, priority=False):
    """Leave headroom below the public API's weighted request limits."""
    while True:
        with _REQUEST_LOCK:
            now = time.time()
            _REQUEST_TIMES[:] = [(stamp, weight) for stamp, weight in _REQUEST_TIMES if now - stamp < 86400]
            limits = [(60, 600), (3600, 5000), (86400, 10000)] if priority else [(60, 500), (3600, 4500), (86400, 9000)]
            waits = [((now // window) + 1) * window - now + 1
                     for window, limit in limits
                     if sum(weight for stamp, weight in _REQUEST_TIMES if stamp // window == now // window) + cost > limit]
            if not waits:
                _REQUEST_TIMES.append((now, cost))
                return
            delay = min(waits)
        time.sleep(min(60, delay))


def variables():
    return {f'{name}_previous_day{lead}': unit for lead in range(1, 8)
            for name, (_, unit) in FIELDS.items()}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locations(grid):
    bx, by = grid.grid_x_m // 100000, grid.grid_y_m // 100000
    ids = bx.astype(str) + '_' + by.astype(str)
    distance = (grid.grid_x_m + 5000 - (bx + .5) * 100000) ** 2
    distance += (grid.grid_y_m + 5000 - (by + .5) * 100000) ** 2
    points = grid.loc[distance.groupby(ids).idxmin(), ['latitude', 'longitude']].copy()
    points['site'] = ids.loc[points.index]
    return ids, points.sort_values('site').reset_index(drop=True)


def normalise(document, points, start, end, received):
    documents = document if isinstance(document, list) else [document]
    if len(documents) != len(points):
        raise ValueError('Weather response location count changed')
    frames = []
    for (_, point), doc in zip(points.iterrows(), documents):
        if doc.get('utc_offset_seconds') != 0 or doc.get('timezone') not in ('GMT', 'UTC'):
            raise ValueError('UTC weather timestamps required')
        if any(doc.get('hourly_units', {}).get(key) != unit for key, unit in variables().items()):
            raise ValueError('Weather units differ from the model contract')
        if abs(doc['latitude'] - point.latitude) > .35 or abs(doc['longitude'] - point.longitude) > .35:
            raise ValueError('Weather response location differs from the request')
        hourly = pd.DataFrame(doc['hourly'])
        stamp = pd.to_datetime(hourly.pop('time'), utc=True)
        expected = pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(days=2),
                                 freq='h', inclusive='left', tz='UTC')
        if stamp.duplicated().any() or not stamp.reset_index(drop=True).equals(pd.Series(expected)):
            raise ValueError('Weather hourly range is incomplete or duplicated')
        local_dates = stamp.dt.tz_convert(ZONE).dt.strftime('%Y-%m-%d')
        for lead in range(1, 8):
            names = {f'{name}_previous_day{lead}': field for name, (field, _) in FIELDS.items()}
            x = hourly[list(names)].rename(columns=names).astype(float)
            valid = (np.isfinite(x).all(axis=1) & x.temp.between(-90, 60)
                     & x.rh.between(0, 100) & x.rain.ge(0) & x.wind.ge(0))
            x.loc[~valid, list(WEATHER_COLUMNS)] = np.nan
            x['date'], x['time'] = local_dates, stamp
            result = x.groupby('date', sort=True).agg(temp=('temp', 'max'), rh=('rh', 'min'),
                rain=('rain', 'sum'), wind=('wind', 'max'), hours=('temp', 'count'), latest=('time', 'max'))
            result = result.loc[start:end].reset_index()
            dates = pd.DatetimeIndex(result.date)
            midnight = dates.tz_localize(ZONE).tz_convert('UTC')
            next_midnight = (dates + pd.Timedelta(days=1)).tz_localize(ZONE).tz_convert('UTC')
            result['expected_hours'] = (next_midnight - midnight).total_seconds().astype(int) // 3600
            issue = (dates - pd.Timedelta(days=lead - 1)).tz_localize(ZONE).tz_convert('UTC')
            reference = result.pop('latest') - pd.Timedelta(days=lead)
            result['issue_time'] = issue.astype(str)
            result['reference_upper_bound'] = reference.astype(str)
            result['time_safe'] = reference.to_numpy() < issue.to_numpy()
            result.loc[result.hours.ne(result.expected_hours), list(WEATHER_COLUMNS)] = np.nan
            result['site'], result['lead'], result['received_at'] = point.site, lead, received
            result['model'], result['contract'] = MODEL, VERSION
            frames.append(result)
    return pd.concat(frames, ignore_index=True)


def acquire(points, start, end, folder, fresh=False):
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    def batch_request(index):
        batch = points.iloc[index:index + 6]
        params = {'latitude': ','.join(f'{v:.5f}' for v in batch.latitude),
                  'longitude': ','.join(f'{v:.5f}' for v in batch.longitude),
                  'start_date': start, 'end_date': (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                  'hourly': ','.join(variables()), 'models': MODEL,
                  'timezone': 'UTC', 'wind_speed_unit': 'kmh'}
        path = folder / f'{start}_{end}_{index}.parquet'
        receipt_path = path.with_suffix('.json')
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        age = (pd.Timestamp.now(tz='UTC') - pd.Timestamp(receipt['received_at'])).total_seconds() if receipt else float('inf')
        if (path.exists() and receipt.get('params') == params and receipt.get('sha256') == digest(path)
                and (not fresh or 0 <= age < 10800)):
            return pd.read_parquet(path)
        else:
            for attempt in range(3):
                try:
                    days = (pd.Timestamp(params['end_date']) - pd.Timestamp(start)).days + 1
                    wait_for_budget(len(batch) * len(variables()) / 10 * max(1, days / 14), priority=fresh)
                    with _DOWNLOAD_SLOTS:
                        response = requests.get(ENDPOINT, params=params, timeout=(30, 180))
                    if response.status_code == 429:
                        reason = response.json().get('reason', 'Request limit reached')
                        print(f'Provider limit: {reason}. Waiting before retry.', flush=True)
                        until_midnight = (pd.Timestamp.now(tz='UTC').normalize() + pd.Timedelta(days=1)
                                          - pd.Timestamp.now(tz='UTC')).total_seconds() + 61
                        until_hour = (pd.Timestamp.now(tz='UTC').ceil('h') - pd.Timestamp.now(tz='UTC')).total_seconds() + 61
                        delay = until_hour if 'hour' in reason.lower() else until_midnight if 'daily' in reason.lower() else 61
                        time.sleep(delay)
                    response.raise_for_status()
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
            received = pd.Timestamp.now(tz='UTC').isoformat()
            frame = normalise(response.json(), batch, start, end, received)
            temporary = path.with_suffix('.tmp')
            frame.to_parquet(temporary, index=False)
            temporary.replace(path)
            receipt = {'params': params, 'url': response.url, 'received_at': received,
                       'sha256': digest(path), 'contract': VERSION}
            receipt_path.write_text(json.dumps(receipt, indent=2))
        return frame
    with ThreadPoolExecutor(max_workers=3) as pool:
        for number, frame in enumerate(pool.map(batch_request, range(0, len(points), 6)), 1):
            frames.append(frame)
            print(f'{start} {end}: {min(number * 6, len(points))}/{len(points)} weather locations', flush=True)
    result = pd.concat(frames, ignore_index=True)
    if result.duplicated(['site', 'date', 'lead']).any():
        raise ValueError('Duplicate weather location/date/lead')
    return result


def collect_current(workspace, now=None):
    workspace = Path(workspace)
    folder = workspace / 'data/processed/ontario_7day_v1'
    grid = pd.read_parquet(workspace / 'data/processed/ontario_range_v1/grid.parquet')
    _, points = locations(grid)
    clock = pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    start = clock.tz_convert(ZONE).strftime('%Y-%m-%d')
    end = (pd.Timestamp(start) + pd.Timedelta(days=6)).strftime('%Y-%m-%d')
    batch_id = clock.floor('3h').strftime('%Y%m%dT%HZ')
    history_start = (pd.Timestamp(start) - pd.Timedelta(days=7)).strftime('%Y-%m-%d')
    frame = acquire(points, history_start, end, folder / 'forecast_cache' / batch_id, fresh=True)
    lead = (pd.to_datetime(frame.date) - pd.Timestamp(start)).dt.days + 1
    frame = frame[frame.lead.eq(lead.clip(lower=1))].copy()
    name = f'weather_{clock.strftime("%Y%m%dT%H%M%S%fZ")}.parquet'
    frame.to_parquet(folder / name, index=False)
    manifest = {'contract': VERSION, 'model': MODEL, 'start': start, 'end': end, 'sites': len(points),
                'received_at': pd.to_datetime(frame.received_at, utc=True).min().isoformat(),
                'collected_at': pd.Timestamp.now(tz='UTC').isoformat(), 'past_days': 7,
                'file': name, 'sha256': digest(folder / name),
                'historical_availability_verified': False}
    temporary = folder / 'current.tmp.json'
    temporary.write_text(json.dumps(manifest, indent=2))
    temporary.replace(folder / 'current.json')
    return manifest


def collect_archive(workspace):
    workspace = Path(workspace)
    folder = workspace / 'data/processed/ontario_7day_v1'
    _, points = locations(pd.read_parquet(workspace / 'data/processed/ontario_range_v1/grid.parquet'))
    for year in (2024, 2025):
        receipt_path = folder / f'archive_{year}.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        if receipt.get('contract') == VERSION and all((folder / name).exists() and digest(folder / name) == value
                for name, value in receipt.get('sha256', {}).items()) and len(receipt.get('sha256', {})) == 6:
            continue
        frame = acquire(points, f'{year}-05-01', f'{year}-10-31', folder / 'archive_cache')
        hashes = {}
        for month in range(5, 11):
            part = frame[frame.date.str.startswith(f'{year}-{month:02}')]
            path = folder / f'weather_{year}_{month:02}.parquet'
            part.to_parquet(path.with_suffix('.tmp'), index=False)
            path.with_suffix('.tmp').replace(path)
            hashes[path.name] = digest(path)
        receipt_path.write_text(json.dumps({'contract': VERSION, 'sha256': hashes}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['current', 'archive'])
    parser.add_argument('workspace', type=Path)
    args = parser.parse_args()
    print(collect_current(args.workspace) if args.mode == 'current' else collect_archive(args.workspace), flush=True)
