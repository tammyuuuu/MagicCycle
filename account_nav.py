"""Public account NAV updates; never writes research inputs or user accounts."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json, math, requests, uuid, time
ROOT=Path(__file__).resolve().parent
ZONE=timezone(timedelta(hours=8))
CACHE=ROOT/'docs/account_nav.json'
def baseline():
    manifest=json.loads((ROOT/'workspace_data/manifest.json').read_text(encoding='utf8'))
    data=json.loads((ROOT/'workspace_data'/manifest['current']).read_text(encoding='utf8'))
    monitor=ROOT/'docs/purchase_monitor.json'
    if monitor.exists():
        snapshot=json.loads(monitor.read_text(encoding='utf8'))
        for row in snapshot.get('rows',[]):
            if row.get('kind')=='us' and row['code'] not in data['funds'] and row.get('nav_date') and isinstance(row.get('unit_nav'),(int,float)) and row['unit_nav']>0:
                data['funds'][row['code']]={'name':row['name'],'nav':[[row['nav_date'],row['unit_nav']]],'dividends':[],'account_only':True}
    return data
def build_snapshot(refresh=False, force=False):
    data=baseline();now=datetime.now(ZONE);old={}
    if CACHE.exists():
        try:old=json.loads(CACHE.read_text(encoding='utf8'))
        except (OSError,ValueError):pass
    need_history=any(f.get('account_only') and not old.get('funds',{}).get(code,{}).get('history_complete') and code not in old.get('errors',{}) for code,f in data['funds'].items())
    if refresh and not force and not need_history and old.get('attempted_at'):
        try:
            if 0 <= (now-datetime.fromisoformat(old['attempted_at'])).total_seconds()<900:return old
        except ValueError:pass
    result={'schema':'xingxun-account-nav-v1','source':'https://api.fund.eastmoney.com/f10/lsjz','attempted_at':now.isoformat() if refresh else old.get('attempted_at'),'funds':{},'errors':{}}
    def fetch_one(item):
        code,fund=item;existing=old.get('funds',{}).get(code,{});base_date=fund['nav'][-1][0]
        fallback={'nav':existing.get('nav',[]),'updated_at':existing.get('updated_at'),'history_complete':existing.get('history_complete',False)}
        if fund.get('account_only') and fallback['nav']:base_date=min([base_date]+[point[0] for point in fallback['nav']])
        if not refresh:return code,fallback,None
        try:
            full_history=bool(fund.get('account_only') and (force or not fallback['history_complete']));page_size=200 if full_history else 5
            if full_history:base_date='1900-01-01'
            cutoff=max([base_date]+[point[0] for point in fallback['nav']]);rows=[];deadline=time.monotonic()+20
            for page in range(1,61):
                if time.monotonic()>=deadline:raise ValueError('净值补齐超时，沿用已保存数据')
                response=requests.get(result['source'],params={'fundCode':code,'pageIndex':page,'pageSize':page_size},headers={'Referer':'https://fundf10.eastmoney.com/','User-Agent':'Mozilla/5.0'},timeout=min(10,max(1,deadline-time.monotonic())))
                response.raise_for_status();payload=response.json();batch=(payload.get('Data') or {}).get('LSJZList');total=payload.get('TotalCount')
                if not isinstance(batch,list):raise ValueError('未取得新净值，继续显示保存净值')
                if not batch:
                    if full_history and rows:break
                    raise ValueError('未取得新净值，继续显示保存净值')
                if full_history and rows and min(row['FSRQ'] for row in batch)>=min(row['FSRQ'] for row in rows):raise ValueError('历史净值分页没有前进，待核实')
                rows.extend(batch)
                if full_history:
                    if isinstance(total,(int,float)) and total>0 and len(rows)>=total:break
                elif min(row['FSRQ'] for row in batch)<=cutoff or len(batch)<page_size:break
            else:raise ValueError('历史净值缺口过长，需要补齐账户净值后重算')
            points=dict(fallback["nav"])
            known_dividends={d['ex_date'] for d in fund.get('dividends',[])}
            for row in rows:
                day=row['FSRQ'];datetime.strptime(day,'%Y-%m-%d');nav=float(row['DWJZ'])
                if day>now.date().isoformat() or not math.isfinite(nav) or nav<=0:raise ValueError('净值或日期异常')
                if day>base_date and row.get('FHSP') and row['FHSP'] not in ('--','-') and day not in known_dividends:
                    raise ValueError('新分红或折算待核实，暂不扩展账户净值')
                if day in points and points[day]!=nav:raise ValueError('同日净值冲突')
                if day>=base_date:points[day]=nav
            return code,{'nav':[[day,nav] for day,nav in sorted(points.items())],'updated_at':now.isoformat(),'history_complete':full_history or fallback['history_complete'],'provider_total':total},None
        except requests.RequestException:
            if fund.get('account_only'):fallback['history_complete']=False
            return code,fallback,'净值来源暂不可用，沿用保存数据'
        except (ValueError,KeyError,TypeError) as error:
            if fund.get('account_only'):fallback['history_complete']=False
            return code,fallback,str(error)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code,fund,error in pool.map(fetch_one,data['funds'].items()):
            result['funds'][code]=fund
            if error:result['errors'][code]=error
    if refresh:
        temp=CACHE.with_name(CACHE.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf8');temp.replace(CACHE)
    return result
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--refresh',action='store_true');parser.add_argument('--force',action='store_true');args=parser.parse_args()
    snapshot=build_snapshot(args.refresh,force=args.force)
    if not args.refresh:CACHE.write_text(json.dumps(snapshot,ensure_ascii=False,allow_nan=False),encoding='utf8')
    print('Account NAV snapshot:',len(snapshot['funds']),'funds;',len(snapshot['errors']),'warnings')
