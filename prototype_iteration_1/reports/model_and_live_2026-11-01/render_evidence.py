from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

root=Path(__file__).resolve().parents[2]
r=root/'reports/weather_history_2026-11-01'
fig,axes=plt.subplots(1,2,figsize=(11,4.8))
for ax,protocol,title in zip(axes,['temporal','inner_spatial'],['Temporal development','Geographic development']):
    for spec,color in [('reference','#1a4c40'),('history','#b35924')]:
        d=pd.read_csv(r/f'{protocol}_{spec}_reliability.csv')
        ax.plot(d.mean_probability*100,d.event_rate*100,'o-',color=color,label=spec)
    ax.plot([0,6],[0,6],'--',color='gray',lw=1,label='perfect calibration')
    ax.set_xscale('symlog',linthresh=.01);ax.set_yscale('symlog',linthresh=.01)
    ax.set_xlabel('Mean estimated probability (%)');ax.set_ylabel('Observed event rate (%)')
    ax.set_title(title);ax.set_xlim(0,6);ax.set_ylim(0,6);ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Fixed-bin reliability on exposed 2017 development data',fontsize=14)
fig.text(.5,.01,'New wildfire-only target. Highest bins have few cases; zero-event bins remain visible. Not independent final evaluation.',ha='center',fontsize=9)
fig.tight_layout(rect=[0,.045,1,.94]);fig.savefig(r/'calibration.png',dpi=160);plt.close(fig)

q=root/'reports/live_qualification_2026-11-01'
d=json.loads((q/'qualification_results.json').read_text())
rows=[]
for row in d['weather_metrics_by_valid_hour']:
    for m in row['metrics']:
        rows.append({'valid_time_utc':row['valid_time_utc'],**m})
f=pd.DataFrame(rows);f.to_csv(q/'weather_metrics_by_hour.csv',index=False)
fig,axes=plt.subplots(1,3,figsize=(11,3.8))
for ax,field,title in zip(axes,['temp_c','rh_pct','wind_kmh'],['Temperature (°C)','Humidity (percentage points)','Wind (km/h)']):
    a=f.loc[f.field.eq(field)];ax.plot(pd.to_datetime(a.valid_time_utc),a.mae,'o-',color='#1a4c40',markersize=3)
    ax.set_title(title);ax.set_ylabel('Mean absolute difference');ax.set_ylim(bottom=0);ax.grid(alpha=.2)
    ax.tick_params(axis='x',rotation=30,labelsize=7)
fig.suptitle('One archived HRDPS run compared with hindsight ERA5-Land',fontsize=13)
fig.text(.5,.01,'Centroid samples, post-issue valid times only. Spatially dependent pairs; weather differences do not qualify an ignition model.',ha='center',fontsize=9)
fig.tight_layout(rect=[0,.065,1,.92]);fig.savefig(q/'weather_comparison.png',dpi=160);plt.close(fig)
