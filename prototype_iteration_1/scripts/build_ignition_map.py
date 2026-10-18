"""Build a self-contained historical research map from frozen final predictions."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scripts.week5_ignition import ROOT, REPORT, MODELS
from scripts.prepare_historical_weather_v2 import digest, save


def map_payload(grid,predictions,explanations):
    if grid.grid_id.duplicated().any() or predictions.duplicated(['grid_id','ignition_date']).any():raise ValueError('Duplicate map keys')
    ids=grid.grid_id.tolist();days={}
    for day,frame in predictions.groupby('ignition_date',sort=True):
        if set(frame.grid_id)!=set(ids):raise ValueError('Map day has missing/extra cells')
        frame=frame.set_index('grid_id').reindex(ids)
        probabilities=frame.probability.to_numpy(dtype=float)
        if not np.isfinite(probabilities).all() or ((probabilities<0)|(probabilities>1)).any():raise ValueError('Unavailable/invalid risk may not become zero')
        days[day]={'p':probabilities.tolist(),'y':frame.ignition.astype(int).tolist(),'missing':frame.cwfis_missing.astype(int).tolist()}
    if not days:raise ValueError('No historical predictions')
    return {'cells':[{'id':row.grid_id,'x':int(row.grid_x_m),'y':int(row.grid_y_m),'lon':float(row.centroid_longitude),'lat':float(row.centroid_latitude)} for row in grid.itertuples()],
            'days':days,'explanations':{r['grid_id']:r for r in explanations['rows']},'explanation_date':explanations['date']}


HTML='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ontario wildfire · historical risk</title>
<style>
:root{color-scheme:light;--ink:#19352f;--muted:#63766f;--paper:#f4f6f1;--line:#dbe3da}*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--paper);color:var(--ink)}header{padding:25px 4vw;background:#173d34;color:#fff;display:flex;align-items:center;justify-content:space-between;gap:25px}h1{font-size:27px;letter-spacing:-.7px;margin:0}header p{color:#b9d1c6;margin:5px 0 0}.pill{padding:7px 12px;border:1px solid #8aa99b;border-radius:20px;font-size:12px;white-space:nowrap}.layout{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:20px;padding:25px 4vw}.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px}label{font-weight:600}select{padding:8px;border:1px solid var(--line);border-radius:6px;font:inherit;color:var(--ink);margin-left:10px}button{cursor:pointer;padding:8px 12px;border:1px solid var(--line);border-radius:6px;background:white;color:var(--ink);font:inherit}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.legend{font-size:12px;display:flex;gap:12px;flex-wrap:wrap;color:var(--muted);margin:16px 0}.key{display:inline-block;width:11px;height:11px;vertical-align:middle;margin-right:4px}.canvasbox{background:#eef3ef;border-radius:8px;position:relative}canvas{display:block;width:100%;height:580px;cursor:crosshair}h2{font-size:16px;margin:0 0 13px}.note{font-size:12px;color:var(--muted)}.metric{font-size:32px;line-height:1.2;font-weight:650;margin:8px 0}.meta{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}.divider{border:0;border-top:1px solid var(--line);margin:18px 0}.factor{font-size:12px;margin:10px 0}.row{display:flex;justify-content:space-between;gap:10px;margin:8px 0}.small{font-size:12px}.disclaimer{margin:0 4vw 24px;padding:15px 20px;border-left:3px solid #dba65c;background:#fff7e8;font-size:13px}#tip{display:none;position:absolute;pointer-events:none;background:#173d34;color:white;padding:8px 10px;border-radius:6px;font-size:12px;z-index:3}#status{font-size:12px;color:var(--muted);margin-top:8px}@media(max-width:900px){.layout{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column;gap:12px}h1{font-size:24px;line-height:1.15}canvas{height:420px}}
</style>
<header><div><h1>Ontario wildfire risk</h1><p>Historical research · 10 km cells · recorded calendar-day starts</p></div><span class="pill">2019 retrospective evaluation</span></header>
<div class="layout"><main class="card"><div class="toolbar"><label for="day">Historical date</label><select id="day"></select><button id="next">Next day →</button><label class="small"><input id="truth" type="checkbox"> Show recorded starts</label></div>
<div class="legend" id="legend"></div><div class="canvasbox"><canvas id="map" tabindex="0" role="img" aria-label="Ontario grid of historical wildfire ignition probabilities. Select a cell for details."></canvas><div id="tip"></div></div><p id="status" aria-live="polite"></p></main>
<aside class="card"><h2>Selected cell</h2><div id="cellname" class="note">Select a grid cell on the map.</div><div class="metric" id="prob">—</div><div class="meta">Estimated probability</div><div id="details" class="small"></div><hr class="divider"><h2>Main contributing factors</h2><div id="factors" class="note">Select a cell to view available factor details.</div><hr class="divider"><h2>Daily view</h2><div id="summary"></div><p class="note">Colour bands show probability ranges. They are not approved low/moderate/high danger categories.</p></aside></div>
<p class="disclaimer"><strong>Research demonstration.</strong> These are retrospective model estimates, not live fire warnings. Calibration and final evaluation do not establish operational accuracy. Missing weather remains flagged. Factors describe the model's raw log-odds attribution and do not prove causes.</p>
<script id="map-data" type="application/json">__PAYLOAD__</script><script>
const D=JSON.parse(document.getElementById('map-data').textContent), cells=D.cells, days=Object.keys(D.days), sel=document.getElementById('day'),canvas=document.getElementById('map'),ctx=canvas.getContext('2d');
const $=id=>document.getElementById(id), colors=['#dce9da','#97bd9b','#4d8f79','#d6ad54','#d57a42','#9d3d35'],edges=[0,.0001,.0005,.001,.005,.01],labels=['<0.01%','0.01–0.05%','0.05–0.1%','0.1–0.5%','0.5–1%','≥1%'];
let selected=-1,view;const lookup=new Map(cells.map((c,i)=>[c.x+','+c.y,i]));
days.forEach(day=>{let o=document.createElement('option');o.value=o.textContent=day;sel.appendChild(o)});
$('legend').innerHTML=labels.map((t,i)=>'<span><i class="key" style="background:'+colors[i]+'"></i>'+t+'</span>').join('');
function colour(p){let i=0;while(i<edges.length-1&&p>=edges[i+1])i++;return colors[i]}
function pct(p){return (p*100).toFixed(4)+'%'}
const minX=Math.min(...cells.map(c=>c.x)),maxX=Math.max(...cells.map(c=>c.x))+10000,minY=Math.min(...cells.map(c=>c.y)),maxY=Math.max(...cells.map(c=>c.y))+10000;
function draw(){const rect=canvas.getBoundingClientRect(),ratio=window.devicePixelRatio||1;canvas.width=rect.width*ratio;canvas.height=rect.height*ratio;ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,rect.width,rect.height);const scale=Math.min((rect.width-35)/(maxX-minX),(rect.height-35)/(maxY-minY));view={scale,ox:(rect.width-(maxX-minX)*scale)/2,oy:(rect.height-(maxY-minY)*scale)/2};let day=D.days[sel.value];cells.forEach((c,i)=>{let x=view.ox+(c.x-minX)*scale,y=view.oy+(maxY-c.y-10000)*scale,size=10000*scale;ctx.fillStyle=colour(day.p[i]);ctx.fillRect(x,y,size+.1,size+.1);if($('truth').checked&&day.y[i]){ctx.strokeStyle='#101c22';ctx.lineWidth=1.5;ctx.strokeRect(x,y,size,size)}if(i===selected){ctx.strokeStyle='#222';ctx.lineWidth=2;ctx.strokeRect(x-1,y-1,size+2,size+2)}});$('summary').innerHTML='<div class="row"><span>Cells</span><strong>'+cells.length.toLocaleString()+'</strong></div><div class="row"><span>Recorded positive cells</span><strong>'+day.y.reduce((a,b)=>a+b,0)+'</strong></div><div class="row"><span>Missing station weather</span><strong>'+day.missing.reduce((a,b)=>a+b,0)+'</strong></div>';$('status').textContent=sel.value+' · Select a cell to inspect probability and source coverage.';details()}
function details(){if(selected<0)return;const c=cells[selected],day=D.days[sel.value];$('cellname').textContent=c.id+' · '+c.lat.toFixed(3)+', '+c.lon.toFixed(3);$('prob').textContent=pct(day.p[selected]);$('details').textContent=(day.missing[selected]?'Station weather unavailable; model uses missing-value handling.':'Station weather supported within the declared radius.')+' Recorded start: '+(day.y[selected]?'yes':'no')+'.';const e=sel.value===D.explanation_date?D.explanations[c.id]:null;let parent=$('factors');parent.textContent='';if(!e){parent.textContent='Factor details are available for '+D.explanation_date+'.';return}e.top_factors.forEach(f=>{let item=document.createElement('div');item.className='factor';item.textContent=f.feature.replaceAll('_',' ')+' · '+(f.raw_log_odds_contribution>=0?'+':'')+f.raw_log_odds_contribution.toFixed(3)+' raw log odds';parent.appendChild(item)})}
function hit(ev){let r=canvas.getBoundingClientRect(),x=ev.clientX-r.left,y=ev.clientY-r.top;let gx=Math.floor(((x-view.ox)/view.scale+minX)/10000)*10000,gy=Math.floor((maxY-(y-view.oy)/view.scale)/10000)*10000;return {i:lookup.get(gx+','+gy),x,y}}
canvas.addEventListener('click',ev=>{let h=hit(ev);if(h.i!==undefined){selected=h.i;draw()}});canvas.addEventListener('mousemove',ev=>{let h=hit(ev);if(h.i===undefined){$('tip').style.display='none';return}$('tip').textContent=pct(D.days[sel.value].p[h.i]);$('tip').style.cssText='display:block;left:'+Math.min(h.x+12,canvas.clientWidth-100)+'px;top:'+Math.max(0,h.y-35)+'px'});canvas.addEventListener('mouseleave',()=>$('tip').style.display='none');canvas.addEventListener('keydown',ev=>{if(['ArrowLeft','ArrowRight'].includes(ev.key)){ev.preventDefault();selected=Math.max(0,Math.min(cells.length-1,selected+(ev.key==='ArrowRight'?1:-1)));draw()}});sel.addEventListener('change',draw);$('truth').addEventListener('change',draw);$('next').addEventListener('click',()=>{sel.selectedIndex=(sel.selectedIndex+1)%days.length;draw()});window.addEventListener('resize',draw);draw();
</script></html>'''


def run():
    if not (REPORT/'final_evaluation.json').exists():raise FileNotFoundError('Completed frozen final evaluation required')
    output=REPORT/'historical_ignition_map.html'
    if output.exists():raise FileExistsError('Map already exists')
    grid=pd.read_csv(ROOT/'team_repository/data/interim/ontario_fire_region_10km_grid.csv')
    predictions=pd.read_parquet(MODELS/'temporal_final_predictions.parquet')
    explanation=json.loads((MODELS/'temporal_first_day_explanations.json').read_text());payload=map_payload(grid,predictions,explanation)
    output.write_text(HTML.replace('__PAYLOAD__',json.dumps(payload,separators=(',',':')).replace('<','\\u003c')))
    save(REPORT/'map_build_audit.json',{'path':str(output),'sha256':digest(output),'bytes':output.stat().st_size,'cells':len(grid),'dates':len(payload['days']),'default_date':next(iter(payload['days'])),'model_mode':'retrospective_final_evaluation','explanation_scale':'raw log odds, not calibrated probability','operational':False,'code_sha256':digest(Path(__file__))})
    print('built map',len(grid),len(payload['days']),output.stat().st_size,flush=True)


if __name__=='__main__':run()
