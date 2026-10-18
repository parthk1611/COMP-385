"""Frozen within-season selected-source study; never substitutes historical/live inputs."""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from scripts.prepare_historical_weather_v2 import ROOT,digest,save
from scripts.ignition_comparison import candidates,sample_mask,corrected_weights,predict_bundle,metrics,daily_budget
from scripts.week5_ignition import fit_calibration,apply_calibration,diagnostic_bins
from scripts.build_ignition_map import HTML,map_payload

REPORT=ROOT/'reports/week_5_completion_2026-10-16'
SOURCE=ROOT/'data/processed/selected_2025_ignition_panel'
OUTPUT=ROOT/'data/processed/selected_2025_models_v1'


def select_dates(frame,bounds):
    if bounds[0]>bounds[1]:raise ValueError('Reversed study dates')
    return frame.loc[frame.ignition_date.between(*bounds)].copy()


def study_metrics(frame,p):
    y=frame.ignition.to_numpy();result={'rows':len(y),'positives':int(y.sum()),'prevalence':float(y.mean())}
    if len(np.unique(y))<2:return {**result,'status':'class-sensitive metrics undefined'}
    result.update(metrics(y,p));budget=daily_budget(frame,p)
    result.update(daily_budget_recall=float(budget.hits.sum()/budget.positives.sum()),daily_budget_precision=float(budget.hits.sum()/budget.alerts.sum()),hits=int(budget.hits.sum()),alerts=int(budget.alerts.sum()),bins=diagnostic_bins(y,p))
    return result


def fit_bundle(frame,features,settings):
    sampled=frame.loc[sample_mask(frame)];weights=corrected_weights(sampled.ignition.to_numpy(),len(frame),int(frame.ignition.sum()));model=candidates()['lightgbm']
    if model.get_params(deep=False)!=settings:raise ValueError('Frozen selected-source model settings changed')
    model.fit(sampled[features].astype('float32'),sampled.ignition.to_numpy(),sample_weight=weights)
    return {'model':model,'features':features,'mode':'selected2025_withinseason_research','training_prior':float(frame.ignition.mean()),'fitting_rows':len(sampled)}


def run():
    if OUTPUT.exists():raise FileExistsError('Selected study version already exists')
    plan=json.loads((REPORT/'completion_protocol.json').read_text())['selected_2025'];contract=json.loads((SOURCE/'predictor_contract.json').read_text());manifest=json.loads((SOURCE/'manifest.json').read_text())
    if digest(SOURCE/'manifest.json')!=plan['source_manifest_sha256'] or digest(SOURCE/'predictor_contract.json')!=plan['contract_sha256']:raise ValueError('Selected source contract changed')
    record=next(v for v in manifest['outputs'] if v['path'].endswith('cell_days.parquet'))
    if digest(Path(record['path']))!=record['sha256']:raise ValueError('Selected data changed')
    features=contract['predictors'];columns=['grid_id','ignition_date','reported_fire_start']+features
    selectors=pd.read_csv(ROOT/'reports/week_2_development_2026-10-15/ignition_spatial_partition_v1.csv').set_index('grid_id').spatial_role
    def read(role,protocol):
        bounds=plan[role];frame=pd.read_parquet(SOURCE/'cell_days.parquet',columns=columns,filters=[('ignition_date','>=',bounds[0]),('ignition_date','<=',bounds[1])]);frame['ignition']=frame.reported_fire_start.astype('int8')
        if frame.duplicated(['grid_id','ignition_date']).any() or not frame.ignition_date.between(*bounds).all():raise ValueError('Invalid selected study keys/role')
        assigned=frame.grid_id.map(selectors)
        if assigned.isna().any():raise ValueError('Unassigned selected-source geography')
        if protocol=='spatial':frame=frame.loc[assigned.eq('spatial_test' if role=='final_test' else 'spatial_development')].copy()
        return frame
    OUTPUT.mkdir();validation=[];calibration=[];models=[];statuses={}
    with threadpool_limits(limits=4):
        for protocol in ['temporal','spatial']:
            train=read('initial_training',protocol);val=read('validation',protocol)
            if train.ignition.sum()<plan['minimum_positives']['training']:raise ValueError('Insufficient selected-source training support')
            initial=fit_bundle(train,features,plan['lightgbm_settings']);p=predict_bundle(initial,val[features].astype('float32'))
            validation.append({'protocol':protocol,'training':{'rows':len(train),'positives':int(train.ignition.sum())},'validation':{'raw':study_metrics(val,p),'training_prior':study_metrics(val,np.full(len(val),initial['training_prior']))},'model_selection':'Family/settings fixed in completionprotocol before2025role reads; validation does not retune them'})
            final_train=read('final_refit',protocol);cal=read('calibration',protocol);bundle=fit_bundle(final_train,features,plan['lightgbm_settings']);raw=predict_bundle(bundle,cal[features].astype('float32'))
            if cal.ignition.sum()<plan['minimum_positives']['calibration']:
                statuses[protocol]='insufficient calibration positives; uncalibrated research only';bundle['calibrator']=None
            else:bundle['calibrator']=fit_calibration(cal.ignition.to_numpy(),raw);statuses[protocol]='within-season calibrated research, no cross-year/live qualification'
            bundle.update(contract_sha256=digest(SOURCE/'predictor_contract.json'),protocol=protocol,qualification=statuses[protocol])
            path=OUTPUT/f'{protocol}_selected2025.joblib';joblib.dump(bundle,path,compress=3);loaded=joblib.load(path)
            np.testing.assert_allclose(predict_bundle(loaded,cal[features].astype('float32')),raw,atol=1e-10,rtol=1e-6)
            models.append({'path':str(path),'sha256':digest(path),'save_load_parity':True})
            calibration.append({'protocol':protocol,'refit_rows':len(final_train),'refit_positives':int(final_train.ignition.sum()),'fitting_rows':bundle['fitting_rows'],'rows':len(cal),'positives':int(cal.ignition.sum()),'calibrator':bundle['calibrator'],'raw_fit_diagnostics':study_metrics(cal,raw)})
        save(REPORT/'selected_final_freeze.json',{'protocol_sha256':digest(REPORT/'completion_protocol.json'),'models':models,'code_sha256':digest(Path(__file__)),'validation':validation,'calibration':calibration,'final_not_used_for_choices':True})
        results=[]
        for protocol in ['temporal','spatial']:
            model_record=next(v for v in models if Path(v['path']).name.startswith(protocol))
            if digest(Path(model_record['path']))!=model_record['sha256']:raise ValueError('Frozen selected model changed')
            bundle=joblib.load(model_record['path']);test=read('final_test',protocol);raw=predict_bundle(bundle,test[features].astype('float32'));calibrated=apply_calibration(bundle['calibrator'],raw) if bundle['calibrator'] else raw
            summary={'protocol':protocol,'qualification':statuses[protocol],'minimum_final_positive_guard_passed':bool(test.ignition.sum()>=plan['minimum_positives']['final_test']),'raw':study_metrics(test,raw),'calibrated':study_metrics(test,calibrated),'training_prior':study_metrics(test,np.full(len(test),bundle['training_prior']))}
            result=test[['grid_id','ignition_date','ignition']].copy();result['raw_probability']=raw;result['probability']=calibrated;result['cwfis_missing']=test[['temp_c','rh_pct','wind_kmh','rain_24h_mm']].isna().any(axis=1).astype(int);result.to_parquet(OUTPUT/f'{protocol}_final_predictions.parquet',index=False)
            first=test[test.ignition_date.eq(test.ignition_date.min())];x=first[features].astype('float32');contrib=bundle['model'].booster_.predict(x,pred_contrib=True,num_threads=4);margin=bundle['model'].booster_.predict(x,raw_score=True,num_threads=4);np.testing.assert_allclose(contrib.sum(axis=1),margin,atol=1e-7,rtol=1e-5)
            explanations=[]
            for i,row in enumerate(first.itertuples()):
                top=np.argsort(-np.abs(contrib[i,:-1]))[:3];explanations.append({'grid_id':row.grid_id,'ignition_date':row.ignition_date,'top_factors':[{'feature':features[j],'raw_log_odds_contribution':float(contrib[i,j])} for j in top]})
            save(OUTPUT/f'{protocol}_first_day_explanations.json',{'date':first.ignition_date.min(),'rows':explanations,'raw_log_odds_additivity_checked':True});results.append(summary);print('selected',protocol,'final positives',int(test.ignition.sum()),'AP',summary['calibrated'].get('average_precision'),flush=True)
    save(REPORT/'selected_2025_results.json',{'validation':validation,'calibration':calibration,'final':results,'models':models,'source_contract_sha256':digest(SOURCE/'predictor_contract.json'),'qualification':'Within-one-season2025 only; research FWIstartup; finalEDA exposure disclosed; no operational/cross-year claim','live_compatible':False,'code_sha256':digest(Path(__file__))})
    grid=pd.read_parquet(ROOT/'data/processed/selected_provincial_static_native_2025/static_features.parquet',columns=['grid_id','grid_x_m','grid_y_m','centroid_longitude','centroid_latitude']);pred=pd.read_parquet(OUTPUT/'temporal_final_predictions.parquet');explain=json.loads((OUTPUT/'temporal_first_day_explanations.json').read_text());payload=map_payload(grid,pred,explain)
    html=HTML.replace('__PAYLOAD__',json.dumps(payload,separators=(',',':')).replace('<','\\u003c')).replace('2019 retrospective evaluation','2025 within-season evaluation').replace('Historical research ·','Selected-source research ·').replace('Historical date','Evaluation date').replace('Station weather unavailable; model uses missing-value handling.','ERA5 weather unavailable; model uses missing-value handling.').replace('Station weather supported within the declared radius.','ERA5 grid-centre weather supported.').replace('Missing station weather','Missing ERA5 weather')
    (REPORT/'selected_2025_ignition_map.html').write_text(html)


if __name__=='__main__':run()
