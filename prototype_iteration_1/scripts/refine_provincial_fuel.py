"""Replace sampled fuel shares with area-weighted native 30 m pixel fractions."""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from scripts.prepare_historical_weather_v2 import ROOT,REPORT,digest,save
from scripts.prepare_provincial_static import OUTPUT as SAMPLED
OUTPUT=ROOT/'data/processed/selected_provincial_static_native_2025'


def weighted_codes(values,transform,bounds):
    left,bottom,right,top=bounds
    if transform.b or transform.d or transform.a<=0 or transform.e>=0:raise ValueError('Expected north-up projected fuel raster')
    c0=max(0,math.floor((left-transform.c)/transform.a));c1=min(values.shape[1],math.ceil((right-transform.c)/transform.a))
    r0=max(0,math.floor((transform.f-top)/abs(transform.e)));r1=min(values.shape[0],math.ceil((transform.f-bottom)/abs(transform.e)))
    if c1<=c0 or r1<=r0:return {},0.
    xl=transform.c+np.arange(c0,c1)*transform.a;yt=transform.f+np.arange(r0,r1)*transform.e
    wx=np.maximum(0,np.minimum(xl+transform.a,right)-np.maximum(xl,left))
    wy=np.maximum(0,np.minimum(yt,top)-np.maximum(yt+transform.e,bottom))
    areas=wy[:,None]*wx[None,:];window=values[r0:r1,c0:c1];valid=np.isfinite(window)&(areas>0)
    if not valid.any():return {},0.
    if (window[valid]<0).any() or not np.equal(window[valid],np.floor(window[valid])).all():raise ValueError('Invalid categorical fuel code')
    totals=np.bincount(window[valid].astype('int32'),weights=areas[valid]);return {int(i):float(totals[i]) for i in np.flatnonzero(totals)},float(areas[valid].sum())


def native_fuel(grid):
    frame=grid[['grid_id','grid_x_m','grid_y_m']].copy()
    frame['tile']=[f'x{math.floor(x/100000)*100000:+08d}_y{math.floor(y/100000)*100000:+08d}' for x,y in zip(frame.grid_x_m,frame.grid_y_m)]
    rows=[];sources=[]
    for tile,cells in frame.groupby('tile',sort=True):
        path=ROOT/'data/raw/ontario/fbp/2024'/f'{tile}.tif'
        if not path.exists():
            for cell in cells.itertuples():rows.append({'grid_id':cell.grid_id,'fbp_native_valid_area_fraction':0.})
            continue
        with rasterio.open(path) as ds:
            if ds.crs.to_epsg()!=3978:raise ValueError('Fuel raster must use EPSG:3978')
            values=ds.read(1,masked=True).astype('float32').filled(np.nan)
            for cell in cells.itertuples():
                totals,area=weighted_codes(values,ds.transform,(cell.grid_x_m,cell.grid_y_m,cell.grid_x_m+10000,cell.grid_y_m+10000))
                row={'grid_id':cell.grid_id,'fbp_native_valid_area_fraction':area/1e8}
                row.update({f'fbp_2024_code_{code}_share':count/area for code,count in totals.items()});rows.append(row)
        sources.append({'path':str(path),'sha256':digest(path)})
    result=pd.DataFrame(rows);columns=[c for c in result if c.startswith('fbp_2024_code_')]
    result.loc[result.fbp_native_valid_area_fraction>0,columns]=result.loc[result.fbp_native_valid_area_fraction>0,columns].fillna(0.)
    result=result.set_index('grid_id').reindex(grid.grid_id).reset_index()
    if not np.allclose(result.loc[result.fbp_native_valid_area_fraction>0,columns].sum(axis=1),1.):raise ValueError('Fuel fractions do not sum to one')
    return result,sources


def run(output=OUTPUT,fuel_only=False):
    if (output/'manifest.json').exists():raise FileExistsError('Completed native static dataset exists')
    output.mkdir(parents=True,exist_ok=True);grid_path=REPORT/'current_boundary_centroid_grid.csv';grid=pd.read_csv(grid_path)
    cache=output/'native_fuel.parquet';metadata=output/'native_fuel_manifest.json'
    if cache.exists() and metadata.exists():
        fuel_manifest=json.loads(metadata.read_text())
        if digest(cache)!=fuel_manifest['sha256'] or digest(grid_path)!=fuel_manifest['grid_sha256']:raise ValueError('Native fuel cache changed')
        fuel=pd.read_parquet(cache)
    else:
        fuel,sources=native_fuel(grid);fuel.to_parquet(cache,index=False)
        fuel_manifest={'path':str(cache),'sha256':digest(cache),'grid_sha256':digest(grid_path),'sources':sources,'method':'Exact native pixel intersection area within one nominal source tile per cell; uncovered boundary strips/nodata retained in valid-area coverage; no cross-tile double counting','code_sha256':digest(Path(__file__))};save(metadata,fuel_manifest)
    if fuel_only:print('native fuel prepared',len(fuel),flush=True);return
    sampled_manifest=json.loads((SAMPLED/'manifest.json').read_text());sampled=pd.read_parquet(SAMPLED/'static_features.parquet')
    if digest(SAMPLED/'static_features.parquet')!=sampled_manifest['output']['sha256']:raise ValueError('Sampled forest/terrain changed')
    remove=[c for c in sampled if c.startswith('fbp_2024_code_') or c=='fbp_sample_valid_fraction']
    result=sampled.drop(columns=remove).merge(fuel,on='grid_id',validate='one_to_one',sort=False)
    result['static_version']='selected-static-native-fuel-v2';path=output/'static_features.parquet';result.to_parquet(path,index=False)
    summary={'rows':len(result),'sampled_static_manifest_sha256':digest(SAMPLED/'manifest.json'),'native_fuel_manifest_sha256':digest(metadata),'code_sha256':digest(Path(__file__)),
      'fuel_method':fuel_manifest['method'],'forest_terrain_method':'100 deterministic 1 km strata centres per cell; continuous landscape quadrature estimates, not full native-area means',
      'min_fuel_valid_area_fraction':float(result.fbp_native_valid_area_fraction.min()),'zero_fuel_support_cells':int((result.fbp_native_valid_area_fraction==0).sum()),
      'output':{'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size},'operationally_validated':False}
    save(output/'manifest.json',summary);save(REPORT/'native_static_build_audit.json',summary);print('native static complete',len(result),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=OUTPUT);parser.add_argument('--fuel-only',action='store_true');args=parser.parse_args();run(args.output_dir,args.fuel_only)
