"""Past-only weather-history ablation on a new wildfire target; development only."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.ignition_comparison import candidates, corrected_weights, digest, inner_spatial_roles, predict_bundle, save_json
from scripts.model_refinement import checked_sources, evaluate, frozen_artifacts, paired_recall_interval
from scripts.week5_ignition import fit_calibration

KEYS = ['grid_id', 'ignition_date']
SPECS = ('reference', 'history', 'history_quality')
FOLDS = (2014, 2015)
PROTOCOLS = ('temporal', 'inner_spatial')
WINDOWS = (3, 7)
HISTORY = [f'fire_history_{x}_{w}d' for w in (30, 365) for x in ('same_cell', 'neighborhood')] + ['fire_history_days_since_same_cell']
WX_VALUES = [f'wx_{f}_{kind}_{w}d' for f in ('fwi', 'dmc') for w in WINDOWS for kind in ('mean', 'delta')]
WX_QUALITY = [f'wx_{f}_{kind}_{w}d' for f in ('fwi', 'dmc') for w in WINDOWS for kind in ('count', 'incomplete')]


def retained_events(events):
    prescribed = events.fire_type.eq('PB') | events.is_prescribed.eq('PB') | events.cause.eq('H-PB')
    return events.loc[~prescribed].copy()


def relabel(frame, events):
    kept = retained_events(events)
    counts = kept.groupby(KEYS).size()
    result = frame.copy()
    result['ignition_count'] = counts.reindex(pd.MultiIndex.from_frame(frame[KEYS]), fill_value=0).to_numpy().astype('int32')
    result['ignition'] = result.ignition_count.gt(0).astype('int8')
    return result


def weather_history(frame):
    if frame.duplicated(KEYS).any() or not frame.ignition_date.str[:4].astype(int).between(2010, 2017).all():
        raise ValueError('Unique exposed-development keys are required')
    stamps = pd.to_datetime(frame.ignition_date)
    result = pd.DataFrame(index=frame.index)
    for field in ('fwi', 'dmc'):
        wide = frame.pivot(index='ignition_date', columns='grid_id', values=f'cwfis_{field}')
        wide.index = pd.to_datetime(wide.index)
        wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max()))
        positions = (wide.index.get_indexer(stamps), wide.columns.get_indexer(frame.grid_id))
        for window in WINDOWS:
            count = wide.rolling(window, min_periods=1).count()
            mean = wide.rolling(window, min_periods=window).mean()
            delta = wide - wide.shift(window-1)
            for kind, values in [('mean', mean), ('delta', delta), ('count', count), ('incomplete', count.lt(window))]:
                result[f'wx_{field}_{kind}_{window}d'] = values.to_numpy()[positions].astype('float32')
    return result


def history_values(frame, events):
    """Recompute all target-derived histories using only retained, strictly earlier events."""
    result = pd.DataFrame(np.nan, index=frame.index, columns=HISTORY, dtype='float32')
    by_cell = {key: np.sort(pd.to_datetime(g.ignition_date).to_numpy(dtype='datetime64[D]').astype(int))
               for key, g in events.groupby('grid_id')}
    for key, rows in frame.groupby('grid_id', sort=False):
        _, x, y = key.split('_');x, y = int(x), int(y)
        days = pd.to_datetime(rows.ignition_date).to_numpy(dtype='datetime64[D]').astype(int)
        same = by_cell.get(key, np.array([], dtype=int))
        neighbors = [by_cell.get(f'ofr10km_{x+dx}_{y+dy}', np.array([], dtype=int))
                     for dx in (-10000, 0, 10000) for dy in (-10000, 0, 10000)]
        nearby = np.sort(np.concatenate(neighbors))
        for window in (30, 365):
            for name, values in [('same_cell', same), ('neighborhood', nearby)]:
                result.loc[rows.index, f'fire_history_{name}_{window}d'] = (
                    np.searchsorted(values, days, side='left') - np.searchsorted(values, days-window, side='left'))
        indices = np.searchsorted(same, days, side='left')-1
        if len(same):
            result.loc[rows.index, 'fire_history_days_since_same_cell'] = np.where(indices >= 0, days-same[np.maximum(indices, 0)], np.nan)
    return result


def choose_features(contract, protocol, spec):
    if protocol not in PROTOCOLS or spec not in SPECS:
        raise ValueError('Unregistered experiment')
    features = contract['temporal_candidate_predictors' if protocol == 'temporal' else 'spatial_candidate_predictors'][:]
    if spec != 'reference':
        features += WX_VALUES
    if spec == 'history_quality':
        features += WX_QUALITY
    return features


def build_year(data, year, mapping, events, features):
    role = 'training' if year <= 2015 else 'validation'
    if year not in range(2010, 2018):
        raise ValueError('Reserved final years are not accessible')
    frame = pd.read_parquet(data/f'{role}.parquet', columns=KEYS+['ignition']+features,
        filters=[('ignition_date', '>=', f'{year}-01-01'), ('ignition_date', '<=', f'{year}-12-31')])
    original = frame.ignition.copy()
    all_counts = events.groupby(KEYS).size().reindex(pd.MultiIndex.from_frame(frame[KEYS]), fill_value=0)
    if not np.array_equal(original.to_numpy(), all_counts.gt(0).to_numpy()):
        raise ValueError('Original target does not reconcile with its event source')
    frame = relabel(frame, events)
    label_changes = int(frame.ignition.ne(original).sum())
    rebuilt = history_values(frame, retained_events(events))
    frame[HISTORY] = rebuilt[HISTORY]
    frame = pd.concat([frame, weather_history(frame)], axis=1)
    frame['inner_role'] = frame.grid_id.map(mapping)
    if frame.inner_role.isna().any():
        raise ValueError('Unassigned geography')
    frame['_year'] = year
    frame['_bucket'] = pd.util.hash_pandas_object(frame[KEYS], index=False).to_numpy() % 100
    for f in features+WX_VALUES+WX_QUALITY:
        frame[f] = frame[f].astype('float32')
    return frame, label_changes


def train_bundle(sample, population, cutoff, protocol, spec, contract):
    train = sample.loc[sample._year.lt(cutoff)]
    pop = population.loc[population.year.lt(cutoff)]
    if protocol == 'inner_spatial':
        train = train.loc[train.inner_role.eq('inner_training')]
        pop = pop.loc[pop.inner_role.eq('inner_training')]
    features = choose_features(contract, protocol, spec)
    weights = corrected_weights(train.ignition.to_numpy(), int(pop.rows.sum()), int(pop.positives.sum()))
    model = candidates()['lightgbm']
    model.fit(train[features], train.ignition, sample_weight=weights)
    return {'model':model, 'features':features, 'protocol':protocol, 'candidate':spec,
            'target_version':'wildfire_explicit_PB_excluded_v1', 'mode':'development_only',
            'fitted_rows':len(train), 'training_through':cutoff-1}


def select_spec(records, protocol):
    rows = pd.DataFrame([r for r in records if r['protocol'] == protocol])
    reference = rows.loc[rows.candidate.eq('reference')].set_index('year').sort_index()
    eligible = ['reference']
    for name in SPECS[1:]:
        c = rows.loc[rows.candidate.eq(name)].set_index('year').sort_index()
        if (len(c) != 2 or len(reference) != 2 or set(c.index) != set(FOLDS)):
            raise ValueError('Complete matched folds required')
        if (c.average_precision.mean() > reference.average_precision.mean()
                and c.daily_budget_recall.mean() >= reference.daily_budget_recall.mean()
                and (c.average_precision/reference.average_precision >= .9).all()):
            eligible.append(name)
    return max(eligible, key=lambda name:float(rows.loc[rows.candidate.eq(name), 'average_precision'].mean()))


def reliability(frame, probability):
    # Fixed probability bins, rather than boundaries learned from the evaluation outcomes.
    bins = np.array([0, .0001, .0003, .001, .003, .01, .03, .1, 1.000001])
    f = pd.DataFrame({'p':probability, 'y':frame.ignition.to_numpy(), 'bin':np.digitize(probability, bins)-1})
    return f.groupby('bin').agg(rows=('y','size'), positives=('y','sum'), mean_probability=('p','mean'), event_rate=('y','mean')).reset_index()


def run(workspace, output, cache):
    if output.exists() or cache.exists():
        raise FileExistsError('Use new output/cache versions')
    data = workspace/'data/processed/ignition_weather_v2_development'
    manifest, contract = checked_sources(data)
    event_path = workspace/'team_repository/data/interim/ontario_fire_region_nfdb_ignitions_2010_2019.csv'
    columns = KEYS+['cause','fire_type','is_prescribed']
    events = pd.concat([c.loc[c.ignition_date.lt('2018')] for c in pd.read_csv(event_path, usecols=columns, chunksize=2000)], ignore_index=True)
    selector = workspace/'reports/week_2_development_2026-10-15/ignition_spatial_partition_v1.csv'
    mapping = inner_spatial_roles(pd.read_csv(selector)).set_index('grid_id').inner_role
    protected = frozen_artifacts(workspace)
    output.mkdir(parents=True);cache.mkdir(parents=True)
    save_json(output/'protocol.json', {'registered_before_fitting':True, 'created_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),
        'target':'wildfire_explicit_PB_excluded_v1; H and unknown retained; all target history rebuilt',
        'feature_cutoff':'row t contains observations t-1; windows never exceed t-1; absent season days remain missing',
        'candidates':list(SPECS), 'folds':list(FOLDS), 'negative_sample_percent':1, 'all_positives_retained':True,
        'calibration':2016, 'diagnostic':2017, 'capacity':.01, 'original_final_records_used':False,
        'acceptance':'Higher mean selection AP, no lower mean capacity recall, no fold AP below 90% reference; confirmation requires higher AP and recall, neither Brier nor log loss worse. Development only; no automatic promotion.',
        'sources':{'manifest':digest(data/'manifest.json'),'event_source':digest(event_path),'selector':digest(selector)},
        'code_sha256':digest(Path(__file__)), 'protected_before':protected})
    save_json(output/'fresh_evaluation_reservation.json', {'registered_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),
        'period':['2027-05-01','2027-10-31'],'scope':'future 10 km Ontario fire-season target under the new policy',
        'labels_accessed':False,'features_or_outcomes_available':False,'protocol':'Freeze candidate, calibration and target/source contracts before label access; compare all-cell temporal and existing spatial-role subgroups at fixed 1% daily budget. Do not tune after scoring. No fresh generalization claim until completed.',
        'source_availability':'Future source vintages, reporting completeness and actual availability must be verified; not an acquired evaluation set.'})
    parts, counts, labels = [], [], []
    for year in range(2010, 2018):
        frame, changes = build_year(data, year, mapping, events, contract['temporal_candidate_predictors'])
        frame.to_parquet(cache/f'{year}.parquet', index=False)
        labels.append({'year':year,'rows':len(frame),'positive_cell_days':int(frame.ignition.sum()),'changed_labels':changes})
        for role, group in frame.groupby('inner_role'):
            counts.append({'year':year,'inner_role':role,'rows':len(group),'positives':int(group.ignition.sum())})
        if year <= 2015:
            parts.append(frame.loc[frame.ignition.eq(1) | frame._bucket.lt(1)])
        print('prepared year',year,'target changes',changes,flush=True)
    sample = pd.concat(parts, ignore_index=True);population = pd.DataFrame(counts)
    save_json(output/'target_audit.json', {'years':labels,'excluded_event_records':len(events)-len(retained_events(events)),
        'unknown_cause_records_retained':int(retained_events(events).cause.fillna('U').isin(['U','']).sum()),
        'target_source_sha256':digest(event_path),'input_panel_labels_reconciled_to_retained_events':True})
    records=[]
    for year in FOLDS:
        validation=pd.read_parquet(cache/f'{year}.parquet')
        for protocol in PROTOCOLS:
            val=validation if protocol=='temporal' else validation.loc[validation.inner_role.eq('inner_validation')]
            for spec in SPECS:
                bundle=train_bundle(sample,population,year,protocol,spec,contract)
                result,_,_=evaluate(bundle,val)
                result.update(year=year,protocol=protocol,candidate=spec)
                records.append(result);save_json(output/'rolling_results.json',records)
                print('rolling',year,protocol,spec,result['average_precision'],result['hits'],flush=True)
    selected={p:select_spec(records,p) for p in PROTOCOLS}
    save_json(output/'selection_freeze.json', {'selected':selected,'frozen_before_2017_scoring':True})
    calibration=pd.read_parquet(cache/'2016.parquet');confirmation=pd.read_parquet(cache/'2017.parquet')
    rows=[];uncertainty={};gates={}
    for protocol in PROTOCOLS:
        cal=calibration if protocol=='temporal' else calibration.loc[calibration.inner_role.eq('inner_training')]
        val=confirmation if protocol=='temporal' else confirmation.loc[confirmation.inner_role.eq('inner_validation')]
        budgets={};results={}
        for spec in SPECS:
            bundle=train_bundle(sample,population,2016,protocol,spec,contract)
            raw=predict_bundle(bundle,cal[bundle['features']])
            bundle['calibrator']=fit_calibration(cal.ignition.to_numpy(),raw)
            result,budget,probability=evaluate(bundle,val)
            path=cache/f'{protocol}_{spec}.joblib';joblib.dump(bundle,path,compress=3)
            reloaded=joblib.load(path)
            np.testing.assert_allclose(predict_bundle(reloaded,val.iloc[:100][bundle['features']]),predict_bundle(bundle,val.iloc[:100][bundle['features']]),rtol=1e-12)
            result.update(protocol=protocol,candidate=spec,model_sha256=digest(path),save_load_parity=True)
            rows.append(result);results[spec]=result;budgets[spec]=budget
            budget.to_csv(output/f'{protocol}_{spec}_daily.csv',index=False)
            reliability(val,probability).to_csv(output/f'{protocol}_{spec}_reliability.csv',index=False)
            print('confirm',protocol,spec,result['average_precision'],result['hits'],flush=True)
        uncertainty[protocol]={s:paired_recall_interval(budgets['reference'],budgets[s]) for s in SPECS[1:]}
        reference=results['reference'];candidate=results[selected[protocol]]
        gates[protocol]=bool(selected[protocol]!='reference' and candidate['average_precision']>reference['average_precision']
            and candidate['daily_budget_recall']>reference['daily_budget_recall'] and candidate['brier']<=reference['brier']
            and candidate['log_loss']<=reference['log_loss'])
    if frozen_artifacts(workspace)!=protected:
        raise RuntimeError('Earlier scientific artifacts changed')
    result={'results':rows,'paired_recall_intervals':uncertainty,'selected':selected,'development_gates_pass':gates,
        'promoted':False,'promotion_reason':'No untouched evaluation has been scored; serving defaults unchanged regardless of development result.',
        'protected_artifacts_unchanged':True,'scope':'Previously exposed 2017 development diagnostics; new target differs slightly from old benchmark'}
    save_json(output/'results.json',result)
    save_json(output/'cache_manifest.json', {p.name:{'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(cache.iterdir()) if p.is_file()})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--cache-dir',type=Path,required=True)
    a=p.parse_args()
    with threadpool_limits(limits=4):
        run(a.workspace.resolve(),a.output_dir.resolve(),a.cache_dir.resolve())
