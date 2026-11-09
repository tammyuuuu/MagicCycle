"""Download AAPL research inputs once; never overwrite the frozen snapshot."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parent
RAW=ROOT/'raw'; RAW.mkdir(parents=True,exist_ok=True)
end=int(dt.datetime(2026,11,8,tzinfo=dt.timezone.utc).timestamp())
tasks=[('AAPL_chart.json','https://query1.finance.yahoo.com/v8/finance/chart/AAPL',
        {'period1':1199145600,'period2':end,'interval':'1d','events':'div,splits'},{'User-Agent':'Mozilla/5.0'}),
       ('AAPL_facts.json','https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json',{},
        {'User-Agent':os.environ.get('MSFT_SEC_USER_AGENT','Xingxun research contact research@example.org')})]
manifest=[]
for name,url,params,headers in tasks:
    path=RAW/name
    if not path.exists():
        response=requests.get(url,params=params,headers=headers,timeout=30);response.raise_for_status();response.json()
        path.write_bytes(response.content)
    manifest.append({'file':name,'source':url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
bil=RAW/'BIL_chart.json'
if bil.exists():
    manifest.append({'file':bil.name,'source':'research_nvda_strategy/raw/BIL_chart.json',
                     'sha256':hashlib.sha256(bil.read_bytes()).hexdigest()})
(ROOT/'sources.json').write_text(json.dumps({'frozen_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
 'sample_end':'2026-11-06','files':manifest},indent=2),encoding='utf8')
print('Frozen:',', '.join(x['file'] for x in manifest))
