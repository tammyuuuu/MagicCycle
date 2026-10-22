from pathlib import Path
import requests,json,datetime,hashlib
from fetch_data import FUNDS,ROOT,RAW
def main():
    log=[]
    for code in FUNDS:
        if code=='000198':continue
        p=RAW/f'{code}_history.json'
        url='https://api.fund.eastmoney.com/f10/lsjz'
        if not p.exists():
            rows=[];page=1
            while True:
                r=requests.get(url,params=dict(fundCode=code,pageIndex=page,pageSize=1000,startDate='2018-01-01',endDate='2026-10-21'),headers={'Referer':'https://fundf10.eastmoney.com/'},timeout=30);r.raise_for_status();j=r.json()
                a=(j.get('Data') or {}).get('LSJZList') or []
                if not a:break
                rows.extend(a)
                if len(rows)>=int(j.get('TotalCount') or 0):break
                page+=1
                if page>50:raise RuntimeError('pagination limit')
            p.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
        rows=json.loads(p.read_text(encoding='utf-8'))
        print(code,len(rows),rows[:1],flush=True)
        log.append(dict(code=code,url=url,params={'startDate':'2018-01-01','endDate':'2026-10-21','pageSize':1000},sha256=hashlib.sha256(p.read_bytes()).hexdigest(),retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        f=RAW/f'{code}_fhsp.html'
        if not f.exists():
            r=requests.get(f'https://fundf10.eastmoney.com/fhsp_{code}.html',timeout=25);r.raise_for_status();f.write_bytes(r.content)
    (ROOT/'history_manifest.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
