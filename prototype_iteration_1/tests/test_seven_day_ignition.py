import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.tree import DecisionTreeClassifier

from scripts.seven_day_ignition import outlook, parse_query
from scripts.seven_day_training import FEATURES, improvement, with_rain_history
from scripts.seven_day_weather import MODEL, VERSION

NOW = datetime(2026, 11, 14, 12, tzinfo=ZoneInfo('America/Toronto'))


@pytest.fixture
def workspace(tmp_path):
    base = tmp_path / 'data/processed/ontario_range_v1'
    data = tmp_path / 'data/processed/ontario_7day_v1'
    base.mkdir(parents=True)
    data.mkdir(parents=True)
    grid = pd.DataFrame({'grid_id': ['a', 'b'], 'longitude': [-89., -80.], 'latitude': [49., 44.],
                         'grid_x_m': [0, 100000], 'grid_y_m': [0, 0],
                         'region': ['Northwest', 'South (below 46 N)'], 'landscape_complete': [True, False]})
    grid.to_parquet(base / 'grid.parquet', index=False)
    np.save(base / 'seasonal_2026.npy', np.full((366, 2), .001, dtype='float32'))
    checksum = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    (base / 'runtime_manifest.json').write_text(json.dumps({'model': {'name': 'fixture'}, 'sha256': {
        name: checksum(base / name) for name in ['grid.parquet', 'seasonal_2026.npy']}}))
    rows = []
    for day in pd.date_range('2026-11-14', periods=7):
        for site, temp in [('0_0', 10.), ('1_0', 30.)]:
            rows.append({'site': site, 'date': str(day.date()), 'lead': day.day - 13,
                         'temp': temp, 'rh': 40., 'rain': 0., 'wind': 15., 'hours': 24,
                         'expected_hours': 24, 'time_safe': True, 'received_at': NOW.isoformat(),
                         'model': MODEL, 'contract': VERSION})
    frame = pd.DataFrame(rows).sample(frac=1, random_state=1)
    frame.to_parquet(data / 'weather.parquet', index=False)
    (data / 'current.json').write_text(json.dumps({'contract': VERSION, 'model': MODEL, 'sites': 2,
        'start': '2026-11-14', 'end': '2026-11-20', 'file': 'weather.parquet',
        'sha256': checksum(data / 'weather.parquet'), 'received_at': NOW.isoformat()}))
    x = pd.DataFrame(np.zeros((4, len(FEATURES))), columns=FEATURES)
    x['temp'] = [0., 10., 20., 30.]
    model = DecisionTreeClassifier(max_depth=1, random_state=1).fit(x, [0, 0, 1, 1])
    joblib.dump({'model': model, 'calibrator': None, 'blend': .5, 'features': FEATURES,
                 'contract': VERSION, 'operationally_validated': False}, data / 'candidate.joblib')
    (data / 'model.json').write_text(json.dumps({'file': 'candidate.joblib', 'sha256': checksum(data / 'candidate.joblib'),
        'contract': VERSION, 'features': FEATURES, 'ranking_improved': True, 'all_metrics_improved': False,
        'model': 'fixture', 'operationally_validated': False}))
    return tmp_path


def test_seven_days_are_fixed_and_dates_use_ontario():
    start, end, region, selected = parse_query({}, datetime(2026, 11, 15, 2, tzinfo=ZoneInfo('UTC')))
    assert str(start) == '2026-11-14' and str(end) == '2026-11-20'
    assert region == 'All Ontario' and selected == start


@pytest.mark.parametrize('query', [{'days': ['10']}, {'model': ['x']}, {'date': ['2026-11-21']},
                                  {'date': ['2026-11-13']}, {'region': ['../../']}, {'view': ['bad']}])
def test_range_and_model_inputs_are_rejected(query):
    with pytest.raises(ValueError): parse_query(query, NOW)


def test_weather_mapping_and_range_totals_match(workspace):
    daily, cells = outlook(workspace, {}, NOW)
    assert daily['days'] == 7 and len(daily['rows']) == 7
    assert all(row['weather_cells_used'] == 2 for row in daily['rows'])
    assert cells.iloc[0].grid_id == 'b'
    assert cells.expected_positive_days.sum() == pytest.approx(sum(r['expected_positive_cell_days'] for r in daily['rows']))
    assert cells.weather_days_used.eq(7).all()
    assert daily['operationally_validated'] is False
    assert 'outside' in daily['model_notice'].lower()


def test_stale_weather_falls_back_visibly(workspace):
    later = datetime(2026, 11, 14, 20, tzinfo=ZoneInfo('America/Toronto'))
    daily, cells = outlook(workspace, {}, later)
    assert all(row['weather_cells_used'] == 0 for row in daily['rows'])
    assert cells.weather_days_used.eq(0).all()
    assert cells.expected_positive_days.sum() == pytest.approx(.014)
    assert 'historical' in daily['model_notice'].lower()


def test_model_integrity_is_enforced(workspace):
    path = workspace / 'data/processed/ontario_7day_v1/candidate.joblib'
    path.write_bytes(b'changed')
    with pytest.raises(OSError, match='checksum'): outlook(workspace, {}, NOW)


def test_probability_regression_cannot_pass_full_promotion():
    baseline = {'average_precision': .1, 'recall': .1, 'brier': .01, 'log_loss': .1}
    candidate = {'average_precision': .2, 'recall': .2, 'brier': .02, 'log_loss': .11}
    assert improvement(candidate, baseline) == {'ranking': True, 'probability': False, 'all': False}


def test_experimental_weather_is_used_without_claiming_validation(workspace):
    path = workspace / 'data/processed/ontario_7day_v1/model.json'
    meta = json.loads(path.read_text())
    meta['ranking_improved'] = False
    path.write_text(json.dumps(meta))
    daily, cells = outlook(workspace, {}, NOW)
    assert all(row['weather_cells_used'] == 2 for row in daily['rows'])
    assert all(row['weather']['status'] == 'available' for row in daily['rows'])
    assert cells.expected_positive_days.sum() > .014
    assert cells.candidate_weather_days_used.eq(7).all()
    assert np.allclose(cells.candidate_expected_positive_days, cells.expected_positive_days)
    assert daily['model']['ranking_improved'] is False
    assert daily['operationally_validated'] is False
    assert daily['selection_policy'] == 'experimental_weather_plus_history'
    assert 'experimental' in daily['model_notice'].lower()
    assert 'historical estimates remain active' not in daily['model_notice'].lower()


def test_weather_changes_the_displayed_prediction_without_changing_history(workspace):
    daily, before = outlook(workspace, {}, NOW)
    path = workspace / 'data/processed/ontario_7day_v1/weather.parquet'
    weather = pd.read_parquet(path)
    weather['temp'] = 0.
    weather.to_parquet(path, index=False)
    receipt = path.parent / 'current.json'
    meta = json.loads(receipt.read_text())
    meta['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(meta))
    after_daily, after = outlook(workspace, {}, NOW)
    assert after.expected_positive_days.sum() < before.expected_positive_days.sum()
    assert np.allclose(after.historical_expected_positive_days, before.historical_expected_positive_days)
    assert after_daily['estimate_summary']['weather_days_used'] == 7


@pytest.mark.parametrize('stale', [False, True])
def test_prospective_records_separate_candidate_and_active_model_checksums(workspace, monkeypatch, stale):
    from scripts import seven_day_ignition as ignition
    data = workspace / 'data/processed/ontario_7day_v1'
    model = json.loads((data / 'model.json').read_text())
    model['ranking_improved'] = False
    (data / 'model.json').write_text(json.dumps(model))
    actual_outlook = ignition.outlook
    clock = datetime(2026, 11, 14, 20, tzinfo=ZoneInfo('America/Toronto')) if stale else NOW
    monkeypatch.setattr(ignition, 'outlook', lambda ws, query, all_days=False:
                        actual_outlook(ws, query, clock, all_days=all_days))
    saved = pd.read_parquet(ignition.save_prospective(workspace))
    base = json.loads((workspace / 'data/processed/ontario_range_v1/runtime_manifest.json').read_text())
    assert saved.model_sha256.eq(base['sha256']['seasonal_2026.npy'] if stale else model['sha256']).all()
    assert saved.candidate_model_sha256.eq(model['sha256']).all()
    assert saved.candidate_weather_days_used.eq(0 if stale else 1).all()
    assert saved.weather_days_used.eq(0 if stale else 1).all()
    assert saved.selection_policy.eq('experimental_weather_plus_history').all()


def test_one_day_map_preserves_the_weather_inputs(workspace):
    daily, cells = outlook(workspace, {'view': ['day'], 'date': ['2026-11-20']}, NOW)
    assert cells.date.eq('2026-11-20').all() and cells.lead.eq(7).all()
    assert cells.wind.eq(15).all() and cells.rain.eq(0).all()
    assert cells.probability.sum() == pytest.approx(daily['rows'][-1]['expected_positive_cell_days'])


def test_prior_rain_uses_forecasts_available_for_the_same_issue_day():
    rows = [{'site': 'a', 'date': f'2024-06-{day:02}', 'lead': lead, 'rain': lead * 100. + day,
             'hours': 24, 'expected_hours': 24, 'time_safe': True}
            for day in range(1, 9) for lead in range(1, 8)]
    weather = pd.DataFrame(rows)
    result = with_rain_history(weather)
    target = result[result.date.eq('2024-06-08') & result.lead.eq(4)].iloc[0]
    assert target.prior_rain_7d_mm == 307 + 206 + 105 + 104 + 103 + 102 + 101
    assert target.prior_rain_coverage_days == 7
    weather.loc[weather.date.eq('2024-06-07') & weather.lead.eq(3), 'hours'] = 23
    missing = with_rain_history(weather)
    target = missing[missing.date.eq('2024-06-08') & missing.lead.eq(4)].iloc[0]
    assert target.prior_rain_coverage_days == 6 and np.isnan(target.prior_rain_7d_mm)


def test_dashboard_has_fixed_outlook_controls_and_valid_javascript():
    import re
    import shutil
    import subprocess
    from scripts.forecast_view import PAGE
    assert 'id="prediction-days"' not in PAGE
    assert 'id="prediction-estimate-model"' not in PAGE
    assert 'Seven-day ignition outlook' in PAGE
    assert '/api/ignition-outlook?' in PAGE
    if shutil.which('node'):
        for script in re.findall(r'<script>(.*?)</script>', PAGE, re.S):
            checked = subprocess.run(['node', '--check'], input=script, text=True, capture_output=True)
            assert checked.returncode == 0, checked.stderr


def test_diagnostic_publishes_an_audited_bundle_and_retains_an_equal_incumbent(workspace, monkeypatch):
    from scripts import seven_day_training as training
    from scripts.seven_day_weather import locations
    base = workspace / 'data/processed/ontario_range_v1'
    data = workspace / 'data/processed/ontario_7day_v1'
    choices = pd.DataFrame({'grid_x_m': np.arange(20) * 100000, 'grid_y_m': 0,
                            'longitude': -85., 'latitude': 50.})
    ids, _ = locations(choices)
    held = pd.util.hash_pandas_object(ids, index=False).mod(5).eq(0)
    indices = [*choices.index[held][:2], *choices.index[~held][:2]]
    grid = choices.loc[indices].copy().reset_index(drop=True)
    grid['grid_id'] = ['held_positive', 'held_negative', 'fit_positive', 'fit_negative']
    grid.to_parquet(base / 'grid.parquet', index=False)
    (data / 'model.json').unlink()
    best = {'model': 'logistic', 'negative_fraction': .01, 'calibration': 'raw',
            'weather_weight': .5, 'improvement': {'ranking': True, 'all': True}}
    monkeypatch.setattr(training, 'fingerprint', lambda ws, diagnostic=True: ('a' * 64, {}))
    monkeypatch.setattr(training, 'search_models', lambda ws, identity, ledger: (best, data / 'candidate.joblib'))

    def tiny_panel(ws, year, start, end, fraction=1., allowed=None):
        rows = []
        for day in [f'{year}-05-01', f'{year}-05-02']:
            for lead in range(1, 8):
                for key in grid.grid_id:
                    if allowed is not None and key not in allowed:
                        continue
                    y = int(key.endswith('positive'))
                    row = dict.fromkeys(FEATURES, 0.)
                    row.update(grid_id=key, date=day, lead=lead, ignition=y,
                               temp=30. if y else 10., seasonal_probability=.001)
                    rows.append(row)
        frame = pd.DataFrame(rows)
        frame.attrs.update(population_rows=len(frame), population_positives=int(frame.ignition.sum()))
        return frame

    monkeypatch.setattr(training, 'build_panel', tiny_panel)
    result = training.run(workspace)
    registered = json.loads((data / 'model.json').read_text())
    assert registered['training_fingerprint'] == 'a' * 64
    assert registered['features'] == FEATURES and registered['operationally_validated'] is False
    assert set(result['by_lead']) == set(map(str, range(1, 8)))
    assert result['held_geography']['held_cells'] == 2
    registered['ranking_improved'] = True
    (data / 'model.json').write_text(json.dumps(registered))
    before = (data / 'model.json').read_bytes()
    monkeypatch.setattr(training, 'fingerprint', lambda ws, diagnostic=True: ('b' * 64, {}))
    result = training.run(workspace)
    assert result['replaced_previous_model'] is False
    assert (data / 'model.json').read_bytes() == before
