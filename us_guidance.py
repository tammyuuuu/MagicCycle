"""美股新资金与持仓指导：月度长期方向、短期热度、价格恢复确认。"""
import numpy as np
import pandas as pd

VERSION = 'us_momentum_heat_v2'
PARAMETERS = {'momentum_months': 12, 'heat_window': 60, 'heat_threshold': .15,
              'cooling_threshold': .05, 'recovery_window': 20, 'reduce_fraction': .5}


def guidance_frame(close, heat_threshold=.15, cooling_threshold=.05):
    if not 0 <= cooling_threshold < heat_threshold:
        raise ValueError('冷却线应低于过热线')
    if close.empty:
        raise ValueError('行情为空')
    monthly = close.resample('ME').last()
    monthly = monthly.loc[monthly.index <= close.index[-1]]
    change = monthly.pct_change(12, fill_method=None)
    change = change.where(monthly.rolling(13, min_periods=13).count() == 13)
    direction = change.reindex(close.index, method='ffill')
    dates = pd.Series(monthly.index.strftime('%Y-%m-%d'), index=monthly.index).reindex(close.index, method='ffill')
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()
    deviation = close / ma60 - 1
    ready = direction.notna() & ma20.notna() & ma60.notna()
    strong = close > ma20
    heated, previous_heat = False, False
    rows = []
    for i, value in enumerate(deviation):
        previous_heat = heated
        if np.isfinite(value):
            if value <= cooling_threshold and strong.iloc[i]:
                heated = False
            if value >= heat_threshold:
                heated = True
        positive = bool(ready.iloc[i] and direction.iloc[i] > 0)
        if not ready.iloc[i]:
            status = 'watch'
        elif not positive:
            status = 'exit'
        elif heated:
            status = 'reduce' if not previous_heat else 'watch'
        elif previous_heat:
            status = 'add'
        elif strong.iloc[i]:
            status = 'buy'
        else:
            status = 'watch'
        rows.append({'status': status, 'heated': heated,
                     'entry_allowed': positive and not heated and bool(strong.iloc[i]),
                     'target': (0. if not positive else .5 if heated else 1.)})
    frame = pd.DataFrame(rows, index=close.index)
    frame['momentum12'] = direction
    frame['signal_date'] = dates
    frame['ma20'] = ma20
    frame['ma60'] = ma60
    frame['deviation60'] = deviation
    frame['ready'] = ready
    frame['short_strong'] = strong
    return frame


def analyze(data, item, metrics, details):
    frame = guidance_frame(data.close)
    row = frame.iloc[-1]
    valid = bool(row.ready)
    status = row.status
    signal_date = str(row.signal_date) if pd.notna(row.signal_date) else None
    m = float(row.momentum12 * 100) if valid else None
    heat = float(row.deviation60 * 100) if pd.notna(row.deviation60) else None
    short = bool(row.short_strong)
    reasons = {
        'buy': '长期方向向上，价格高于20日均价且未过热；本期新资金可买入，已有持仓不必重复交易。',
        'add': '过热已消化，价格高于20日均价；可加大本期投入，未持有也可买入。',
        'reduce': '首次进入短期过热阶段，已有持仓考虑减半一次；未持有先不买。',
        'exit': '最近完整月份的过去12个月涨幅不为正，长期方向转弱；已有持仓考虑退出。',
    }
    reason = reasons.get(status, '仍处于过热阶段，先不新增投入，不重复减仓。' if row.heated else
                         '价格尚未高于20日均价，先等短期恢复；这一条件本身不要求卖出已有持仓。')
    if not valid:
        reason = '不足13个连续完整月份或短期价格历史不足，先观察。'
    checks = [('长期方向', f'{signal_date}过去12个月涨幅{m:+.2f}%，' + ('方向向上' if m > 0 else '方向转弱')),
              ('短期热度', f'价格较60日均价偏离{heat:+.2f}%，' + ('过热阶段尚未解除' if row.heated else '未处于过热阶段')),
              ('价格恢复', '价格' + ('高于' if short else '尚未高于') + '20日均价')] if valid else [
                  ('判断前提', '13个连续完整月份，以及至少60个交易日价格')]
    notice = item.get('premium_notice')
    active_notice = bool(notice and data.index[-1].date().isoformat() == notice['date'])
    if active_notice:
        checks.insert(0, ('溢价提醒', notice['date'] + '基金公司提示场内溢价；新资金暂不追买'))
        if status in ('buy', 'add', 'watch'):
            status, reason = 'watch', '基金公司已提示场内溢价，先不新增投入；已有持仓继续按长期方向与过热条件判断。'
    if details.get('data_warning'):
        checks.insert(0, ('行情前提', '更新受限，先等待数据更新'))
        status, reason = 'watch', '行情更新受限，先观察；待数据更新后再按策略判断。'
    metrics.update(momentum12_pct=round(m, 2) if m is not None else None,
                   ma20=float(row.ma20) if pd.notna(row.ma20) else None,
                   ma60=float(row.ma60) if pd.notna(row.ma60) else None,
                   ma60_deviation_pct=round(heat, 2) if heat is not None else None)
    details.update(strategy_mode='us_monthly_trend', strategy_version=VERSION,
                   legacy=None, parameters=dict(PARAMETERS), insufficient_history=not valid,
                   enabled_decisions=['add', 'buy', 'watch', 'reduce', 'exit'],
                   signal_date=signal_date, heat_active=bool(row.heated),
                   fresh_add=status == 'add', fresh_reduce=status == 'reduce',
                   new_money_action=status if status in ('buy', 'add') else 'watch',
                   new_money_fraction={'buy': .5, 'add': 1.}.get(status, 0.),
                   premium_notice=dict(notice) if active_notice else None)
    return {'symbol': item['code'], 'name': item['name'], 'asset_type': 'broad_etf',
            'subtype': 'us_equity', 'date': data.index[-1].date().isoformat(),
            'status': status, 'action': {'add': '加仓', 'buy': '买入', 'watch': '观察', 'reduce': '减仓', 'exit': '退出'}[status],
            'reason': reason, 'risk_level': 'normal', 'metrics': metrics, 'details': details,
            'decision_basis': checks,
            'decision_conditions': [{'condition': title, 'result': text, 'met': None} for title, text in checks]}
