"""Apple observation only: no strategy buy/sell signals or personal holdings."""
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

ROOT=Path(__file__).resolve().parent/'research_aapl_strategy'
LIVE=ROOT/'live';RAW=LIVE/'raw';SNAPSHOT=LIVE/'snapshot.json'
VERSION='AAPL-DD20-ADD25-v1'
spec=importlib.util.spec_from_file_location('aapl_observation_engine',msft_monitor.ROOT/'backtest.py')
bt=importlib.util.module_from_spec(spec);spec.loader.exec_module(bt);bt.ROOT=LIVE

def calculate(now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    expected=msft_monitor.expected_date(now)
    prices,splits,_=bt.load_chart('AAPL');prices=prices.loc[:pd.Timestamp(expected)]
    if len(prices)<2 or prices.index[-1].date()!=expected:raise ValueError('缺少最新完整交易日行情')
    for day in pd.date_range('2026-01-01',expected):
        if msft_monitor.session(day.date()) and day not in prices.index:raise ValueError(f'行情缺少交易日 {day.date()}')
    x,_=bt.signals(prices,bt.pit_fundamentals('AAPL',splits))
    rank=x.PE.rolling(756,min_periods=378).apply(lambda a:np.sum(a[np.isfinite(a)]<=a[-1])/np.isfinite(a).sum() if np.isfinite(a[-1]) else np.nan,raw=True)
    row=x.iloc[-1]
    if not np.isfinite(row.PE) or not np.isfinite(rank.iloc[-1]):raise ValueError('财报缺失、过期或估值历史不足')
    cash,_,_=bt.load_chart('BIL')
    cash=cash.loc[:pd.Timestamp(expected)]
    if not prices.loc['2013-01-02':].index.isin(cash.index).all():raise ValueError('BIL 历史行情缺失')
    drawdown=1-prices.close/prices.close.rolling(252,min_periods=252).max()
    dates=prices.index; start=dates.get_loc(pd.Timestamp('2013-01-02'))
    reserve=.999/float(cash.loc[dates[start],'adjopen']); active=False; trades=[]; latest=None
    # The first 2013 open may execute the prior December month-end signal.
    for i in range(start-1,len(dates)):
        day=dates[i].date()
        is_month_end=(dates[i+1].month!=dates[i].month) if i+1<len(dates) else msft_monitor.month_end(day)
        if not is_month_end:continue
        value=drawdown.iloc[i]
        if not np.isfinite(value):continue
        condition=bool(value>=.20); triggered=condition and not active; active=condition
        planned=dates[i+1].date() if i+1<len(dates) else msft_monitor.next_session(day)
        available=reserve*float(cash.loc[dates[i+1] if i+1<len(dates) else dates[i],'adjopen' if i+1<len(dates) else 'adjclose'])
        event=None
        if triggered and available+1e-12>=.25:
            event={'signal_date':day.isoformat(),'planned_date':planned.isoformat(),'action':'加仓','drawdown':float(value)}
            if i+1<len(dates):
                reserve-=.25/float(cash.loc[dates[i+1],'adjopen'])
                event['executed']=True
            else:event['executed']=False
            trades.append(event)
        latest={'date':day.isoformat(),'drawdown':float(value),'action':'加仓' if event else '持有/观察'}
    return {'date':expected.isoformat(),'close':float(row.close),'change_pct':float((row.close/x.close.iloc[-2]-1)*100),
            'pe':float(row.PE),'percentile':float(rank.iloc[-1]),'filed':row.filed.date().isoformat(),
            'drawdown':float(drawdown.iloc[-1]),'monthly':latest,'last_trade':trades[-1] if trades else None,
            'trade_history':trades,'reserve_value':float(reserve*cash.loc[dates[-1],'adjclose']),
            'updated_at':now.isoformat(),'version':VERSION}

def read_snapshot():
    try:return json.loads(SNAPSHOT.read_text(encoding='utf8'))
    except (OSError,ValueError):return None

def refresh():
    now=dt.datetime.now(dt.timezone.utc)
    urls=[('AAPL_chart.json','https://query1.finance.yahoo.com/v8/finance/chart/AAPL',
           {'period1':1199145600,'period2':int(now.timestamp())+86400,'interval':'1d','events':'div,splits'},{'User-Agent':'Mozilla/5.0'}),
          ('AAPL_facts.json','https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json',{},
           {'User-Agent':os.environ.get('MSFT_SEC_USER_AGENT','Xingxun research contact research@example.org')}),
          ('BIL_chart.json','https://query1.finance.yahoo.com/v8/finance/chart/BIL',
           {'period1':1199145600,'period2':int(now.timestamp())+86400,'interval':'1d','events':'div,splits'},{'User-Agent':'Mozilla/5.0'})]
    originals={name:(RAW/name).read_bytes() for name,_,_,_ in urls}
    try:
        downloads={}
        for name,url,params,headers in urls:
            response=requests.get(url,params=params,headers=headers,timeout=20)
            response.raise_for_status();response.json();downloads[name]=response.content
        for name,data in downloads.items():(RAW/name).write_bytes(data)
        result=calculate(now)
        temp=SNAPSHOT.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf8');temp.replace(SNAPSHOT)
        return result,None
    except Exception as exc:
        for name,data in originals.items():(RAW/name).write_bytes(data)
        return read_snapshot(),str(exc)

def render(snapshot=None,error=None,now=None):
    snapshot=snapshot or read_snapshot()
    if snapshot and 'monthly' not in snapshot:
        try:snapshot=calculate(now)
        except Exception:snapshot=None
    if not snapshot:return '<div class="card" data-asset-symbol="AAPL"><h2>Apple <span class="muted">AAPL</span></h2><p>行情暂无</p></div>'
    now=now or dt.datetime.now(dt.timezone.utc)
    try:fresh=not error and dt.date.fromisoformat(snapshot['date'])==msft_monitor.expected_date(now)
    except ValueError:fresh=False
    event,event_status,executable=msft_monitor.signal_view(snapshot,now,fresh)
    executable=bool(executable and event and snapshot['monthly']['date']==event['signal_date'])
    status='add' if executable else 'watch'
    event_status='暂时观察' if event_status=='数据未更新' else event_status
    event_text=(f"{event['signal_date']} · 加仓 · 计划 {event['planned_date']} 美股开盘 · {event_status}" if event else '暂无')
    deadline=int(dt.datetime.combine(dt.date.fromisoformat(event['planned_date'])+dt.timedelta(days=1),dt.time.min,msft_monitor.ZoneInfo('America/New_York')).timestamp()*1000) if event else 0
    expiry_day=msft_monitor.next_session(dt.date.fromisoformat(snapshot['date']))
    expiry=int(dt.datetime.combine(expiry_day,dt.time(18),msft_monitor.ZoneInfo('America/New_York')).timestamp()*1000)
    from asset_states import render_rail,render_basis
    metrics=pd.read_csv(ROOT/'base_add_metrics.csv'); metrics=metrics[(metrics.strategy=='dd_20')&(metrics.tranche==.25)]
    rolling=pd.read_csv(ROOT/'base_add_rolling_summary.csv');r=rolling[(rolling.strategy=='dd_20')&(rolling.tranche==.25)].iloc[0]
    rows=''
    for period,label in [('1y','近1年'),('3y','近3年'),('5y','近5年')]:
        m=metrics[metrics.period==period].iloc[0]
        rows+=f'<tr><td>{label}</td><td>{m.twr_cagr:.2%}</td><td>{m.max_drawdown:.2%}</td><td>{m.add_count/m.years:.2f}</td></tr>'
    rows+=f'<tr><td>滚动5年</td><td>{r.mean_twr_cagr:.2%}</td><td>{r.median_max_drawdown:.2%}</td><td>{r.mean_add_count/5:.2f}</td></tr>'
    basis=[('策略规则','月末收盘距过去252个交易日最高收盘价回撤≥20%时，每次加仓基础仓位初始金额的25%；下一交易日开盘模拟执行。'),
           ('重复触发','月末条件由不满足转为满足才触发；须先恢复到阈值以内才可再次触发。预留资金不足一笔时不加仓。'),
           ('估值观察',f"PE {snapshot['pe']:.2f}，过去3年分位 {snapshot['percentile']:.1%}；估值不触发交易。"),
           ('预算约束','实际加仓前自行核对：Apple 持仓及本次加仓合计不得超过总投资预算的10%；可用额度不足则减少或不加仓。'),
           ('模拟账户',f"独立模拟，未读取个人实盘持仓；剩余预留资金相当于初始基础仓位的 {snapshot['reserve_value']:.1%}。"),
           ('数据与风险',f"Yahoo 行情及 SEC 财报，披露 {snapshot['filed']}；产品需求、增长、监管与估值变化可能影响收益。{snapshot['version']}")]
    summary={'asset_type':'aapl_add','status':status,'action':'加仓' if executable else '持有/观察',
             'reason':'月末条件已触发，计划下个交易日开盘。' if executable else '等待新的月末加仓条件。',
             'decision_basis':basis,'details':{'strategy_presentation':{'title':'候选加仓策略',
             'backtest':{'annual_pct':float(r.mean_twr_cagr)*100,'max_drawdown_pct':abs(float(r.median_max_drawdown))*100,
               'start':'2013-01-02','end':'2026-11-06','annual_label':'滚动5年年化（平均）',
               'drawdown_label':'最大回撤（中位）','period_label':'107个重叠滚动5年窗口'}}}}
    rail=render_rail(summary).replace('<b>当前建议：','<b class="aapl-status">当前建议：',1)
    history=''.join(f"<li>{escape(t['signal_date'])} · 加仓 · 计划 {escape(t['planned_date'])} 开盘</li>" for t in reversed(snapshot.get('trade_history',[])))
    return f'''<div class="card" data-asset-symbol="AAPL"><h2>Apple <span class="muted">AAPL</span></h2>
    <p>数据日 {escape(snapshot['date'])} · 当前 ${snapshot['close']:.2f} · 当日涨跌 {snapshot['change_pct']:+.2f}%</p>
    <p class="fine">最新回撤 {snapshot['drawdown']:.2%} · PE {snapshot['pe']:.2f} · 过去3年分位 {snapshot['percentile']:.1%}</p>
    <p class="fine">月末确认 {escape(snapshot['monthly']['date'])} · 回撤 {snapshot['monthly']['drawdown']:.2%} · {escape(snapshot['monthly']['action'])}</p>
    <p class="fine aapl-recent-signal" data-deadline="{deadline}" data-expiry="{expiry}">最近加仓信号：{escape(event_text)}</p>
    {rail}
    <details><summary>查看判断依据</summary>{render_basis(summary)}
    <details><summary>查看历史加仓信号</summary><ul class="strategy-basis">{history or '<li>暂无记录</li>'}</ul></details>
    <details><summary>查看各区间回测</summary><div style="overflow-x:auto"><table><thead><tr><th>区间</th><th>年化</th><th>最大回撤</th><th>加仓/年</th></tr></thead><tbody>{rows}</tbody></table></div>
    <p class="strategy-note">滚动5年为年化平均、回撤中位及平均次数，窗口重叠；其他区间独立建仓。含 BIL 收益、分红再投和单边0.1%成本，不含税与汇率。历史表现不保证未来收益。</p></details></details></div>'''
