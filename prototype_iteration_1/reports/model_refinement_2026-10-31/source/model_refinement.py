"""Versioned ignition development experiments; never score the old final tests."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

from scripts.ignition_comparison import (
    candidates, corrected_weights, daily_budget, digest, inner_spatial_roles,
    metrics, predict_bundle, save_json, validate_years,
)
from scripts.week5_ignition import apply_calibration, fit_calibration

SEED = 385
FOLDS = (2014, 2015)
PROTOCOLS = ('temporal', 'inner_spatial')


def candidate_specs():
    return [
        {'name': 'historical_rate', 'family': 'historical_rate', 'negative_percent': 1},
        {'name': 'logistic', 'family': 'logistic', 'negative_percent': 1},
        {'name': 'histogram_reference', 'family': 'histogram_boosting', 'negative_percent': 1},
        {'name': 'lightgbm_reference', 'family': 'lightgbm', 'negative_percent': 1},
        {'name': 'lightgbm_dense', 'family': 'lightgbm', 'negative_percent': 5},
        {'name': 'lightgbm_regularized', 'family': 'lightgbm', 'negative_percent': 5,
         'params': {'n_estimators': 250, 'learning_rate': .03, 'num_leaves': 7,
                    'max_depth': 3, 'min_child_samples': 300, 'min_child_weight': 5.,
                    'reg_lambda': 20., 'reg_alpha': .1}},
        {'name': 'lightgbm_nohistory', 'family': 'lightgbm', 'negative_percent': 5,
         'no_history': True},
    ]


def validate_development(frame, role):
    validate_years(frame.ignition_date, role)
    if not frame.ignition.isin([0, 1]).all():
        raise ValueError('Nonbinary target')


def sampling_mask(frame, percent):
    if percent not in (1, 5):
        raise ValueError('Only preregistered negative sampling rates are allowed')
    return frame.ignition.eq(1).to_numpy() | (frame._bucket.to_numpy() < percent)


def fold_masks(frame, year, protocol):
    if year not in FOLDS or protocol not in PROTOCOLS:
        raise ValueError('Only preregistered development folds are allowed')
    years = frame.ignition_date.str[:4].astype(int)
    train, val = years.lt(year), years.eq(year)
    if protocol == 'inner_spatial':
        train &= frame.inner_role.eq('inner_training')
        val &= frame.inner_role.eq('inner_validation')
    return train.to_numpy(), val.to_numpy()


def validate_predictors(features, contract, protocol):
    key = 'temporal_candidate_predictors' if protocol == 'temporal' else 'spatial_candidate_predictors'
    if (len(set(features)) != len(features) or not set(features).issubset(contract[key])
            or set(features) & set(contract['never_predictors'])):
        raise ValueError('Predictors violate the existing feature contract')


def choose_candidate(records):
    frame = pd.DataFrame(records)
    expected = set(FOLDS)
    if set(frame.year) != expected or frame.duplicated(['candidate', 'year']).any():
        raise ValueError('Selection accepts complete unique rolling folds only')
    if any(set(g.year) != expected for _, g in frame.groupby('candidate')):
        raise ValueError('Incomplete candidate comparison')
    reference = frame[frame.candidate.eq('lightgbm_reference')].set_index('year')
    if len(reference) != 2:
        raise ValueError('Missing reference')
    eligible = ['lightgbm_reference']
    for name, rows in frame.groupby('candidate'):
        rows = rows.set_index('year').sort_index()
        if (rows.average_precision.mean() > reference.average_precision.mean()
                and rows.daily_budget_recall.mean() >= reference.daily_budget_recall.mean()
                and (rows.average_precision / reference.average_precision >= .9).all()):
            eligible.append(name)
    means = frame.groupby('candidate').average_precision.mean()
    return sorted(set(eligible), key=lambda name: (-means[name], name))[0]


def paired_recall_interval(reference, candidate, repetitions=1000):
    keys = ['date', 'rows', 'positives', 'alerts']
    if not reference[keys].reset_index(drop=True).equals(candidate[keys].reset_index(drop=True)):
        raise ValueError('Paired uncertainty requires matching dates and populations')
    merged = reference[keys + ['hits']].copy()
    merged['delta_hits'] = candidate.hits.to_numpy() - reference.hits.to_numpy()
    week = (pd.to_datetime(merged.date) - pd.Timestamp(merged.date.min())).dt.days // 7
    blocks = merged.groupby(week)[['positives', 'delta_hits']].sum()
    if blocks.positives.sum() <= 0:
        raise ValueError('Recall needs positive support')
    indices = np.random.default_rng(SEED).integers(0, len(blocks), (repetitions, len(blocks)))
    denominator = blocks.positives.to_numpy()[indices].sum(axis=1)
    numerator = blocks.delta_hits.to_numpy()[indices].sum(axis=1)
    valid = denominator > 0
    return {'observed_delta': float(merged.delta_hits.sum() / merged.positives.sum()),
            'ci95': np.quantile(numerator[valid] / denominator[valid], [.025, .975]).tolist(),
            'week_blocks': len(blocks), 'undefined_replicates': int((~valid).sum()),
            'method': 'paired seven-day block bootstrap; conditional development uncertainty'}


def checked_sources(data_dir):
    manifest = json.loads((data_dir / 'manifest.json').read_text())
    contract_path = data_dir / 'predictor_contract.json'
    if digest(contract_path) != manifest['predictor_contract_sha256']:
        raise ValueError('Predictor contract changed')
    for role in ('training', 'validation'):
        record = manifest['files'][role]
        path = data_dir / f'{role}.parquet'
        if path.resolve() != Path(record['path']).resolve() or digest(path) != record['sha256']:
            raise ValueError('Development input hash or path changed')
    return manifest, json.loads(contract_path.read_text())


def attach_roles(frame, mapping, role):
    validate_development(frame, role)
    if frame.duplicated(['grid_id', 'ignition_date']).any():
        raise ValueError('Duplicate development key')
    frame['inner_role'] = pd.Categorical(frame.grid_id.map(mapping))
    if frame.inner_role.isna().any():
        raise ValueError('Unassigned geography')
    return frame


def load_training(data_dir, features, mapping, expected_rows):
    parts, summaries = [], []
    columns = ['grid_id', 'ignition_date', 'ignition'] + features
    for batch in pq.ParquetFile(data_dir / 'training.parquet').iter_batches(batch_size=200000, columns=columns):
        frame = attach_roles(batch.to_pandas(), mapping, 'training')
        frame['_year'] = frame.ignition_date.str[:4].astype(int)
        summaries.append(frame.groupby(['_year', 'inner_role'], observed=True).ignition.agg(['size', 'sum']))
        frame['_bucket'] = pd.util.hash_pandas_object(frame[['grid_id', 'ignition_date']], index=False).to_numpy() % 100
        parts.append(frame.loc[sampling_mask(frame, 5)])
    population = pd.concat(summaries).groupby(level=[0, 1]).sum().reset_index()
    if int(population['size'].sum()) != expected_rows:
        raise ValueError('Incomplete development input')
    sampled = pd.concat(parts, ignore_index=True)
    if sampled.duplicated(['grid_id', 'ignition_date']).any():
        raise ValueError('Duplicate fitting key across batches')
    return sampled, population


def read_year(data_dir, year, features, mapping):
    role = 'training' if year <= 2015 else 'validation'
    if year not in (2014, 2015, 2016, 2017):
        raise ValueError('Reserved evaluation data is not accessible')
    columns = ['grid_id', 'ignition_date', 'ignition'] + features
    frame = pd.read_parquet(data_dir / f'{role}.parquet', columns=columns,
                            filters=[('ignition_date', '>=', f'{year}-01-01'),
                                     ('ignition_date', '<=', f'{year}-12-31')])
    return attach_roles(frame, mapping, role)


def fitting_data(sampled, population, before_year, protocol, spec):
    train = sampled.loc[sampled._year.lt(before_year)]
    pop = population.loc[population._year.lt(before_year)]
    if protocol == 'inner_spatial':
        train = train.loc[train.inner_role.eq('inner_training')]
        pop = pop.loc[pop.inner_role.eq('inner_training')]
    train = train.loc[sampling_mask(train, spec['negative_percent'])]
    weights = corrected_weights(train.ignition.to_numpy(), int(pop['size'].sum()), int(pop['sum'].sum()))
    return train, weights


def fit_candidate(sampled, population, year, protocol, spec, contract):
    train, weights = fitting_data(sampled, population, year, protocol, spec)
    key = 'temporal_candidate_predictors' if protocol == 'temporal' else 'spatial_candidate_predictors'
    features = [f for f in contract[key] if not (spec.get('no_history') and f.startswith('fire_history_'))]
    validate_predictors(features, contract, protocol)
    model = candidates()[spec['family']]
    if spec.get('params'):
        model.set_params(**spec['params'])
    start = time.perf_counter()
    x, y = train[features].astype('float32'), train.ignition.to_numpy()
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite predictor')
    if spec['family'] == 'logistic':
        model.fit(x, y, scaler__sample_weight=weights, classifier__sample_weight=weights)
    else:
        model.fit(x, y, sample_weight=weights)
    return {'model': model, 'features': features, 'protocol': protocol,
            'candidate': spec['name'], 'mode': 'development_only_not_a_new_final_test',
            'fitted_rows': len(train), 'fitted_positives': int(y.sum()),
            'fit_seconds': time.perf_counter() - start,
            'training_prior': float(np.average(y, weights=weights))}


def evaluate(bundle, frame):
    raw = predict_bundle(bundle, frame[bundle['features']].astype('float32'))
    probability = apply_calibration(bundle['calibrator'], raw) if bundle.get('calibrator') else raw
    result = metrics(frame.ignition.to_numpy(), probability)
    budget = daily_budget(frame, probability)
    result.update(daily_budget_recall=float(budget.hits.sum() / budget.positives.sum()),
                  daily_budget_precision=float(budget.hits.sum() / budget.alerts.sum()),
                  hits=int(budget.hits.sum()), alerts=int(budget.alerts.sum()))
    return result, budget, probability


def rolling_comparison(sampled, population, data_dir, mapping, contract, output):
    records = []
    for year in FOLDS:
        validation = read_year(data_dir, year, contract['temporal_candidate_predictors'], mapping)
        for protocol in PROTOCOLS:
            val = validation if protocol == 'temporal' else validation.loc[validation.inner_role.eq('inner_validation')]
            for spec in candidate_specs():
                if protocol == 'inner_spatial' and spec.get('no_history'):
                    continue
                bundle = fit_candidate(sampled, population, year, protocol, spec, contract)
                result, _, _ = evaluate(bundle, val)
                result.update(candidate=spec['name'], year=year, protocol=protocol,
                              fit_seconds=bundle['fit_seconds'], fitted_rows=bundle['fitted_rows'])
                records.append(result)
                save_json(output / 'rolling_results.json', records)
                print(f"{protocol} {year} {spec['name']}: AP={result['average_precision']:.6f} recall={result['daily_budget_recall']:.4f}", flush=True)
    return records


def confirm(sampled, population, data_dir, mapping, contract, selected, output, model_dir):
    calibration = read_year(data_dir, 2016, contract['temporal_candidate_predictors'], mapping)
    confirmation = read_year(data_dir, 2017, contract['temporal_candidate_predictors'], mapping)
    rows, paired = [], {}
    for protocol in PROTOCOLS:
        cal = calibration if protocol == 'temporal' else calibration.loc[calibration.inner_role.eq('inner_training')]
        val = confirmation if protocol == 'temporal' else confirmation.loc[confirmation.inner_role.eq('inner_validation')]
        budgets = {}
        for name in dict.fromkeys(['lightgbm_reference', selected[protocol]]):
            spec = next(s for s in candidate_specs() if s['name'] == name)
            bundle = fit_candidate(sampled, population, 2016, protocol, spec, contract)
            raw = predict_bundle(bundle, cal[bundle['features']].astype('float32'))
            bundle['calibrator'] = fit_calibration(cal.ignition.to_numpy(), raw)
            bundle['calibration'] = {'year': 2016, 'geography': 'all' if protocol == 'temporal' else 'inner_training'}
            result, budget, probability = evaluate(bundle, val)
            path = model_dir / f'{protocol}_{name}.joblib'
            joblib.dump(bundle, path, compress=3)
            loaded = joblib.load(path)
            check = apply_calibration(loaded['calibrator'], predict_bundle(
                loaded, val.iloc[:1000][loaded['features']].astype('float32')))
            np.testing.assert_allclose(check, probability[:1000], rtol=1e-12, atol=1e-12)
            result.update(protocol=protocol, candidate=name, model_sha256=digest(path),
                          calibration=bundle['calibrator'], save_load_parity=True)
            rows.append(result); budgets[name] = budget
            budget.to_csv(output / f'{protocol}_{name}_2017_daily.csv', index=False)
            print(f"confirmation {protocol} {name}: AP={result['average_precision']:.6f} recall={result['daily_budget_recall']:.4f}", flush=True)
        paired[protocol] = paired_recall_interval(budgets['lightgbm_reference'], budgets[selected[protocol]])
    return {'results': rows, 'paired_budget_recall': paired,
            'scope': '2017 development confirmation, previously exposed in earlier experiments; not a pristine final test'}


def frozen_artifacts(workspace):
    paths = []
    for directory in ('ignition_models_week5_v1', 'selected_2025_models_v1', 'spread_replay_corrected_v2'):
        paths.extend(p for p in (workspace / 'data/processed' / directory).glob('*') if p.is_file())
    for pattern in ('week_5_prototype_2026-10-16/*.json', 'week_5_completion_2026-10-16/*results.json'):
        paths.extend((workspace / 'reports').glob(pattern))
    return {str(p): digest(p) for p in sorted(paths)}


def run(workspace, output, model_dir):
    if output.exists() or model_dir.exists():
        raise FileExistsError('Use new experiment and model output directories')
    data_dir = workspace / 'data/processed/ignition_weather_v2_development'
    manifest, contract = checked_sources(data_dir)
    selector = workspace / 'reports/week_2_development_2026-10-15/ignition_spatial_partition_v1.csv'
    inner = inner_spatial_roles(pd.read_csv(selector))
    mapping = inner.set_index('grid_id').inner_role
    protected = frozen_artifacts(workspace)
    output.mkdir(parents=True); model_dir.mkdir(parents=True)
    protocol = {'selection_folds': [2014, 2015], 'training': '2010 through year before each fold',
                'selection_rule': 'Largest mean AP, mean budget recall not lower than reference, no fold AP below 90% of reference; otherwise retain reference',
                'negative_sampling': 'all positives plus nested key-hash 1% or 5% negatives, inverse sampling weights',
                'calibration': '2016, natural prevalence; spatial calibration uses inner-training geography only',
                'confirmation': '2017; historically exposed development data, not an independent final test',
                'spatial': 'existing deterministic 100 km blocks and 20 km centre buffer; no history features',
                'old_final_observations_used': False, 'new_data_sources_or_vintages': False,
                'daily_budget': 'existing ceil(1% of eligible cells), deterministic hash ties',
                'candidates': candidate_specs(), 'selector_sha256': digest(selector),
                'manifest_sha256': digest(data_dir / 'manifest.json'),
                'predictor_contract_sha256': digest(data_dir / 'predictor_contract.json'),
                'code_sha256': digest(Path(__file__)), 'protected_files_before': protected,
                'versions': {p: importlib.metadata.version(p) for p in ('numpy', 'pandas', 'scikit-learn', 'lightgbm', 'pyarrow')},
                'references': ['https://lightgbm.readthedocs.io/en/latest/Parameters.html',
                               'https://scikit-learn.org/stable/modules/cross_validation.html']}
    save_json(output / 'protocol.json', protocol)
    start = time.perf_counter()
    sampled, population = load_training(data_dir, contract['temporal_candidate_predictors'], mapping,
                                         manifest['files']['training']['rows'])
    population.to_csv(output / 'training_population_by_year_and_role.csv', index=False)
    print(f'Loaded {len(sampled):,} fitting rows at maximum 5% negative sampling', flush=True)
    with threadpool_limits(limits=4):
        records = rolling_comparison(sampled, population, data_dir, mapping, contract, output)
        selected = {p: choose_candidate([r for r in records if r['protocol'] == p]) for p in PROTOCOLS}
        save_json(output / 'selection_freeze.json', {'selected': selected, 'rolling_results_sha256': digest(output / 'rolling_results.json'),
                                                   'confirmation_not_read_before_selection': True})
        result = confirm(sampled, population, data_dir, mapping, contract, selected, output, model_dir)
    if frozen_artifacts(workspace) != protected:
        raise RuntimeError('An earlier scientific artifact changed')
    result.update(selected=selected, elapsed_seconds=time.perf_counter() - start,
                  frozen_artifacts_unchanged=True, reserved_observations_used=False,
                  model_directory=str(model_dir))
    save_json(output / 'results.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.workspace.resolve(), args.output_dir.resolve(), args.model_dir.resolve())
