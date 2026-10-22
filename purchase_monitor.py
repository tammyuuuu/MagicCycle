"""Daily public purchase-channel and low-volatility watchlist snapshots."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ZONE=timezone(timedelta(hours=8))
ROOT=Path(__file__).resolve().parent
QUOTA_SOURCE='https://qdiilimit.com/'
FUNDS=[
 dict(code='021000',name='南方纳指100 I',kind='us',index='纳指100',channel='南方基金官方App/官网',fee_pct=.66,product_url='https://www.nffund.com/new/personal-financing/detail.html?fundCode=021000',note='被动指数；销售服务费含现行优惠，可能调整'),
 dict(code='019441',name='万家纳指100 A',kind='us',index='纳指100',channel='万家基金官方App/官网',fee_pct=.65,product_url='https://www.wjasset.com/products/qdii/019441/',note='被动指数；另计申购费，A/C额度合并'),
 dict(code='022525',name='天弘纳指100 D',kind='us',index='纳指100',channel='支付宝等指定代销',fee_pct=.8,product_url='https://fund.stockstar.com/funds/f10/fundbuy_022525.html',note='被动指数；未登录代销渠道确认个人可买状态'),
 dict(code='017641',name='摩根标普500 A',kind='us',index='标普500',channel='摩根官方及代销',fee_pct=.65,product_url='https://ecmob.cifm.com/lcsm/mall/fundDetail?product_code=017641',note='被动指数；另计申购费'),
 dict(code='022523',name='天弘标普500 D',kind='us',index='标普500',channel='支付宝等指定代销',fee_pct=1.05,product_url='https://www.howbuy.com/fund/info/dtl/0225235315675.htm',note='主动管理QDII-FOF；另有底层基金费用，不等同纯被动指数'),
 dict(code='006484',name='广发中债1—3年国开债指数A',kind='bond',index='短久期政策性金融债',channel='广发官方及代销',product_url='https://www.gffunds.com.cn/funds/?fundcode=006484',note='仅债券配置观察；受利率波动影响，净值可能下跌，不作为应急现金替代；另计申购和赎回费用'),
]

def parse_quota(html,today):
    soup=BeautifulSoup(html,'html.parser')
    title=soup.find('h1');heading=title.get_text(' ',strip=True) if title else ''
    match=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日',heading)
    if not match:raise ValueError('额度页面缺少数据日期')
    source_date=f'{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}'
    if source_date!=today:raise ValueError(f'额度来源日期{source_date}不是今天{today}')
    rows={}
    for table in soup.find_all('table'):
        all_rows=table.find_all('tr')
        if not all_rows:continue
        headers=[x.get_text(' ',strip=True) for x in all_rows[0].find_all(['th','td'])]
        if not any('代销限额' in x for x in headers):continue
        for tr in all_rows[1:]:
            cells=[x.get_text(' ',strip=True) for x in tr.find_all(['th','td'])]
            if len(cells)!=len(headers):continue
            values=dict(zip(headers,cells))
            code=values.get('基金代码','')
            if not re.fullmatch(r'\d{6}',code):continue
            def pick(prefix):return next((v for k,v in values.items() if k.startswith(prefix)),None)
            rows[code]=dict(retail_limit=pick('代销限额'),direct_limit=pick('直销限额'),notice=pick('备注'),source_date=source_date)
    if not rows:raise ValueError('未识别任何场外额度表')
    # Preserve published future-effective changes rather than silently using today's quota.
    alerts=[x.get_text(' ',strip=True) for x in soup.find_all('li') if re.search(r'\d{4}-\d{2}-\d{2}.*生效',x.get_text())]
    return rows,alerts

def parse_nav(payload,kind):
    items=(payload.get('Data') or {}).get('LSJZList') or []
    if not items:raise ValueError('无净值/收益数据')
    rows=sorted(items,key=lambda x:x.get('FSRQ',''),reverse=True)
    item=rows[0];date=item.get('FSRQ','')
    datetime.strptime(date,'%Y-%m-%d')
    def number(value):
        try:
            result=float(str(value).rstrip('%'))
            if not (-float('inf')<result<float('inf')):return None
            return result
        except (ValueError,TypeError):return None
    first=number(item.get('DWJZ'));second=number(item.get('LJJZ'))
    if first is None or first<0:raise ValueError('无有效净值/每万份收益')
    if kind=='money' and second is None:raise ValueError('无有效七日年化收益')
    return dict(nav_date=date,unit_nav=first if kind!='money' else None,
                income_per_10000=first if kind=='money' else None,
                yield_7d_pct=second if kind=='money' else None,
                nav_purchase_status=item.get('SGZT'),nav_redeem_status=item.get('SHZT'))

def fetch_nav(fund):
    code=fund['code'];url='https://api.fund.eastmoney.com/f10/lsjz'
    r=requests.get(url,params=dict(fundCode=code,pageIndex=1,pageSize=1),
                   headers={'Referer':f'https://fundf10.eastmoney.com/jjjz_{code}.html','User-Agent':'Mozilla/5.0'},timeout=10)
    r.raise_for_status();return parse_nav(r.json(),fund['kind'])

def update_snapshot(path=None):
    path=Path(path) if path else ROOT/'docs'/'purchase_monitor.json'
    now=datetime.now(ZONE);today=now.date().isoformat();quota={};alerts=[];errors=[]
    try:
        response=requests.get(QUOTA_SOURCE,headers={'User-Agent':'Mozilla/5.0'},timeout=12)
        response.raise_for_status();quota,alerts=parse_quota(response.text,today)
    except Exception as exc:errors.append('额度更新失败：'+str(exc))
    def build(fund):
        row=dict(fund);row['quota']=quota.get(fund['code']) if fund['kind']=='us' else None
        row['quota_state']='当日公开额度，未登录渠道确认' if row['quota'] else '未取得当日额度，不判断可买'
        row['nav_source']=f'https://fundf10.eastmoney.com/jjjz_{fund["code"]}.html'
        try:
            row.update(fetch_nav(fund))
            date=datetime.strptime(row['nav_date'],'%Y-%m-%d').date()
            age=(now.date()-date).days
            row['nav_state']='近期披露' if 0<=age<=7 else '净值过旧或日期异常，仅供核对'
        except Exception as exc:row['nav_state']='获取失败';row['nav_error']=str(exc)
        return row
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(build,FUNDS))
    snapshot=dict(version=1,updated_at=now.isoformat(timespec='seconds'),quota_source=QUOTA_SOURCE,source_type='第三方公开公告汇总；并非渠道交易确认',
                  rows=rows,future_alerts=alerts,errors=errors)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temp.replace(path)
    print(f'购买渠道与低波动观察已更新：{path}；当日额度{sum(bool(r["quota"]) for r in rows)}项，净值{sum("nav_date" in r for r in rows)}项',flush=True)
    return snapshot

if __name__=='__main__':update_snapshot()
