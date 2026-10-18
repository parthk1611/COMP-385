"""Download and verify HRDPS weather; keep research FWI distinct from trusted state."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from pyproj import Geod,Transformer
import rasterio
import requests

from scripts.prepare_historical_weather_v2 import ROOT,REPORT,digest,save
from scripts.prepare_provincial_weather import standard_offsets
from scripts.prepare_selected_weather import FWI,wind

FIELDS={'temp_c':('TMP','AGL-2m','[C]'),'rh_pct':('RH','AGL-2m','[%]'),
        'u_grid_ms':('UGRD','AGL-10m','[m/s]'),'v_grid_ms':('VGRD','AGL-10m','[m/s]'),
        'precip_mm':('APCP','Sfc','[kg/(m^2)]')}


def utc_now():return pd.Timestamp.now(tz='UTC')


def grid_relative(path):
    data=path.read_bytes()
    if data[:4]!=b'GRIB' or data[7]!=2:raise ValueError('Expected GRIB edition 2')
    offset=16
    while offset<len(data)-4:
        size=int.from_bytes(data[offset:offset+4],'big')
        if size<5:raise ValueError('Invalid GRIB section')
        if data[offset+4]==3:
            if int.from_bytes(data[offset+12:offset+14],'big')!=1:raise ValueError('Expected rotated lat/lon template 3.1')
            return bool(data[offset+54]&8)
        offset+=size
    raise ValueError('Missing GRIB grid definition')


def rotate_wind(u,v,north_bearing_degrees):
    angle=np.radians(north_bearing_degrees)
    return u*np.cos(angle)+v*np.sin(angle),-u*np.sin(angle)+v*np.cos(angle)


def incremental_rain(values,start,end,previous=None):
    start,end=pd.Timestamp(start),pd.Timestamp(end)
    if end-start==pd.Timedelta(hours=1):
        result=np.asarray(values,dtype=float)
    elif previous is not None and previous[1]==start and previous[2]==end-pd.Timedelta(hours=1):
        result=np.asarray(values,dtype=float)-previous[0]
    else:
        return np.full_like(values,np.nan,dtype=float)
    return np.where(np.isfinite(result)&(result>=-1e-5),np.maximum(result,0),np.nan)


def choose_available_run(bundles,issue):
    issue=pd.Timestamp(issue)
    if issue.tzinfo is None:raise ValueError('Issue timestamp requires timezone')
    eligible=[b for b in bundles if pd.Timestamp(b['run_time_utc'])<=issue and pd.Timestamp(b['available_at_utc'])<=issue]
    if not eligible:raise ValueError('No completely retrieved run was available at issue')
    return max(eligible,key=lambda b:pd.Timestamp(b['run_time_utc']))


def discover_run(issue):
    issue=pd.Timestamp(issue).tz_convert('UTC');trace=[]
    for day in (issue.normalize(),issue.normalize()-pd.Timedelta(days=1)):
        for hour in (18,12,6,0):
            candidate=day+pd.Timedelta(hours=hour)
            if candidate>issue:continue
            url=f'https://dd.weather.gc.ca/{candidate:%Y%m%d}/WXO-DD/model_hrdps/continental/2.5km/{candidate:%H}/024/'
            response=requests.get(url,timeout=(10,30))
            names=[f'{candidate:%Y%m%dT%HZ}_MSC_HRDPS_{token}_{level}_RLatLon0.0225_PT024H.grib2' for token,level,_ in FIELDS.values()]
            complete=response.status_code==200 and all(name in response.text for name in names)
            trace.append({'run_time_utc':candidate.isoformat(),'listing_status':response.status_code,'surface_lead24_listed':complete})
            if complete:return candidate,trace
    raise ValueError('No recent run lists all five required 24h surface fields')


def validate_seed(seed,expected_date,allow_research=False,expected_noon=None,issue=None):
    if seed['date']!=expected_date:raise ValueError('Stale FWI seed date')
    if expected_noon is not None and (not seed.get('noon_time_utc') or pd.Timestamp(seed['noon_time_utc'])!=expected_noon):raise ValueError('Seed must describe the exact previous standard-noon state')
    if issue is not None and (not seed.get('available_at_utc') or pd.Timestamp(seed['available_at_utc'])>issue):raise ValueError('FWI seed availability is unknown or after issue')
    if seed.get('trusted') is not True and not allow_research:raise ValueError('Trusted FWI state required')
    for key in ('ffmc','dmc','dc'):
        value=seed[key]
        if not np.isfinite(value) or value<0 or (key=='ffmc' and value>101):raise ValueError('Invalid FWI state')
    if not seed.get('provenance'):raise ValueError('Seed provenance required')
    return {k:float(seed[k]) for k in ('ffmc','dmc','dc')}


def state_checkpoint(daily,available,run_time,grid_sha256):
    result={'_metadata':{'version':'hrdps-research-fwi-checkpoint-v1','grid_sha256':grid_sha256,
      'generated_at_utc':str(available),'weather_run_time_utc':str(run_time),
      'state_kind':'forecast_derived_not_observed','operationally_validated':False}}
    for row in daily.itertuples():
        if not np.isfinite([row.ffmc,row.dmc,row.dc]).all():continue
        result[row.grid_id]={'date':row.date,'noon_time_utc':row.noon_time_utc.isoformat(),'available_at_utc':str(available),
           'ffmc':float(row.ffmc),'dmc':float(row.dmc),'dc':float(row.dc),'trusted':False,'state_kind':'forecast_update',
           'provenance':f'Forecast-derived FWI state from HRDPS {run_time}; research only, never an observed-state claim'}
    return result


def download(run,lead,field,cache,records):
    token,level,_=FIELDS[field];stamp=run.strftime('%Y%m%dT%HZ')
    name=f'{stamp}_MSC_HRDPS_{token}_{level}_RLatLon0.0225_PT{lead:03d}H.grib2'
    url=f'https://dd.weather.gc.ca/{run:%Y%m%d}/WXO-DD/model_hrdps/continental/2.5km/{run:%H}/{lead:03d}/{name}'
    path=cache/name
    if path.exists() and name in records:
        if digest(path)!=records[name]['sha256']:raise ValueError('Cached HRDPS hash changed')
        return path
    response=requests.get(url,stream=True,timeout=(20,120));response.raise_for_status();temporary=path.with_suffix('.partial')
    with temporary.open('wb') as handle:
        for chunk in response.iter_content(1024*1024):handle.write(chunk)
    response.close();temporary.replace(path)
    records[name]={'path':str(path),'url':url,'sha256':digest(path),'bytes':path.stat().st_size,'retrieved_at_utc':utc_now().isoformat()}
    save(cache/'download_manifest.json',records)
    return path


def sample_grib(path,grid,run,lead,field):
    with rasterio.open(path) as ds:
        meta=ds.tags(1);meta['grid_signature']=f'{ds.crs.to_wkt()}|{ds.shape}|{ds.transform}';expected_unit=FIELDS[field][2]
        if meta['GRIB_UNIT']!=expected_unit:raise ValueError('GRIB units changed')
        reference=pd.Timestamp(int(meta['GRIB_REF_TIME']),unit='s',tz='UTC');valid=pd.Timestamp(int(meta['GRIB_VALID_TIME']),unit='s',tz='UTC')
        if reference!=run or valid!=run+pd.Timedelta(hours=lead):raise ValueError('GRIB run/valid time differs from requested file')
        if field=='precip_mm':
            start=reference+pd.Timedelta(seconds=int(meta['GRIB_FORECAST_SECONDS']))
            interval=int((valid-start).total_seconds()/3600)
            if interval<1 or valid-start!=pd.Timedelta(hours=interval) or not re.search(rf'\b{interval:02d} hr Total precipitation',meta.get('GRIB_COMMENT','')):raise ValueError('Unknown precipitation accumulation interval')
            meta['accumulation_start_utc']=start.isoformat()
        to_grid=Transformer.from_crs(4326,ds.crs,always_xy=True);x,y=to_grid.transform(grid.centroid_longitude.to_numpy(),grid.centroid_latitude.to_numpy())
        rr,cc=rasterio.transform.rowcol(ds.transform,x,y);rr,cc=np.asarray(rr),np.asarray(cc)
        if ((rr<0)|(rr>=ds.height)|(cc<0)|(cc>=ds.width)).any():raise ValueError('Grid centre outside HRDPS domain')
        raster=ds.read(1,masked=True).astype('float32').filled(np.nan);values=raster[rr,cc]
        bearing=None
        if field in ('u_grid_ms','v_grid_ms'):
            relative=grid_relative(path)
            if relative:
                inverse=Transformer.from_crs(ds.crs,4326,always_xy=True);lon2,lat2=inverse.transform(x,np.asarray(y)+1e-5)
                bearing,_,_=Geod(a=6371229,b=6371229).inv(grid.centroid_longitude.to_numpy(),grid.centroid_latitude.to_numpy(),lon2,lat2)
            else:bearing=np.zeros(len(grid))
        return values,bearing,meta


def run(output,run_time=None,research_startup=False,seed_path=None):
    output.mkdir(parents=True,exist_ok=True)
    if (output/'manifest.json').exists():raise FileExistsError('Completed live demo exists; use a new output directory')
    if run_time:
        run=pd.Timestamp(run_time);selection_trace=[{'selection':'explicit run; completion verified by downloads'}]
    else:run,selection_trace=discover_run(utc_now())
    if run.tzinfo is None:raise ValueError('Run must include timezone')
    run=run.tz_convert('UTC')
    if run.hour not in (0,6,12,18) or run.minute or run.second:raise ValueError('Invalid HRDPS run')
    grid=pd.read_csv(REPORT/'current_boundary_centroid_grid.csv');names,offsets=standard_offsets(grid)
    cache=output/'raw';cache.mkdir(exist_ok=True);record_path=cache/'download_manifest.json';records=json.loads(record_path.read_text()) if record_path.exists() else {}
    tables=[];raw_metadata={};previous_precip=None;grid_signature=None
    for lead in range(1,25):
        fields={};bearings={}
        for field in FIELDS:
            path=download(run,lead,field,cache,records);values,bearing,meta=sample_grib(path,grid,run,lead,field)
            if grid_signature is None:grid_signature=meta['grid_signature']
            elif grid_signature!=meta['grid_signature']:raise ValueError('HRDPS fields do not share one native grid')
            if field=='precip_mm':
                start=pd.Timestamp(meta['accumulation_start_utc']);end=run+pd.Timedelta(hours=lead)
                fields[field]=incremental_rain(values,start,end,previous_precip);previous_precip=(values,start,end)
            else:fields[field]=values
            raw_metadata.setdefault(field,meta)
            if bearing is not None:bearings[field]=bearing
        if not np.allclose(bearings['u_grid_ms'],bearings['v_grid_ms'],atol=1e-9):raise ValueError('U/V wind grids differ')
        u,v=rotate_wind(fields.pop('u_grid_ms'),fields.pop('v_grid_ms'),bearings['u_grid_ms'])
        speed,direction=wind(u,v);fields.update(wind_kmh=speed,wind_from_degrees=direction,u_earth_ms=u,v_earth_ms=v)
        frame=pd.DataFrame(fields);frame['grid_id']=grid.grid_id;frame['valid_time_utc']=run+pd.Timedelta(hours=lead);frame['run_time_utc']=run
        tables.append(frame)
        if lead%6==0:print('HRDPS lead',lead,'complete',flush=True)
    hourly=pd.concat(tables,ignore_index=True)
    # Previous-run hourly rain closes the current day's standard-noon rain window.
    history={}
    previous_run=run-pd.Timedelta(days=1)
    previous=None
    for lead in range(1,25):
        path=download(previous_run,lead,'precip_mm',cache,records);values,_,meta=sample_grib(path,grid,previous_run,lead,'precip_mm')
        start=pd.Timestamp(meta['accumulation_start_utc']);end=previous_run+pd.Timedelta(hours=lead)
        history[end]=incremental_rain(values,start,end,previous);previous=(values,start,end)
    available=utc_now();bundle={'run_time_utc':run.isoformat(),'available_at_utc':available.isoformat()}
    choose_available_run([bundle],available)
    issue=available;future=hourly[hourly.valid_time_utc>issue]
    required=pd.date_range(issue.ceil('h'),periods=6,freq='h')
    six_hours_covered=set(required).issubset(set(future.valid_time_utc))
    hourly['available_at_utc']=available;hourly['mode']='live_forecast_research_adapter'
    hourly.to_parquet(output/'hourly_weather.parquet',index=False)
    seeds=json.loads(seed_path.read_text()) if seed_path else None
    grid_sha=digest(REPORT/'current_boundary_centroid_grid.csv')
    if seeds and seeds.get('_metadata',{}).get('grid_sha256',grid_sha)!=grid_sha:raise ValueError('FWI checkpoint grid differs')
    daily=[]
    for offset in sorted(set(offsets)):
        cells=np.flatnonzero(offsets==offset);noon=run.normalize()+pd.Timedelta(hours=12-int(offset))
        if noon<=issue:noon+=pd.Timedelta(days=1)
        if noon not in set(hourly.valid_time_utc):continue
        noon_frame=hourly[hourly.valid_time_utc==noon].set_index('grid_id')
        rain=[]
        for stamp in pd.date_range(noon-pd.Timedelta(hours=23),noon,freq='h'):
            if stamp in history:rain.append(history[stamp])
            else:
                selected=hourly[hourly.valid_time_utc==stamp].set_index('grid_id').reindex(grid.grid_id)
                rain.append(selected.precip_mm.to_numpy() if len(selected) else np.full(len(grid),np.nan))
        rain=np.stack(rain)
        for i in cells:
            key=grid.grid_id.iloc[i];values=noon_frame.loc[key];expected=(noon.date()-pd.Timedelta(days=1)).isoformat()
            seed=(seeds or {}).get(key)
            if seed is None and research_startup:seed={'date':expected,'noon_time_utc':(noon-pd.Timedelta(days=1)).isoformat(),'available_at_utc':issue.isoformat(),**FWI.STARTUP,'trusted':False,'provenance':'Explicit research restart with standard constants; not observed or overwintered state'}
            status='missing_trusted_seed';codes={k:np.nan for k in ('ffmc','dmc','dc','isi','bui','fwi')}
            if seed is not None:
                state=validate_seed(seed,expected,allow_research=research_startup,expected_noon=noon-pd.Timedelta(days=1),issue=issue)
                valid=np.isfinite(rain[:,i]).all() and (rain[:,i]>=0).all() and np.isfinite([values.temp_c,values.rh_pct,values.wind_kmh]).all() and -90<=values.temp_c<=60 and 0<=values.rh_pct<=100 and values.wind_kmh>=0
                if valid:
                    codes=FWI.daily_codes(float(values.temp_c),float(values.rh_pct),float(values.wind_kmh),float(rain[:,i].sum()),noon.month,state);status='trusted_seed_forecast_update' if seed['trusted'] else ('research_checkpoint_forecast_update' if seed.get('state_kind')=='forecast_update' else 'research_startup_forecast_update')
                else:status='incomplete_weather'
            daily.append({'grid_id':key,'date':noon.date().isoformat(),'noon_time_utc':noon,'standard_offset_hours':int(offset),'status':status,'rain_24h_mm':float(rain[:,i].sum()) if np.isfinite(rain[:,i]).all() else np.nan,**codes})
    if not daily:raise ValueError('Selected run does not cover a future standard noon; select a newer completed run')
    fwi=pd.DataFrame(daily);fwi.to_parquet(output/'daily_forecast_fwi.parquet',index=False)
    checkpoint=state_checkpoint(fwi,available,run.isoformat(),grid_sha);save(output/'state_checkpoint.json',checkpoint)
    summary={'state_checkpoint_valid_cells':len(checkpoint)-1,'seed_path':str(seed_path) if seed_path else None,'bundle':bundle,'run_selection_trace':selection_trace,'issue_time_utc':issue.isoformat(),'next_six_hours_covered':six_hours_covered,'grid_cells':len(grid),'hourly_rows':len(hourly),'fwi_rows':len(fwi),
             'fwi_status_counts':fwi.status.value_counts().to_dict(),'hourly_null_rows':{c:int(hourly[c].isna().sum()) for c in ('temp_c','rh_pct','wind_kmh','precip_mm')},'research_startup':research_startup,'operationally_validated':False,
             'input_metadata':raw_metadata,'code_sha256':digest(Path(__file__)),'download_files':len(records),'wind_policy':'GRIB2 Section3 template3.1 component bit5; grid-relative U/V rotated using geodesic grid-north bearing',
             'rain_policy':'Accumulation intervals validated from metadata; difference only consecutive values with same accumulation start; reset 1h values used directly; unknown gaps remain null. Prior-run history is model forecast, not observed rain',
             'ignition_model_compatibility':'Not interchangeable with CWFIS benchmark; no ignition model invoked',
             'outputs':[{'path':str(p),'sha256':digest(p),'bytes':p.stat().st_size} for p in (output/'hourly_weather.parquet',output/'daily_forecast_fwi.parquet',output/'state_checkpoint.json')]}
    save(output/'manifest.json',summary);save(REPORT/'hrdps_live_integration_audit.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='input_metadata'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=ROOT/'data/processed/hrdps_live_research_2026-10-16');parser.add_argument('--run-time');parser.add_argument('--research-startup',action='store_true');parser.add_argument('--seed-path',type=Path)
    a=parser.parse_args();run(a.output_dir,a.run_time,a.research_startup,a.seed_path)
