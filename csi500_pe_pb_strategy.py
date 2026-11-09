"""Frozen PE/PB5 OR entry, PE exit. Used by live signals and backtest replay."""
import numpy as np
import pandas as pd
from broad_signal_rules import signal_frame
from valuation_data import summarize, normalize_pb_history, load_pb_cache, PB_SOURCE, PB_SOURCE_URL

STRATEGY_ID = 'pe_or_pb5_pe_exit'
STRATEGY_VERSION = 'csi500_pe_or_pb5_pe_exit_v4'
PARAMETERS = dict(valuation_years=5, pb_valuation_years=5, fixed_valuation_years=True,
                  entry_percentile=60, pb_entry_percentile=10, exit_percentile=30,
                  entry_ma_window=120, ma_window=120, valuation_lag=1,
                  exit_priority=True, signal_execution='next_open')


def positions(close, pe, pb, window=120):
    average = close.rolling(window, min_periods=window).mean()
    held = False
    states = []
    for price, a, p, b in zip(close, average, pe, pb):
        if np.isfinite(a) and np.isfinite(p) and np.isfinite(b):
            if p >= 30 and price <= a:
                held = False
            elif not held and ((p < 60 and price > a) or b < 10):
                held = True
        states.append(float(held))
    return pd.Series(states, index=close.index)


def pb_frame(data, history):
    history = normalize_pb_history(pd.DataFrame(history).to_dict('records'))
    history = history[history.date <= data.index[-1]]
    if history.empty:
        return pd.DataFrame({'percentile': np.nan}, index=data.index)
    # As-of monthly latest sampling, exactly as in frozen monthly PB research.
    rows = []
    h = history.rename(columns={'pb': 'pe'})
    for date in history.date:
        s = summarize(h, date, 5)
        rows.append({'date': date, 'percentile': s.get('percentile'), 'valuation_date': date})
    aligned = pd.DataFrame(rows).set_index('date').reindex(data.index, method='ffill')
    age = (pd.Series(data.index, index=data.index) - aligned.valuation_date).dt.days
    aligned['percentile'] = aligned.percentile.where(age.between(0, 35))
    return aligned.shift(1)


def frame(data, pe_history, pb_history):
    pe_history = pd.DataFrame(pe_history, columns=['date', 'pe']).copy()
    pe_history['date'] = pd.to_datetime(pe_history.date)
    pe_history = pe_history[pe_history.date <= data.index[-1]]
    average = data.close.rolling(120, min_periods=120).mean()
    if pe_history.empty:
        pe = pd.DataFrame({'percentile': np.nan, 'ready': False}, index=data.index)
    else:
        pe = signal_frame(data, pe_history, 5, lag=1)
    pb = pb_frame(data, pb_history)
    ready = pe.ready & pb.percentile.notna() & average.notna()
    return pd.DataFrame(dict(ready=ready, position=positions(data.close, pe.percentile, pb.percentile),
                             percentile=pe.percentile, pb_percentile=pb.percentile, average=average), index=data.index)


def analyze(data, item, metrics, details):
    pe = pd.DataFrame(item.get('valuation_history') or [], columns=['date', 'pe'])
    if not pe.empty:
        pe.date = pd.to_datetime(pe.date)
        pe = pe[pe.date <= data.index[-1]]
    pb = (normalize_pb_history(item['pb_valuation_history']) if 'pb_valuation_history' in item
          else load_pb_cache(data.index[-1]))
    f = frame(data, pe, pb)
    row = f.iloc[-1]
    peval = pbval = None
    if len(data) > 1:
        as_of = data.index[-2]
        if not pe.empty:
            peval = summarize(pe, as_of, 5)
            peval.update(source='乐咕乐股 · 指数等权滚动PE（ttmPe，月度快照）')
        if not pb.empty:
            pbval = summarize(pb.rename(columns={'pb': 'pe'}), as_of, 5)
            pbval.update(metric='PB', source=PB_SOURCE, source_url=PB_SOURCE_URL)
    ready = bool(row.ready) and not details.get('data_warning')
    pe_pct = float(row.percentile) if pd.notna(row.percentile) else None
    pb_pct = float(row.pb_percentile) if pd.notna(row.pb_percentile) else None
    above = bool(pd.notna(row.average) and data.close.iloc[-1] > row.average)
    exit_now = ready and pe_pct >= 30 and not above
    allowed = ready and bool(row.position)
    status = 'buy' if allowed else 'exit' if exit_now else 'watch'
    if not ready:
        reason = 'PE、PB或行情数据不足、过旧，暂时观察，待数据更新后再判断。'
    elif exit_now:
        reason = '当前PE估值不算低，价格也不高于120日均线，因此策略建议退出。如果尚未买入，继续等待即可。'
    elif allowed:
        reason = ('PB已处于极低位，策略允许提前买入；目前未触发PE退出条件。已有持仓继续持有，尚未买入可按策略买入。'
                  if pb_pct < 10 and not above else
                  '当前处于策略允许买入和持有的阶段，尚未触发PE退出条件。已有持仓继续持有，尚未买入可按策略买入。')
    else:
        reason = 'PE趋势买入和PB极低位买入条件尚未满足，继续等待即可。'
    checks = [('估值参考', 'PE、PB均固定近5年；不随全局估值参考切换'),
              ('PE分位', f'{pe_pct:g}%（{peval["date"]}）' if pe_pct is not None and peval else '数据不足或过旧'),
              ('PB分位', f'{pb_pct:g}%（{pbval["date"]}）' if pb_pct is not None and pbval else '数据不足或过旧'),
              ('买入条件', 'PE分位低于60%且收盘高于MA120，或PB分位低于10%；退出条件成立时不买入'),
              ('退出条件', 'PE分位至少30%且收盘不高于MA120；退出优先，PB低估不覆盖退出'),
              ('策略阶段', '数据不足，暂停判断' if not ready else '保持持有许可，等待退出条件' if allowed else '退出或等待新的入场条件')]
    metrics.update(valuation_percentile=pe_pct, pb_percentile=pb_pct, ma120=float(row.average) if pd.notna(row.average) else None)
    details.update(strategy_mode='broad_individual', strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
                   legacy=None, enabled_decisions=['buy','watch','exit'], insufficient_history=not ready,
                   valuation=peval, pb_valuation=pbval, parameters=dict(PARAMETERS),
                   strategy_options={}, valuation_options={}, pb_data_warning=item.get('pb_data_warning'),
                   new_money_fraction=.5 if status=='buy' else 0.)
    return dict(symbol=item['code'], name=item['name'], asset_type='broad_etf', subtype=item.get('index'),
                date=data.index[-1].date().isoformat(), status=status, action={'buy':'买入','exit':'退出','watch':'观察'}[status],
                reason=reason, risk_level='normal', metrics=metrics, details=details, decision_basis=checks,
                decision_conditions=[dict(condition=k,result=v,met=None) for k,v in checks])
