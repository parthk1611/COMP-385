"""Selected-source monthly development study; August and final dates stay excluded."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.ignition_comparison import candidates, corrected_weights, digest, save_json
from scripts.model_refinement import candidate_specs, evaluate, frozen_artifacts, sampling_mask


def check_development_dates(frame):
    if not frame.ignition_date.between('2025-05-01', '2025-07-31').all():
        raise ValueError('Only May to July development data is allowed')
    if frame.duplicated(['grid_id', 'ignition_date']).any() or not frame.ignition.isin([0, 1]).all():
        raise ValueError('Invalid development keys or target')


def fit(frame, features, spec, contract_hash):
    check_development_dates(frame)
    sampled = frame.loc[sampling_mask(frame, spec['negative_percent'])]
    weights = corrected_weights(sampled.ignition.to_numpy(), len(frame), int(frame.ignition.sum()))
    model = candidates()[spec['family']]
    if spec.get('params'):
        model.set_params(**spec['params'])
    x = sampled[features].astype('float32')
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite predictor')
    if spec['family'] == 'logistic':
        model.fit(x, sampled.ignition.to_numpy(), scaler__sample_weight=weights, classifier__sample_weight=weights)
    else:
        model.fit(x, sampled.ignition.to_numpy(), sample_weight=weights)
    return {'model': model, 'features': features, 'candidate': spec['name'],
            'mode': 'selected_source_monthly_development_uncalibrated',
            'fitting_rows': len(sampled), 'training_rows': len(frame),
            'training_positives': int(frame.ignition.sum()),
            'predictor_contract_sha256': contract_hash, 'live_compatible': False}


def select(records):
    frame = pd.DataFrame(records)
    if (frame.duplicated(['candidate', 'month']).any()
            or any(set(g.month) != {'2025-06', '2025-07'} for _, g in frame.groupby('candidate'))):
        raise ValueError('Only complete June and July development comparisons are allowed')
    reference = frame.loc[frame.candidate.eq('lightgbm_reference')].set_index('month')
    eligible = ['lightgbm_reference']
    for name, group in frame.groupby('candidate'):
        group = group.set_index('month')
        if (group.average_precision.mean() > reference.average_precision.mean()
                and group.daily_budget_recall.mean() >= reference.daily_budget_recall.mean()
                and (group.average_precision / reference.average_precision >= .9).all()):
            eligible.append(name)
    means = frame.groupby('candidate').average_precision.mean()
    return sorted(set(eligible), key=lambda name: (-means[name], name))[0]


def run(workspace, output, model_dir):
    if output.exists() or model_dir.exists():
        raise FileExistsError('Use new output directories')
    source = workspace / 'data/processed/selected_2025_ignition_panel'
    manifest_path, contract_path = source / 'manifest.json', source / 'predictor_contract.json'
    manifest, contract = json.loads(manifest_path.read_text()), json.loads(contract_path.read_text())
    path = source / 'cell_days.parquet'
    record = next(r for r in manifest['outputs'] if r['path'].endswith('cell_days.parquet'))
    if path.resolve() != Path(record['path']).resolve() or digest(path) != record['sha256']:
        raise ValueError('Selected-source panel changed')
    features = contract['predictors']
    if len(set(features)) != len(features) or set(features) & set(contract['never_predictors']):
        raise ValueError('Forbidden predictor')
    output.mkdir(parents=True); model_dir.mkdir(parents=True)
    specs = [s for s in candidate_specs() if not s.get('no_history')]
    protected = frozen_artifacts(workspace)
    save_json(output / 'protocol.json', {
        'candidates': specs, 'predictor_contract_sha256': digest(contract_path),
        'source_manifest_sha256': digest(manifest_path), 'source_panel_sha256': record['sha256'],
        'folds': [{'fit': ['2025-05-01', '2025-05-31'], 'validate': '2025-06'},
                  {'fit': ['2025-05-01', '2025-06-30'], 'validate': '2025-07'}],
        'selection': 'Mean AP improvement, no mean 1% budget recall drop, no fold AP below 90% of reference',
        'scope': 'One-season, previously exposed development; no independent confirmation or calibrated probability claim',
        'reserved_observations_used': False, 'separate_from_historical_models': True,
        'code_sha256': digest(Path(__file__)),
    })
    frame = pd.read_parquet(path, columns=['grid_id', 'ignition_date', 'reported_fire_start'] + features,
                            filters=[('ignition_date', '>=', '2025-05-01'), ('ignition_date', '<=', '2025-07-31')])
    frame['ignition'] = frame.reported_fire_start.astype('int8')
    check_development_dates(frame)
    frame['_bucket'] = pd.util.hash_pandas_object(frame[['grid_id', 'ignition_date']], index=False).to_numpy() % 100
    records = []
    with threadpool_limits(limits=4):
        for month in ('2025-06', '2025-07'):
            training = frame.loc[frame.ignition_date.lt(month + '-01')]
            validation = frame.loc[frame.ignition_date.str.startswith(month)]
            for spec in specs:
                bundle = fit(training, features, spec, digest(contract_path))
                result, budget, _ = evaluate(bundle, validation)
                result.update(candidate=spec['name'], month=month, fitting_rows=bundle['fitting_rows'],
                              training_rows=bundle['training_rows'], training_positives=bundle['training_positives'])
                records.append(result)
                budget.to_csv(output / f"{month}_{spec['name']}_daily.csv", index=False)
                save_json(output / 'rolling_results.json', records)
                print(f"{month} {spec['name']}: AP={result['average_precision']:.6f} recall={result['daily_budget_recall']:.4f}", flush=True)
        chosen = select(records)
        save_json(output / 'selection_freeze.json', {'selected': chosen, 'selection_data': 'May-July 2025 only',
                                                   'rolling_results_sha256': digest(output / 'rolling_results.json')})
        spec = next(s for s in specs if s['name'] == chosen)
        bundle = fit(frame, features, spec, digest(contract_path))
        model_path = model_dir / f'{chosen}_development.joblib'
        joblib.dump(bundle, model_path, compress=3)
        loaded = joblib.load(model_path)
        sample = frame.iloc[:1000][features].astype('float32')
        np.testing.assert_allclose(loaded['model'].predict_proba(sample), bundle['model'].predict_proba(sample), atol=1e-12)
    if frozen_artifacts(workspace) != protected:
        raise RuntimeError('An earlier scientific artifact changed')
    result = {'selected': chosen, 'scope': 'Uncalibrated monthly development candidate; not installed in the dashboard',
              'model_sha256': digest(model_path), 'model_path': str(model_path), 'save_load_parity': True,
              'frozen_artifacts_unchanged': True, 'reserved_observations_used': False,
              'calibration_required_before_probability_use': True,
              'cross_year_validation_available': False, 'results': records}
    save_json(output / 'results.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.workspace.resolve(), args.output_dir.resolve(), args.model_dir.resolve())
