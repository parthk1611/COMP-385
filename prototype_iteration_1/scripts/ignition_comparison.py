"""Development-only ignition comparison; calibration and final-test files stay closed."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import resource
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from lightgbm import LGBMClassifier

ROOT = Path(__file__).resolve().parents[1]
WEEK2 = ROOT / 'reports/week_2_development_2026-10-15'
OUTPUT = ROOT / 'reports/week_3_design_2026-10-15'
DATA = ROOT / 'data/processed/ignition_evaluation_v1'
SEED = 385
MODELS = ('historical_rate', 'logistic', 'histogram_boosting', 'lightgbm')


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def validate_years(dates: pd.Series, role: str) -> None:
    bounds = {'training': (2010, 2015), 'validation': (2016, 2017)}
    if role not in bounds:
        raise ValueError('Only training and validation roles are allowed')
    years = dates.str[:4].astype(int)
    if not years.between(*bounds[role]).all():
        raise ValueError(f'Unexpected year in {role}; reserved years cannot enter development')


def validate_features(features: list[str], contract: dict, spatial: bool) -> None:
    if len(features) != len(set(features)) or set(features) & set(contract['never_predictors']):
        raise ValueError('Duplicate or forbidden predictor')
    if spatial and any(name.startswith('fire_history_') for name in features):
        raise ValueError('History predictors are forbidden in the spatial experiment')


def sample_mask(frame: pd.DataFrame) -> np.ndarray:
    keys = pd.util.hash_pandas_object(frame[['grid_id', 'ignition_date']], index=False).to_numpy()
    return (frame.ignition.to_numpy() == 1) | (keys % 100 == 0)


def corrected_weights(y: np.ndarray, population_rows: int, population_positives: int) -> np.ndarray:
    if int(y.sum()) != population_positives or not (y == 0).any():
        raise ValueError('Sampling lost positive rows or all negatives')
    negative_weight = (population_rows - population_positives) / int((y == 0).sum())
    return np.where(y == 1, 1., negative_weight)


def inner_spatial_roles(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result['inner_role'] = 'outer_reserved'
    result['nearest_inner_validation_m'] = np.nan
    dev = result.spatial_role.eq('spatial_development')
    chosen = result.apply(lambda row: int(hashlib.sha256(
        f"comp385-inner-spatial-v1|{row.block_x}|{row.block_y}".encode()).hexdigest()[:16], 16) % 5 == 0, axis=1)
    validation = dev & chosen
    if not validation.any():
        raise ValueError('No inner validation blocks')
    distance, _ = cKDTree(result.loc[validation, ['grid_x_m', 'grid_y_m']]).query(result[['grid_x_m', 'grid_y_m']])
    result['nearest_inner_validation_m'] = distance
    result.loc[dev & ~chosen & (distance >= 20000), 'inner_role'] = 'inner_training'
    result.loc[dev & ~chosen & (distance < 20000), 'inner_role'] = 'inner_buffer'
    result.loc[validation, 'inner_role'] = 'inner_validation'
    return result


def read_development(role: str, columns: list[str], manifest: dict, inner: pd.DataFrame, data_dir: Path = DATA, boundary_only: bool = False):
    if role not in ('training', 'validation'):
        raise ValueError('Reserved partitions are not accessible to this entry point')
    path = data_dir / f'{role}.parquet'
    record = manifest['files'][role]
    if path.resolve() != Path(record['path']).resolve() or digest(path) != record['sha256']:
        raise ValueError('Partition path or content differs from the frozen materialization')
    parts = []
    counts = {name: {'rows': 0, 'positives': 0} for name in ('temporal', 'inner_spatial')}
    mapping = inner.set_index('grid_id').inner_role
    wanted_inner = 'inner_training' if role == 'training' else 'inner_validation'
    for batch in pq.ParquetFile(path).iter_batches(batch_size=200000, columns=columns):
        frame = batch.to_pandas()
        validate_years(frame.ignition_date, role)
        if boundary_only:
            frame = frame.loc[frame.current_boundary_centroid_eligible].copy()
        frame['inner_role'] = frame.grid_id.map(mapping)
        if frame.inner_role.isna().any() or not frame.ignition.isin([0, 1]).all():
            raise ValueError('Unassigned geography or invalid target')
        for name, selected in [('temporal', frame), ('inner_spatial', frame[frame.inner_role == wanted_inner])]:
            counts[name]['rows'] += len(selected)
            counts[name]['positives'] += int(selected.ignition.sum())
        if role == 'training':
            frame = frame.loc[sample_mask(frame)]
        parts.append(frame)
    result = pd.concat(parts, ignore_index=True)
    if role == 'training' and not (result.ignition.sum() == counts['temporal']['positives']):
        raise ValueError('Training sampling dropped a positive')
    return result, counts


def candidates() -> dict:
    return {
        'historical_rate': DummyClassifier(strategy='prior'),
        'logistic': Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
                              ('scaler', StandardScaler()),
                              ('classifier', LogisticRegression(C=1., max_iter=2000, tol=1e-5, random_state=SEED))]),
        'histogram_boosting': HistGradientBoostingClassifier(max_iter=150, learning_rate=.05, max_leaf_nodes=15,
                                max_depth=6, min_samples_leaf=100, l2_regularization=2., early_stopping=False, random_state=SEED),
        'lightgbm': LGBMClassifier(n_estimators=150, learning_rate=.05, num_leaves=15, max_depth=6,
                         min_child_samples=100, reg_lambda=2., n_jobs=4, random_state=SEED, deterministic=True,
                         force_col_wise=True, verbosity=-1),
    }


def predict_bundle(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    if list(frame.columns) != bundle['features']:
        raise ValueError('Predictor names/order differ from the fitted bundle')
    if np.isinf(frame.to_numpy()).any():
        raise ValueError('Infinite predictor value')
    probability = bundle['model'].predict_proba(frame)[:, 1]
    if not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
        raise ValueError('Invalid model probability')
    return probability


def metrics(y: np.ndarray, probability: np.ndarray) -> dict:
    return {'rows': len(y), 'positives': int(y.sum()), 'prevalence': float(y.mean()),
            'average_precision': float(average_precision_score(y, probability)),
            'roc_auc': float(roc_auc_score(y, probability)),
            'brier': float(brier_score_loss(y, probability)),
            'log_loss': float(log_loss(y, probability, labels=[0, 1])),
            'mean_probability': float(probability.mean())}


def daily_budget(frame: pd.DataFrame, probability: np.ndarray) -> pd.DataFrame:
    scores = frame[['grid_id', 'ignition_date', 'ignition']].copy()
    scores['probability'] = probability
    scores['tie'] = pd.util.hash_pandas_object(scores[['grid_id', 'ignition_date']], index=False).to_numpy()
    rows = []
    for day, group in scores.groupby('ignition_date', sort=True):
        budget = max(1, int(np.ceil(len(group) * .01)))
        alerts = group.sort_values(['probability', 'tie'], ascending=[False, True]).head(budget)
        rows.append({'date': day, 'rows': len(group), 'positives': int(group.ignition.sum()),
                     'alerts': budget, 'hits': int(alerts.ignition.sum())})
    return pd.DataFrame(rows)


def run(output: Path = OUTPUT, data_dir: Path = DATA, contract_path: Path | None = None, boundary_only: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'model_comparison.json').exists():
        raise FileExistsError('Completed experiment exists; use a new --output-dir version')
    model_dir = ROOT / 'data/processed/ignition_models_week3_v1' / output.name
    model_dir.mkdir(parents=True, exist_ok=False)
    contract_path = contract_path or WEEK2 / 'predictor_contract_v1.json'
    contract = json.loads(contract_path.read_text())
    manifest_path = data_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    reservation_path = WEEK2 / 'evaluation_reservation_v1.json'
    if digest(reservation_path) != manifest['selector_manifest_sha256']:
        raise ValueError('Frozen evaluation reservation changed')
    reservation = json.loads(reservation_path.read_text())
    for name, expected in reservation['selectors'].items():
        if digest(WEEK2 / name) != expected['sha256']:
            raise ValueError('Frozen selector changed')
    inner = inner_spatial_roles(pd.read_csv(WEEK2 / 'ignition_spatial_partition_v1.csv'))
    inner.to_csv(output / 'inner_spatial_partition_v1.csv', index=False)
    feature_sets = {'temporal': contract['temporal_candidate_predictors'], 'inner_spatial': contract['spatial_candidate_predictors']}
    for protocol, features in feature_sets.items():
        validate_features(features, contract, spatial=protocol != 'temporal')
    configuration = {'data_dir': str(data_dir.resolve()), 'boundary_only_sensitivity': boundary_only, 'scope': 'Development comparison, not final-test or operational performance',
                     'training_years': [2010, 2015], 'validation_years': [2016, 2017],
                     'training_sampling': 'all positives + pandas row-key hash modulo100==0 negatives; inverse sampling weights',
                     'negative_sampling_hash': 'pandas.util.hash_pandas_object on grid_id/ignition_date, index=False',
                     'validation_sampling': 'none', 'feature_sets': feature_sets,
                     'primary_metric': 'average_precision', 'selection_rule': 'Largest temporal development AP; examine inner spatial and per-year results before promotion. No final-test tuning.',
                     'daily_alert_budget': 'ceil(1% of eligible cells), hash ties; illustrative capacity, not stakeholder-approved',
                     'imputation': 'Logistic: medians/indicators fitted on selected training rows; scaler weighted. Trees retain NaNs.',
                     'settings': {name: model.get_params(deep=False) for name, model in candidates().items() if name != 'logistic'},
                     'logistic': {'C': 1., 'max_iter': 2000, 'tol': 1e-5, 'class_weight': None},
                     'seed': SEED, 'threads': 4, 'no_random_early_stopping_split': True,
                     'reserved_content_read': {'calibration_2018': False, 'final_test_2019': False},
                     'outer_spatial_test_cells_used': 'Only in temporal experiment by the original all-geography temporal protocol; never in inner-spatial fitting/validation. Outer 2019 scoring untouched.',
                     'versions': {p: importlib.metadata.version(p) for p in ('numpy', 'pandas', 'pyarrow', 'scipy', 'scikit-learn', 'lightgbm', 'joblib')},
                     'python': platform.python_version(), 'code_sha256': digest(Path(__file__)),
                     'predictor_contract_sha256': digest(contract_path), 'materialization_manifest_sha256': digest(manifest_path),
                     'reservation_sha256': digest(reservation_path), 'inner_selector_sha256': digest(output / 'inner_spatial_partition_v1.csv')}
    save_json(output / 'experiment_config.json', configuration)
    columns = ['grid_id', 'ignition_date', 'ignition', 'spatial_role'] + feature_sets['temporal']
    if boundary_only:
        columns.append('current_boundary_centroid_eligible')
    start = time.perf_counter()
    train, train_counts = read_development('training', columns, manifest, inner, data_dir, boundary_only)
    validation, validation_counts = read_development('validation', columns, manifest, inner, data_dir, boundary_only)
    print(f'Loaded {len(train)} sampled training and {len(validation)} full validation rows', flush=True)
    records, model_records = [], []
    with threadpool_limits(limits=4):
        for protocol, features in feature_sets.items():
            training = train if protocol == 'temporal' else train[train.inner_role == 'inner_training']
            val = validation if protocol == 'temporal' else validation[validation.inner_role == 'inner_validation']
            x, y = training[features].astype('float32'), training.ignition.to_numpy()
            vx, vy = val[features].astype('float32'), val.ignition.to_numpy()
            if np.isinf(x.to_numpy()).any() or np.isinf(vx.to_numpy()).any():
                raise ValueError('Infinite source predictors')
            weights = corrected_weights(y, train_counts[protocol]['rows'], train_counts[protocol]['positives'])
            row_hash = hashlib.sha256(pd.util.hash_pandas_object(training[['grid_id', 'ignition_date']], index=False).to_numpy().tobytes()).hexdigest()
            predictions = val[['grid_id', 'ignition_date', 'ignition']].reset_index(drop=True).copy()
            for name, model in candidates().items():
                fit_start = time.perf_counter()
                with warnings.catch_warnings():
                    warnings.simplefilter('error', ConvergenceWarning)
                    if name == 'logistic':
                        model.fit(x, y, scaler__sample_weight=weights, classifier__sample_weight=weights)
                    else:
                        model.fit(x, y, sample_weight=weights)
                fit_seconds = time.perf_counter() - fit_start
                bundle = {'model': model, 'features': features, 'protocol': protocol,
                          'mode': 'retrospective_development_uncalibrated', 'feature_contract_sha256': digest(contract_path)}
                probability = predict_bundle(bundle, vx)
                result = metrics(vy, probability)
                result.update(protocol=protocol, model=name, fitted_rows=len(y), fitted_positive_rows=int(y.sum()),
                              eligible_training_rows=train_counts[protocol]['rows'], feature_count=len(features),
                              training_row_key_hash=row_hash, fit_seconds=fit_seconds)
                for year in (2016, 2017):
                    selected = val.ignition_date.str.startswith(str(year)).to_numpy()
                    result[f'year_{year}'] = metrics(vy[selected], probability[selected])
                budgets = daily_budget(val, probability)
                result['daily_budget_recall'] = float(budgets.hits.sum() / budgets.positives.sum())
                result['daily_budget_precision'] = float(budgets.hits.sum() / budgets.alerts.sum())
                result['false_alerts_per_1000_cell_days'] = float((budgets.alerts.sum() - budgets.hits.sum()) / len(val) * 1000)
                rng = np.random.default_rng(SEED)
                boot = budgets.iloc[rng.integers(0, len(budgets), size=1000 * len(budgets))].reset_index(drop=True)
                numer = boot.hits.to_numpy().reshape(1000, -1).sum(axis=1)
                denom = boot.positives.to_numpy().reshape(1000, -1).sum(axis=1)
                result['daily_bootstrap_recall_95pct'] = np.quantile(numer / denom, [.025, .975]).tolist()
                budgets.to_csv(output / f'{protocol}_{name}_daily_alerts.csv', index=False)
                latencies = []
                for day in sorted(val.ignition_date.unique())[:20]:
                    day_x = vx.loc[val.ignition_date == day]
                    score_start = time.perf_counter(); predict_bundle(bundle, day_x)
                    latencies.append(time.perf_counter() - score_start)
                result['p95_model_only_daily_score_seconds_20_days'] = float(np.quantile(latencies, .95))
                path = model_dir / f'{protocol}_{name}.joblib'
                joblib.dump(bundle, path)
                loaded = joblib.load(path)
                probe = vx.iloc[:min(1000, len(vx))]
                restored = predict_bundle(loaded, probe)
                np.testing.assert_allclose(restored, probability[:len(probe)], rtol=1e-6, atol=1e-8)
                model_records.append({'protocol': protocol, 'model': name, 'path': str(path), 'bytes': path.stat().st_size,
                                      'sha256': digest(path), 'save_load_prediction_parity': True,
                                      'save_load_max_absolute_probability_difference': float(np.max(np.abs(restored - probability[:len(probe)])))})
                predictions[name] = probability
                records.append(result)
                print(protocol, name, 'AP', round(result['average_precision'], 6), 'fit_seconds', round(fit_seconds, 2), flush=True)
            predictions.to_parquet(model_dir / f'{protocol}_validation_predictions.parquet', index=False)
    summary = {'config_sha256': digest(output / 'experiment_config.json'), 'training_population': train_counts,
               'validation_population': validation_counts, 'results': records, 'models': model_records,
               'recommended_development_candidate': max((r for r in records if r['protocol'] == 'temporal'), key=lambda r: r['average_precision'])['model'],
               'total_seconds': time.perf_counter() - start, 'peak_process_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
               'final_test_scored': False, 'calibration_fitted': False, 'operational_acceptance': False}
    save_json(output / 'model_comparison.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    parser.add_argument('--data-dir', type=Path, default=DATA)
    parser.add_argument('--contract-path', type=Path)
    parser.add_argument('--boundary-only', action='store_true')
    args = parser.parse_args()
    run(args.output_dir, args.data_dir, args.contract_path, args.boundary_only)


if __name__ == '__main__':
    main()
