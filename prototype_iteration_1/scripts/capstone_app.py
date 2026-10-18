"""Loopback-only capstone research dashboard with fail-closed live ignition."""
from __future__ import annotations
import argparse,io,json,re
from pyproj import Transformer
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import numpy as np
import pandas as pd
from scripts.prepare_historical_weather_v2 import ROOT,digest,save

REPORT=ROOT/'reports/week_5_completion_2026-10-16'
REVIEW=ROOT/'reports/week_5_final_review_2026-10-16'
HISTORICAL=ROOT/'data/processed/ignition_models_week5_v1/temporal_final_predictions.parquet'
SELECTED=ROOT/'data/processed/selected_2025_models_v1/temporal_final_predictions.parquet'
LIVE=ROOT/'data/processed/hrdps_live_research_2026-10-16_stateful'


def assess_live_inputs(era_dates,forecast_dates,seeds,model_qualification):
    trusted=sum(v.get('trusted') is True and v.get('state_kind')=='observed' for k,v in seeds.items() if k!='_metadata')
    paired=sorted(set(era_dates)&set(forecast_dates));checks={'contemporaneous_ERA5_HRDPS_reference_days':len(paired),'trusted_observed_state_cells':trusted,'model_live_qualified':model_qualification is True}
    reasons=[]
    if not paired:reasons.append('No coincident ERA5/HRDPS reference dates for measured forecast-source parity')
    if trusted==0:reasons.append('Available FWI checkpoints are forecast-derived research states, not trusted observed/overwintered initial conditions')
    if model_qualification is not True:reasons.append('Selected-source model is qualified only for a retrospective within-season study')
    # Presence of reference days/state is not enough: a signed-off measured parity decision is separate.
    reasons.append('No accepted cross-source/issue-time validation decision exists')
    return {'status':'unavailable','probability':None,'checks':checks,'reasons':reasons,'forecast_weather_adapter':'implemented and unit-tested','research_scenarios_only':True,'operational':False}


def readiness_report():
    mapping=pd.read_parquet(ROOT/'data/processed/selected_provincial_2025/daily_weather.parquet',columns=['date'])
    forecast=pd.read_parquet(LIVE/'hourly_weather.parquet',columns=['valid_time_utc']);seeds=json.loads((LIVE/'state_checkpoint.json').read_text())
    decision=assess_live_inputs(mapping.date.unique().tolist(),forecast.valid_time_utc.dt.strftime('%Y-%m-%d').unique().tolist(),seeds,False)
    decision.update(input_hashes={'forecast_manifest':digest(LIVE/'manifest.json'),'state_checkpoint':digest(LIVE/'state_checkpoint.json'),'selected_model_results':digest(REPORT/'selected_2025_results.json')},unit_contract={'ERA5_temperature':'Kelvin to Celsius','HRDPS_temperature':'Celsius checked from GRIB','wind':'Both paths yield earth-relative km/h and meteorological from-bearing; rotated-grid wind requires rotation','rain':'Both yield mm after source-specific reset-aware interval decoding','FWI':'Shared equations with exact standard-noon/state clock, but startup/provenance and source distributions are not interchangeable'},scope='Assessment completed: live acceptance fails. No live ignition prediction may be emitted by this prototype.')
    REVIEW.mkdir(parents=True,exist_ok=True)
    save(REVIEW/'live_readiness.json',decision);return decision


def validate_query(query):
    if set(query)!={'date','grid_id'} or any(len(v)!=1 for v in query.values()):raise ValueError('One date and grid_id are required')
    day=query['date'][0];grid=query['grid_id'][0]
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or not re.fullmatch(r'ofr10km_-?\d{1,9}_-?\d{1,9}',grid):raise ValueError('Invalid key format')
    if pd.Timestamp(day).strftime('%Y-%m-%d')!=day:raise ValueError('Invalid date')
    return day,grid


def score_response(source,day,grid):
    frame=pd.read_parquet(source,filters=[('ignition_date','=',day),('grid_id','=',grid)],columns=['grid_id','ignition_date','probability','raw_probability','ignition','cwfis_missing'])
    if frame.empty:return 404,{'status':'not_found','probability':None}
    if len(frame)!=1:return 503,{'status':'unavailable','probability':None,'reason':'duplicate_saved_key'}
    r=frame.iloc[0];p=float(r.probability);raw=float(r.raw_probability)
    if not np.isfinite([p,raw]).all() or not 0<=p<=1 or not 0<=raw<=1:return 503,{'status':'unavailable','probability':None,'reason':'invalid_saved_probability'}
    return 200,{'status':'ok','grid_id':grid,'date':day,'issue_time_utc':pd.Timestamp(day,tz='America/Toronto').tz_convert('UTC').isoformat(),'probability':p,'raw_probability':raw,'recorded_start':bool(r.ignition),'weather_missing':bool(r.cwfis_missing),'mode':'retrospective_saved_evaluation','live':False}


def study_provenance(study):
    if study not in ('historical','selected'):raise ValueError('Unsupported study')
    if study=='historical':
        model=ROOT/'data/processed/ignition_models_week5_v1/temporal_lightgbm_calibrated.joblib'
        contract=ROOT/'data/processed/ignition_weather_v2_development/predictor_contract.json'
        sources='NFDB/CDEM/CWFIS v2'
    else:
        model=ROOT/'data/processed/selected_2025_models_v1/temporal_selected2025.joblib'
        contract=ROOT/'data/processed/selected_2025_ignition_panel/predictor_contract.json'
        sources='Ontario starts/FBP2024/SCANFIv1.2-2020/MRDEM/ERA5-2025 researchFWI'
    return {'source_versions':sources,'model_id':model.stem,'model_sha256':digest(model),'feature_contract_sha256':digest(contract)}


def feature_unit(name):
    if name.endswith('_pct'):return '%'
    if name.endswith('_kmh'):return 'km/h'
    if name.endswith('_temp_c') or name=='temp_c':return '°C'
    if name.endswith('_mm'):return 'mm'
    if name.endswith('_km'):return 'km'
    if name.endswith('_deg'):return 'degrees'
    if name.endswith('_m'):return 'm'
    if 'fraction' in name or name.endswith('_share'):return 'fraction 0–1'
    if name.endswith('_hours'):return 'hours'
    if 'day_of_year' in name:return 'day of year'
    if 'days_since' in name:return 'days (null means no earlier observed record)'
    if name.startswith('fire_history_') or name.endswith('_count'):return 'count'
    if name.endswith('coverage_days'):return 'days'
    if any(name.endswith(code) for code in ['ffmc','dmc','dc','isi','bui','fwi','dsr']):return 'index'
    return 'dimensionless / indicator'


def cell_details(study,day,grid):
    if study not in ('historical','selected'):raise ValueError('Unsupported study')
    code,score=score_response(HISTORICAL if study=='historical' else SELECTED,day,grid)
    if code!=200:return code,score
    directory=ROOT/('data/processed/ignition_models_week5_v1' if study=='historical' else 'data/processed/selected_2025_models_v1')
    document=json.loads((directory/'temporal_first_day_explanations.json').read_text())
    score.update(study_provenance(study),issue_time_utc=pd.Timestamp(day,tz='America/Toronto').tz_convert('UTC').isoformat(),explanation_scale='raw model log odds; not causal or calibrated probability contributions')
    if day!=document['date']:return 200,{**score,'explanation_status':'unavailable_for_this_date','factors':[]}
    explanation=next((r for r in document['rows'] if r['grid_id']==grid),None)
    if explanation is None:return 200,{**score,'explanation_status':'unavailable_for_this_cell','factors':[]}
    names=[r['feature'] for r in explanation['top_factors']];source=ROOT/('data/processed/ignition_weather_v2_reserved/final_test.parquet' if study=='historical' else 'data/processed/selected_2025_ignition_panel/cell_days.parquet')
    frame=pd.read_parquet(source,filters=[('ignition_date','=',day),('grid_id','=',grid)],columns=names+['issue_time_utc'])
    if len(frame)!=1:raise ValueError('Detail feature key mismatch')
    factors=[]
    for f in explanation['top_factors']:
        value=frame.iloc[0][f['feature']];missing=bool(pd.isna(value));factors.append({**f,'value':None if missing else float(value),'unit':feature_unit(f['feature']),'missing':missing})
    return 200,{**score,'issue_time_utc':pd.Timestamp(frame.issue_time_utc.iloc[0]).isoformat(),'explanation_status':'available','factors':factors}


def export_predictions(study,day,format):
    if study not in ('historical','selected') or format not in ('csv','geojson'):raise ValueError('Unsupported export')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or pd.Timestamp(day).strftime('%Y-%m-%d')!=day:raise ValueError('Invalid export date')
    source=HISTORICAL if study=='historical' else SELECTED
    frame=pd.read_parquet(source,filters=[('ignition_date','=',day)])
    if frame.empty:raise ValueError('Date not supported by this evaluated study')
    if study=='historical':
        grid=pd.read_csv(ROOT/'team_repository/data/interim/ontario_fire_region_10km_grid.csv');model=ROOT/'data/processed/ignition_models_week5_v1/temporal_lightgbm_calibrated.joblib';contract=ROOT/'data/processed/ignition_weather_v2_development/predictor_contract.json';sources='NFDB/CDEM/CWFIS daily-valid-station v2'
    else:
        grid=pd.read_parquet(ROOT/'data/processed/selected_provincial_static_native_2025/static_features.parquet',columns=['grid_id','grid_x_m','grid_y_m']);model=ROOT/'data/processed/selected_2025_models_v1/temporal_selected2025.joblib';contract=ROOT/'data/processed/selected_2025_ignition_panel/predictor_contract.json';sources='Ontario IFR starts/FBP2024/SCANFIv1.2-2020/MRDEM/ERA5-2025 researchFWI'
    frame=frame.merge(grid[['grid_id','grid_x_m','grid_y_m']],on='grid_id',validate='one_to_one',how='left')
    if frame.grid_x_m.isna().any():raise ValueError('Missing export geometry')
    frame['issue_time_utc']=pd.Timestamp(day,tz='America/Toronto').tz_convert('UTC').isoformat();frame['model_id']=model.stem;frame['model_sha256']=digest(model);frame['feature_contract_sha256']=digest(contract);frame['source_versions']=sources;frame['source_grid_crs']='EPSG:3978';frame['threshold_version']='numeric-probability-bands-v1-no-approved-danger-categories';frame['mode']='retrospective_evaluation';frame['uncertainty']='not_estimated'
    if format=='csv':return frame.to_csv(index=False).encode(),'text/csv',len(frame)
    transform=Transformer.from_crs(3978,4326,always_xy=True);features=[]
    for record in frame.to_dict(orient='records'):
        x,y=record['grid_x_m'],record['grid_y_m'];corners=[(x,y),(x+10000,y),(x+10000,y+10000),(x,y+10000),(x,y)];coordinates=[list(transform.transform(a,b)) for a,b in corners]
        features.append({'type':'Feature','geometry':{'type':'Polygon','coordinates':[coordinates]},'properties':record})
    return json.dumps({'type':'FeatureCollection','features':features,'geometry_crs':'EPSG:4326'},allow_nan=False).encode(),'application/geo+json',len(frame)


HOME='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ontario Wildfire · Capstone</title><style>body{margin:0;font:15px system-ui;background:#f2f5f0;color:#183c32}header{padding:20px 3vw;background:#183c32;color:white}h1{font-size:25px;margin:0}header p{margin:7px 0;color:#c2d7cd}nav{display:flex;gap:8px;padding:14px 3vw;flex-wrap:wrap}button{padding:10px 14px;background:white;border:1px solid #b9cdbf;border-radius:7px;color:#183c32;cursor:pointer}button[aria-pressed=true]{background:#d5e5d7;font-weight:bold}iframe{width:100%;height:calc(100vh - 195px);border:0;background:white}.note{padding:8px 3vw;font-size:12px;color:#566b62}#readiness{padding:25px 3vw;max-width:1000px}li{margin:12px 0}.tag{background:#fff0cc;padding:10px;border-radius:7px}</style><header><h1>Ontario Wildfire Research</h1><p>COMP 385 · 10 km ignition risk and separate 90 m incident spread</p></header><nav aria-label="Capabilities"><button data-view="historical" aria-pressed="true">Historical ignition · 2019</button><button data-view="selected" aria-pressed="false">Selected sources · 2025</button><button data-view="spread" aria-pressed="false">Corrected spread reconstruction</button><button data-view="live" aria-pressed="false">Live readiness</button></nav><div style="padding:0 3vw" id="exports"><button id="csv">Export selected date · CSV</button> <button id="geojson">GeoJSON</button> <button id="details-button">Cell details and provenance</button></div><section id="cell-details" class="note" aria-live="polite"></section><div class="note">Research prototype. Recorded calendar-day ignition risk and incident spread are separate tasks. No live warnings are issued. Sources: Ontario MNR fire records; NRCan fuels/forest/terrain; ECCC weather; Copernicus ERA5; NASA VIIRS for spread validation.</div><iframe id="view" title="Historical ignition risk" src="/historical.html"></iframe><section id="readiness" hidden><h2>Live ignition is unavailable</h2><p class="tag">Weather ingestion works. The evidence does not qualify live ignition scoring.</p><ul id="reasons"></ul><p id="checks"></p><p>Forecast-derived FWI is never relabelled as observed state. The app returns an unavailable result rather than a fabricated zero-risk prediction.</p></section><script>
const routes={historical:['/historical.html','Historical ignition risk'],selected:['/selected.html','Selected-source ignition risk'],spread:['/spread.html','Corrected fire-spread reconstruction']};
const panel=document.getElementById('cell-details');
const currentStudy=()=>document.querySelector('nav button[aria-pressed=true]').dataset.view;
function bindSelectionChanges(){
  const doc=document.getElementById('view').contentDocument;
  if(!doc?.getElementById('day'))return;
  const clear=()=>{panel.textContent='Selection changed. Request cell details again.'};
  doc.getElementById('day').addEventListener('change',clear);
  doc.getElementById('next')?.addEventListener('click',clear);
  doc.getElementById('map')?.addEventListener('click',clear);
}
document.getElementById('view').addEventListener('load',bindSelectionChanges);
bindSelectionChanges();
async function request(url,format='json',allowUnavailable=false){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch(url,{signal:controller.signal});
    const data=format==='blob'&&response.ok?await response.blob():await response.json();
    if(!response.ok&&!(allowUnavailable&&response.status===503&&data.status==='unavailable'))throw Error(data.message||data.reason||data.status||'Request failed');
    return data;
  }finally{clearTimeout(timer)}
}
function showError(error){panel.textContent=error.name==='AbortError'?'Request timed out. Please retry.':'Request unavailable: '+error.message}
document.querySelectorAll('nav button').forEach(button=>button.onclick=async()=>{
  document.querySelectorAll('nav button').forEach(x=>x.setAttribute('aria-pressed',String(x===button)));
  const key=button.dataset.view,live=key==='live';
  document.getElementById('view').hidden=live;
  document.getElementById('readiness').hidden=!live;
  document.getElementById('exports').hidden=live||key==='spread';panel.textContent='';
  if(live){
    const list=document.getElementById('reasons');list.textContent='Checking saved readiness evidence...';document.getElementById('checks').textContent='';
    try{
      const data=await request('/api/live-ignition','json',true);
      if(!Array.isArray(data.reasons)||!data.checks)throw Error(data.message||'Readiness evidence unavailable');
      list.textContent='';data.reasons.forEach(text=>{const item=document.createElement('li');item.textContent=text;list.appendChild(item)});
      document.getElementById('checks').textContent='Reference overlap: '+data.checks.contemporaneous_ERA5_HRDPS_reference_days+' days. Trusted observed-state cells: '+data.checks.trusted_observed_state_cells+'.';
    }catch(error){list.textContent='Saved readiness evidence is unavailable.';showError(error)}
  }else{document.getElementById('view').src=routes[key][0];document.getElementById('view').title=routes[key][1]}
});
function selectedKey(){
  const study=currentStudy(),doc=document.getElementById('view').contentDocument;
  if(!routes[study]||study==='spread'||!doc?.getElementById('day'))throw Error('Wait for an ignition map to load.');
  return {study,doc,day:doc.getElementById('day').value};
}
document.getElementById('details-button').onclick=async()=>{
  try{
    const {study,doc,day}=selectedKey(),cell=doc.getElementById('cellname')?.textContent.split(' · ')[0];
    if(!cell?.startsWith('ofr10km_')){panel.textContent='Select a grid cell on the map first.';return}
    panel.textContent='Loading cell details...';
    const data=await request('/api/cell-details?'+new URLSearchParams({study,date:day,grid_id:cell}));
    if(currentStudy()!==study||doc.getElementById('day').value!==day||doc.getElementById('cellname')?.textContent.split(' · ')[0]!==cell)return;
    panel.textContent=data.source_versions+' · '+data.mode+' · '+data.issue_time_utc+' · '+data.explanation_scale;
    const factors=data.factors||[];
    factors.forEach(factor=>{const item=document.createElement('p');item.textContent=factor.feature+': '+(factor.missing?'unavailable':factor.value.toFixed(3)+' '+factor.unit)+'; contribution '+factor.raw_log_odds_contribution.toFixed(3)+' raw log odds';panel.appendChild(item)});
    if(!factors.length)panel.appendChild(document.createTextNode(' Factor details unavailable for this date.'));
  }catch(error){showError(error)}
};
['csv','geojson'].forEach(format=>document.getElementById(format).onclick=async()=>{
  try{
    const {study,day}=selectedKey();panel.textContent='Preparing export...';
    const blob=await request('/api/export?'+new URLSearchParams({study,date:day,format}),'blob');
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=study+'_'+day+'.'+format;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    panel.textContent='Export ready: '+study+' '+day+'.';
  }catch(error){showError(error)}
});
</script></html>'''


def build():
    readiness_report();(REVIEW/'index.html').write_text(HOME)


class Handler(BaseHTTPRequestHandler):
    def send_json(self,status,value):
        body=json.dumps(value,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        try:self.handle_get()
        except (OSError,json.JSONDecodeError) as error:
            self.log_error('Local artifact unavailable: %s',error)
            self.send_json(503,{'status':'unavailable','probability':None,'reason':'local_artifact_unavailable','message':'A required local result file is missing, unreadable or invalid.'})
    def handle_get(self):
        path=urlsplit(self.path);routes={'/':REPORT/'index.html','/historical.html':ROOT/'reports/week_5_prototype_2026-10-16/historical_ignition_map.html','/selected.html':REPORT/'selected_2025_ignition_map.html','/spread.html':REPORT/'corrected_spread_viewer.html'}
        if path.path=='/':
            body=HOME.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if path.path=='/api/cell-details':
            q=parse_qs(path.query,keep_blank_values=True)
            try:
                study=q.pop('study')
                if len(study)!=1:raise ValueError('Study required once')
                day,grid=validate_query(q);status,value=cell_details(study[0],day,grid)
            except (KeyError,ValueError,OverflowError):return self.send_json(400,{'status':'invalid_request','probability':None})
            return self.send_json(status,value)
        if path.path=='/api/export':
            q=parse_qs(path.query,keep_blank_values=True)
            try:
                if set(q)!={'study','date','format'} or any(len(v)!=1 for v in q.values()):raise ValueError('Invalid export query')
                body,mime,rows=export_predictions(q['study'][0],q['date'][0],q['format'][0])
            except (ValueError,OverflowError):return self.send_json(400,{'status':'invalid_export'})
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Content-Disposition',f'attachment; filename="{q["study"][0]}_{q["date"][0]}.{q["format"][0]}"');self.end_headers();self.wfile.write(body);return
        if path.path=='/api/live-ignition':return self.send_json(503,json.loads((REPORT/'live_readiness.json').read_text()))
        if path.path in ('/api/historical-score','/api/selected-score'):
            try:
                day,grid=validate_query(parse_qs(path.query,keep_blank_values=True));status,value=score_response(HISTORICAL if path.path=='/api/historical-score' else SELECTED,day,grid)
            except (ValueError,OverflowError):return self.send_json(400,{'status':'invalid_request','probability':None})
            if status==200:value.update(study_provenance('historical' if path.path=='/api/historical-score' else 'selected'))
            return self.send_json(status,value)
        if path.path not in routes:return self.send_json(404,{'status':'not_found'})
        file=routes[path.path]
        if not file.exists():return self.send_json(503,{'status':'unavailable','probability':None})
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(file.stat().st_size));self.end_headers()
        with file.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):self.wfile.write(chunk)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','serve']);p.add_argument('--port',type=int,default=8767);a=p.parse_args()
    if a.mode=='build':build()
    else:ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
