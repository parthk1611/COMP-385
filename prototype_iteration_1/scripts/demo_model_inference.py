"""Recompute one exposed development example from a saved model for a classroom demo."""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.ignition_comparison import digest, predict_bundle
from scripts.week5_ignition import apply_calibration


def validate_demo_key(day, grid_id):
    if (not re.fullmatch(r'2017-\d{2}-\d{2}', day)
            or pd.Timestamp(day).strftime('%Y-%m-%d')!=day
            or not re.fullmatch(r'ofr10km_-?\d+_-?\d+', grid_id)):
        raise ValueError('Use a valid 2017 development date and a 10 km grid identifier')


def run(workspace, day, grid_id):
    validate_demo_key(day, grid_id)
    record = next(r for r in json.loads((workspace/'reports/model_refinement_2026-10-31/results.json').read_text())['results']
                  if r['protocol']=='inner_spatial')
    model_path = workspace/'data/processed/ignition_refinement_2026-10-31/inner_spatial_lightgbm_reference.joblib'
    data = workspace/'data/processed/ignition_weather_v2_development'
    manifest = json.loads((data/'manifest.json').read_text())
    if digest(model_path)!=record['model_sha256'] or digest(data/'validation.parquet')!=manifest['files']['validation']['sha256']:
        raise ValueError('A pinned demo model or input changed')
    bundle = joblib.load(model_path)
    frame = pd.read_parquet(data/'validation.parquet', columns=bundle['features']+['ignition','issue_time_utc'],
                            filters=[('ignition_date','=',day), ('grid_id','=',grid_id)])
    if len(frame)!=1:
        raise ValueError('The demo requires one exact development cell-day')
    start=time.perf_counter()
    with threadpool_limits(limits=4):
        raw=predict_bundle(bundle,frame[bundle['features']].astype('float32'))
        probability=apply_calibration(bundle['calibrator'],raw)
    result={'mode':'retrospective development inference; not a current forecast',
            'grid_id':grid_id,'date':day,'issue_time_utc':frame.issue_time_utc.iloc[0],
            'features_passed_to_model':len(bundle['features']),
            'target_passed_to_model':False,'raw_probability':float(raw[0]),
            'probability':float(probability[0]),'probability_percent':float(probability[0]*100),
            'recorded_start':bool(frame.ignition.iloc[0]),'model_sha256':record['model_sha256'],
            'scoring_seconds_excluding_file_loading':time.perf_counter()-start,
            'interpretation':'predict_proba executed now on a saved historical feature row; this does not validate live forecasting'}
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--date',default='2017-08-09');p.add_argument('--grid-id',default='ofr10km_470000_40000')
    a=p.parse_args();run(a.workspace.resolve(),a.date,a.grid_id)
