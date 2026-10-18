"""Frozen historical refit, disjoint calibration, and one-time retrospective evaluation."""
from __future__ import annotations
import argparse
from collections import deque
from datetime import timedelta
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import minimize
from scipy.special import expit, logit
from threadpoolctl import threadpool_limits
from scripts import prepare_historical_weather_v2 as weather
from scripts.ignition_comparison import candidates, corrected_weights, daily_budget, metrics, predict_bundle, sample_mask

ROOT=weather.ROOT
REPORT=ROOT/'reports/week_5_prototype_2026-10-16'
DATA=ROOT/'data/processed/ignition_weather_v2_reserved'
MODELS=ROOT/'data/processed/ignition_models_week5_v1'
DEV=ROOT/'data/processed/ignition_weather_v2_development'
ORIGINAL=ROOT/'data/processed/ignition_evaluation_v1'
WEEK2=ROOT/'reports/week_2_development_2026-10-15'
PROTOCOLS=('temporal','spatial')


def validate_role(dates,role):
    limits={'training':(2010,2017),'calibration':(2018,2018),'final_test':(2019,2019)}
    if role not in limits or not dates.str[:4].astype(int).between(*limits[role]).all():
        raise ValueError('Wrong year/role; no reserved-year refit is allowed')


def configuration():
    plan=json.loads((REPORT/'protocol_freeze.json').read_text())
    for path,expected in plan['frozen_files'].items():
        if weather.digest(ROOT/path)!=expected:raise ValueError(f'Frozen dependency changed: {path}')
    return plan


def require_final_freeze(report=REPORT):
    freeze=json.loads((report/'final_evaluation_freeze.json').read_text())
    for record in freeze['artifacts']:
        if weather.digest(Path(record['path']))!=record['sha256']:raise ValueError('Frozen calibration artifact changed')
    return freeze


def checked_partition(folder,role,columns=None):
    manifest=json.loads((folder/'manifest.json').read_text());record=manifest['files'][role]
    path=folder/f'{role}.parquet'
    if str(path)!=record['path'] or weather.digest(path)!=record['sha256']:raise ValueError('Partition hash/path changed')
    return pd.read_parquet(path,columns=columns)


def join_reserved(original,new_weather,role):
    keys=['grid_id','ignition_date'];labels=['ignition','ignition_count','large_fire_200ha']
    validate_role(original.ignition_date,role)
    if original.duplicated(keys).any() or new_weather.duplicated(keys).any():raise ValueError('Duplicate cell/date')
    prior=(pd.to_datetime(new_weather.ignition_date)-pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    if not new_weather.cwfis_observation_date.eq(prior).all():raise ValueError('Weather is not exact prior day')
    old=[c for c in original if c.startswith('cwfis_')]
    if not set(old).issubset(new_weather):raise ValueError('Weather interface incomplete')
    result=original.drop(columns=old).merge(new_weather,on=keys,how='left',sort=False,validate='one_to_one',indicator=True)
    if not result['_merge'].eq('both').all() or not result[keys+labels].equals(original[keys+labels].reset_index(drop=True)):raise ValueError('Incomplete join or changed target/order')
    result=result.drop(columns='_merge');result['feature_set_version']='ignition-feature-candidate-v2-daily-stations'
    return result


def prepare_reserved(role):
    configuration()
    if role=='final_test':require_final_freeze()
    year={'calibration':2018,'final_test':2019}[role];DATA.mkdir(exist_ok=True)
    path=DATA/f'{role}.parquet';record_path=DATA/f'{role}_manifest.json'
    if path.exists() or record_path.exists():raise FileExistsError('Reserved build already exists')
    source=ROOT/'team_repository/data/raw/cwfis/cwfis_fwi2010sv3.0_ll.csv.bz2'
    source_manifest=json.loads((source.parent/'manifest.json').read_text())
    if weather.digest(source)!=source_manifest['expected_sha256']:raise ValueError('CWFIS raw hash changed')
    grid=pd.read_csv(ROOT/'team_repository/data/interim/ontario_fire_region_10km_grid.csv').sort_values('grid_id').reset_index(drop=True)
    dates=pd.date_range(f'{year}-05-01',f'{year}-10-31')
    required={(d-pd.Timedelta(days=lag)).date().isoformat() for d in dates for lag in range(1,8)}
    obs,profile=weather.load_observations(source,required,grid)
    groups=dict(tuple(obs.groupby('observation_date',sort=False)));empty=obs.iloc[:0]
    frames=[];window=deque(maxlen=7);previous=dates[0].date()-timedelta(days=8)
    for issue in dates:
        end=issue.date()-timedelta(days=1)
        while previous<end:
            previous+=timedelta(days=1);frame,_=weather.daily_features(grid,groups.get(previous.isoformat(),empty))
            window.append((previous,frame.cwfis_precip_mm.to_numpy()))
        frame=frame.copy();rain,coverage=weather.prior_week_rain(window,issue.date())
        frame['cwfis_precip_7d_mm']=rain;frame['cwfis_precip_7d_coverage_days']=coverage
        frame['ignition_date']=issue.date().isoformat();frame['cwfis_observation_date']=end.isoformat()
        frame['weather_feature_version']='historical-weather-development-v2';frame['cwfis_source_id']='cwfis_fwi_2010s_v3_ll';frame['cwfis_maximum_station_distance_km']=200.
        frames.append(frame)
    original=checked_partition(ORIGINAL,role);joined=join_reserved(original,pd.concat(frames,ignore_index=True),role)
    joined.to_parquet(path,index=False)
    record={'path':str(path),'sha256':weather.digest(path),'bytes':path.stat().st_size,'rows':len(joined),'year':year,'role':role,'original_sha256':weather.digest(ORIGINAL/f'{role}.parquet'),'target_keys_labels_unchanged':True,'weather_missing_fraction':float(joined.cwfis_missing.mean()),'weather_method':'Frozen daily_features/prior_week_rain from Week4; 4 stations, 200km; no new tuning','source_profile':profile,'code_sha256':weather.digest(Path(__file__))}
    weather.save(record_path,record)
    manifests={p.stem.removesuffix('_manifest'):json.loads(p.read_text()) for p in DATA.glob('*_manifest.json')}
    weather.save(DATA/'manifest.json',{'files':manifests,'source_contract_sha256':weather.digest(DEV/'predictor_contract.json')})
    print('prepared',role,len(joined),flush=True)


def probability_logits(probability):
    p=np.asarray(probability,dtype=float)
    if not np.isfinite(p).all() or ((p<0)|(p>1)).any():raise ValueError('Invalid probability')
    return logit(np.clip(p,1e-12,1-1e-12))


def fit_calibration(y,probability):
    x=probability_logits(probability);y=np.asarray(y,dtype=float)
    if x.shape!=y.shape or not np.isin(y,[0,1]).all() or len(np.unique(y))!=2:raise ValueError('Calibration needs both binary classes')
    def objective(parameters):
        a,b=parameters;z=a*x+b;residual=expit(z)-y
        return np.mean(np.logaddexp(0,z)-y*z),np.array([np.mean(residual*x),np.mean(residual)])
    fitted=minimize(objective,[1.,0.],method='L-BFGS-B',jac=True,bounds=[(1e-6,20),(-50,50)],options={'ftol':1e-14,'gtol':1e-10,'maxiter':1000})
    if not fitted.success:raise RuntimeError('Calibration did not converge: '+fitted.message)
    return {'method':'positive-slope logistic recalibration of clipped raw logit; natural prevalence; no smoothing/weights','slope':float(fitted.x[0]),'intercept':float(fitted.x[1]),'clip':1e-12,'optimizer_success':bool(fitted.success),'bounds':[[1e-6,20],[-50,50]]}


def apply_calibration(calibrator,probability):
    return expit(calibrator['slope']*probability_logits(probability)+calibrator['intercept'])


def read_refit(features,protocol):
    manifest=json.loads((DEV/'manifest.json').read_text());parts=[];rows=positives=0
    columns=['grid_id','ignition_date','ignition','spatial_role']+features
    for role in ('training','validation'):
        path=DEV/f'{role}.parquet'
        if weather.digest(path)!=manifest['files'][role]['sha256']:raise ValueError('Development data changed')
        for batch in pq.ParquetFile(path).iter_batches(batch_size=200000,columns=columns):
            frame=batch.to_pandas();validate_role(frame.ignition_date,'training')
            if protocol=='spatial':frame=frame.loc[frame.spatial_role.eq('spatial_development')]
            rows+=len(frame);positives+=int(frame.ignition.sum());parts.append(frame.loc[sample_mask(frame)])
    return pd.concat(parts,ignore_index=True),rows,positives


def calibrate():
    plan=configuration()
    if MODELS.exists():raise FileExistsError('Final refit/calibration already started; use explicit new version')
    if not (DATA/'calibration_manifest.json').exists():prepare_reserved('calibration')
    calibration=checked_partition(DATA,'calibration');validate_role(calibration.ignition_date,'calibration')
    contract=json.loads((DEV/'predictor_contract.json').read_text());MODELS.mkdir()
    records=[];summaries=[]
    with threadpool_limits(limits=4):
        for protocol in PROTOCOLS:
            features=contract['temporal_candidate_predictors' if protocol=='temporal' else 'spatial_candidate_predictors']
            training,rows,positives=read_refit(features,protocol);y=training.ignition.to_numpy();weights=corrected_weights(y,rows,positives)
            model=candidates()['lightgbm']
            if model.get_params(deep=False)!=plan['lightgbm_settings']:raise ValueError('Chosen model settings changed')
            model.fit(training[features].astype('float32'),y,sample_weight=weights)
            val=calibration if protocol=='temporal' else calibration.loc[calibration.spatial_role.eq('spatial_development')]
            raw_bundle={'model':model,'features':features,'protocol':protocol,'feature_contract_sha256':weather.digest(DEV/'predictor_contract.json'),'mode':'historical_refit_2010_2017'}
            raw=predict_bundle(raw_bundle,val[features].astype('float32'));calibrator=fit_calibration(val.ignition.to_numpy(),raw)
            bundle={**raw_bundle,'calibrator':calibrator,'calibration_year':2018,'training_prior':positives/rows,'protocol_freeze_sha256':weather.digest(REPORT/'protocol_freeze.json')}
            path=MODELS/f'{protocol}_lightgbm_calibrated.joblib';joblib.dump(bundle,path,compress=3)
            loaded=joblib.load(path);pred=apply_calibration(loaded['calibrator'],predict_bundle(loaded,val[features].astype('float32')))
            np.testing.assert_allclose(pred,apply_calibration(calibrator,raw),atol=1e-10,rtol=1e-6)
            records.append({'path':str(path),'sha256':weather.digest(path),'save_load_parity':True})
            summaries.append({'protocol':protocol,'refit_rows':rows,'refit_positives':positives,'sampled_fitting_rows':len(training),'calibrator':calibrator,'calibration_fit_diagnostics_not_unbiased_validation':{'raw':metrics(val.ignition.to_numpy(),raw),'calibrated':metrics(val.ignition.to_numpy(),pred)},'feature_count':len(features)})
            print('refit/calibrated',protocol,'calibration rows',len(val),flush=True)
    weather.save(REPORT/'calibration_report.json',{'results':summaries,'models':records,'final_test_opened':False,'code_sha256':weather.digest(Path(__file__))})
    artifacts=records+[{'path':str(REPORT/'calibration_report.json'),'sha256':weather.digest(REPORT/'calibration_report.json')},{'path':str(REPORT/'protocol_freeze.json'),'sha256':weather.digest(REPORT/'protocol_freeze.json')}]
    weather.save(REPORT/'final_evaluation_freeze.json',{'artifacts':artifacts,'alert_policy':plan['alert_policy'],'selection_complete_before_final_content':True,'calibration_fit_on':2018,'no_post_final_tuning':True})


def diagnostic_bins(y,p):
    edges=np.array([0,1e-5,1e-4,5e-4,.001,.005,.01,.05,.1,.5,1.000001]);rows=[]
    indices=np.searchsorted(edges,p,side='right')-1
    for i in range(len(edges)-1):
        mask=indices==i
        rows.append({'lower':float(edges[i]),'upper':float(edges[i+1]),'count':int(mask.sum()),'positives':int(y[mask].sum()),'mean_probability':float(p[mask].mean()) if mask.any() else None,'observed_frequency':float(y[mask].mean()) if mask.any() else None})
    return rows


def evaluate():
    configuration();require_final_freeze()
    if (REPORT/'final_evaluation_started.json').exists():raise FileExistsError('One-time final evaluation already started; inspect retained artifacts rather than retuning/rerunning')
    weather.save(REPORT/'final_evaluation_started.json',{'protocol_freeze_sha256':weather.digest(REPORT/'protocol_freeze.json'),'started_utc':pd.Timestamp.now(tz='UTC').isoformat(),'code_sha256':weather.digest(Path(__file__))})
    if not (DATA/'final_test_manifest.json').exists():prepare_reserved('final_test')
    final=checked_partition(DATA,'final_test');validate_role(final.ignition_date,'final_test');results=[]
    with threadpool_limits(limits=4):
        for protocol in PROTOCOLS:
            bundle=joblib.load(MODELS/f'{protocol}_lightgbm_calibrated.joblib')
            frame=final if protocol=='temporal' else final.loc[final.spatial_role.eq('spatial_test')]
            raw=predict_bundle(bundle,frame[bundle['features']].astype('float32'));cal=apply_calibration(bundle['calibrator'],raw);y=frame.ignition.to_numpy()
            predictions=frame[['grid_id','ignition_date','ignition','cwfis_missing']].reset_index(drop=True).copy();predictions['raw_probability']=raw;predictions['probability']=cal
            predictions['mode']='retrospective_final_evaluation';predictions.to_parquet(MODELS/f'{protocol}_final_predictions.parquet',index=False)
            for variant,p in [('training_prior',np.full(len(frame),bundle['training_prior'])),('uncalibrated',raw),('calibrated',cal)]:
                record={'protocol':protocol,'variant':variant,**metrics(y,p),'bins':diagnostic_bins(y,p)}
                budget=daily_budget(frame,p);record.update(daily_budget_recall=float(budget.hits.sum()/budget.positives.sum()),daily_budget_precision=float(budget.hits.sum()/budget.alerts.sum()),false_alerts_per_1000=float((budget.alerts.sum()-budget.hits.sum())/len(frame)*1000))
                rng=np.random.default_rng(385);indices=rng.integers(0,len(budget),size=(1000,len(budget)));n=budget.hits.to_numpy()[indices].sum(axis=1);d=budget.positives.to_numpy()[indices].sum(axis=1);valid=d>0
                record['daily_bootstrap_recall_95pct']=np.quantile(n[valid]/d[valid],[.025,.975]).tolist();record['daily_bootstrap_undefined_replicates']=int((~valid).sum())
                record['weather_subgroups']={}
                for missing in (0,1):
                    mask=frame.cwfis_missing.eq(missing).to_numpy();record['weather_subgroups'][str(missing)]=metrics(y[mask],p[mask]) if len(np.unique(y[mask]))==2 else {'rows':int(mask.sum()),'positives':int(y[mask].sum()),'status':'class-sensitive metrics undefined'}
                budget.to_csv(REPORT/f'{protocol}_{variant}_final_daily_alerts.csv',index=False);results.append(record)
            # TreeSHAP contributions explain raw log odds, not calibrated probability.
            first_day=frame.ignition_date.min();daily=frame.loc[frame.ignition_date.eq(first_day)]
            contrib=bundle['model'].booster_.predict(daily[bundle['features']].astype('float32'),pred_contrib=True,num_threads=4)
            raw_margin=bundle['model'].booster_.predict(daily[bundle['features']].astype('float32'),raw_score=True,num_threads=4)
            np.testing.assert_allclose(contrib.sum(axis=1),raw_margin,rtol=1e-5,atol=1e-7)
            top=np.argsort(-np.abs(contrib[:,:-1]),axis=1)[:,:3];explanations=[]
            for i,row in enumerate(daily.itertuples()):
                explanations.append({'grid_id':row.grid_id,'ignition_date':row.ignition_date,'base_raw_log_odds':float(contrib[i,-1]),'raw_log_odds':float(raw_margin[i]),'top_factors':[{'feature':bundle['features'][j],'raw_log_odds_contribution':float(contrib[i,j])} for j in top[i]]})
            weather.save(MODELS/f'{protocol}_first_day_explanations.json',{'date':first_day,'scope':'Local TreeSHAP raw-log-odds attribution, not causal importance or calibrated probability change','additivity_checked':True,'rows':explanations})
            print('evaluated',protocol,len(frame),flush=True)
    weather.save(REPORT/'final_evaluation.json',{'results':results,'final_year':2019,'source':'corrected CWFIS research hindcast','prior_2019_eda_exposure':True,'model_selection_after_final':False,'operational_acceptance':False,'code_sha256':weather.digest(Path(__file__))})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['calibrate','evaluate']);args=parser.parse_args()
    if args.stage=='calibrate':calibrate()
    else:evaluate()
