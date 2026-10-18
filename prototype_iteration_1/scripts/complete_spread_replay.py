"""Restore versioned local landscapes and replay the fixed research simulator."""
from __future__ import annotations
import argparse,json,logging,sys
from pathlib import Path
from multiprocessing import get_context
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject,transform_bounds,Resampling
from scripts.prepare_historical_weather_v2 import ROOT,digest,save

SPREAD=ROOT/'team_repository/capability_2_fire_spread'
sys.path.insert(0,str(SPREAD/'scripts'))
import simulate_spread as simulator
import run_spread_replay as replay
import export_spread_viewer_data as exporter
import spread_common as common
from shapely.geometry import shape,mapping

REPORT=ROOT/'reports/week_5_completion_2026-10-16'
LANDSCAPES=ROOT/'data/processed/spread_landscapes_restored_v2'
RESULT=ROOT/'data/processed/spread_replay_corrected_v2'


def intersects(a,b):return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]


def source_index(folder):
    result=[]
    for path in sorted(folder.glob('*.tif')):
        with rasterio.open(path) as ds:bounds=transform_bounds(ds.crs,3978,*ds.bounds,densify_pts=21)
        result.append((path,bounds))
    return result


def warped_window(window,index,method,nodata):
    shape=(window['rows'],window['columns']);transform=from_origin(window['west'],window['north'],90,90)
    bounds=(window['west'],window['south'],window['east'],window['north']);result=np.full(shape,nodata,dtype='float32');used=[]
    for path,source_bounds in index:
        if not intersects(bounds,source_bounds):continue
        destination=np.full(shape,nodata,dtype='float32')
        with rasterio.open(path) as ds:
            reproject(rasterio.band(ds,1),destination,src_transform=ds.transform,src_crs=ds.crs,src_nodata=ds.nodata,dst_transform=transform,dst_crs=3978,dst_nodata=nodata,resampling=method,num_threads=1)
        valid=destination!=nodata;result[valid]=destination[valid];used.append(str(path))
    return result,used


def restore():
    if (LANDSCAPES/'manifest.json').exists():raise FileExistsError('Completed versioned landscapes exist')
    frozen=json.loads((REPORT/'completion_protocol.json').read_text());old=json.loads((SPREAD/'data/raw/fuel_terrain/fuel_windows_manifest.json').read_text())
    windows=[w for w in old['windows'] if w['fire_id'] in set(frozen['spread_calibration_fires']+frozen['spread_holdout_fires'])]
    output=LANDSCAPES/'fuel_terrain/windows';output.mkdir(parents=True,exist_ok=True)
    fuel=source_index(ROOT/'data/raw/ontario/fbp/2024');terrain=source_index(ROOT/'data/raw/ontario/mrdem_30m')
    records=[];sources=set()
    for i,w in enumerate(windows,1):
        row={'fire_id':w['fire_id'],'outputs':[]}
        for kind,index,method,nodata in [('fbp_fuel',fuel,Resampling.nearest,-9999),('mrdem_dtm',terrain,Resampling.bilinear,-32767)]:
            data,used=warped_window(w,index,method,nodata);sources.update(used);valid=data!=nodata
            if valid.mean()<.95:raise ValueError(f'Insufficient {kind} landscape support {w["fire_id"]}: {valid.mean()}')
            path=output/f'{w["fire_id"]}_{kind}_90m.tif'
            with rasterio.open(path,'w',driver='GTiff',count=1,dtype='float32',height=w['rows'],width=w['columns'],crs=3978,transform=from_origin(w['west'],w['north'],90,90),nodata=nodata,compress='deflate') as ds:ds.write(data,1)
            row['outputs'].append({'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size,'valid_fraction':float(valid.mean()),'kind':kind})
        records.append(row);print('restored',i,len(windows),w['fire_id'],flush=True)
    # Loader reads geometry/filenames only; no old download/byte identity is copied.
    save(LANDSCAPES/'fuel_terrain/fuel_windows_manifest.json',{'windows':windows,'mode':'regenerated from pinned local sources, not byte restoration'})
    original=json.loads((ROOT/'data/raw/ontario/manifest.json').read_text());known={str(ROOT/v['path']):v['sha256'] for v in original['files']}
    ledger=[]
    for name in sorted(sources):
        path=Path(name);actual=digest(path)
        if name not in known or actual!=known[name]:raise ValueError('Pinned landscape source changed')
        ledger.append({'path':name,'sha256':actual})
    save(LANDSCAPES/'manifest.json',{'records':records,'sources':ledger,'source_versions':{'fuel':'FBP2024','terrain':'MRDEM30m DTM'},'method':'Nearest fuel / bilinear MRDEM onto archived90m geometry. Shared native tiles can have small uncovered edge strips; retain coverage/nodata. New provenance, not old-byte restoration.','outcome_assistance':'Archived final-perimeter domains and optional scar repair: reconstruction only','code_sha256':digest(Path(__file__))})


def prepare_perimeters():
    target=LANDSCAPES/'interim/spread_fire_perimeters.geojson'
    if target.exists():raise FileExistsError('Versioned perimeter cache exists')
    source=ROOT/'data/raw/week_2_completion/fire_disturbance/fire_disturbance_area.geojson'
    manifest=json.loads((source.parent/'manifest.json').read_text());expected=next(v for v in manifest['layers'] if v['filename']==source.name)['sha256']
    if digest(source)!=expected:raise ValueError('Pinned area source changed')
    plan=json.loads((REPORT/'completion_protocol.json').read_text());wanted=set(plan['spread_calibration_fires']+plan['spread_holdout_fires']);features=[];repaired=0
    for feature in json.loads(source.read_text())['features']:
        props=feature['properties'];key=f"{props['FIRE_YEAR']}_{props['FIRE_DISTURBANCE_AREA_IDENT']}"
        if key not in wanted:continue
        geometry=shape(feature['geometry'])
        if not geometry.is_valid:geometry=geometry.buffer(0);repaired+=1
        features.append({'type':'Feature','properties':{'fire_id':key},'geometry':mapping(geometry)})
    if len(features)!=len(wanted) or {v['properties']['fire_id'] for v in features}!=wanted:raise ValueError('Ambiguous/missing selected perimeters')
    target.parent.mkdir(parents=True,exist_ok=True);save(target,{'type':'FeatureCollection','features':features})
    save(LANDSCAPES/'perimeter_manifest.json',{'source':str(source),'source_sha256':expected,'path':str(target),'sha256':digest(target),'fires':len(features),'invalid_repaired_by_buffer0':repaired,'method':'Same geometric repair as original catalogue; selected frozen IDs only. Outcome-assisted reconstruction input, never ignition predictor.','code_sha256':digest(Path(__file__))})


def activate_landscapes():
    simulator.RAW=LANDSCAPES
    common.INTERIM=LANDSCAPES/'interim'


def worker(job):
    activate_landscapes()
    return replay._worker(job)


def run_replay():
    if RESULT.exists():raise FileExistsError('Completed replay output exists')
    frozen=json.loads((REPORT/'completion_protocol.json').read_text());manifest=json.loads((LANDSCAPES/'manifest.json').read_text())
    for record in manifest['records']:
        for item in record['outputs']:
            if digest(Path(item['path']))!=item['sha256']:raise ValueError('Regenerated landscape changed')
    calibration=frozen['spread_calibration_fires'];holdout=frozen['spread_holdout_fires'];RESULT.mkdir()
    with get_context('spawn').Pool(4) as pool:
        jobs=[(fire,ros,flank) for fire in calibration for ros in replay.SCALES for flank in replay.FLANK_SCALES]
        rows=[]
        for i,part in enumerate(pool.imap_unordered(worker,jobs),1):
            rows+=part
            if i%24==0:print('calibration jobs',i,len(jobs),flush=True)
        tuning=pd.DataFrame(rows);settings={key:replay.summarise(group) for key,group in tuning.groupby(['ros_scale','flank_scale'])}
        best=min(settings,key=lambda key:replay.tuning_error(settings[key]));print('frozen chosen scales',best,flush=True)
        save(RESULT/'calibration_freeze.json',{'chosen_ros_scale':best[0],'chosen_flank_scale':best[1],'landscapes_sha256':digest(LANDSCAPES/'manifest.json'),'calibration_fires':calibration,'holdout_not_used_for_selection':True})
        test=pd.DataFrame([row for part in pool.imap_unordered(worker,[(fire,*best) for fire in holdout]) for row in part])
    tuning.to_csv(RESULT/'spread_simulator_calibration_steps_v1.csv',index=False);test.to_csv(RESULT/'spread_simulator_holdout_steps_v1.csv',index=False)
    long=replay.summarise(test[test.observed_distance_m>=replay.LONG_RUN_M]);summary={'propagation_revision':'surface-barrier-clearance-v2','mode':'retrospective_reconstruction_final_perimeter_assisted','forecast_validation':False,'new_landscape_lineage':True,'calibration_fires':calibration,'holdout_fires':holdout,'chosen_ros_scale':best[0],'chosen_flank_scale':best[1],'holdout':replay.summarise(test),'holdout_steps_with_observed_head_run_of_1500_m_or_more':long,'calibration_by_setting':{str(k):v for k,v in settings.items()},'limits':['Previously inspected holdout; corrected-revision regression reconstruction, not pristine forecast validation','Archived final-perimeter domains/scar repair and retrospective weather','1.3area heuristic retained from published implementation, not independently justified on untouched data','Missing source edge strips retained; no equivalence to unavailable old TIFFbytes claimed'],'source_sha256':digest(Path(__file__))}
    save(RESULT/'spread_simulator_v1_scores.json',summary);save(REPORT/'corrected_spread_results.json',summary);print(json.dumps(summary['holdout']),flush=True)


def viewer():
    activate_landscapes();scores=json.loads((RESULT/'spread_simulator_v1_scores.json').read_text());settings=simulator.Settings(ros_scale=scores['chosen_ros_scale'],flank_scale=scores['chosen_flank_scale'],repair_burn_scar=True)
    fires=pd.read_csv(SPREAD/'data/processed/ontario_fire_spread_fires_v1.csv',dtype={'fire_id':str}).set_index('fire_id')
    holdout=pd.read_csv(RESULT/'spread_simulator_holdout_steps_v1.csv');cal=pd.read_csv(RESULT/'spread_simulator_calibration_steps_v1.csv');cal=cal[np.isclose(cal.ros_scale,settings.ros_scale)&np.isclose(cal.flank_scale,settings.flank_scale)]
    shapes={r['fire_id']:next(v for v in json.loads((LANDSCAPES/'fuel_terrain/fuel_windows_manifest.json').read_text())['windows'] if v['fire_id']==r['fire_id']) for r in json.loads((LANDSCAPES/'manifest.json').read_text())['records']}
    chosen=[]
    for table in [holdout,cal]:
        counts=table.groupby('fire_id').size();counts=counts[[shapes[f]['rows']*shapes[f]['columns']<=exporter.MAX_GRID_CELLS for f in counts.index]].sort_values(ascending=False,kind='stable')
        chosen += [(fire,table[table.fire_id==fire]) for fire in counts.index[:2]]
    replay._shared['detections']=dict(tuple(pd.read_csv(SPREAD/'data/processed/ontario_fire_spread_detections_v1.csv.gz',dtype={'fire_id':str},usecols=['fire_id','observation','x','y']).groupby('fire_id')))
    payload={'settings':{'mode':'retrospective_reconstruction_final_perimeter_assisted','forecastValidated':False,'rosScale':settings.ros_scale,'flankScale':settings.flank_scale,'cell375':375,'detectableShare':replay.DETECTABLE_SHARE,'ignitionHours':6,'basemapCredit':'Fuel/terrain grid; no external basemap'},'scores':{'holdout':scores['holdout'],'longRuns':scores['holdout_steps_with_observed_head_run_of_1500_m_or_more'],'calibrationFires':len(scores['calibration_fires']),'holdoutFires':scores['holdout']['fires']},'fires':[exporter.export_fire(fire,settings,fires.loc[fire],table,logging.getLogger('viewer'),False) for fire,table in chosen]}
    script='window.SPREAD_VIEWER_DATA = '+json.dumps(payload,separators=(',',':'))+';';template=exporter.TEMPLATE.read_text();html=template.replace(exporter.DATA_TAG,'<script>'+script+'</script>')
    html=html.replace('new MutationObserver(requestDraw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });','const themeRoot = document.documentElement; if (themeRoot instanceof Node) new MutationObserver(requestDraw).observe(themeRoot, { attributes: true, attributeFilter: ["data-theme"] });')
    html=html.replace('</style>','</style>'+'<div style="padding:12px;background:#ffe9bc;color:#3b2b12;font:14px system-ui">Corrected research reconstruction — final-perimeter assisted; not validated as a live forecast. 1/3/6-hour controls are simulation outputs, not validated horizon skill.</div>',1)
    path=REPORT/'corrected_spread_viewer.html';path.write_text(html);save(REPORT/'spread_viewer_audit.json',{'path':str(path),'sha256':digest(path),'fires':[p['id'] for p in payload['fires']],'revision':'surface-barrier-clearance-v2','forecast_validated':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['restore','perimeters','replay','viewer']);a=parser.parse_args();{'restore':restore,'perimeters':prepare_perimeters,'replay':run_replay,'viewer':viewer}[a.stage]()
