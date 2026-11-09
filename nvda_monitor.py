"""NVDA long-term buy/hold display; no personal holdings or timing signals."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from html import escape
import numpy as np
import pandas as pd
import requests
import msft_monitor

ROOT=Path(__file__).resolve().parent/'research_nvda_strategy'
LIVE=ROOT/'live';RAW=LIVE/'raw';SNAPSHOT=LIVE/'snapshot.json'
VERSION='NVDA-BUY-HOLD-v2'
spec=importlib.util.spec_from_file_location('nvda_entry_engine',msft_monitor.ROOT/'backtest.py')
bt=importlib.util.module_from_spec(spec);spec.loader.exec_module(bt);bt.ROOT=LIVE

def calculate(now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    expected=msft_monitor.expected_date(now)
    prices,splits,_=bt.load_chart('NVDA');prices=prices.loc[:pd.Timestamp(expected)]
    if len(prices)<2 or prices.index[-1].date()!=expected:raise ValueError('缺少最新完整交易日行情')
    for day in pd.date_range('2026-01-01',expected):
        if msft_monitor.session(day.date()) and day not in prices.index:raise ValueError(f'行情缺少交易日 {day.date()}')
    x,_=bt.signals(prices,bt.pit_fundamentals('NVDA',splits))
    ranks=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
    row=x.iloc[-1]
    if not np.isfinite(row.PE) or not np.isfinite(ranks.iloc[-1]):raise ValueError('财报缺失、过期或估值历史不足')
    return {'date':expected.isoformat(),'close':float(row.close),'change_pct':float((row.close/x.close.iloc[-2]-1)*100),
            'pe':float(row.PE),'percentile':float(ranks.iloc[-1]),'filed':row.filed.date().isoformat(),
            'updated_at':now.isoformat(),'version':VERSION}

def read_snapshot():
    try:return json.loads(SNAPSHOT.read_text(encoding='utf8'))
    except (OSError,ValueError):return None

def refresh():
    now=dt.datetime.now(dt.timezone.utc)
    urls=[('NVDA_chart.json','https://query1.finance.yahoo.com/v8/finance/chart/NVDA',
           {'period1':1199145600,'period2':int(now.timestamp())+86400,'interval':'1d','events':'div,splits'}, {'User-Agent':'Mozilla/5.0'}),
          ('NVDA_facts.json','https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json',{},
           {'User-Agent':os.environ.get('MSFT_SEC_USER_AGENT','Xingxun research contact research@example.org')})]
    originals={name:(RAW/name).read_bytes() for name,_,_,_ in urls}
    try:
        downloads={}
        for name,url,params,headers in urls:
            r=requests.get(url,params=params,headers=headers,timeout=20);r.raise_for_status();r.json();downloads[name]=r.content
        for name,data in downloads.items():(RAW/name).write_bytes(data)
        result=calculate(now)
        temp=SNAPSHOT.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf8');temp.replace(SNAPSHOT)
        return result,None
    except Exception as exc:
        for name,data in originals.items():(RAW/name).write_bytes(data)
        return read_snapshot(),str(exc)

def render(snapshot=None,error=None,now=None):
    snapshot=snapshot or read_snapshot()
    if not snapshot:
        return '<div class="card" data-asset-symbol="NVDA"><h2>NVIDIA <span class="muted">NVDA</span></h2><p>策略数据尚未核验，请刷新。</p></div>'
    d=pd.read_csv(ROOT/'pe_recent_aligned.csv');selected=d[d.threshold==0]
    roll=pd.read_csv(ROOT/'pe_rolling_5y_summary.csv');full=roll[roll.threshold==0].iloc[0]
    research=roll[roll.threshold==50].iloc[0]
    rows=''
    for period,label in [('1y','近1年'),('3y','近3年'),('5y','近5年')]:
        r=selected[selected.period==period].iloc[0];rows+=f'<tr><td>{label}</td><td>{r.CAGR:.2%}</td><td>{r.max_drawdown:.2%}</td><td>{r.stock_orders_per_year:.2f}</td></tr>'
    from asset_states import render_rail,render_basis
    summary={'asset_type':'nvda_entry','status':'buy','action':'买入／持有',
             'reason':'以长期持有为主；PE和买点研究仅供参考。',
             'decision_basis':[('主要策略','买入／持有，以长期持有为主；不产生择时交易信号'),
                               ('估值参考',f"PE {snapshot['pe']:.2f}，过去3年分位 {snapshot['percentile']:.1%}；不构成交易阈值"),
                               ('买点研究',f"107个滚动五年窗口中，立即买入平均年化 {full.mean_cagr:.2%}；等待PE分位≤50%为 {research.mean_cagr:.2%}，仅供参考"),
                               ('数据与版本',f"财报披露 {snapshot['filed']} · {VERSION}")],
             'details':{'strategy_presentation':{'title':'长期持有',
               'backtest':{'annual_pct':float(full.mean_cagr)*100,'max_drawdown_pct':abs(float(full.median_drawdown))*100,
                 'start':str(full.first_start),'end':'2026-10-30','annual_label':'滚动5年年化（平均）',
                 'drawdown_label':'最大回撤（中位）','period_label':'历史滚动5年 · 107个窗口 · 数据至2026-11-06'}}}}
    rail=render_rail(summary)
    return f'''<div class="card" data-asset-symbol="NVDA"><h2>NVIDIA <span class="muted">NVDA</span></h2>
    <p>数据日 {escape(snapshot['date'])} · 当前 ${snapshot['close']:.2f} · 当日涨跌 {snapshot['change_pct']:+.2f}%</p>
    {rail}<p class="muted">PE {snapshot['pe']:.2f} · 过去3年分位 {snapshot['percentile']:.1%}；买点研究仅供参考。</p>
    <details><summary>查看判断依据</summary>{render_basis(summary)}
    <details><summary>查看各区间回测</summary><div style="overflow-x:auto"><table><thead><tr><th>区间</th><th>年化</th><th>最大回撤</th><th>股票交易/年</th></tr></thead><tbody>{rows}</tbody></table></div>
    <p class="strategy-note">以上为立即买入的近期区间。滚动五年研究窗口高度重叠；分红再投，单边0.1%建仓成本，不含税与汇率。历史表现不保证未来收益。</p></details></details></div>'''
