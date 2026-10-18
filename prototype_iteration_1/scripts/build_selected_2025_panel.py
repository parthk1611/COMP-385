"""Join selected 2025 research inputs, preserving provider dates and quality flags."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

from scripts.prepare_historical_weather_v2 import ROOT,REPORT,digest,save
from scripts.refine_provincial_fuel import OUTPUT as STATIC
from scripts.prepare_provincial_weather import OUTPUT as WEATHER

OUTPUT=ROOT/'data/processed/selected_2025_ignition_panel'


def provider_dates(values):
    # Provider date fields are epoch-encoded calendar dates, not ignition instants.
    return pd.to_datetime(pd.to_numeric(values,errors='coerce'),unit='ms',utc=True,errors='coerce').dt.strftime('%Y-%m-%d')


def source_events(source,grid):
    document=json.loads(source.read_text());rows=[]
    for feature in document['features']:
        props=feature['properties'];geometry=feature.get('geometry') or {}
        if props.get('FIRE_YEAR')!=2025:continue
        coordinates=geometry.get('coordinates') if geometry.get('type')=='Point' else None
        rows.append({'source_objectid':props.get('OBJECTID'),'source_fire_id':props.get('FIRE_DISTURBANCE_AREA_IDENT'),
                     'fire_year':props.get('FIRE_YEAR'),'fire_type':props.get('FIRE_TYPE_CODE'),
                     'raw_start_date':props.get('FIRE_START_DATE'),'longitude':coordinates[0] if coordinates else np.nan,'latitude':coordinates[1] if coordinates else np.nan})
    frame=pd.DataFrame(rows);frame['ignition_date']=provider_dates(frame.raw_start_date)
    xy_valid=np.isfinite(frame[['longitude','latitude']]).all(axis=1)
    x,y=Transformer.from_crs(4326,3978,always_xy=True).transform(frame.longitude.to_numpy(),frame.latitude.to_numpy())
    frame['grid_id']=[f'ofr10km_{int(np.floor(a/10000))*10000}_{int(np.floor(b/10000))*10000}' if np.isfinite(a) and np.isfinite(b) else '' for a,b in zip(x,y)]
    frame['exclusion_reason']=''
    frame.loc[frame.fire_type!='IFR','exclusion_reason']='outside_selected_IFR_label_type'
    frame.loc[frame.ignition_date.isna(),'exclusion_reason']='missing_start_date'
    frame.loc[frame.ignition_date.notna()&~frame.ignition_date.str.startswith('2025',na=False),'exclusion_reason']='year_date_conflict'
    frame.loc[~xy_valid,'exclusion_reason']='missing_or_invalid_geometry'
    frame.loc[frame.exclusion_reason.eq('')&~frame.grid_id.isin(grid.grid_id),'exclusion_reason']='outside_fixed_centroid_grid'
    frame.loc[frame.exclusion_reason.eq('')&~frame.ignition_date.between('2025-05-01','2025-10-31'),'exclusion_reason']='outside_declared_fire_season'
    if frame.source_objectid.isna().any() or frame.source_objectid.duplicated().any():raise ValueError('Invalid source OBJECTID instance keys')
    return frame


def shifted_weather(weather):
    if weather.duplicated(['grid_id','date']).any():raise ValueError('Duplicate weather cell/date')
    weather=weather.sort_values(['grid_id','date']).reset_index(drop=True).copy()
    weather['rain_prior_7_noon_days_mm']=weather.groupby('grid_id',sort=False).rain_24h_mm.rolling(7,min_periods=7).sum().reset_index(level=0,drop=True)
    weather['weather_observation_date']=weather['date']
    weather['ignition_date']=(pd.to_datetime(weather['date'])+pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    weather['issue_time_utc']=pd.to_datetime(weather.ignition_date).dt.tz_localize('America/Toronto').dt.tz_convert('UTC')
    if not (weather.noon_time_utc<weather.issue_time_utc).all():raise ValueError('Weather observation is not before issue')
    return weather.drop(columns='date')


def run(output=OUTPUT):
    if output.exists():raise FileExistsError('Use a new output directory')
    static_manifest=json.loads((STATIC/'manifest.json').read_text());weather_manifest=json.loads((WEATHER/'manifest.json').read_text())
    for manifest in (static_manifest,weather_manifest):
        if digest(Path(manifest['output']['path']))!=manifest['output']['sha256']:raise ValueError('Source artifact hash changed')
    static=pd.read_parquet(STATIC/'static_features.parquet')
    mapping=pd.read_parquet(WEATHER/'grid_weather_mapping.parquet')[['grid_id','standard_timezone','standard_offset_hours']]
    static=static.merge(mapping,on='grid_id',how='left',validate='one_to_one')
    if static.standard_offset_hours.isna().any():raise ValueError('Missing standard-noon mapping')
    weather=shifted_weather(pd.read_parquet(WEATHER/'daily_weather.parquet'))
    source=ROOT/'data/raw/week_2_completion/fire_disturbance/fire_disturbance_point.geojson';source_manifest=json.loads((source.parent/'manifest.json').read_text())
    records=source_manifest.get('layers',[])
    if isinstance(records,dict):records=list(records.values())
    matching=[r for r in records if r['filename']==source.name]
    if not matching or digest(source)!=matching[0]['sha256']:raise ValueError('Pinned provincial point source changed')
    events=source_events(source,static);selected=events[events.exclusion_reason.eq('')]
    counts=selected.groupby(['grid_id','ignition_date']).size().rename('recorded_start_count').reset_index()
    dates=pd.date_range('2025-05-01','2025-10-31',freq='D').strftime('%Y-%m-%d')
    panel=pd.MultiIndex.from_product([dates,static.grid_id],names=['ignition_date','grid_id']).to_frame(index=False)
    panel=panel.merge(counts,on=['grid_id','ignition_date'],how='left',validate='one_to_one',sort=False)
    panel['recorded_start_count']=panel.recorded_start_count.fillna(0).astype('int16');panel['reported_fire_start']=(panel.recorded_start_count>0).astype('int8')
    panel=panel.merge(static,on='grid_id',how='left',validate='many_to_one',sort=False)
    weather=weather[weather.ignition_date.between('2025-05-01','2025-10-31')]
    panel=panel.merge(weather,on=['grid_id','ignition_date'],how='left',validate='one_to_one',sort=False,indicator=True)
    if not panel['_merge'].eq('both').all():raise ValueError('Incomplete weather join')
    panel=panel.drop(columns='_merge')
    if len(panel)!=len(static)*len(dates) or panel.duplicated(['grid_id','ignition_date']).any():raise ValueError('Panel universe changed')
    predictors=[c for c in panel if c.startswith('fbp_2024_code_') or c.startswith('mrdem_') or c.startswith('scanfi_2020_')]
    predictors += ['temp_c','rh_pct','wind_kmh','rain_24h_mm','rain_prior_7_noon_days_mm','ffmc','dmc','dc','isi','bui','fwi']
    predictors += ['fbp_native_valid_area_fraction','scanfi_species_valid_fraction','fwi_state_valid','rain_coverage_hours']
    if np.isinf(panel[predictors].to_numpy(dtype=float)).any():raise ValueError('Infinite candidate predictors')
    output.mkdir(parents=True);panel.to_parquet(output/'cell_days.parquet',index=False)
    events.to_csv(output/'fire_source_adjudication.csv',index=False)
    contract={'version':'selected-2025-fixed-landscape-v1','predictors':predictors,'never_predictors':[c for c in panel if c not in predictors],
      'target':'reported_fire_start','negative_semantics':'No IFR start recorded on this date/cell in the pinned source, not proof of no ignition',
      'label_date':'Provider calendar date preserved from epoch encoding; no exact ignition clock inferred','issue_timezone':'America/Toronto, midnight',
      'observed_weather_cutoff':'Previous local-standard-noon day for each cell; all observation instants precede issue',
      'source_scope':'Ontario points = labels; FBP2024/SCANFIv1.2-2020/MRDEM = fixed landscape; ERA5 = hindcast weather; VIIRS/areas = separate validation; HRDPS = separate live research adapter',
      'training_ready':False,'reason':'One-year fixed-landscape research panel; requires its own frozen evaluation design and model calibration. Not input-compatible with historical CWFIS bundles.'}
    save(output/'predictor_contract.json',contract)
    summary={'rows':len(panel),'cells':len(static),'dates':len(dates),'positive_cell_days':int(panel.reported_fire_start.sum()),'selected_source_records':len(selected),
      'excluded_source_counts':events.loc[events.exclusion_reason.ne(''),'exclusion_reason'].value_counts().to_dict(),
      'all_weather_instants_before_issue':bool((panel.noon_time_utc<panel.issue_time_utc).all()),'feature_null_rows':{c:int(panel[c].isna().sum()) for c in predictors},
      'fwistate_valid_rows':int(panel.fwi_state_valid.sum()),'code_sha256':digest(Path(__file__)),'static_manifest_sha256':digest(STATIC/'manifest.json'),
      'weather_manifest_sha256':digest(WEATHER/'manifest.json'),'grid_weather_mapping_sha256':digest(WEATHER/'grid_weather_mapping.parquet'),'point_source_sha256':digest(source),
      'outputs':[{'path':str(p),'sha256':digest(p),'bytes':p.stat().st_size} for p in (output/'cell_days.parquet',output/'fire_source_adjudication.csv',output/'predictor_contract.json')],
      'training_ready':False,'operationally_validated':False}
    save(output/'manifest.json',summary);save(REPORT/'selected_2025_panel_audit.json',summary);print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=OUTPUT);run(parser.parse_args().output_dir)
