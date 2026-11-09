"""只下载并保存原始外部指标，不运行策略。"""
import json
from datetime import datetime,timezone
from pathlib import Path
import requests
import pandas as pd

OUT=Path('results/gold_macro/data')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest={'fetched_at_utc':datetime.now(timezone.utc).isoformat(),'series':{}}
    for series in ('DFII10','DEXCHUS','GVZCLS'):
        url='https://fred.stlouisfed.org/graph/fredgraph.csv'
        r=requests.get(url,params={'id':series,'cosd':'2012-01-01','coed':'2026-10-29'},timeout=45);r.raise_for_status()
        if not r.text.startswith('observation_date'):raise ValueError(r.text[:100])
        (OUT/f'{series}_raw.csv').write_text(r.text,encoding='utf-8')
        df=pd.read_csv(OUT/f'{series}_raw.csv')
        manifest['series'][series]={'url':r.url,'rows':len(df),'first':str(df.iloc[0,0]),'last':str(df.iloc[-1,0]),'vintage':'latest downloaded; not first-release archive'}
    url='https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB'
    p1=int(pd.Timestamp('2012-01-01',tz='UTC').timestamp());p2=int(pd.Timestamp('2026-10-30',tz='UTC').timestamp())
    r=requests.get(url,params={'period1':p1,'period2':p2,'interval':'1d'},headers={'User-Agent':'Mozilla/5.0'},timeout=45);r.raise_for_status()
    (OUT/'DXY_raw.json').write_text(r.text,encoding='utf-8')
    node=r.json()['chart']['result'][0]
    dates=pd.to_datetime(node['timestamp'],unit='s',utc=True).tz_convert(node['meta']['exchangeTimezoneName']).date
    df=pd.DataFrame({'observation_date':dates,'DXY':node['indicators']['quote'][0]['close']}).dropna()
    df.to_csv(OUT/'DXY_raw.csv',index=False)
    manifest['series']['DXY']={'url':r.url,'symbol':'DX-Y.NYB','timezone':node['meta']['exchangeTimezoneName'],'first':str(df.iloc[0,0]),'last':str(df.iloc[-1,0]),'rows':len(df),'vintage':'market close history; no immutable first-release proof'}
    (OUT/'fetch.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
