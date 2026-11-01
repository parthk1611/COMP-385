"""Measure matched weather and state lineage without qualifying an operational model."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from scripts.ignition_comparison import digest, save_json
from scripts.prepare_selected_weather import FWI, deaccumulate_era5, humidity, wind

KEYS = ['grid_id', 'valid_time_utc']
WEATHER = ['temp_c', 'rh_pct', 'wind_kmh', 'precip_mm']


def utc_stamp(value):
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        raise ValueError('An explicit timezone is required')
    return result.tz_convert('UTC')


def check_times(frame, columns):
    for col in columns:
        if not isinstance(frame[col].dtype, pd.DatetimeTZDtype) or frame[col].isna().any():
            raise ValueError('Unique, timezone-aware, nonmissing clocks are required')
    if frame[KEYS].isna().any().any():
        raise ValueError('Missing cell-time key')
    if frame.duplicated(KEYS).any():
        raise ValueError('Duplicate cell-time key')


def pair_weather(forecast, reference, issue):
    issue = utc_stamp(issue)
    check_times(forecast, ['valid_time_utc', 'run_time_utc', 'available_at_utc'])
    check_times(reference, ['valid_time_utc'])
    if ((forecast.available_at_utc > issue) | (forecast.run_time_utc > forecast.available_at_utc)).any():
        raise ValueError('Forecast not available at issue or availability predates run')
    lead = forecast.valid_time_utc - forecast.run_time_utc
    if not lead.between(pd.Timedelta(hours=1), pd.Timedelta(hours=48)).all():
        raise ValueError('Invalid HRDPS forecast lead')
    eligible = forecast.loc[forecast.valid_time_utc > issue].copy()
    paired = eligible.merge(reference[KEYS+WEATHER], on=KEYS, suffixes=('_forecast', '_reference'), validate='one_to_one')
    return paired, {'eligible_forecast_rows':len(eligible), 'excluded_pre_issue_valid_rows':len(forecast)-len(eligible),
        'paired_rows':len(paired), 'unmatched_eligible_rows':len(eligible)-len(paired),
        'paired_days':int(paired.valid_time_utc.dt.date.nunique()),
        'distinct_runs':int(paired.run_time_utc.nunique()), 'issue_time_utc':issue.isoformat(),
        'reference_policy':'Independent reanalysis retrieved after issue; used as hindsight reference only, never as a historical input'}


def weather_metrics(paired):
    rows=[]
    for field in WEATHER:
        a=paired[field+'_forecast'].to_numpy();b=paired[field+'_reference'].to_numpy()
        valid=np.isfinite(a)&np.isfinite(b)
        if field=='temp_c':
            valid &= (a>=-90)&(a<=60)&(b>=-90)&(b<=60)
        else:
            valid &= (a>=0)&(b>=0)
            if field=='rh_pct':
                valid &= (a<=100)&(b<=100)
        delta=a[valid]-b[valid]
        rows.append({'field':field,'finite_pairs':int(valid.sum()),'missing_or_invalid_pairs':int((~valid).sum()),
            'bias':float(delta.mean()) if len(delta) else None,'mae':float(np.abs(delta).mean()) if len(delta) else None,
            'rmse':float(np.sqrt(np.square(delta).mean())) if len(delta) else None,
            'units':{'temp_c':'degC','rh_pct':'percentage points','wind_kmh':'km/h','precip_mm':'mm per preceding hour'}[field]})
    return rows


def parse_station_file(path, expected_date):
    frame=pd.read_csv(path,dtype=str).map(lambda x:x.strip() if isinstance(x,str) else x)
    frame=frame.loc[frame.REPDATE.eq(expected_date.replace('-',''))].copy()
    if frame.empty:
        raise ValueError('No station records for the requested date')
    frame['station_id']=frame.AGENCY.fillna('')+'|'+frame.AES.fillna('')+'|'+frame.WMO.fillna('')
    if frame.station_id.duplicated().any():
        raise ValueError('Station identifiers are not unique')
    names={'TEMP':'temp_c','RH':'rh_pct','WS':'wind_kmh','PRECIP':'rain_24h_mm',
        'FFMC':'ffmc','DMC':'dmc','DC':'dc','FWI':'fwi','CALCSTATUS':'calcstatus'}
    for source,target in names.items():
        values=pd.to_numeric(frame[source],errors='coerce')
        valid=values.ge(-90)&values.le(60) if target=='temp_c' else values.ge(0)
        if target=='rh_pct':valid &= values.le(100)
        if target=='ffmc':valid &= values.le(101)
        if target=='calcstatus':valid=values.notna()
        frame[target]=values.where(valid)
    frame['date']=expected_date;frame['trusted']=False
    frame['state_kind']='station_reported_archive_not_issue_verified'
    return frame


def validate_state_lineage(seed, issue, previous_noon):
    issue,previous_noon=utc_stamp(issue),utc_stamp(previous_noon)
    if seed.get('trusted') is not True or seed.get('state_kind') not in ('observed','overwintered_observed'):
        raise ValueError('Forecast/startup/research state cannot be called observed by a trusted flag')
    if utc_stamp(seed['available_at_utc']) > issue or utc_stamp(seed['noon_time_utc']) != previous_noon:
        raise ValueError('State availability or previous standard-noon clock is incompatible')
    if seed.get('date') != previous_noon.date().isoformat():
        raise ValueError('State date differs from previous noon')
    if not re.fullmatch('[a-f0-9]{64}',seed.get('source_sha256','')) or not seed.get('provenance'):
        raise ValueError('State requires verifiable source lineage')
    values=np.array([seed[k] for k in ('ffmc','dmc','dc')],dtype=float)
    if not np.isfinite(values).all() or (values<0).any() or values[0]>101:
        raise ValueError('Invalid moisture codes')
    return True


def reference_container(paths, field):
    matches=[]
    for path in paths:
        with rasterio.open(path) as container:
            names=container.subdatasets
            if any(name.endswith(':'+field) for name in names):matches.append(path)
            elif not names and container.tags().get(field+'#units'):matches.append(path)
    if len(matches)!=1:
        raise ValueError(f'Expected exactly one reference container for {field}')
    return matches[0]


def reference_clock(ds, field, unit):
    tags=ds.tags()
    geographic=(tags.get('latitude#units'),tags.get('longitude#units'),ds.transform.b,ds.transform.d)
    if geographic!=('degrees_north','degrees_east',0,0) or min(ds.transform.a,-ds.transform.e)<=0:
        raise ValueError('Expected a regular geographic reference grid')
    expected=(unit,'accum' if field=='tp' else 'instant')
    if (tags.get(field+'#units'),tags.get(field+'#GRIB_stepType'))!=expected:
        raise ValueError('Reference unit or aggregation mismatch')
    if field in ('u10','v10') and tags.get(field+'#GRIB_uvRelativeToGrid')!='0':
        raise ValueError('Reference wind must be earth-relative')
    times=pd.to_datetime([int(ds.tags(i)['NETCDF_DIM_valid_time']) for i in range(1,ds.count+1)],unit='s',utc=True)
    if not times.is_unique or not times.is_monotonic_increasing or not ((times[1:]-times[:-1])==pd.Timedelta(hours=1)).all():
        raise ValueError('Reference hourly sequence is incomplete')
    return times


def sample_reference(paths, grid):
    arrays={};expected_times=None;geometry=None
    expected_units={'t2m':'K','d2m':'K','u10':'m s**-1','v10':'m s**-1','tp':'m'}
    for field,unit in expected_units.items():
        path=reference_container(paths,field)
        with rasterio.open(f'netcdf:"{path}":{field}') as ds:
            times=reference_clock(ds,field,unit);geom=(ds.crs,ds.shape,ds.transform)
            if expected_times is not None and (not times.equals(expected_times) or geom!=geometry):
                raise ValueError('Reference variable clocks or grids differ')
            expected_times=times;geometry=geom
            rr,cc=rasterio.transform.rowcol(ds.transform,grid.centroid_longitude.to_numpy(),grid.centroid_latitude.to_numpy())
            rr,cc=np.asarray(rr),np.asarray(cc)
            if ((rr<0)|(rr>=ds.height)|(cc<0)|(cc>=ds.width)).any():
                raise ValueError('Reference domain does not cover all model centroids')
            raw=ds.read(masked=True).astype('float32').filled(np.nan)
            arrays[field]=raw[:,rr,cc]
    speed,_=wind(arrays['u10'],arrays['v10'])
    result={'temp_c':arrays['t2m']-273.15,'rh_pct':humidity(arrays['t2m'],arrays['d2m']),
        'wind_kmh':speed,'precip_mm':deaccumulate_era5(expected_times,arrays['tp'])}
    rows=[]
    for i,t in enumerate(expected_times):
        frame=pd.DataFrame({key:value[i] for key,value in result.items()})
        frame['grid_id']=grid.grid_id.to_numpy();frame['valid_time_utc']=t;rows.append(frame)
    return pd.concat(rows,ignore_index=True)


def station_code_diagnostic(directory):
    previous=parse_station_file(directory/'cwfis_fwi_20261015.csv','2026-10-15')
    today=parse_station_file(directory/'cwfis_fwi_20261016.csv','2026-10-16')
    joined=today.merge(previous[['station_id','ffmc','dmc','dc','calcstatus','OPTS']],on='station_id',suffixes=('','_previous'),validate='one_to_one')
    needed=['temp_c','rh_pct','wind_kmh','rain_24h_mm','ffmc_previous','dmc_previous','dc_previous','ffmc','dmc','dc','fwi']
    valid=np.isfinite(joined[needed]).all(axis=1)
    diagnostic=joined.loc[valid].copy();predictions=[]
    for r in diagnostic.itertuples():
        predictions.append(FWI.daily_codes(r.temp_c,r.rh_pct,r.wind_kmh,r.rain_24h_mm,10,
            {'ffmc':r.ffmc_previous,'dmc':r.dmc_previous,'dc':r.dc_previous}))
    predicted=pd.DataFrame(predictions,index=diagnostic.index)
    rows=[]
    for code in ('ffmc','dmc','dc','fwi'):
        delta=predicted[code]-diagnostic[code]
        rows.append({'code':code,'pairs':len(delta),'mae':float(delta.abs().mean()),'within_0_15':int(delta.abs().le(.15).sum())})
    diagnostic[['station_id','date','calcstatus','OPTS','calcstatus_previous','OPTS_previous']].to_csv(directory/'station_pair_quality.csv',index=False)
    return {'station_pairs':len(joined),'finite_code_pairs':len(diagnostic),'diagnostics':rows,
        'calcstatus_today':today.calcstatus.value_counts(dropna=False).astype(int).to_dict(),
        'canonical_acceptance':False,'trusted_grid_state_cells':0,
        'limitations':['Published rounded codes and weather, unknown code-quality flag semantics, station time/location details and initialization can differ.',
            'Daily station CSV lacks latitude/longitude and record-level issue-time availability. Archive retrieved today does not prove it was available at the October16 issue.',
            'This is a station-code consistency diagnostic, not a verified observed grid checkpoint, overwintering qualification or canonical implementation certification.']}


def qualification_decision(pair_audit, trusted_cells):
    return {'status':'unavailable','probability':None,'operational':False,
        'checks':{'paired_reference_weather':pair_audit,'trusted_issue_verified_grid_state_cells':trusted_cells,
            'accepted_model_source_issue_time_qualification':False},
        'reasons':['A matched weather case is not model or forecast-skill qualification; independent issue dates and seasons are still needed.',
            'No grid-matched, exact previous-standard-noon observed/overwintered state with verified issue-time availability is accepted.',
            'The selected-source model uses prior-day retrospective ERA5 research features. Forecast-day HRDPS features and state lineage require a separate trained/evaluated contract.',
            'No accepted cross-source/issue-time model validation decision exists.']}


def run(workspace, directory):
    forecast_dir=workspace/'data/processed/hrdps_live_research_2026-10-16_stateful'
    manifest=json.loads((forecast_dir/'manifest.json').read_text())
    forecast_path=forecast_dir/'hourly_weather.parquet'
    expected=next(r['sha256'] for r in manifest['outputs'] if r['path'].endswith('/hourly_weather.parquet'))
    if digest(forecast_path)!=expected:
        raise ValueError('Pinned forecast input changed')
    seed_path=forecast_dir/'state_checkpoint.json'
    seed_expected=next(r['sha256'] for r in manifest['outputs'] if r['path'].endswith('/state_checkpoint.json'))
    if digest(seed_path)!=seed_expected:
        raise ValueError('Pinned state checkpoint changed')
    grid_path=workspace/'reports/week_4_data_2026-10-16/current_boundary_centroid_grid.csv'
    seeds=json.loads((forecast_dir/'state_checkpoint.json').read_text())
    if digest(grid_path)!=seeds['_metadata']['grid_sha256']:
        raise ValueError('Forecast/reference centroid grid changed')
    summary={'created_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'forecast_manifest_sha256':digest(forecast_dir/'manifest.json'),
        'grid_sha256':digest(grid_path),'station_code_check':station_code_diagnostic(directory)}
    reference_path=directory/'era5_land_20261015_17.nc'
    acquisition=json.loads((directory/'era5_acquisition.json').read_text())
    pair_audit={'paired_days':0,'paired_rows':0,'status':'reference acquisition incomplete'}
    if acquisition.get('status')=='downloaded':
        if digest(reference_path)!=acquisition['sha256']:
            raise ValueError('Reference download hash changed')
        parts=directory/'reference_parts';parts.mkdir(exist_ok=True)
        if zipfile.is_zipfile(reference_path):
            paths=[]
            with zipfile.ZipFile(reference_path) as z:
                for name in z.namelist():
                    if name.endswith('.nc'):
                        target=parts/Path(name).name;target.write_bytes(z.read(name));paths.append(target)
        else:paths=[reference_path]
        reference=sample_reference(paths,pd.read_csv(grid_path))
        reference.to_parquet(directory/'hourly_reference.parquet',index=False)
        forecast=pd.read_parquet(forecast_path)
        paired,pair_audit=pair_weather(forecast,reference,manifest['issue_time_utc'])
        summary['weather_metrics']=weather_metrics(paired)
        summary['weather_metrics_by_valid_hour']=[{'valid_time_utc':stamp.isoformat(),'metrics':weather_metrics(g)} for stamp,g in paired.groupby('valid_time_utc')]
        paired.to_parquet(directory/'paired_weather.parquet',index=False)
    summary['qualification']=qualification_decision(pair_audit,0)
    summary['reference_acquisition_status']=acquisition.get('status')
    summary['code_sha256']=digest(Path(__file__))
    save_json(directory/'qualification_results.json',summary)
    live=summary['qualification'].copy()
    live['checks']={'contemporaneous_ERA5_HRDPS_reference_days':pair_audit.get('paired_days',0),
        'matched_post_issue_cell_times':pair_audit.get('paired_rows',0),'independent_forecast_runs':pair_audit.get('distinct_runs',0),
        'trusted_observed_state_cells':0,'model_live_qualified':False}
    live['evidence']={'report':'live_qualification_2026-11-01/qualification_results.json','sha256':digest(directory/'qualification_results.json')}
    live['scope']='One archived forecast run checked against hindsight ERA5-Land; not live model qualification.'
    save_json(directory/'live_readiness.json',live)
    print(json.dumps(summary['qualification'],indent=2),flush=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();run(a.workspace.resolve(),a.output_dir.resolve())
