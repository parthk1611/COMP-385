"""Versioned 1 km quadrature of selected landscapes over the fixed 10 km grid."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from pyproj import Transformer
import requests

from scripts.prepare_historical_weather_v2 import ROOT, REPORT, digest, save
from scripts.prepare_ignition_pilot import SCANFI, SCANFI_FILES, CONIFERS

OUTPUT=ROOT/'data/processed/selected_provincial_static_2025'


def quadrature(grid):
    offsets=np.arange(500,10000,1000)
    dx,dy=np.meshgrid(offsets,offsets)
    return grid.grid_x_m.to_numpy()[:,None]+dx.ravel(),grid.grid_y_m.to_numpy()[:,None]+dy.ravel()


def sample_tiles(paths,x,y):
    result=np.full(x.size,np.nan,dtype='float32');xx,yy=x.ravel(),y.ravel();records=[]
    for path in sorted(paths):
        with rasterio.open(path) as source:
            sx,sy=Transformer.from_crs(3978,source.crs,always_xy=True).transform(xx,yy)
            inside=(sx>=source.bounds.left)&(sx<source.bounds.right)&(sy>source.bounds.bottom)&(sy<=source.bounds.top)&~np.isfinite(result)
            if not inside.any():continue
            rr,cc=rasterio.transform.rowcol(source.transform,sx[inside],sy[inside]);rr,cc=np.asarray(rr),np.asarray(cc)
            values=source.read(1,masked=True).astype('float32').filled(np.nan)
            selected=values[rr,cc];result[np.flatnonzero(inside)]=selected
            records.append({'path':str(path),'sha256':digest(path),'sampled_positions':int(inside.sum()),'crs':str(source.crs)})
    return result.reshape(x.shape),records


def fuel_fractions(values):
    valid=np.isfinite(values);counts=valid.sum(axis=1)
    codes=sorted(int(c) for c in np.unique(values[valid]))
    result={'fbp_sample_valid_fraction':counts/values.shape[1]}
    for code in codes:
        result[f'fbp_2024_code_{code}_share']=np.divide((values==code).sum(axis=1),counts,out=np.full(len(values),np.nan),where=counts>0)
    return pd.DataFrame(result)


def canopy_summary(layers):
    closure=layers['closure'];total=sum(layers[name] for name in (*CONIFERS,'prcB'));conifer=sum(layers[name] for name in CONIFERS)
    valid=np.isfinite(closure)&(closure>=0)&(closure<=100)&np.isfinite(total)&((total>0)|(closure==0))
    for name in (*CONIFERS,'prcB'):
        valid &= np.isfinite(layers[name])&(layers[name]>=0)&(layers[name]<=100)
    weight=np.where(valid,closure,0);fraction=np.divide(conifer,total,out=np.zeros_like(total),where=total>0)
    denom=weight.sum(axis=1)
    return pd.DataFrame({'scanfi_species_valid_fraction':valid.mean(axis=1),
      'scanfi_2020_closure_sample_mean_pct':np.divide(weight.sum(axis=1),valid.sum(axis=1),out=np.full(len(weight),np.nan),where=valid.sum(axis=1)>0),
      'scanfi_2020_canopy_weighted_conifer_pct':np.divide(100*(weight*fraction).sum(axis=1),denom,out=np.full(len(weight),np.nan),where=denom>0)})


def local_source(url,filename,identity):
    folder=ROOT/'data/raw/scanfi_v1_2_national';folder.mkdir(parents=True,exist_ok=True)
    target=folder/filename;metadata=target.with_suffix('.json');partial=target.with_suffix('.tif.partial');partial_meta=target.with_suffix('.partial.json')
    if target.exists() and metadata.exists():
        record=json.loads(metadata.read_text())
        if record['identity']!=identity or digest(target)!=record['sha256']:raise ValueError('Pinned national SCANFI copy changed')
        return target,record
    if partial.exists() and (not partial_meta.exists() or json.loads(partial_meta.read_text())!=identity):partial.unlink()
    save(partial_meta,identity)
    for attempt in range(3):
        start=partial.stat().st_size if partial.exists() else 0
        headers={'Range':f'bytes={start}-','If-Range':identity['ETag']} if start else {}
        try:
            response=requests.get(url,headers=headers,stream=True,timeout=(20,90));response.raise_for_status()
            if response.headers.get('ETag')!=identity['ETag']:raise ValueError('SCANFI source identity changed during transfer')
            append=bool(start and response.status_code==206)
            if append and not response.headers.get('Content-Range','').startswith(f'bytes {start}-'):raise ValueError('Invalid range response')
            mode='ab' if append else 'wb'
            with partial.open(mode) as handle:
                last=handle.tell()
                for chunk in response.iter_content(4*1024*1024):
                    handle.write(chunk)
                    if handle.tell()-last>=512*1024*1024:
                        print('SCANFI download',filename,handle.tell(),flush=True);last=handle.tell()
            response.close()
            expected=int(identity['Content-Length']) if identity['Content-Length'] else None
            if expected is not None and partial.stat().st_size!=expected:raise requests.RequestException('Incomplete national file')
            partial.replace(target);record={'url':url,'identity':identity,'path':str(target),'sha256':digest(target),'bytes':target.stat().st_size}
            save(metadata,record);print('SCANFI source complete',filename,flush=True);return target,record
        except requests.RequestException:
            if attempt==2:raise
    raise RuntimeError('National source download failed')


def remote_layer(name,filename,grid,output):
    cache=output/'scanfi_cache';cache.mkdir(exist_ok=True);path=cache/f'{name}.npy';meta=cache/f'{name}.json'
    url=f'{SCANFI}/{filename}'
    response=requests.head(url,timeout=60);response.raise_for_status()
    identity={k:response.headers.get(k) for k in ('ETag','Last-Modified','Content-Length')}
    if path.exists() and meta.exists():
        record=json.loads(meta.read_text())
        if record['identity']!=identity or digest(path)!=record['sample_sha256']:raise ValueError('Remote SCANFI identity/cache changed')
        return np.load(path),record
    left=int(grid.grid_x_m.min());top=int(grid.grid_y_m.max()+10000)
    width=int((grid.grid_x_m.max()+10000-left)//1000);height=int((top-grid.grid_y_m.min())//1000)
    transform=from_origin(left,top,1000,1000);x,y=quadrature(grid);rr,cc=rasterio.transform.rowcol(transform,x.ravel(),y.ravel())
    local,source_record=local_source(url,filename,identity)
    with rasterio.Env(GDAL_NUM_THREADS='1'):
        with rasterio.open(local) as source:
            with WarpedVRT(source,crs='EPSG:3978',transform=transform,width=width,height=height,resampling=Resampling.nearest,warp_mem_limit=128) as vrt:
                raster=vrt.read(1,masked=True).astype('float32').filled(np.nan)
            values=raster[np.asarray(rr),np.asarray(cc)].reshape(x.shape)
            record={'url':url,'identity':identity,'national_source':source_record,'native_crs':source.crs.to_wkt(),'native_overviews':source.overviews(1),'method':'Nearest-neighbour 1 km quadrature in EPSG:3978; 100 samples per cell, not exact full native-pixel area means'}
    np.save(path,values);record['sample_sha256']=digest(path);save(meta,record)
    print('SCANFI sampled',name,flush=True)
    return values,record


def run(output=OUTPUT):
    if (output/'manifest.json').exists():raise FileExistsError('Completed static dataset exists')
    output.mkdir(parents=True,exist_ok=True)
    grid_path=REPORT/'current_boundary_centroid_grid.csv';grid=pd.read_csv(grid_path);x,y=quadrature(grid)
    config={'code_sha256':digest(Path(__file__)),'grid_sha256':digest(grid_path),'mode':'fixed-landscape retrospective study',
       'sampling':'100 deterministic equal-area 1 km strata centres per 10 km cell; native categorical nearest sampling. Fractions/terrain statistics are quadrature estimates.',
       'versions':{'FBP':'2024','SCANFI':'v1.2/2020','MRDEM':'30m DTM'},'historical_2010_2019_join':False}
    save(output/'config.json',config)
    fuel_path=output/'fuel_samples.npy';terrain_path=output/'terrain_samples.npy'
    if fuel_path.exists():
        fuel=np.load(fuel_path);fuel_sources=json.loads((output/'fuel_sources.json').read_text())
    else:
        fuel,fuel_sources=sample_tiles((ROOT/'data/raw/ontario/fbp/2024').glob('*.tif'),x,y);np.save(fuel_path,fuel);save(output/'fuel_sources.json',fuel_sources)
    print('fuel done',flush=True)
    if terrain_path.exists():
        terrain=np.load(terrain_path);terrain_sources=json.loads((output/'terrain_sources.json').read_text())
    else:
        terrain,terrain_sources=sample_tiles((ROOT/'data/raw/ontario/mrdem_30m').glob('*.tif'),x,y);np.save(terrain_path,terrain);save(output/'terrain_sources.json',terrain_sources)
    print('terrain done',flush=True)
    layers={};remote=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(remote_layer,name,filename,grid,output):name for name,filename in SCANFI_FILES.items()}
        for future in as_completed(futures):
            name=futures[future];values,record=future.result();layers[name]=values;remote.append(record)
    remote.sort(key=lambda record:record['url'])
    result=pd.concat([grid,fuel_fractions(fuel),canopy_summary(layers)],axis=1)
    valid=np.isfinite(terrain);count=valid.sum(axis=1);result['mrdem_sample_valid_fraction']=count/100
    result['mrdem_elevation_sample_mean_m']=np.divide(np.where(valid,terrain,0).sum(axis=1),count,out=np.full(len(grid),np.nan),where=count>0)
    centred=terrain-result.mrdem_elevation_sample_mean_m.to_numpy()[:,None]
    result['mrdem_elevation_sample_std_m']=np.sqrt(np.divide(np.where(valid,centred**2,0).sum(axis=1),count,out=np.full(len(grid),np.nan),where=count>0))
    dy,dx=np.gradient(terrain.reshape(-1,10,10),1000.,1000.,axis=(1,2));slope=np.hypot(dx,dy);result['mrdem_sampled_1km_slope_mean_pct']=100*np.nanmean(slope,axis=(1,2))
    result['fbp_version']='2024';result['scanfi_version']='v1.2_2020';result['static_version']='selected-static-quadrature-v1'
    path=output/'static_features.parquet';result.to_parquet(path,index=False)
    summary={'config':config,'rows':len(result),'grid_ids_unique':bool(result.grid_id.is_unique),'fuel_sources':fuel_sources,'terrain_sources':terrain_sources,'scanfi_sources':remote,
     'quality':{'missing_fuel_cells':int((result.fbp_sample_valid_fraction==0).sum()),'missing_terrain_cells':int((count==0).sum()),'missing_scanfi_cells':int((result.scanfi_species_valid_fraction==0).sum()),'negative_elevation_samples':int((terrain<0).sum())},
     'output':{'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size},'full_native_area_aggregation':False,'full_remote_source_sha256_available':True}
    save(output/'manifest.json',summary);save(REPORT/'provincial_static_build_audit.json',summary);print('static build complete',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=OUTPUT);run(parser.parse_args().output_dir)
