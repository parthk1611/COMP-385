"""Small read-only view of the live-observation and regional-research snapshot."""

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wildfire observations and research notices</title>
<style>body{font:16px system-ui;margin:0;color:#183c32;background:#f2f5f0}header{background:#183c32;color:white;padding:24px}main{max-width:1150px;margin:auto;padding:20px}a{color:inherit}table{border-collapse:collapse;width:100%;background:white;margin:12px 0 28px}th,td{text-align:left;padding:10px;border-bottom:1px solid #d4ddd5;vertical-align:top}th{background:#e6eee7}p{line-height:1.5}.scroll{overflow:auto}.note{padding:12px;border-left:4px solid #9c6024;background:#fff6e9}#error{color:#8b201c}h2{margin-top:30px}summary{cursor:pointer}small{font-size:13px}</style>
<header><a href="/" target="_top">Back to model studies</a><h1>Wildfire observations and research notices</h1><p>Reported incidents, forecast weather context and historical spread examples</p></header>
<main><p id="status" role="status">Loading the latest saved snapshot…</p><p id="error" role="alert"></p>
<p class="note">Live ignition and spread predictions are unavailable. Notices stay in this local prototype; public alerts are not sent. Fire causes shown here are reported source attributes.</p>
<h2>Reported active-fire feed</h2><p>Retrieval time does not establish when a fire’s condition or perimeter was last observed. This feed supplies points. District names use the dated MNR administrative reference package.</p>
<div class="scroll"><table><thead><tr><th>Fire</th><th>Reported condition</th><th>Reported cause</th><th>Confirmed date (UTC)</th><th>Reference district</th><th>Forecast weather context</th></tr></thead><tbody id="fires"></tbody></table></div>
<h2>Historical spread examples</h2><p>Saved final-perimeter-assisted reconstructions. These are not forecasts for the current incidents above. Areas use reference district boundaries for demonstration; uncertainty is not estimated.</p>
<a href="/api/workflow/footprints">Download reconstruction footprints (GeoJSON)</a>
<div class="scroll"><table><thead><tr><th>Historical fire</th><th>Scenario start (local standard)</th><th>Hours</th><th>Reconstructed area (ha)</th><th>District overlap</th></tr></thead><tbody id="scenarios"></tbody></table></div>
<h2>Local notices and drafts</h2><p>Reported-fire notices describe source observations. Reconstruction drafts demonstrate the regional alert workflow. Neither is an evacuation instruction or a validated public warning.</p>
<div class="scroll"><table><thead><tr><th>Type</th><th>District</th><th>Message</th></tr></thead><tbody id="notices"></tbody></table></div>
<h2>Remaining live-model requirements</h2><ul id="blockers"></ul></main>
<script>
const byId=id=>document.getElementById(id);
const cell=(row,value)=>{const td=document.createElement('td');td.textContent=value??'Unavailable';row.appendChild(td);return td};
const number=(x,places=1)=>x===null||x===undefined?'unavailable':Number(x).toFixed(places);
const row=(target,values)=>{const tr=document.createElement('tr');values.forEach(v=>cell(tr,v));byId(target).appendChild(tr);return tr};
(async()=>{try{
 const response=await fetch('/api/workflow');const data=await response.json();if(!response.ok)throw new Error(data.message||'The workflow snapshot is unavailable.');
 byId('status').textContent='Feed retrieved '+data.collected_at_utc+' · '+data.freshness+' snapshot · weather run '+data.weather.run_time_utc+'.';
 if(data.last_refresh?.status==='failed')byId('error').textContent='The last refresh failed. Showing the previous snapshot with its original timestamp.';
 if(!data.incidents.length)row('fires',['No incidents returned by the source.','','','','','']);
 data.incidents.forEach(f=>{
   const tr=row('fires',[f.name,f.reported_condition,f.reported_cause,f.confirmed_at_utc,f.districts.map(d=>d.district).join(', ')||'No district match']);
   const td=document.createElement('td');tr.appendChild(td);const context=f.weather_context;
   if(!context||!context.hours.length){td.textContent='Weather context unavailable for the next hours.';return}
   const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=context.hours.length+' future hours; nearest centroid '+number(context.centroid_distance_km)+' km';details.appendChild(summary);
   context.hours.forEach(w=>{const p=document.createElement('p');p.textContent=w.valid_time_utc+': '+number(w.temp_c)+' °C; RH '+number(w.rh_pct)+'%; wind '+number(w.wind_kmh)+' km/h from '+number(w.wind_from_degrees)+'°; preceding-hour rain '+number(w.precip_mm,2)+' mm';details.appendChild(p)});td.appendChild(details);
 });
 data.scenarios.forEach(s=>row('scenarios',[s.incident_id,s.start_local,s.horizon_hours,number(s.footprint_ha,2),s.districts.map(d=>d.district+' ('+number(d.overlap_ha,2)+' ha)').join(', ')||'No district overlap']));
 data.notices.forEach(n=>row('notices',[n.kind==='reported_fire'?'Reported observation':'Reconstruction draft',n.district,n.message]));
 data.live_blockers.forEach(reason=>{const li=document.createElement('li');li.textContent=reason;byId('blockers').appendChild(li)});
}catch(error){byId('status').textContent='No usable workflow snapshot.';byId('error').textContent=error.message}})();
</script></html>"""
