"""Bounded model search with chronological calibration and untouched older studies."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import joblib
from lightgbm import LGBMClassifier
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from scripts.range_predictions import day_index
from scripts.seven_day_weather import VERSION, digest, locations
from scripts.week5_ignition import apply_calibration, fit_calibration

LANDSCAPE = ['scanfi_2020_closure_sample_mean_pct', 'scanfi_2020_canopy_weighted_conifer_pct',
             'scanfi_species_valid_fraction', 'terrain_elevation_mean_m', 'terrain_slope_deg', 'terrain_coverage_fraction']
FEATURES = ['seasonal_probability', 'season_sin', 'season_cos', 'longitude', 'latitude',
            'temp', 'rh', 'rain', 'wind', 'hours', 'lead', 'weather_complete',
            'prior_rain_7d_mm', 'prior_rain_coverage_days', *LANDSCAPE]
SEED = 385


def save_json(path, value):
    temporary = path.with_suffix('.tmp.json')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False))
    temporary.replace(path)


def enrich_grid(grid, workspace):
    path = Path(workspace) / 'team_repository/data/interim/cdem_terrain_10km_summary.csv'
    if not path.exists():
        return grid
    terrain = pd.read_csv(path)
    if terrain.grid_id.duplicated().any() or not terrain.terrain_source_vintage_end_year.le(2011).all():
        raise ValueError('Legacy static terrain contract changed')
    columns = ['terrain_elevation_mean_m', 'terrain_slope_deg', 'terrain_coverage_fraction']
    return grid.join(terrain.set_index('grid_id')[columns], on='grid_id', validate='one_to_one')


def with_rain_history(weather):
    """Use only rainfall forecasts whose reference bound precedes the same issue day."""
    weather = weather.copy()
    keys = pd.MultiIndex.from_frame(weather[['site', 'date', 'lead']])
    valid = weather.hours.eq(weather.expected_hours) & weather.time_safe.eq(True) & np.isfinite(weather.rain)
    source = pd.Series(weather.rain.where(valid).to_numpy(), index=keys)
    totals, coverage = np.zeros(len(weather)), np.zeros(len(weather), dtype=int)
    for lag in range(1, 8):
        prior_dates = (pd.to_datetime(weather.date) - pd.Timedelta(days=lag)).dt.strftime('%Y-%m-%d')
        prior_leads = np.maximum(1, weather.lead.to_numpy() - lag)
        prior_keys = pd.MultiIndex.from_arrays([weather.site, prior_dates, prior_leads])
        values = source.reindex(prior_keys).to_numpy()
        totals += np.nan_to_num(values, nan=0.)
        coverage += np.isfinite(values)
    weather['prior_rain_7d_mm'] = np.where(coverage == 7, totals, np.nan)
    weather['prior_rain_coverage_days'] = coverage
    return weather


def feature_frame(grid, baseline, weather, day, lead):
    ids, _ = locations(grid)
    part = weather[(weather.date == str(day)[:10]) & weather.lead.eq(lead)]
    if part.duplicated('site').any():
        raise ValueError('Duplicate weather location')
    x = part.set_index('site').reindex(ids).reset_index(drop=True)
    complete = x.hours.eq(x.expected_hours) & x.time_safe.eq(True)
    frame = grid[['longitude', 'latitude']].reset_index(drop=True).copy()
    frame['seasonal_probability'] = baseline
    angle = 2 * np.pi * pd.Timestamp(day).dayofyear / 365.25
    frame['season_sin'], frame['season_cos'] = np.sin(angle), np.cos(angle)
    for name in ['temp', 'rh', 'rain', 'wind', 'hours']:
        frame[name] = x[name].where(complete)
    frame['lead'], frame['weather_complete'] = lead, complete.astype(int)
    frame['prior_rain_7d_mm'] = x['prior_rain_7d_mm']
    frame['prior_rain_coverage_days'] = x['prior_rain_coverage_days']
    for name in LANDSCAPE:
        frame[name] = grid[name].to_numpy() if name in grid else np.nan
    return frame[FEATURES].astype('float32')


def build_panel(workspace, year, start, end, fraction=1., allowed=None):
    folder = Path(workspace) / 'data/processed/ontario_range_v1'
    new_folder = Path(workspace) / 'data/processed/ontario_7day_v1'
    grid = enrich_grid(pd.read_parquet(folder / 'grid.parquet'), workspace)
    events = pd.read_parquet(folder / 'labels_audit.parquet')
    events = events[events.year.eq(year) & events.reason.eq('retained')]
    truth = set(zip(events.date.dt.strftime('%Y-%m-%d'), events.grid_id))
    rates = np.load(folder / f'seasonal_{year}.npy', allow_pickle=False)
    weather = pd.concat([pd.read_parquet(new_folder / f'weather_{year}_{m:02}.parquet')
                         for m in range(pd.Timestamp(start).month, pd.Timestamp(end).month + 1)], ignore_index=True)
    if weather.duplicated(['site', 'date', 'lead']).any() or not weather.contract.eq(VERSION).all():
        raise ValueError('Archive weather contract or keys changed')
    weather = with_rain_history(weather)
    allowed_mask = grid.grid_id.isin(allowed).to_numpy() if allowed is not None else np.ones(len(grid), dtype=bool)
    tables, population_rows, population_positives = [], 0, 0
    for day in pd.date_range(start, end):
        text = day.strftime('%Y-%m-%d')
        y = np.array([int((text, key) in truth) for key in grid.grid_id], dtype='uint8')
        hashes = pd.util.hash_pandas_object(pd.DataFrame({'grid_id': grid.grid_id, 'date': text}), index=False).to_numpy()
        sampled = allowed_mask & ((y == 1) | (hashes % 10000 < round(fraction * 10000)))
        population_rows += int(allowed_mask.sum()) * 7
        population_positives += int(y[allowed_mask].sum()) * 7
        for lead in range(1, 8):
            frame = feature_frame(grid, rates[day_index(day)], weather, text, lead).loc[sampled].copy()
            frame['grid_id'], frame['date'], frame['ignition'] = grid.loc[sampled, 'grid_id'].to_numpy(), text, y[sampled]
            tables.append(frame)
    result = pd.concat(tables, ignore_index=True)
    result.attrs.update(population_rows=population_rows, population_positives=population_positives)
    return result


def daily_hits(frame, probability):
    rows = []
    for (day, lead), part in frame.groupby(['date', 'lead'], sort=True):
        order = np.lexsort((part.grid_id.to_numpy(), -probability[part.index]))
        count = max(1, int(np.ceil(len(part) * .01)))
        rows.append({'date': day, 'lead': lead, 'hits': int(part.ignition.to_numpy()[order[:count]].sum()),
                     'alerts': count, 'positives': int(part.ignition.sum())})
    return pd.DataFrame(rows)


def evaluate(frame, probability):
    probability = np.asarray(probability, dtype=float)
    y = frame.ignition.to_numpy()
    if not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
        raise ValueError('Invalid candidate probabilities')
    budget = daily_hits(frame, probability)
    hits, alerts = int(budget.hits.sum()), int(budget.alerts.sum())
    return {'rows': len(y), 'positive_cell_day_leads': int(y.sum()),
            'unique_positive_cell_days': int(frame.loc[frame.ignition.eq(1), ['grid_id', 'date']].drop_duplicates().shape[0]),
            'average_precision': float(average_precision_score(y, probability)),
            'brier': float(brier_score_loss(y, probability)),
            'log_loss': float(log_loss(y, probability, labels=[0, 1])),
            'recall': hits / int(y.sum()) if y.sum() else 0., 'hits': hits, 'alerts': alerts,
            'mean_probability': float(probability.mean())}


def improvement(candidate, baseline):
    ranking = (candidate['average_precision'] > baseline['average_precision']
               and candidate['recall'] >= baseline['recall'])
    probability = candidate['brier'] <= baseline['brier'] and candidate['log_loss'] <= baseline['log_loss']
    return {'ranking': bool(ranking), 'probability': bool(probability), 'all': bool(ranking and probability)}


def estimator(name):
    if name in ('logistic', 'mlp'):
        model = (LogisticRegression(C=.1, max_iter=1000, random_state=SEED) if name == 'logistic' else
                 MLPClassifier(hidden_layer_sizes=(32, 16), alpha=.01, batch_size=512,
                               max_iter=100, early_stopping=False, random_state=SEED))
        return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                             StandardScaler(), model)
    if name == 'histogram_boosting':
        return HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=7, min_samples_leaf=100,
                                               l2_regularization=10., early_stopping=False, random_state=SEED)
    if name == 'extra_trees':
        return make_pipeline(SimpleImputer(strategy='median', add_indicator=True),
                             ExtraTreesClassifier(n_estimators=150, max_depth=10, min_samples_leaf=30,
                                                  max_features=.8, n_jobs=4, random_state=SEED))
    return LGBMClassifier(n_estimators=200, learning_rate=.03, num_leaves=7 if name == 'lightgbm_small' else 15,
                         max_depth=4 if name == 'lightgbm_small' else 6, min_child_samples=100,
                         reg_lambda=10., n_jobs=4, random_state=SEED, deterministic=True,
                         force_col_wise=True, verbosity=-1)


def fit_model(name, frame):
    y = frame.ignition.to_numpy()
    if int(y.sum()) != frame.attrs['population_positives'] or not (y == 0).any():
        raise ValueError('Sampling lost positive cases or every negative case')
    weights = np.where(y == 1, 1., (frame.attrs['population_rows'] - frame.attrs['population_positives']) / int((y == 0).sum()))
    model = estimator(name)
    kwargs = {'sample_weight': weights}
    if hasattr(model, 'steps'):
        kwargs = {model.steps[-1][0] + '__sample_weight': weights}
    model.fit(frame[FEATURES], y, **kwargs)
    return model


def calibrated(model, mapping, frame, blend=1.):
    raw = model.predict_proba(frame[FEATURES])[:, 1]
    probability = apply_calibration(mapping, raw) if mapping else raw
    return blend * probability + (1 - blend) * frame.seasonal_probability.to_numpy()


def fingerprint(workspace, diagnostic=True):
    workspace = Path(workspace)
    files = [workspace / 'data/processed/ontario_range_v1' / name for name in
             ['grid.parquet', 'labels_audit.parquet', 'seasonal_2024.npy', 'seasonal_2025.npy']]
    pattern = 'weather_202[45]_??.parquet' if diagnostic else 'weather_2024_??.parquet'
    files += sorted((workspace / 'data/processed/ontario_7day_v1').glob(pattern))
    if len(files) != (16 if diagnostic else 10):
        raise FileNotFoundError('Complete matched forecast archives are required for this experiment phase')
    ledger = {str(path.relative_to(workspace)): digest(path) for path in files}
    terrain = workspace / 'team_repository/data/interim/cdem_terrain_10km_summary.csv'
    if terrain.exists():
        ledger[str(terrain.relative_to(workspace))] = digest(terrain)
    ledger['trainer_source'] = digest(Path(__file__))
    return hashlib.sha256(json.dumps(ledger, sort_keys=True).encode()).hexdigest(), ledger


def search_models(workspace, identity, ledger):
    data = workspace / 'data/processed/ontario_7day_v1'
    report = workspace / 'reports/ontario_7day_v1'
    report.mkdir(parents=True, exist_ok=True)
    model_file = data / f'candidate_{identity[:12]}.joblib'
    experiment = report / 'experiments' / identity[:12]
    experiment.mkdir(parents=True, exist_ok=True)
    completed = experiment / 'search.json'
    if completed.exists():
        saved = json.loads(completed.read_text())
        if saved['sha256'] != digest(model_file):
            raise OSError('Completed search model checksum changed')
        return saved['best'], model_file
    protocol = {'contract': VERSION, 'features': FEATURES,
                'folds': [{'fit': 'May–June 2024', 'calibration': 'July 8–31 2024', 'selection': 'August 8–31 2024'},
                          {'fit': 'May–July 2024', 'calibration': 'August 8–31 2024', 'selection': 'September 8–October 31 2024'}],
                'purge_days': 7, 'diagnostic': 'May–October 2025; previously exposed development, not independent test',
                'sampling': 'All positives; deterministic 1% and 5% negatives with inverse population weights; same mask across leads',
                'selection_rule': 'Highest selection AP among ranking improvements; prefer all-metric improvements; otherwise retain baseline',
                'weather_offsets': list(range(1, 8)), 'independent_test': False,
                'source_timing': 'Fixed lead reference bounds checked; historical publication times unverified',
                'landscape': 'SCANFI nominal 2020 canopy with coverage; CDEM legacy terrain through 2011; no FBP-2024 backfill or future fire products',
                'rain_history': 'Prior seven local days: offset max(1, target_lead-lag); all references precede the issue day; complete-week sum or missing plus coverage count',
                'geography_scope': 'Hyperparameters selected on 2024 province-wide development; separate diagnostic refit excludes held classifier cells and a 20 km buffer; older history remains available',
                'packages': {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scikit-learn', 'lightgbm']},
                'input_sha256': ledger}
    save_json(experiment / 'protocol.json', protocol)
    calibration_frames = [build_panel(workspace, 2024, '2024-07-08', '2024-07-31'),
                          build_panel(workspace, 2024, '2024-08-08', '2024-08-31')]
    validation_frames = [calibration_frames[1], build_panel(workspace, 2024, '2024-09-08', '2024-10-31')]
    validation = pd.concat(validation_frames, ignore_index=True)
    baseline = evaluate(validation, validation.seasonal_probability.to_numpy())
    trials, best, best_key = [], None, None
    candidates = [('logistic', .01), ('mlp', .01), ('histogram_boosting', .01), ('extra_trees', .01),
                  ('lightgbm_small', .01), ('lightgbm', .01), ('lightgbm_small', .05), ('lightgbm', .05)]
    with threadpool_limits(limits=4):
        for iteration, (name, fraction) in enumerate(candidates, 1):
            raw_parts, calibrated_parts = [], []
            try:
                for fold, fit_end in enumerate(['2024-06-30', '2024-07-31']):
                    fit = build_panel(workspace, 2024, '2024-05-01', fit_end, fraction)
                    model = fit_model(name, fit)
                    cal = calibration_frames[fold]
                    mapping = fit_calibration(cal.ignition.to_numpy(), model.predict_proba(cal[FEATURES])[:, 1])
                    raw = model.predict_proba(validation_frames[fold][FEATURES])[:, 1]
                    raw_parts.append(raw)
                    calibrated_parts.append(apply_calibration(mapping, raw))
            except (ValueError, RuntimeError) as error:
                trials.append({'iteration': iteration, 'model': name, 'negative_fraction': fraction,
                               'status': 'failed', 'error': str(error)})
                save_json(experiment / 'iterations.json', {'baseline': baseline, 'trials': trials, 'best': best})
                print(f'Iteration {iteration} failed: {name}: {error}', flush=True)
                continue
            for calibration_name, p in [('raw', np.concatenate(raw_parts)), ('sigmoid', np.concatenate(calibrated_parts))]:
                for blend in (.25, .5, 1.):
                    p_blended = blend * p + (1 - blend) * validation.seasonal_probability.to_numpy()
                    scores = evaluate(validation, p_blended)
                    gate = improvement(scores, baseline)
                    key = (int(gate['all']), int(gate['ranking']), scores['average_precision'], -scores['log_loss'])
                    trial = {'iteration': iteration, 'model': name, 'negative_fraction': fraction,
                             'calibration': calibration_name, 'weather_weight': blend,
                             'sampled_rows': len(fit), 'population_rows': fit.attrs['population_rows'],
                             'scores': scores, 'improvement': gate,
                             'parameters': (model.steps[-1][1] if hasattr(model, 'steps') else model).get_params()}
                    trials.append(trial)
                    if best_key is None or key > best_key:
                        best_key, best = key, trial
                        joblib.dump({'model': model, 'calibrator': mapping if calibration_name == 'sigmoid' else None,
                                     'blend': blend, 'features': FEATURES, 'contract': VERSION,
                                     'operationally_validated': False}, model_file)
                    save_json(experiment / 'iterations.json', {'baseline': baseline, 'trials': trials, 'best': best})
            print(f'Iteration {iteration}/{len(candidates)}: {name}, negatives {fraction:.0%}; best AP {best["scores"]["average_precision"]:.6f}', flush=True)
    if best is None:
        raise RuntimeError('Every model candidate failed; historical model remains active')
    if fingerprint(workspace, diagnostic=False)[0] != identity:
        raise OSError('Training inputs or code changed during model search')
    save_json(completed, {'best': best, 'file': model_file.name, 'sha256': digest(model_file),
                          'search_fingerprint': identity})
    return best, model_file


def run(workspace):
    workspace = Path(workspace)
    data = workspace / 'data/processed/ontario_7day_v1'
    report = workspace / 'reports/ontario_7day_v1'
    search_identity, search_ledger = fingerprint(workspace, diagnostic=False)
    best, model_file = search_models(workspace, search_identity, search_ledger)
    identity, ledger = fingerprint(workspace)
    previous_path = data / 'model.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    if previous.get('training_fingerprint') == identity:
        return {'status': 'unchanged_data_no_retraining', 'training_fingerprint': identity}
    experiment = report / 'experiments' / identity[:12]
    experiment.mkdir(parents=True, exist_ok=True)
    bundle = joblib.load(model_file)
    # Diagnostic outcomes never enter the completed model search.
    diagnostic = build_panel(workspace, 2025, '2025-05-01', '2025-10-31')
    with threadpool_limits(limits=4):
        probability = calibrated(bundle['model'], bundle['calibrator'], diagnostic, bundle['blend'])
    scores = evaluate(diagnostic, probability)
    baseline_2025 = evaluate(diagnostic, diagnostic.seasonal_probability.to_numpy())
    leads = {}
    for lead, part in diagnostic.groupby('lead', sort=True):
        leads[str(lead)] = {'candidate': evaluate(part.reset_index(drop=True), probability[part.index]),
                            'baseline': evaluate(part.reset_index(drop=True), part.seasonal_probability.to_numpy())}
    results = {'selected': best, 'diagnostic': scores, 'baseline': baseline_2025,
               'search_fingerprint': search_identity,
               'diagnostic_improvement': improvement(scores, baseline_2025), 'by_lead': leads,
               'independent_test': False, 'operationally_validated': False}
    paired = daily_hits(diagnostic, probability).merge(
        daily_hits(diagnostic, diagnostic.seasonal_probability.to_numpy()), on=['date', 'lead'], suffixes=('_candidate', '_baseline'))
    paired['week'] = (pd.to_datetime(paired.date) - pd.Timestamp('2025-05-01')).dt.days // 7
    weekly = paired.groupby('week')[['hits_candidate', 'hits_baseline', 'positives_candidate']].sum().to_numpy()
    rng = np.random.default_rng(SEED)
    boot = weekly[rng.integers(0, len(weekly), size=(2000, len(weekly)))].sum(axis=1)
    valid = boot[:, 2] > 0
    results['recall_change_95_interval'] = np.quantile((boot[valid, 0] - boot[valid, 1]) / boot[valid, 2], [.025, .975]).tolist()
    results['uncertainty_method'] = 'Paired seven-day target-date block bootstrap across all leads; 2000 draws; conditional on this exposed season'
    grid = enrich_grid(pd.read_parquet(workspace / 'data/processed/ontario_range_v1/grid.parquet'), workspace)
    site_ids, _ = locations(grid)
    held = pd.util.hash_pandas_object(site_ids, index=False).mod(5).eq(0).to_numpy()
    distances, _ = cKDTree(grid.loc[held, ['grid_x_m', 'grid_y_m']]).query(grid[['grid_x_m', 'grid_y_m']])
    train_keys = set(grid.loc[~held & (distances >= 20000), 'grid_id'])
    test_keys = set(grid.loc[held, 'grid_id'])
    geo_fit = build_panel(workspace, 2024, '2024-05-01', '2024-07-31', best['negative_fraction'], train_keys)
    geo_cal = build_panel(workspace, 2024, '2024-08-08', '2024-08-31', allowed=train_keys)
    geo_test = diagnostic[diagnostic.grid_id.isin(test_keys)].reset_index(drop=True)
    with threadpool_limits(limits=4):
        geo_model = fit_model(best['model'], geo_fit)
        geo_mapping = fit_calibration(geo_cal.ignition.to_numpy(), geo_model.predict_proba(geo_cal[FEATURES])[:, 1]) if best['calibration'] == 'sigmoid' else None
        geo_probability = calibrated(geo_model, geo_mapping, geo_test, best['weather_weight'])
    results['held_geography'] = {'candidate': evaluate(geo_test, geo_probability),
        'baseline': evaluate(geo_test, geo_test.seasonal_probability.to_numpy()), 'training_cells': len(train_keys),
        'held_cells': len(test_keys), 'buffer_cells': len(grid) - len(train_keys) - len(test_keys),
        'history_policy': 'Past-only older history available everywhere; weather classifier fitting and calibration exclude held cells'}
    results['geographic_improvement'] = improvement(results['held_geography']['candidate'], results['held_geography']['baseline'])
    ranking_improved = best['improvement']['ranking'] and results['diagnostic_improvement']['ranking'] and results['geographic_improvement']['ranking']
    all_metrics_improved = best['improvement']['all'] and results['diagnostic_improvement']['all'] and results['geographic_improvement']['all']
    replace_previous = True
    if previous.get('ranking_improved') and previous.get('features') == FEATURES:
        previous_file = data / previous['file']
        if Path(previous['file']).name != previous['file'] or digest(previous_file) != previous['sha256']:
            raise OSError('Incumbent model integrity failed during comparison')
        incumbent = joblib.load(previous_file)
        with threadpool_limits(limits=4):
            incumbent_probability = calibrated(incumbent['model'], incumbent['calibrator'], diagnostic, incumbent['blend'])
        incumbent_score = evaluate(diagnostic, incumbent_probability)
        results['incumbent_comparison'] = {'scores_on_same_rows': incumbent_score,
                                          'improvement': improvement(scores, incumbent_score)}
        replace_previous = ranking_improved and results['incumbent_comparison']['improvement']['all']
    results['replaced_previous_model'] = bool(replace_previous)
    save_json(experiment / 'results.json', results)
    save_json(report / 'results.json', results)
    if fingerprint(workspace)[0] != identity:
        raise OSError('Training inputs or code changed during the experiment; model was not published')
    if not replace_previous:
        return results
    manifest = {'file': model_file.name, 'sha256': digest(model_file),
                'contract': VERSION, 'features': FEATURES, 'training_fingerprint': identity,
                'ranking_improved': ranking_improved,
                'all_metrics_improved': all_metrics_improved,
                'model': best['model'], 'weather_weight': best['weather_weight'],
                'terrain_sha256': ledger.get('team_repository/data/interim/cdem_terrain_10km_summary.csv'),
                'fit_through': '2024-07-31', 'calibrated_through': '2024-08-31',
                'evaluated_months': list(range(5, 11)), 'operationally_validated': False}
    (data / 'model.tmp.json').write_text(json.dumps(manifest, indent=2))
    (data / 'model.tmp.json').replace(data / 'model.json')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('workspace', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.workspace)), flush=True)
