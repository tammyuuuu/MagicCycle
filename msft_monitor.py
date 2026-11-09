"""MSFT monthly valuation monitor. Cached inputs are never treated as live."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from html import escape

import pandas as pd
import requests
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, USMartinLutherKingJr,
    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay,
    nearest_workday)

ROOT = Path(__file__).resolve().parent / 'research_msft_strategy' / 'engine'
RAW = ROOT / 'raw'
SNAPSHOT = ROOT / 'snapshot.json'
spec = importlib.util.spec_from_file_location('msft_research_engine', ROOT / 'backtest.py')
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

class NYSECalendar(AbstractHolidayCalendar):
    rules = [Holiday('New Year', month=1, day=1, observance=nearest_workday),
             USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
             Holiday('Juneteenth', month=6, day=19, observance=nearest_workday, start_date='2022-01-01'),
             Holiday('Independence', month=7, day=4, observance=nearest_workday),
             USLaborDay, USThanksgivingDay, Holiday('Christmas', month=12, day=25, observance=nearest_workday)]

def session(day):
    # Exchange-specific exceptional closures must be reviewed annually.
    if day.year not in (2026, 2027):
        raise ValueError('美股日历超出已核验范围')
    holidays = NYSECalendar().holidays(start=f'{day.year-1}-12-25', end=f'{day.year+1}-01-07')
    return day.weekday() < 5 and pd.Timestamp(day) not in holidays

def expected_date(now):
    local = now.astimezone(ZoneInfo('America/New_York'))
    day = local.date()
    for _ in range(12):
        # 18:00 ET is conservative, including early-close sessions.
        if session(day) and (day < local.date() or local.hour >= 18): return day
        day -= dt.timedelta(days=1)
    raise ValueError('无法确定美股最新完整交易日')

def month_end(day):
    nxt=day+dt.timedelta(days=1)
    while not session(nxt): nxt += dt.timedelta(days=1)
    return nxt.month != day.month

def next_session(day):
    day += dt.timedelta(days=1)
    while not session(day): day += dt.timedelta(days=1)
    return day

def signal_view(snapshot, now, fresh):
    """Use New York calendar dates; stale data can never authorize a trade."""
    event=snapshot.get('last_trade')
    if not event: return None, '无历史买卖信号', False
    plan=dt.date.fromisoformat(event['planned_date'])
    today=now.astimezone(ZoneInfo('America/New_York')).date()
    expired=today > plan
    return event, ('已过执行日' if expired else '待计划日执行' if fresh else '数据未更新'), bool(fresh and not expired)

def calculate(now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    prices,splits,_=bt.load_chart('MSFT')
    expected=expected_date(now)
    # Yahoo may include the current, unfinished session during market hours.
    prices=prices.loc[:pd.Timestamp(expected)]
    if prices.empty: raise ValueError('行情为空')
    for day in pd.date_range('2026-01-01', expected):
        if session(day.date()) and day not in prices.index:
            raise ValueError(f'行情缺少交易日 {day.date()}')
    facts=bt.pit_fundamentals('MSFT',splits)
    x,_=bt.signals(prices,facts)
    end=x.index[-1].date()
    if end != expected: raise ValueError(f'行情日期 {end} 与最新完整交易日不一致')
    # Historical states use only completed month-end closes; transition is
    # effective at the next trading open, independent of the user's account.
    held=False; last_signal=None; last_signal_date=None; pending=None; transitions=[]; last_trade=None; monthly_position=None; trade_history=[]
    history=x.loc['2013-01-02':]
    for i,(timestamp,row) in enumerate(history.iterrows()):
        day=timestamp.date()
        if pending is not None:
            held=pending; pending=None
            transitions.append({'date':day.isoformat(),'action':'买入' if held else '卖出'})
        is_month_end = (history.index[i+1].month != timestamp.month) if i+1 < len(history) else month_end(day)
        if not is_month_end: continue
        desired=held
        if not bool(row.valuation_valid) or row.PE_rank >= .8: desired=False
        elif row.PE_rank <= .4: desired=True
        action='买入' if desired and not held else '卖出' if held and not desired else '持有/观察'
        last_signal=action; last_signal_date=day.isoformat()
        monthly_position='持有' if desired else '空仓观察'
        if desired != held:
            pending=desired
            planned = history.index[i+1].date() if i+1 < len(history) else next_session(day)
            last_trade={'signal_date':day.isoformat(),'action':action,'planned_date':planned.isoformat()}
            trade_history.append(last_trade)
    row=x.iloc[-1]
    if not bool(row.valuation_valid): raise ValueError('财报数据缺失、过期或估值历史不足')
    return {'date':end.isoformat(),'close':float(row.close),'change_pct':float((row.close / x.close.iloc[-2]-1)*100), 'pe':float(row.PE),
            'percentile':float(row.PE_rank),'filed':row.filed.date().isoformat(),
            'position':'持有' if held else '空仓观察', 'pending':pending,
            'last_signal':last_signal,'last_signal_date':last_signal_date, 'monthly_position':monthly_position, 'last_trade':last_trade, 'trade_history':trade_history,
            'updated_at':now.isoformat(), 'version':'MSFT-PIT-PE-v1', 'transitions':transitions}

def refresh():
    """Fetch both sources together; keep old inputs and snapshot on failure."""
    now=dt.datetime.now(dt.timezone.utc)
    headers={'User-Agent':os.environ.get('MSFT_SEC_USER_AGENT','Xingxun research contact research@example.org')}
    urls=[('MSFT_chart.json','https://query1.finance.yahoo.com/v8/finance/chart/MSFT',
           {'period1':1199145600,'period2':int(now.timestamp())+86400,'interval':'1d','events':'div,splits'}, {'User-Agent':'Mozilla/5.0'}),
          ('MSFT_facts.json','https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json',{},headers)]
    originals={name:(RAW/name).read_bytes() for name,_,_,_ in urls}
    try:
        downloads={}
        for name,url,params,header in urls:
            response=requests.get(url,params=params,headers=header,timeout=20)
            response.raise_for_status(); response.json()
            downloads[name]=response.content
        for name,content in downloads.items(): (RAW/name).write_bytes(content)
        result=calculate(now)
        temp=SNAPSHOT.with_suffix('.tmp')
        temp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf8')
        temp.replace(SNAPSHOT)
        return result, None
    except Exception as exc:
        for name,content in originals.items(): (RAW/name).write_bytes(content)
        return read_snapshot(), str(exc)

def read_snapshot():
    try: return json.loads(SNAPSHOT.read_text(encoding='utf8'))
    except (OSError,ValueError): return None

def render(snapshot=None, error=None, now=None):
    snapshot=snapshot or read_snapshot()
    if not snapshot: return '<div class="card" data-asset-symbol="MSFT"><h2>Microsoft <span class="muted">MSFT</span></h2><p>数据尚不可用，请更新后重试。</p></div>'
    now=now or dt.datetime.now(dt.timezone.utc)
    try:
        fresh = dt.date.fromisoformat(snapshot['date']) == expected_date(now) and not error
        expiry_day=dt.date.fromisoformat(snapshot['date'])+dt.timedelta(days=1)
        while not session(expiry_day): expiry_day+=dt.timedelta(days=1)
        expiry=int(dt.datetime.combine(expiry_day,dt.time(18),ZoneInfo('America/New_York')).timestamp()*1000)
    except ValueError: fresh=False; expiry=0
    event, event_status, executable = signal_view(snapshot, now, fresh)
    status = event['action'] if event and executable and snapshot.get('last_signal_date')==event['signal_date'] else '持有/观察'
    state = '待下个交易日开盘模拟执行' if snapshot.get('pending') is not None and executable else '无待执行交易'
    metrics=pd.read_csv(ROOT/'metrics.csv')
    selected=metrics[(metrics.ticker=='MSFT') & (metrics.strategy=='valuation')]
    rows=''
    for period,label in [('trailing_1y','近1年'),('trailing_3y','近3年'),('trailing_5y','近5年'),('full','全样本')]:
        r=selected[selected.period==period].iloc[0]
        rows+=f'<tr><td>{label}</td><td>{r.CAGR:.2%}</td><td>{r.max_drawdown:.2%}</td><td>{r.stock_orders_per_year:.2f}</td></tr>'
    from asset_states import render_rail, render_basis
    reason=('月末确认买入，等待下个交易日开盘。' if status=='买入' else
            '月末确认卖出，等待下个交易日开盘。' if status=='卖出' else
            '暂无新的月末交易信号，继续观察。' if fresh else '暂时观察。')
    full=selected[selected.period=='full'].iloc[0]
    visible_event_status = '暂时观察' if event_status == '数据未更新' else event_status
    last_trade_text = (f"{event['signal_date']} · {event['action']} · 计划 {event['planned_date']} 美股开盘 · {visible_event_status}" if event else '暂无')
    basis=[('行情前提', '月末确认交易信号' if fresh else '暂时观察'),
           ('估值观察',f"PE {snapshot['pe']:.2f}，历史分位 {snapshot['percentile']:.1%}"),
           ('策略规则','月末PE分位≤40%买入，≥80%卖出；其余维持状态，下一交易日开盘模拟执行'),
           ('模拟状态',f"{snapshot['position']} · {state}；独立于个人实盘持仓"),
           ('数据与版本',f"财报披露 {snapshot['filed']} · {snapshot['version']}")]
    summary={'asset_type':'stock','status':{'买入':'buy','持有/观察':'watch','卖出':'exit'}[status],
             'action':status,'reason':reason,'decision_basis':basis,
             'details':{'strategy_presentation':{'title':'月度估值策略',
                 'backtest':{'annual_pct':float(full.CAGR)*100,'max_drawdown_pct':abs(float(full.max_drawdown))*100,
                             'start':str(full.start),'end':str(full.end)}}}}
    rail=render_rail(summary).replace('<b>当前建议：','<b class="msft-status">当前建议：',1)
    change = snapshot.get('change_pct')
    change_text = f'{change:+.2f}%' if change is not None else '暂无'
    e=escape
    def history_status(item):
        status=signal_view({'last_trade':item},now,fresh)[1]
        return '暂时观察' if status=='数据未更新' else status
    history_rows=''.join(f"<li>{e(item['signal_date'])} · {e(item['action'])} · 计划 {e(item['planned_date'])} 开盘 · {e(history_status(item))}</li>" for item in reversed(snapshot.get('trade_history',[])))
    deadline = int(dt.datetime.combine(dt.date.fromisoformat(event['planned_date'])+dt.timedelta(days=1),dt.time.min,ZoneInfo('America/New_York')).timestamp()*1000) if event else 0
    return f'''<div class="card" data-asset-symbol="MSFT" data-msft-expiry="{expiry}" data-msft-signal-deadline="{deadline}"><h2>Microsoft <span class="muted">MSFT</span></h2>
    <p>数据日 {e(snapshot['date'])} · 当前 ${snapshot['close']:.2f} · 当日涨跌 {change_text}</p>
    <p class="fine">月末确认 {e(snapshot['last_signal_date'] or '暂无')} · 策略状态 {e(snapshot.get('monthly_position') or snapshot['position'])} · {e(snapshot.get('last_signal') or '观察')}</p>
    <p class="fine msft-recent-signal">最近买卖信号：{e(last_trade_text)}</p>
    <p class="fine">历史回测中，延迟10个交易日内执行的全样本收益与最大回撤差异较小，仅供参考。</p>
    {rail}
    <details><summary>查看判断依据</summary>{render_basis(summary)}
    <details><summary>查看历史买卖信号</summary><ul class="strategy-basis">{history_rows or '<li>暂无记录</li>'}</ul></details>
    <details><summary>查看各区间回测</summary><div style="overflow-x:auto"><table><thead><tr><th>区间</th><th>年化</th><th>最大回撤</th><th>股票交易/年</th></tr></thead><tbody>{rows}</tbody></table></div>
    <p class="strategy-note">含股息再投、BIL 空仓收益及单边 0.1% 成本，不含税与汇率。历史留出并非真实样本外；近年优势集中于一次空仓，长期可能踏空。</p></details></details></div>'''
