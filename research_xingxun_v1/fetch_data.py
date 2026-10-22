"""Download immutable public source snapshots; never imports website modules."""
from pathlib import Path
import requests, json, re, hashlib, datetime
import pandas as pd
ROOT=Path(__file__).resolve().parent
RAW=ROOT/'raw'; RAW.mkdir(exist_ok=True)
FUNDS={'000216':'黄金','160706':'沪深300','160119':'中证500','090010':'中证红利','006484':'1-3年国开债','006989':'中短债','000198':'货币基金'}
def main():
    manifest=[]
    for code,label in FUNDS.items():
        url=f'https://fund.eastmoney.com/pingzhongdata/{code}.js'
        path=RAW/f'{code}.js'
        if not path.exists():
            r=requests.get(url,timeout=40);r.raise_for_status();path.write_bytes(r.content)
        raw=path.read_bytes();s=raw.decode('utf-8-sig')
        def extract(name):
            m=re.search(r'var\s+'+name+r'\s*=\s*(\[.*?\]);',s,re.S)
            return json.loads(m.group(1)) if m else []
        rows=extract('Data_netWorthTrend')
        name=re.search(r'var fS_name\s*=\s*"([^"]+)"',s)
        if rows and isinstance(rows[0],dict):
            d=pd.DataFrame(rows);d['date']=pd.to_datetime(d.x,unit='ms',utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None).dt.normalize()
            d.to_csv(ROOT/f'{code}.csv',index=False)
            span=[str(d.date.min().date()),str(d.date.max().date())]
            print(code,name.group(1) if name else '',len(d),span,d.head(2).to_dict('records'),flush=True)
        else:
            span=[];print(code,'non NAV series',str(rows[:2]),flush=True)
        manifest.append(dict(code=code,label=label,name=name.group(1) if name else None,url=url,sha256=hashlib.sha256(raw).hexdigest(),retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),span=span,rows=len(rows)))
        for kind in ('jjfl','jbgk'):
            p=RAW/f'{code}_{kind}.html'
            if not p.exists():
                try:
                    rr=requests.get(f'https://fundf10.eastmoney.com/{kind}_{code}.html',timeout=25);rr.raise_for_status();p.write_bytes(rr.content)
                except Exception as e: print('metadata failure',code,kind,type(e).__name__,flush=True)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
