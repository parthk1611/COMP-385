"""Dashboard navigation and study-specific controls for the local prototype."""

PAGE='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ontario Wildfire · Capstone</title><style>:root{font:14px system-ui;color:#183c32;background:#f6f8f5}*{box-sizing:border-box}body{margin:0}header{padding:20px 28px;background:#163c30;color:#fff;display:flex;justify-content:space-between;gap:24px;align-items:center}h1{font-size:23px;letter-spacing:-.6px;margin:0}header p{margin:6px 0 0;color:#bfd4c4;font-size:12px}.status-label{font-size:11px;letter-spacing:1px;text-transform:uppercase;border-left:1px solid #527466;padding-left:20px;line-height:1.8}nav{display:flex;gap:4px;padding:10px 24px;border-bottom:1px solid #cbd6cd;background:#fff;flex-wrap:wrap}button{padding:10px 13px;background:transparent;border:1px solid transparent;border-radius:4px;color:#3e5d4e;cursor:pointer;font:inherit;font-size:12px}button:hover{background:#edf2eb}button[aria-pressed=true]{background:#e3ece0;color:#153c2e;font-weight:650;border-color:#cad9c7}button:focus-visible,a:focus-visible{outline:3px solid #ba792d;outline-offset:2px}iframe{width:100%;height:calc(100vh - 192px);min-height:420px;border:0;background:#f6f8f5}.note{padding:10px 28px;font-size:11px;color:#52685b;line-height:1.5}#exports{padding:8px 24px;background:#eef3eb;border-bottom:1px solid #d6dfd2}#exports button{background:white;border-color:#c1d0be;margin-right:5px}#cell-details:empty{display:none}#readiness{padding:30px;max-width:1000px}li{margin:12px 0}.tag{background:#fff0cc;padding:14px;border-left:3px solid #b37425}#scope-note{padding:8px 28px;font-size:11px;color:#536a5c;border-bottom:1px solid #d8e0d4;background:#f4f6f0}@media(max-width:650px){header{padding:17px;align-items:flex-start}h1{font-size:20px}.status-label{font-size:9px;padding-left:10px}nav{padding:8px}nav button{padding:9px;font-size:11px}.note,#scope-note{padding:8px 16px}iframe{height:calc(100vh - 240px)}}</style><header><div><h1>Ontario Wildfire</h1><p>COMP 385 · Ignition risk and incident spread research</p></div><div class="status-label">Local research prototype<br>Live forecasting unavailable</div></header><nav aria-label="Capabilities"><button data-view="performance" aria-pressed="true">Geographic performance</button><button data-view="historical" aria-pressed="false">Historical ignition · 2019</button><button data-view="selected" aria-pressed="false">Selected sources · 2025</button><button data-view="spread" aria-pressed="false">Corrected spread reconstruction</button><button data-view="live" aria-pressed="false">Live readiness</button><button data-view="workflow" aria-pressed="false">Reported fires and weather</button></nav><div id="exports" hidden><button id="csv">Export selected date · CSV</button> <button id="geojson">GeoJSON</button> <button id="details-button">Cell details and provenance</button></div><section id="cell-details" class="note" aria-live="polite"></section><div id="scope-note">10 km ignition cell-days · 90 m historical spread reconstruction · Reported fires are observations · No public warnings</div><iframe id="view" title="Geographic development performance" src="/performance.html"></iframe><section id="readiness" hidden><h2>Live ignition is unavailable</h2><p class="tag">Weather ingestion works. The evidence does not qualify live ignition scoring.</p><ul id="reasons"></ul><p id="checks"></p><p>Forecast-derived FWI is never relabelled as observed state. The app returns an unavailable result rather than a fabricated zero-risk prediction.</p></section><script>
const routes={performance:['/performance.html','Geographic development performance'],workflow:['/workflow.html','Reported fires and weather context'],historical:['/historical.html','Historical ignition risk'],selected:['/selected.html','Selected-source ignition risk'],spread:['/spread.html','Corrected fire-spread reconstruction']};
const panel=document.getElementById('cell-details');
const currentStudy=()=>document.querySelector('nav button[aria-pressed=true]').dataset.view;
function bindSelectionChanges(){
  if(!['historical','selected'].includes(currentStudy()))return;
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
  document.getElementById('exports').hidden=!['historical','selected'].includes(key);panel.textContent='';
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
  if(!['historical','selected'].includes(study)||!doc?.getElementById('day'))throw Error('Wait for an ignition map to load.');
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
