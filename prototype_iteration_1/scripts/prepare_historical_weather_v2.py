"""Build a separate daily-available-station weather candidate for development only."""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from collections import deque
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'team_repository'
OUTPUT = ROOT / 'data/processed/historical_weather_development_v2'
REPORT = ROOT / 'reports/week_4_data_2026-10-16'
EARTH_RADIUS_KM = 6371.0088
FIELDS = {'temp': 'cwfis_temp_c', 'rh': 'cwfis_rh_pct', 'ws': 'cwfis_wind_speed_kmh',
          'precip': 'cwfis_precip_mm', 'ffmc': 'cwfis_ffmc', 'dmc': 'cwfis_dmc',
          'dc': 'cwfis_dc', 'isi': 'cwfis_isi', 'bui': 'cwfis_bui', 'fwi': 'cwfis_fwi', 'dsr': 'cwfis_dsr'}


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def sphere(longitude, latitude) -> np.ndarray:
    lon, lat = np.radians(longitude), np.radians(latitude)
    return np.column_stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


def valid_measurements(field: str, values: np.ndarray) -> np.ndarray:
    valid = np.isfinite(values)
    if field == 'temp':
        return valid & (values >= -90) & (values <= 60)
    if field in ('rh', 'ffmc'):
        return valid & (values >= 0) & (values <= (100 if field == 'rh' else 101))
    return valid & (values >= 0)


def daily_features(grid: pd.DataFrame, records: pd.DataFrame, radius_km: float = 200., count: int = 4):
    if not 0 < radius_km <= 1000 or count < 1:
        raise ValueError('Invalid distance radius or station count')
    records = records.loc[valid_measurements('fwi', records.fwi.to_numpy())].sort_values('station_key').reset_index(drop=True)
    n = len(grid)
    if records.empty:
        distance, indices = np.full((n, count), np.inf), np.zeros((n, count), dtype=int)
    else:
        tree = cKDTree(sphere(records.lon, records.lat))
        chord, indices = tree.query(sphere(grid.centroid_longitude, grid.centroid_latitude), k=list(range(1, count + 1)))
        distance = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))
        distance = np.where(np.isfinite(chord), distance, np.inf)
    selected = np.isfinite(distance) & (distance <= radius_km)
    safe_indices = np.minimum(indices, max(0, len(records) - 1))
    weights = np.where(selected, 1 / np.maximum(distance, 1.) ** 2, 0.)
    counts = selected.sum(axis=1)
    result = pd.DataFrame({'grid_id': grid.grid_id.to_numpy(), 'cwfis_station_count': counts.astype('int16'),
                           'cwfis_nearest_station_km': np.where(counts > 0, distance[:, 0], np.nan),
                           'cwfis_observation_coverage_fraction': counts / count,
                           'cwfis_missing': (counts == 0).astype('int8')})
    for raw, name in FIELDS.items():
        values = np.full_like(distance, np.nan) if records.empty else records[raw].to_numpy()[safe_indices]
        valid = selected & valid_measurements(raw, values)
        denominator = (weights * valid).sum(axis=1)
        numerator = (weights * np.where(valid, values, 0.)).sum(axis=1)
        result[name] = np.divide(numerator, denominator, out=np.full(n, np.nan), where=denominator > 0)
    for name in ('imputed_station_fraction', 'calcstatus_nonzero_fraction'):
        if records.empty:
            result[f'cwfis_{name}'] = np.nan
            continue
        if name == 'imputed_station_fraction':
            values = records.opts.str.contains('IDW|M=', regex=True).to_numpy(dtype=float)[safe_indices]
        else:
            status = records.calcstatus.to_numpy()[safe_indices]
            values = np.where(np.isfinite(status), status != 0, np.nan)
        valid = selected & np.isfinite(values)
        denominator = valid.sum(axis=1)
        result[f'cwfis_{name}'] = np.divide(np.where(valid, values, 0).sum(axis=1), denominator,
                                          out=np.full(n, np.nan), where=denominator > 0)
    coverage = {str(radius): int((distance[:, 0] <= radius).sum()) for radius in (100, 200, 300)}
    return result, coverage


def prior_week_rain(window, issue_date: date):
    expected = [issue_date - timedelta(days=lag) for lag in range(7, 0, -1)]
    if [observed for observed, _ in window] != expected:
        raise ValueError('Rainfall window must contain exactly seven consecutive prior days')
    rain = np.stack([values for _, values in window])
    valid = np.isfinite(rain) & (rain >= 0)
    coverage = valid.sum(axis=0).astype('int8')
    total = np.where(coverage == 7, np.where(valid, rain, 0).sum(axis=0), np.nan)
    return total, coverage


def load_observations(source: Path, dates: set[str], grid: pd.DataFrame):
    columns = ['rep_date', 'aes', 'wmo', 'lon', 'lat', 'opts', 'calcstatus', *FIELDS]
    chunks, raw_rows, selected_rows, invalid_coordinates = [], 0, 0, 0
    bounds = (grid.centroid_longitude.min() - 5, grid.centroid_longitude.max() + 5,
              grid.centroid_latitude.min() - 5, grid.centroid_latitude.max() + 5)
    for frame in pd.read_csv(source, compression='bz2', usecols=columns, dtype=str, keep_default_na=False, chunksize=200000):
        raw_rows += len(frame)
        frame['observation_date'] = frame.rep_date.str[:10]
        frame = frame.loc[frame.observation_date.isin(dates)].copy()
        for field in ['lon', 'lat', 'calcstatus', *FIELDS]:
            frame[field] = pd.to_numeric(frame[field], errors='coerce')
        valid_xy = np.isfinite(frame[['lon', 'lat']]).all(axis=1)
        invalid_coordinates += int((~valid_xy).sum())
        frame = frame.loc[valid_xy & frame.lon.between(bounds[0], bounds[1]) & frame.lat.between(bounds[2], bounds[3])].copy()
        selected_rows += len(frame)
        if frame.empty:
            continue
        frame['station_key'] = frame.aes.str.strip() + '|' + frame.wmo.str.strip() + '|' + frame.lon.map(lambda x: f'{x:.5f}') + '|' + frame.lat.map(lambda x: f'{x:.5f}')
        frame['valid_fwi'] = valid_measurements('fwi', frame.fwi.to_numpy())
        chunks.append(frame)
    if not chunks:
        raise ValueError('No station observations for requested dates and bounds')
    all_rows = pd.concat(chunks, ignore_index=True)
    keys = ['observation_date', 'station_key']
    duplicate_rows = int(all_rows.duplicated(keys).sum())
    all_rows = all_rows.sort_values('valid_fwi', ascending=False, kind='stable').drop_duplicates(keys, keep='first')
    all_rows = all_rows.sort_values(keys).reset_index(drop=True)
    invalid_values = {field: int((~valid_measurements(field, all_rows[field].to_numpy())).sum()) for field in FIELDS}
    return all_rows, {'raw_archive_rows': raw_rows, 'selected_rows_before_dedup': selected_rows,
                      'duplicate_date_station_rows': duplicate_rows, 'date_station_rows': len(all_rows),
                      'invalid_coordinate_rows_in_requested_dates': invalid_coordinates, 'invalid_measurements_after_dedup': invalid_values}


def boundary_sensitivity(grid: pd.DataFrame, output: Path) -> dict:
    source = ROOT / 'data/raw/week_2_completion/ontario_fire_region/current_non_ofr_boundary.geojson'
    boundary = gpd.read_file(source)
    if boundary.crs is None or boundary.RESPONSE_SECTOR.eq('OFR').any():
        raise ValueError('Boundary lacks CRS or includes outside-region sectors')
    bad = int((~boundary.geometry.is_valid).sum())
    geometries = boundary.to_crs(3978).geometry
    area = shapely.union_all(shapely.make_valid(geometries.to_numpy()))
    shapely.prepare(area)
    x0, y0, x1, y1 = area.bounds
    xs, ys = np.meshgrid(np.arange(np.floor(x0 / 10000) * 10000, x1 + 10000, 10000),
                         np.arange(np.floor(y0 / 10000) * 10000, y1 + 10000, 10000))
    origins = np.column_stack([xs.ravel(), ys.ravel()])
    inside = shapely.covers(area, shapely.points(origins[:, 0] + 5000, origins[:, 1] + 5000))
    origins = origins[inside].astype(int)
    candidate = pd.DataFrame(origins, columns=['grid_x_m', 'grid_y_m'])
    candidate['grid_id'] = [f'ofr10km_{x}_{y}' for x, y in origins]
    lon, lat = Transformer.from_crs(3978, 4326, always_xy=True).transform(origins[:, 0] + 5000, origins[:, 1] + 5000)
    candidate['centroid_longitude'], candidate['centroid_latitude'] = lon, lat
    candidate = candidate[grid.columns].sort_values('grid_id').reset_index(drop=True)
    candidate.to_csv(output / 'current_boundary_centroid_grid.csv', index=False)
    original_ids, candidate_ids = set(grid.grid_id), set(candidate.grid_id)
    comparison = grid.copy()
    comparison['centroid_in_current_boundary'] = comparison.grid_id.isin(candidate_ids)
    comparison.to_csv(output / 'v1_grid_boundary_sensitivity.csv', index=False)
    return {'boundary_path': str(source), 'boundary_sha256': digest(source), 'input_invalid_geometries': bad,
            'geometry_policy': 'Project to EPSG:3978; make_valid on derived geometry; raw input unchanged',
            'v1_grid_cells': len(grid), 'boundary_only_grid_cells': len(candidate),
            'v1_cells_excluded': sorted(original_ids - candidate_ids), 'boundary_only_new_cells': sorted(candidate_ids - original_ids),
            'role': 'Current-boundary sensitivity only; original pinned boundary absent. Not a historically available replacement.',
            'construction_uses_fire_records': False}


def run(output: Path = OUTPUT, report: Path = REPORT) -> dict:
    if output.exists():
        raise FileExistsError('Use a new output version; this build does not overwrite data')
    output.mkdir(parents=True)
    report.mkdir(parents=True, exist_ok=True)
    source = REPO / 'data/raw/cwfis/cwfis_fwi2010sv3.0_ll.csv.bz2'
    manifest = json.loads((source.parent / 'manifest.json').read_text())
    if digest(source) != manifest['expected_sha256']:
        raise ValueError('Pinned CWFIS source hash mismatch')
    grid_path = REPO / 'data/interim/ontario_fire_region_10km_grid.csv'
    grid = pd.read_csv(grid_path).sort_values('grid_id').reset_index(drop=True)
    grid_ids = set(grid.grid_id)
    if len(grid_ids) != len(grid) or len(grid) != 9673:
        raise ValueError('Unexpected original grid')
    dates = [d for year in range(2010, 2018) for d in pd.date_range(f'{year}-05-01', f'{year}-10-31')]
    required = {(d - pd.Timedelta(days=lag)).date().isoformat() for d in dates for lag in range(1, 8)}
    config = {'feature_version': 'historical-weather-development-v2', 'issue_years': [2010, 2017], 'station_count': 4,
              'max_station_distance_km': 200, 'distance_sensitivity_km': [100, 200, 300],
              'mode': 'retrospective_hindcast_not_operational_forecast', 'code_sha256': digest(Path(__file__)),
              'source_sha256': digest(source), 'grid_sha256': digest(grid_path), 'reserved_evaluation_partitions_opened': False,
              'selection': 'Nearest four daily finite nonnegative-FWI reporting stations within 200 km; no label-based tuning',
              'deduplication': 'First valid FWI record in physical source order per station/date; otherwise first record',
              'precipitation': 'Sum only seven consecutive available prior-day source rain values', 'label_or_model_promotion': False}
    save(output / 'config.json', config)
    started = time.perf_counter()
    observations, source_profile = load_observations(source, required, grid)
    observations.to_parquet(output / 'deduplicated_station_observations.parquet', index=False)
    groups = {key: value for key, value in observations.groupby('observation_date', sort=False)}
    empty = observations.iloc[:0]
    sensitivity, rows, missing, previous = {100: 0, 200: 0, 300: 0}, 0, 0, None
    window = deque(maxlen=7)
    writers = {}
    year_stats = {}
    try:
        for issue in dates:
            first = issue.date() - timedelta(days=7)
            end = issue.date() - timedelta(days=1)
            if previous is None or first > previous + timedelta(days=1):
                window.clear(); previous = first - timedelta(days=1)
            while previous < end:
                previous += timedelta(days=1)
                frame, support = daily_features(grid, groups.get(previous.isoformat(), empty))
                window.append((previous, frame.cwfis_precip_mm.to_numpy()))
                if previous == end:
                    for radius in sensitivity:
                        sensitivity[radius] += support[str(radius)]
            total_rain, available = prior_week_rain(window, issue.date())
            frame['cwfis_precip_7d_mm'] = total_rain
            frame['cwfis_precip_7d_coverage_days'] = available
            frame['ignition_date'] = issue.date().isoformat()
            frame['cwfis_observation_date'] = end.isoformat()
            frame['weather_feature_version'] = config['feature_version']
            frame['cwfis_source_id'] = 'cwfis_fwi_2010s_v3_ll'
            frame['cwfis_maximum_station_distance_km'] = 200.
            if not (frame.cwfis_observation_date < frame.ignition_date).all():
                raise AssertionError('Weather cutoff violation')
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if issue.year not in writers:
                writers[issue.year] = pq.ParquetWriter(output / f'weather_{issue.year}.parquet', table.schema)
            writers[issue.year].write_table(table)
            nmissing = int(frame.cwfis_missing.sum())
            stats = year_stats.setdefault(str(issue.year), {'rows': 0, 'missing': 0})
            stats['rows'] += len(frame); stats['missing'] += nmissing
            rows += len(frame); missing += nmissing
            if issue.day == 31 and issue.month == 10:
                print(issue.year, 'rows', rows, 'missing_fraction', round(missing / rows, 6), flush=True)
    finally:
        for writer in writers.values():
            writer.close()
    expected = len(dates) * len(grid)
    if rows != expected:
        raise AssertionError('Weather row count differs from original development universe')
    mask = boundary_sensitivity(grid, report)
    summary = {'config': config, 'source_profile': source_profile, 'rows': rows, 'expected_rows': expected,
               'missing_rows': missing, 'missing_fraction': missing / rows, 'year_stats': year_stats,
               'nearest_daily_station_coverage': {str(k): v / rows for k, v in sensitivity.items()},
               'boundary_sensitivity': mask, 'time_cutoff_violations': 0,
               'elapsed_seconds': time.perf_counter() - started, 'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
               'outputs': [{'path': str(f), 'bytes': f.stat().st_size, 'sha256': digest(f)} for f in sorted(output.glob('*.parquet'))]}
    save(output / 'manifest.json', summary)
    save(report / 'historical_weather_v2_audit.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    parser.add_argument('--report-dir', type=Path, default=REPORT)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir, args.report_dir), indent=2))
