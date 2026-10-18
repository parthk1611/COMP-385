"""Join the candidate weather layer to development features without changing v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.prepare_historical_weather_v2 import OUTPUT as WEATHER, REPORT, ROOT, digest, save

KEYS = ['grid_id', 'ignition_date']
LABELS = ['ignition', 'ignition_count', 'large_fire_200ha']
VERSION = 'ignition-feature-candidate-v2-daily-stations'
OUTPUT = ROOT / 'data/processed/ignition_weather_v2_development'


def join_frame(original: pd.DataFrame, weather: pd.DataFrame, eligible_cells: set[str]) -> pd.DataFrame:
    if original.duplicated(KEYS).any() or weather.duplicated(KEYS).any():
        raise ValueError('Duplicate cell/date key in a join input')
    if not pd.to_datetime(original.ignition_date).dt.year.between(2010, 2017).all():
        raise ValueError('Only 2010-2017 development rows may enter this join')
    expected = (pd.to_datetime(weather.ignition_date) - pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    if not weather.cwfis_observation_date.eq(expected).all():
        raise ValueError('Weather must come from the exact prior date')
    old_weather = [c for c in original if c.startswith('cwfis_')]
    if not set(old_weather).issubset(weather.columns):
        raise ValueError('Candidate weather does not supply the complete old weather interface')
    base = original.drop(columns=old_weather)
    result = base.merge(weather, on=KEYS, how='left', sort=False, validate='one_to_one', indicator=True)
    if len(result) != len(original) or not result['_merge'].eq('both').all():
        raise ValueError('Incomplete candidate weather join')
    result = result.drop(columns='_merge')
    if not result[KEYS + LABELS].equals(original[KEYS + LABELS].reset_index(drop=True)):
        raise ValueError('Join changed source key order or labels')
    result['feature_set_version'] = VERSION
    result['current_boundary_centroid_eligible'] = result.grid_id.isin(eligible_cells)
    return result


def run(output: Path = OUTPUT, weather_dir: Path = WEATHER, report: Path = REPORT) -> dict:
    if output.exists():
        raise FileExistsError('Candidate dataset exists; use a new output directory')
    weather_manifest = json.loads((weather_dir / 'manifest.json').read_text())
    for record in weather_manifest['outputs']:
        if digest(Path(record['path'])) != record['sha256']:
            raise ValueError('Completed weather artifact changed')
    original_dir = ROOT / 'data/processed/ignition_evaluation_v1'
    original_manifest = json.loads((original_dir / 'manifest.json').read_text())
    eligible = set(pd.read_csv(report / 'current_boundary_centroid_grid.csv').grid_id)
    output.mkdir(parents=True)
    predictor_path = ROOT / 'reports/week_2_development_2026-10-15/predictor_contract_v1.json'
    predictor = json.loads(predictor_path.read_text())
    predictor['candidate_feature_version'] = VERSION
    predictor['never_predictors'] += ['weather_feature_version', 'cwfis_maximum_station_distance_km', 'current_boundary_centroid_eligible']
    save(output / 'predictor_contract.json', predictor)
    records, stats = {}, []
    for role, years in [('training', range(2010, 2016)), ('validation', range(2016, 2018))]:
        source_record = original_manifest['files'][role]
        source = Path(source_record['path'])
        if digest(source) != source_record['sha256']:
            raise ValueError('Original development partition changed')
        destination = output / f'{role}.parquet'
        writer = None
        row_count = 0
        try:
            for year in years:
                original = pq.read_table(source, filters=[('ignition_date', '>=', f'{year}-01-01'), ('ignition_date', '<', f'{year+1}-01-01')]).to_pandas()
                weather = pd.read_parquet(weather_dir / f'weather_{year}.parquet')
                joined = join_frame(original, weather, eligible)
                old_missing = pd.to_numeric(original.cwfis_missing).eq(1).to_numpy()
                new_missing = joined.cwfis_missing.eq(1).to_numpy()
                both = ~old_missing & ~new_missing
                deltas = joined.cwfis_fwi.to_numpy()[both] - original.cwfis_fwi.to_numpy()[both]
                stats.append({'year': year, 'role': role, 'rows': len(joined),
                              'v1_weather_missing': int(old_missing.sum()), 'v2_weather_missing': int(new_missing.sum()),
                              'newly_available_rows': int((old_missing & ~new_missing).sum()),
                              'no_longer_available_rows': int((~old_missing & new_missing).sum()),
                              'fwi_mean_absolute_change_when_both_available': float(np.mean(np.abs(deltas))),
                              'v2_nearest_station_km_quantiles_50_95_100': joined.cwfis_nearest_station_km.quantile([.5, .95, 1.]).tolist(),
                              'v1_positive_cell_days': int(joined.ignition.sum()),
                              'current_boundary_excluded_cell_days': int((~joined.current_boundary_centroid_eligible).sum()),
                              'current_boundary_excluded_positive_cell_days': int(joined.loc[~joined.current_boundary_centroid_eligible, 'ignition'].sum())})
                table = pa.Table.from_pandas(joined, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(destination, table.schema)
                writer.write_table(table)
                row_count += len(joined)
                print(year, 'rows', len(joined), 'old_missing', int(old_missing.sum()), 'new_missing', int(new_missing.sum()), flush=True)
                del original, weather, joined, table
        finally:
            if writer is not None:
                writer.close()
        if row_count != source_record['rows']:
            raise ValueError('Candidate partition row count differs from original')
        records[role] = {'path': str(destination), 'rows': row_count, 'bytes': destination.stat().st_size, 'sha256': digest(destination)}
    summary = {'feature_version': VERSION, 'status': 'development_candidate_not_promoted',
               'files': records, 'year_comparison': stats, 'code_sha256': digest(Path(__file__)),
               'weather_manifest_sha256': digest(weather_dir / 'manifest.json'),
               'original_materialization_manifest_sha256': digest(original_dir / 'manifest.json'),
               'selector_manifest_sha256': original_manifest['selector_manifest_sha256'],
               'predictor_contract_sha256': digest(output / 'predictor_contract.json'),
               'calibration_and_final_test_opened': False, 'model_performance_compared': False,
               'target_keys_and_labels_unchanged': True,
               'mask_policy': 'Retain v1 rows; current-boundary sensitivity flag is metadata and forbidden predictor. No added fire-dependent grid cells or inferred labels.',
               'known_limits': ['Current-boundary scenario is not old-boundary recovery', 'Historical weather availability timestamps unknown',
                                'Daily station/radius/quality/dedup changes need model sensitivity before promotion',
                                'No selected modern-source backfill or live compatibility claim']}
    save(output / 'manifest.json', summary)
    save(report / 'weather_feature_join_audit.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    parser.add_argument('--weather-dir', type=Path, default=WEATHER)
    parser.add_argument('--report-dir', type=Path, default=REPORT)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir, args.weather_dir, args.report_dir), indent=2))
