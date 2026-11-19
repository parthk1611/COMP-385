"""Post-hoc development diagnosis only: cached predictions, no fitting or new inputs."""
import csv
from collections import Counter, defaultdict
import argparse
import sys
import json
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.ignition.common import DEFAULT_CACHE, PARAMS, load_data, load_predictions, prepare_output
from scripts.ignition_modeling.data import year_slice
WINDOWS=ROOT/'artifacts/ignition_modeling/hgb_lightning_windows'
BOTH=ROOT/'artifacts/ignition_modeling/hgb_lightning'
BASE=ROOT/'artifacts/ignition_modeling/hgb_coordinates'
EVENTS=ROOT/'data/interim/ontario_fire_region_nfdb_ignitions_2010_2019.csv'
MODELS=('baseline','24h_only','7d_only','both_windows')
GROUPS=('all_positives','natural_only','human_only','mixed_natural_human','unknown_involved','natural_containing','human_containing')
STATES=('all','24h_and_7d','7d_only','neither','coverage_unknown','any_7d')
BITS={'N':1,'H':2,'U':4}
PARTITION={1:'natural_only',2:'human_only',3:'mixed_natural_human',4:'unknown_involved',5:'unknown_involved',6:'unknown_involved',7:'unknown_involved'}


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def exposure_state(values):
    known=np.isfinite(values).all(axis=1)
    assert not np.isinf(values).any() and not np.any(values<0)
    assert np.all(values[known,1]+1e-14>=values[known,0])
    assert not np.any(known&(values[:,0]>0)&(values[:,1]==0))
    states=np.full(len(values),'coverage_unknown',dtype='<U20')
    states[known&(values[:,0]>0)]='24h_and_7d'
    states[known&(values[:,0]==0)&(values[:,1]>0)]='7d_only'
    states[known&(values[:,1]==0)]='neither'
    return states


def exposure_summary(period,group,states):
    counts = states if isinstance(states, Counter) else Counter(states)
    n = sum(counts.values())
    counts = {state: counts[state] for state in STATES[1:5]}
    covered=n-counts['coverage_unknown']
    detected24=counts['24h_and_7d']
    detected7=detected24+counts['7d_only']
    return dict(period=period,group=group,n_cell_days=n,n_covered=covered,n_unknown_coverage=counts['coverage_unknown'],
                detected_24h=detected24,detected_7d=detected7,seven_day_only=counts['7d_only'],neither=counts['neither'],
                detected_fraction_24h=detected24/n if n else None,detected_fraction_7d=detected7/n if n else None,
                detected_fraction_24h_among_covered=detected24/covered if covered else None,
                detected_fraction_7d_among_covered=detected7/covered if covered else None)


def group_mask(name,masks):
    if name=='all_positives': return np.ones(len(masks),dtype=bool)
    if name=='natural_containing': return (masks&1)!=0
    if name=='human_containing': return (masks&2)!=0
    return np.array([PARTITION[int(mask)]==name for mask in masks])


def state_mask(name,states):
    if name=='all': return np.ones(len(states),dtype=bool)
    if name=='any_7d': return (states=='24h_and_7d')|(states=='7d_only')
    return states==name


def ranking(scores,priorities):
    order=np.lexsort((priorities,-scores))
    actual=np.empty(len(scores),dtype=np.int32)
    actual[order]=np.arange(1,len(scores)+1)
    ordered=scores[order]
    first=np.flatnonzero(np.r_[True,ordered[1:]!=ordered[:-1]])
    stop=np.r_[first[1:],len(scores)]
    lower=np.empty(len(scores),dtype=np.int32)
    upper=np.empty(len(scores),dtype=np.int32)
    lower[order]=np.repeat(first+1,stop-first)
    upper[order]=np.repeat(stop,stop-first)
    return actual,lower,upper,(lower.astype(float)+upper)/2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--baseline-predictions', type=Path, default=BASE)
    parser.add_argument('--window-predictions', type=Path, default=WINDOWS,
                        help='Directory containing 24h_only and 7d_only saved folds')
    parser.add_argument('--both-predictions', type=Path, default=BOTH)
    parser.add_argument('--features', type=Path, default=BOTH / 'lightning_features/ignition-weather-v2-cell-centres-lightning-cg-v1/features.npy',
                        help='Two-column 24h/7d features aligned to the 2010--2016 development prefix')
    parser.add_argument('--events', type=Path, default=EVENTS)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/ignition_modeling/reruns/lightning_diagnosis')
    args = parser.parse_args(argv)
    _, y, manifest, ids, _ = load_data(args.cache)
    features = np.load(args.features, mmap_mode='r')
    development = year_slice(manifest, 2010, 2016)
    if development.start != 0 or features.shape != (development.stop, 2):
        raise ValueError("Lightning features must align with the complete 2010--2016 cache prefix")
    prepare_output(args.output)
    OUT = args.output
    with (ROOT/'data/interim/ontario_fire_region_10km_grid.csv').open() as stream: grid=list(csv.DictReader(stream))
    names=[row['grid_id'] for row in grid]
    assert len(names)==len(set(names))==9673
    lookup={key:index for index,key in enumerate(names)}
    priority=np.argsort(np.argsort(np.asarray(names)))
    events=defaultdict(Counter)
    event_codes=Counter()
    with args.events.open(newline='') as stream:
        for event in csv.DictReader(stream):
            if not 2012<=int(event['year'])<=2016: continue
            day=event['ignition_date']
            assert int(day[:4])==int(event['year']) and day in manifest['date_slices']
            assert event['grid_id'] in lookup
            cause=event['cause'].strip().upper() or 'U'
            assert cause in BITS,repr(cause)
            events[(day,event['grid_id'])][cause]+=1
            event_codes[cause]+=1
    configuration=dict(analysis='cause-aware-lightning-diagnosis-v1',validation_years=list(range(2012,2017)),
                       cause_codes={'N':'natural','H':'human','U':'unknown'},
                       disjoint_partition={'natural_only':'N and no H/U','human_only':'H and no N/U',
                                           'mixed_natural_human':'N and H, no U','unknown_involved':'any U, including N+U/H+U/N+H+U'},
                       overlapping_sensitivity_groups='natural_containing and human_containing include any N/H and can overlap; not summed as a partition',
                       exposure='Cached CG density >0; finite zero is detector-zero, not no physical flash. Unknown coverage kept separate. Windows end one hour before local midnight.',
                       ranking='All9673cells per local day; descending score, ascending immutable grid_id ties. Midrank=mean of minimum/maximum rank within equal-score tie.',
                       capture='Top97/194/484 cells per day. Cohort recall is captured cohort positives / cohort positives; no positive-only precision or reranking.',
                       scope='Existing2012--2016 validation predictions only; no fits, no source downloads, no2017--2019 scoring, no cause codes as model inputs',
                       source_events=str(args.events), source_feature_file=str(args.features))
    dump(OUT/'configuration.json',configuration)
    collected=defaultdict(list)
    background=[]
    annual_counts=[]
    for year in range(2012,2017):
        slices=[(day,start,stop) for day,(start,stop) in manifest['date_slices'].items() if int(day[:4])==year]
        assert len(slices) == 184 and slices == sorted(slices)
        assert all(left[2] == right[1] for left, right in zip(slices, slices[1:]))
        first,last=slices[0][1],slices[-1][2]
        probabilities={}
        directories={'baseline':args.baseline_predictions,'both_windows':args.both_predictions,
                     '24h_only':args.window_predictions/'24h_only','7d_only':args.window_predictions/'7d_only'}
        for model in MODELS:
            probabilities[model] = load_predictions(directories[model], PARAMS, year, y[first:last])
        negative_states=Counter()
        npos=0
        for day,start,stop in slices:
            day_ids=ids[start:stop]
            assert stop-start==9673 and np.array_equal(np.sort(day_ids),np.arange(9673))
            cause_masks=np.zeros(9673,dtype=np.uint8)
            record_counts=np.zeros(9673,dtype=np.int32)
            position_by_grid=np.empty(9673,dtype=np.int32)
            position_by_grid[day_ids]=np.arange(9673)
            for grid_index,grid_name in enumerate(names):
                source=events.get((day,grid_name))
                if source:
                    pos=position_by_grid[grid_index]
                    cause_masks[pos]=sum(BITS[code] for code in source)
                    record_counts[pos]=sum(source.values())
            labels=y[start:stop].astype(bool)
            assert np.array_equal(cause_masks>0,labels),day
            positive=np.flatnonzero(labels)
            npos+=len(positive)
            state=exposure_state(features[start:stop])
            values, frequencies = np.unique(state[~labels], return_counts=True)
            negative_states.update(dict(zip(values, map(int, frequencies))))
            collected['row_index'].append(start+positive)
            collected['grid_code'].append(day_ids[positive].copy())
            collected['date'].append(np.full(len(positive),day))
            collected['year'].append(np.full(len(positive),year,dtype=np.int16))
            collected['cause_mask'].append(cause_masks[positive])
            collected['source_event_count'].append(record_counts[positive])
            collected['lightning'].append(features[start:stop][positive].copy())
            collected['exposure_state'].append(state[positive])
            for model in MODELS:
                p=probabilities[model][start-first:stop-first]
                rank,lower,upper,mid=ranking(p,priority[day_ids])
                for key,value in (('score',p),('rank',rank),('rank_min',lower),('rank_max',upper),('midrank',mid)):
                    collected[f'{model}_{key}'].append(value[positive].copy())
        background.append(exposure_summary(str(year),'negative_cell_days',negative_states))
        annual_counts.append(dict(year=year,dates=len(slices),rows=last-first,positive_cell_days=npos,negative_cell_days=sum(negative_states.values())))
        print(f'Cause/exposure/global ranks {year}: {npos} positive cell-days; all source labels reproduce',flush=True)
    data={key:np.concatenate(values,axis=0) for key,values in collected.items()}
    assert len(data['row_index'])==3384 and len(set(data['row_index'].tolist()))==3384
    assert len(events)==3384 and sum(event_codes.values())==int(data['source_event_count'].sum())
    np.savez_compressed(OUT/'positive_cell_days.npz',**data)
    positive_rows=[]
    for i in range(len(data['row_index'])):
        mask=int(data['cause_mask'][i])
        row=dict(row_index=int(data['row_index'][i]),date=str(data['date'][i]),year=int(data['year'][i]),grid_id=names[int(data['grid_code'][i])],
                 cause_codes='|'.join(code for code in ('N','H','U') if mask&BITS[code]),cause_mask=mask,cause_partition=PARTITION[mask],
                 source_event_count=int(data['source_event_count'][i]),lightning_24h=float(data['lightning'][i,0]),lightning_7d=float(data['lightning'][i,1]),
                 exposure_state=str(data['exposure_state'][i]))
        for model in MODELS:
            for key in ('score','rank','rank_min','rank_max','midrank'):
                value=data[f'{model}_{key}'][i]
                row[f'{model}_{key}']=int(value) if key.startswith('rank') else float(value)
        positive_rows.append(row)
    write_csv(OUT/'positive_cell_days.csv',positive_rows)
    exposure_rows=list(background)
    ranking_rows=[]
    counts=[]
    periods=[str(year) for year in range(2012,2017)]+['pooled']
    for period in periods:
        period_mask=np.ones(3384,dtype=bool) if period=='pooled' else data['year']==int(period)
        for mask in range(1,8):
            counts.append(dict(period=period,cause_mask=mask,cause_codes='|'.join(code for code in ('N','H','U') if mask&BITS[code]),
                               cause_partition=PARTITION[mask],positive_cell_days=int(np.count_nonzero(period_mask&(data['cause_mask']==mask)))))
        for group in GROUPS:
            group_selection=period_mask&group_mask(group,data['cause_mask'])
            exposure_rows.append(exposure_summary(period,group,data['exposure_state'][group_selection]))
            for state in STATES:
                cohort=group_selection&state_mask(state,data['exposure_state'])
                n=int(cohort.sum())
                if not n: continue
                base_mid=data['baseline_midrank'][cohort]
                for model in MODELS:
                    mid=data[f'{model}_midrank'][cohort]
                    rank=data[f'{model}_rank'][cohort]
                    lower=data[f'{model}_rank_min'][cohort]
                    upper=data[f'{model}_rank_max'][cohort]
                    gain=base_mid-mid
                    row=dict(period=period,group=group,exposure_state=state,model=model,n_positive=n,
                             mean_midrank=float(mid.mean()),median_midrank=float(np.median(mid)),
                             mean_rank_gain_vs_baseline=float(gain.mean()),median_rank_gain_vs_baseline=float(np.median(gain)),
                             ranks_better=int(np.count_nonzero(gain>0)),ranks_worse=int(np.count_nonzero(gain<0)),ranks_tied=int(np.count_nonzero(gain==0)))
                    for percent,k in ((1,97),(2,194),(5,484)):
                        expected=np.clip((k-lower+1)/(upper-lower+1),0,1)
                        row[f'captured_top_{percent}pct']=int(np.count_nonzero(rank<=k))
                        row[f'recall_top_{percent}pct']=float(np.mean(rank<=k))
                        row[f'expected_captured_top_{percent}pct']=float(expected.sum())
                        row[f'expected_recall_top_{percent}pct']=float(expected.mean())
                    ranking_rows.append(row)
    assert len(ranking_rows) == 744
    total_negative=sum(row['n_cell_days'] for row in background)
    pooled_background=dict(period='pooled',group='negative_cell_days',n_cell_days=total_negative,
                           n_covered=sum(row['n_covered'] for row in background),n_unknown_coverage=sum(row['n_unknown_coverage'] for row in background),
                           detected_24h=sum(row['detected_24h'] for row in background),detected_7d=sum(row['detected_7d'] for row in background),
                           seven_day_only=sum(row['seven_day_only'] for row in background),neither=sum(row['neither'] for row in background))
    for suffix in ('24h','7d'):
        pooled_background[f'detected_fraction_{suffix}']=pooled_background[f'detected_{suffix}']/total_negative
        pooled_background[f'detected_fraction_{suffix}_among_covered']=pooled_background[f'detected_{suffix}']/pooled_background['n_covered']
    exposure_rows.append(pooled_background)
    assert len(exposure_rows) == 48
    for period in periods:
        partitions=[row for row in exposure_rows if row['period']==period and row['group'] in ('natural_only','human_only','mixed_natural_human','unknown_involved')]
        all_positive=next(row for row in exposure_rows if row['period']==period and row['group']=='all_positives')
        assert sum(row['n_cell_days'] for row in partitions)==all_positive['n_cell_days']
    output=dict(status='complete',validation_years=list(range(2012,2017)),validation_cell_days=sum(row['rows'] for row in annual_counts),
                positive_cell_days=3384,source_event_records=sum(event_codes.values()),source_event_cause_counts=dict(event_codes),annual_counts=annual_counts,
                cause_set_counts=counts,exposure=exposure_rows,ranking=ranking_rows,models=list(MODELS),
                limitations=['Post-hoc cause codes describe outcomes; never predictor inputs.',
                             'Nonzero density is native-grid-supported exposure, not a matched causative flash or exact within-cell strike.',
                             'No pre-issue exposure does not exclude target-day lightning, incomplete detection, spatial/date errors or source outages.',
                             'Unknown/mixed causes retained; natural_containing and human_containing overlap and are not an additive partition.',
                             'Ranks are global daily ranks; positive-only precision/AP would not answer the question and are not reported.',
                             'Pooled and per-year descriptive results reuse development data; no causal explanation or significance claim.'],
                model_fits=0,new_model_predictions=0,reserved_year_scores=0)
    dump(OUT/'results.json',output)
    write_csv(OUT/'exposure_counts.csv',exposure_rows)
    write_csv(OUT/'cause_set_counts.csv',counts)
    write_csv(OUT/'ranking_comparison.csv',ranking_rows)
    print(json.dumps({'positive_cell_days':3384,'source_event_cause_counts':dict(event_codes),
                      'pooled_exposure':[row for row in exposure_rows if row['period']=='pooled'],
                      'pooled_rank_comparison':[row for row in ranking_rows if row['period']=='pooled' and row['group'] in ('natural_only','human_only') and row['exposure_state'] in ('all','24h_and_7d','neither') and row['model'] in ('baseline','24h_only')]},indent=2))


if __name__=='__main__': main()
