"""Sample pinned provincial ERA5 at 10 km cell centres and derive daily research FWI."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import rasterio
import tzfpy

from scripts.prepare_selected_weather import FWI, deaccumulate_era5, humidity, wind
from scripts.prepare_historical_weather_v2 import ROOT, REPORT, digest, save

OUTPUT = ROOT / 'data/processed/selected_provincial_2025'


def standard_offsets(grid: pd.DataFrame):
    names = [tzfpy.get_tz(lon, lat) for lon, lat in zip(grid.centroid_longitude, grid.centroid_latitude)]
    offsets = []
    for name in names:
        if not name:
            raise ValueError('Timezone unresolved')
        zone = ZoneInfo(name)
        values = [(datetime(2025, month, 1, tzinfo=zone).utcoffset() - datetime(2025, month, 1, tzinfo=zone).dst()).total_seconds() / 3600 for month in (1, 7)]
        if values[0] != values[1] or values[0] not in (-5, -6):
            raise ValueError('Unexpected Ontario standard-noon offset')
        offsets.append(int(values[0]))
    return names, np.asarray(offsets)


def sampled_inputs(paths: list[Path], grid: pd.DataFrame):
    parts = {name: [] for name in ('t2m','d2m','u10','v10','tp')}; time_parts=[]; geometry=None
    for path in paths:
        for name in parts:
            with rasterio.open(f'netcdf:"{path}":{name}') as ds:
                tags=ds.tags()
                expected={'t2m':'K','d2m':'K','u10':'m s**-1','v10':'m s**-1','tp':'m'}
                if tags.get(name+'#units') != expected[name] or tags.get(name+'#GRIB_stepType') != ('accum' if name=='tp' else 'instant'):
                    raise ValueError('Unexpected weather unit/aggregation')
                if name in ('u10','v10') and tags.get(name+'#GRIB_uvRelativeToGrid') != '0':
                    raise ValueError('ERA5 wind orientation is not earth-relative')
                geom=(ds.height,ds.width,ds.transform)
                if geometry is not None and geom!=geometry:raise ValueError('Weather grid changed')
                geometry=geom
                times=pd.to_datetime([int(ds.tags(i)['NETCDF_DIM_valid_time']) for i in range(1,ds.count+1)],unit='s',utc=True)
                if name=='t2m':time_parts.append(times)
                elif not times.equals(time_parts[-1]):raise ValueError('Variable clock mismatch')
                rr,cc=rasterio.transform.rowcol(ds.transform,grid.centroid_longitude.to_numpy(),grid.centroid_latitude.to_numpy())
                rr,cc=np.asarray(rr),np.asarray(cc)
                if ((rr<0)|(rr>=ds.height)|(cc<0)|(cc>=ds.width)).any():raise ValueError('Model centre outside input box')
                values=ds.read(masked=True).astype('float32').filled(np.nan)
                parts[name].append(values[:,rr,cc]);del values
        print('sampled',path.name,flush=True)
    times=time_parts[0].append(time_parts[1:])
    if not times.is_unique or not times.is_monotonic_increasing or not ((times[1:]-times[:-1])==pd.Timedelta(hours=1)).all():
        raise ValueError('Provincial hourly clock is incomplete')
    return times,{k:np.concatenate(v) for k,v in parts.items()}


def derive_daily(times, raw, offsets, startup='2025-04-01'):
    n=len(offsets);rain=deaccumulate_era5(times,raw['tp'])
    dates=pd.date_range(times[0].normalize(),times[-1].normalize(),freq='D')
    previous={key:np.full(n,np.nan) for key in ('ffmc','dmc','dc')}
    tables=[]
    for day in dates:
        arrays={name:np.full(n,np.nan) for name in ('temp_c','rh_pct','wind_kmh','wind_from_degrees','rain_24h_mm','ffmc','dmc','dc','isi','bui','fwi')}
        coverage=np.zeros(n,dtype='int8');noon=np.empty(n,dtype='datetime64[ns]')
        for offset in sorted(set(offsets)):
            cells=np.flatnonzero(offsets==offset);instant=day+pd.Timedelta(hours=12-int(offset));idx=times.get_indexer([instant])[0]
            noon[cells]=instant.tz_localize(None).to_datetime64()
            if idx<0:continue
            arrays['temp_c'][cells]=raw['t2m'][idx,cells]-273.15
            arrays['rh_pct'][cells]=humidity(raw['t2m'][idx,cells],raw['d2m'][idx,cells])
            speed,direction=wind(raw['u10'][idx,cells],raw['v10'][idx,cells]);arrays['wind_kmh'][cells]=speed;arrays['wind_from_degrees'][cells]=direction
            indices=times.get_indexer(pd.date_range(instant-pd.Timedelta(hours=23),instant,freq='h'))
            if (indices<0).any():continue
            window=rain[np.ix_(indices,cells)];valid=np.isfinite(window)&(window>=0);count=valid.sum(axis=0)
            coverage[cells]=count;arrays['rain_24h_mm'][cells]=np.where(count==24,np.where(valid,window,0).sum(axis=0),np.nan)
        if day.date().isoformat()==startup:
            previous={key:np.full(n,value) for key,value in FWI.STARTUP.items()}
        valid=(np.isfinite(arrays['temp_c'])&np.isfinite(arrays['rh_pct'])&np.isfinite(arrays['wind_kmh'])&np.isfinite(arrays['rain_24h_mm'])
               &(arrays['temp_c']>=-90)&(arrays['temp_c']<=60)&(arrays['rh_pct']>=0)&(arrays['rh_pct']<=100)&(arrays['wind_kmh']>=0)&np.isfinite(previous['ffmc']))
        if day.date().isoformat()<startup:valid[:]=False
        for i in np.flatnonzero(valid):
            codes=FWI.daily_codes(float(arrays['temp_c'][i]),float(arrays['rh_pct'][i]),float(arrays['wind_kmh'][i]),float(arrays['rain_24h_mm'][i]),day.month,{key:float(value[i]) for key,value in previous.items()})
            for key,value in codes.items():arrays[key][i]=value
        previous={key:arrays[key].copy() for key in previous}
        frame=pd.DataFrame(arrays);frame['date']=day.date().isoformat();frame['noon_time_utc']=pd.to_datetime(noon,utc=True)
        frame['rain_coverage_hours']=coverage;frame['fwi_state_valid']=np.isfinite(arrays['fwi']);frame['cell_position']=np.arange(n)
        tables.append(frame)
    return pd.concat(tables,ignore_index=True)


def run(output=OUTPUT):
    if output.exists():raise FileExistsError('Use an unused output directory')
    output.mkdir(parents=True)
    grid_path=REPORT/'current_boundary_centroid_grid.csv';grid=pd.read_csv(grid_path)
    source=ROOT/'data/raw/week_2_completion/era5_ontario_2025';manifest=json.loads((source/'manifest.json').read_text())
    paths=[]
    for record in manifest['files']:
        path=ROOT/record['path']
        if digest(path)!=record['sha256']:raise ValueError('Pinned ERA5 input changed')
        paths.append(path)
    names,offsets=standard_offsets(grid)
    grid['standard_timezone']=names;grid['standard_offset_hours']=offsets;grid.to_parquet(output/'grid_weather_mapping.parquet',index=False)
    config={'mode':'fixed-landscape_2025_hindcast','sampling':'nearest source pixel at each existing 10 km cell centre; not whole-cell area averaging',
            'grid_sha256':digest(grid_path),'source_manifest_sha256':digest(source/'manifest.json'),'code_sha256':digest(Path(__file__)),
            'fwi_reference_code_sha256':digest(ROOT/'team_repository/capability_2_fire_spread/scripts/fire_weather_index.py'),
            'tzfpy_version':importlib.metadata.version('tzfpy'),'timezone_boundary_data':tzfpy.data_version(),
            'startup':'Research April1 FFMC85/DMC6/DC15; no snow/overwintering/trusted operational state claim',
            'timezone_policy':'Per-centre polygon lookup; fixed standard offset = zone UTC offset minus DST; 2026 boundary lookup is research mapping, not historic-boundary proof',
            'missing_state':'Invalid update permanently invalidates state until explicit startup','input_files':[str(p) for p in paths]}
    save(output/'config.json',config)
    times,raw=sampled_inputs(paths,grid);daily=derive_daily(times,raw,offsets);del raw
    daily['grid_id']=grid.grid_id.to_numpy()[daily.cell_position.to_numpy()];daily=daily.drop(columns='cell_position')
    daily['source_id']='cds_era5_land_2025';daily['weather_version']='provincial-selected-weather-v1'
    path=output/'daily_weather.parquet';daily.to_parquet(path,index=False)
    summary={'config':config,'rows':len(daily),'cells':len(grid),'dates':daily.date.nunique(),'hours':len(times),'valid_fwi_rows':int(daily.fwi_state_valid.sum()),
             'timezone_counts':grid.standard_timezone.value_counts().to_dict(),'standard_offset_counts':{str(k):int(v) for k,v in grid.standard_offset_hours.value_counts().items()},
             'per_field_null_rows':{c:int(daily[c].isna().sum()) for c in ('temp_c','rh_pct','wind_kmh','rain_24h_mm','fwi')},'output':{'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size},'operational_eligible':False}
    save(output/'manifest.json',summary);save(REPORT/'provincial_weather_build_audit.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='config'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=OUTPUT)
    run(parser.parse_args().output_dir)
