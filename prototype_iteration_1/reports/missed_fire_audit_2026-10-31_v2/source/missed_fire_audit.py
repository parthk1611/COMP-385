"""Audit the exposed 2017 development miss cases without changing a fitted model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.stats import hypergeom
from threadpoolctl import threadpool_limits

from scripts.ignition_comparison import digest, inner_spatial_roles, predict_bundle, save_json
from scripts.model_refinement import (
    checked_sources, fitting_data, frozen_artifacts, load_training, read_year,
)
from scripts.week5_ignition import apply_calibration

KEYS = ['grid_id', 'ignition_date']
QUALITY = ['cwfis_missing', 'cwfis_nearest_station_km', 'cwfis_station_count',
           'cwfis_fwi', 'cwfis_dmc', 'cwfis_rh_pct', 'terrain_elevation_mean_m',
           'terrain_ruggedness_m']


def validate_grid(grid):
    origins = grid.grid_id.str.extract(r'^ofr10km_(-?\d+)_(-?\d+)$').astype(float)
    mismatch = (origins[0].to_numpy() != grid.grid_x_m) | (origins[1].to_numpy() != grid.grid_y_m)
    lon, lat = Transformer.from_crs(3978, 4326, always_xy=True).transform(
        grid.grid_x_m.to_numpy()+5000, grid.grid_y_m.to_numpy()+5000)
    error = np.hypot(lon-grid.centroid_longitude, lat-grid.centroid_latitude)
    return {'cells': len(grid), 'duplicate_grid_ids': int(grid.grid_id.duplicated().sum()),
            'key_origin_mismatches': int(mismatch.sum()),
            'off_lattice_origins': int(((grid.grid_x_m % 10000 != 0) | (grid.grid_y_m % 10000 != 0)).sum()),
            'max_centroid_coordinate_error_degrees': float(error.max()),
            'origin_semantics': 'EPSG:3978 lower-left origin; centroid adds 5000 m to each coordinate'}


def audit_labels(panel, events):
    expected = events.groupby(KEYS).size().rename('expected_count').reset_index()
    merged = panel[KEYS+['ignition', 'ignition_count']].merge(expected, on=KEYS, how='left', validate='one_to_one')
    merged['expected_count'] = merged.expected_count.fillna(0).astype(int)
    keys = pd.MultiIndex.from_frame(panel[KEYS])
    source_keys = pd.MultiIndex.from_frame(expected[KEYS])
    return {'source_events': len(events), 'source_positive_cell_days': len(expected),
            'source_keys_missing_from_panel': int((~source_keys.isin(keys)).sum()),
            'label_mismatches': int(merged.ignition.ne(merged.expected_count.gt(0)).sum()),
            'event_count_mismatches': int(merged.ignition_count.ne(merged.expected_count).sum())}


def rank_daily(frame):
    if (frame.duplicated(KEYS).any() or not np.isfinite(frame.probability).all()
            or not frame.probability.between(0, 1).all()):
        raise ValueError('Invalid keyed probability table')
    result = frame.copy()
    result['_tie'] = pd.util.hash_pandas_object(result[KEYS], index=False).to_numpy()
    result = result.sort_values(['ignition_date', 'probability', '_tie'], ascending=[True, False, True])
    result['daily_rank'] = result.groupby('ignition_date').cumcount()+1
    result['daily_rows'] = result.groupby('ignition_date').grid_id.transform('size')
    result['daily_budget'] = np.maximum(1, np.ceil(result.daily_rows*.01).astype(int))
    result['rank_fraction'] = result.daily_rank/result.daily_rows
    result['selected'] = result.daily_rank.le(result.daily_budget)
    return result.drop(columns='_tie')


def cohort_summary(frame):
    positives = frame.ignition.eq(1)
    hits = int((positives & frame.selected).sum())
    supported = frame.cwfis_missing.eq(0)
    return {'rows': len(frame), 'positive_cell_days': int(positives.sum()),
            'selected_cell_days': int(frame.selected.sum()), 'hits': hits,
            'recall': hits/int(positives.sum()) if positives.any() else None,
            'false_alerts': int((frame.selected & ~positives).sum()),
            'positive_weather_supported': int((positives & supported).sum()),
            'positive_weather_missing': int((positives & ~supported).sum()),
            'positive_rank_fraction_min': float(frame.loc[positives, 'rank_fraction'].min()) if positives.any() else None,
            'positive_rank_fraction_median': float(frame.loc[positives, 'rank_fraction'].median()) if positives.any() else None}


def capacity_diagnostic(frame):
    records = []
    for fraction in [.01, .02, .05, .1, .2]:
        selected = frame.daily_rank.le(np.ceil(frame.daily_rows*fraction).astype(int).clip(lower=1))
        hits = int((selected & frame.ignition.eq(1)).sum())
        records.append({'capacity': fraction, 'selected_cell_days': int(selected.sum()),
                        'hits': hits, 'recall': hits/int(frame.ignition.sum()),
                        'purpose': 'diagnostic only; original primary capacity stays at 1%'})
    return records


def random_capacity_reference(frame):
    daily = frame.groupby('ignition_date').agg(rows=('grid_id','size'),
        positives=('ignition','sum'), budget=('daily_budget','first'))
    expected = (daily.budget*daily.positives/daily.rows).sum()
    log_zero = hypergeom.logpmf(0, daily.rows.to_numpy(), daily.positives.to_numpy(), daily.budget.to_numpy())
    return {'expected_hits': float(expected), 'probability_of_zero_hits':float(np.exp(log_zero.sum())),
            'assumption':'Independent uniform random sampling without replacement within each day at the same capacity',
            'interpretation':'Reference calculation, not a model significance test or a new decision threshold'}


def weighted_median(values, weights):
    valid = values.notna().to_numpy()
    if not valid.any():
        return None
    values, weights = values.to_numpy()[valid], weights[valid]
    order = np.argsort(values)
    return float(values[order][np.searchsorted(np.cumsum(weights[order]), weights.sum()/2)])


def distribution_comparison(training, weights, validation):
    records = []
    for feature in QUALITY:
        tr, va = training[feature], validation[feature]
        finite = tr.dropna()
        outside = va.notna() & (va.lt(finite.min()) | va.gt(finite.max()))
        records.append({'feature': feature, 'weighted_training_median': weighted_median(tr, weights),
                        'validation_median': float(va.median()) if va.notna().any() else None,
                        'weighted_training_missing_fraction': float(np.average(tr.isna(), weights=weights)),
                        'validation_missing_fraction': float(va.isna().mean()),
                        'validation_outside_sampled_training_range_fraction': float(outside.mean()),
                        'missed_positive_median': (lambda x: None if pd.isna(x) else float(x))(
                            validation.loc[validation.ignition.eq(1), feature].median())})
    return records


def event_alignment(events):
    x, y = Transformer.from_crs(4326, 3978, always_xy=True).transform(
        events.longitude.to_numpy(), events.latitude.to_numpy())
    identifiers = [f'ofr10km_{int(a)}_{int(b)}' for a, b in zip(np.floor(x/10000)*10000, np.floor(y/10000)*10000)]
    return {'checked_event_records': len(events),
            'independent_projected_cell_mismatches': int(np.count_nonzero(events.grid_id.to_numpy()!=identifiers)),
            'method': 'Independent pyproj WGS84 to EPSG:3978 transform and 10000 m floor indexing'}


def run(workspace, output):
    if output.exists():
        raise FileExistsError('Use a new audit version')
    data = workspace/'data/processed/ignition_weather_v2_development'
    manifest, contract = checked_sources(data)
    selector = workspace/'reports/week_2_development_2026-10-15/ignition_spatial_partition_v1.csv'
    inner = inner_spatial_roles(pd.read_csv(selector));mapping = inner.set_index('grid_id').inner_role
    protected = frozen_artifacts(workspace)
    model_path = workspace/'data/processed/ignition_refinement_2026-10-31/inner_spatial_lightgbm_reference.joblib'
    prior = json.loads((workspace/'reports/model_refinement_2026-10-31/results.json').read_text())
    expected = next(r for r in prior['results'] if r['protocol']=='inner_spatial')['model_sha256']
    if digest(model_path)!=expected:
        raise ValueError('Development reference model changed')
    output.mkdir(parents=True)
    save_json(output/'protocol.json', {'mode': 'diagnostic audit of exposed 2017 development observations',
        'model_sha256': expected, 'source_manifest_sha256': digest(data/'manifest.json'),
        'selector_sha256': digest(selector), 'primary_capacity': .01,
        'no_refitting_or_default_changes': True, 'final_period_records_used': False,
        'capacity_sensitivity_is_not_a_new_alert_policy': True, 'code_sha256': digest(Path(__file__))})
    features = contract['temporal_candidate_predictors']
    extra = ['ignition_count', 'issue_time_utc', 'cwfis_observation_date']
    frame = read_year(data, 2017, features+extra, mapping)
    grid = pd.read_csv(workspace/'team_repository/data/interim/ontario_fire_region_10km_grid.csv')
    events_path = workspace/'team_repository/data/interim/ontario_fire_region_nfdb_ignitions_2010_2019.csv'
    chunks = [c.loc[c.ignition_date.str.startswith('2017')] for c in pd.read_csv(events_path, chunksize=2000)]
    events = pd.concat(chunks, ignore_index=True)
    prior_day = (pd.to_datetime(frame.ignition_date)-pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    expected_issue = pd.to_datetime(frame.ignition_date).dt.tz_localize('America/Toronto').dt.tz_convert('UTC')
    label = audit_labels(frame, events)
    consistency = {'grid': validate_grid(grid), 'event_cell_alignment': event_alignment(events),
                   'labels': label, 'duplicate_cell_days': int(frame.duplicated(KEYS).sum()),
                   'eligible_cells': frame.grid_id.nunique(), 'eligible_dates': frame.ignition_date.nunique(),
                   'rows_per_cell_min': int(frame.groupby('grid_id').size().min()),
                   'rows_per_cell_max': int(frame.groupby('grid_id').size().max()),
                   'weather_prior_day_mismatches': int(frame.cwfis_observation_date.ne(prior_day).sum()),
                   'issue_time_mismatches': int(pd.to_datetime(frame.issue_time_utc, utc=True).ne(expected_issue).sum())}
    save_json(output/'integrity.json', consistency)
    bundle = joblib.load(model_path)
    with threadpool_limits(limits=4):
        raw = predict_bundle(bundle, frame[bundle['features']].astype('float32'))
        frame['probability'] = apply_calibration(bundle['calibrator'], raw)
    cohorts = {}
    for role in ('inner_training', 'inner_validation'):
        ranked = rank_daily(frame.loc[frame.inner_role.eq(role)])
        cohorts[role] = cohort_summary(ranked)
        if role=='inner_validation':
            validation = ranked
    missed = validation.loc[validation.ignition.eq(1)].copy()
    event_details = events.groupby(KEYS).agg(event_records=('nfdb_fire_id','size'),
        causes=('cause', lambda s: '|'.join(sorted(set(s.dropna())))),
        fire_types=('fire_type', lambda s: '|'.join(sorted(set(s.dropna())))))
    missed = missed.merge(event_details.reset_index(), on=KEYS, validate='one_to_one')
    missed = missed.merge(grid, on='grid_id', validate='many_to_one')
    missed.sort_values(['rank_fraction','ignition_date','grid_id']).to_csv(output/'positive_case_audit.csv',index=False)
    validation.loc[validation.selected & validation.ignition.eq(0)].to_csv(output/'false_alerts.csv',index=False)
    monthly = validation.assign(month=validation.ignition_date.str[:7]).groupby('month').apply(
        lambda g: pd.Series(cohort_summary(g)), include_groups=False)
    monthly.to_csv(output/'monthly_diagnostics.csv')
    sampled, population = load_training(data, features, mapping, manifest['files']['training']['rows'])
    training, weights = fitting_data(sampled, population, 2016, 'inner_spatial', {'negative_percent':1})
    distributions = distribution_comparison(training, weights, validation)
    pd.DataFrame(distributions).to_csv(output/'feature_distribution_comparison.csv',index=False)
    positive_events = events.merge(inner[['grid_id','inner_role']], on='grid_id', validate='many_to_one')
    prescribed = events.fire_type.eq('PB') | events.is_prescribed.eq('PB') | events.cause.eq('H-PB')
    held_events = positive_events.loc[positive_events.inner_role.eq('inner_validation')]
    summary = {'integrity': consistency, 'cohorts': cohorts, 'capacity_diagnostic': capacity_diagnostic(validation),
        'random_capacity_reference':random_capacity_reference(validation),
        'held_geography_source_events': len(held_events), 'held_geography_cause_counts':held_events.cause.value_counts().to_dict(),
        'prescribed_source_records_all_2017':int(prescribed.sum()),
        'prescribed_source_records_held_geography':int((held_events.fire_type.eq('PB')|held_events.is_prescribed.eq('PB')|held_events.cause.eq('H-PB')).sum()),
        'best_positive_example':missed.sort_values('rank_fraction').iloc[0][KEYS+['daily_rank','daily_budget','rank_fraction','probability']].to_dict(),
        'same_model_training_geography_2017_is_not_in_sample_fit':True,
        'limitations':['Audit is confined to previously exposed 2017 development observations; not a new final evaluation.',
                       'Reported starts are archive labels; absence of a record is not verified absence of fire.',
                       'Weather-date checks do not establish historical archive publication availability.',
                       'Prescribed-burn flags need a versioned wildfire-only target policy; original labels are unchanged.',
                       'Distribution differences and missed-case descriptions do not establish causes.']}
    if frozen_artifacts(workspace)!=protected:
        raise RuntimeError('Earlier model or result artifact changed')
    summary['protected_artifacts_unchanged']=True
    save_json(output/'results.json', summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();run(a.workspace.resolve(),a.output_dir.resolve())
