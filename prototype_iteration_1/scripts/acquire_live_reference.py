"""Acquire a bounded, pinned hindsight reference for the archived October 16 HRDPS case."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import pandas as pd
import requests

from scripts.ignition_comparison import digest, save_json

VARIABLES=['2m_temperature','2m_dewpoint_temperature','10m_u_component_of_wind',
           '10m_v_component_of_wind','total_precipitation']


def run(workspace, output, download=False):
    if output.exists():
        raise FileExistsError('Use a new acquisition directory')
    output.mkdir(parents=True)
    grid=pd.read_csv(workspace/'reports/week_4_data_2026-10-16/current_boundary_centroid_grid.csv')
    request={'variable':VARIABLES,'year':['2026'],'month':['10'],'day':['15','16','17'],
        'time':[f'{h:02d}:00' for h in range(24)],'data_format':'netcdf','download_format':'unarchived',
        'area':[round(float(grid.centroid_latitude.max())+.2,1),round(float(grid.centroid_longitude.min())-.2,1),
                round(float(grid.centroid_latitude.min())-.2,1),round(float(grid.centroid_longitude.max())+.2,1)]}
    record={'dataset':'reanalysis-era5-land','request':request,'requested_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),
            'purpose':'Independent hindsight reference; never an issue-time observation/input','status':'plan_only'}
    save_json(output/'era5_acquisition.json',record)
    if not download:
        return record
    records=[]
    for day in ('15','16','17'):
        filename=f'cwfis_fwi_202610{day}.csv'
        url=f'https://cwfis.cfs.nrcan.gc.ca/downloads/fwi_obs/current/{filename}'
        response=requests.get(url,timeout=(10,60))
        item={'url':url,'status':response.status_code,'retrieved_at_utc':pd.Timestamp.now(tz='UTC').isoformat()}
        if response.status_code==200:
            path=output/filename;path.write_bytes(response.content)
            item.update(bytes=path.stat().st_size,sha256=digest(path))
        records.append(item);save_json(output/'cwfis_acquisition.json',records)
    import cdsapi
    target=output/'era5_land_20261015_17.nc'
    client=cdsapi.Client(quiet=True,debug=False,timeout=60,retry_max=0)
    record['status']='requested';save_json(output/'era5_acquisition.json',record)
    client.retrieve(record['dataset'],request,str(target))
    record.update(status='downloaded',bytes=target.stat().st_size,sha256=digest(target),retrieved_at_utc=pd.Timestamp.now(tz='UTC').isoformat())
    save_json(output/'era5_acquisition.json',record)
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--download',action='store_true')
    a=p.parse_args();run(a.workspace.resolve(),a.output_dir.resolve(),a.download)
