# -*- coding: utf-8 -*-
"""行业ETF：20日均线趋势策略，收盘判断、下一交易日执行。

非线上状态转入线上时提醒买入；线上观察，首次线下减半、连续两日线下退出。
持仓和盈亏不改变市场判断。
"""

import math
import pandas as pd


from strategy_config import SECTOR_PROFILE
DEFAULT_PROFILE = dict(SECTOR_PROFILE)
STRATEGY_VERSION = 'sector_ma20_partial_v2'


def partial_exit_targets(close, window=20):
    """首个线下交易日保留一半，连续两日线下退出；线上恢复。"""
    above = trend_positions(close, window)
    ready = close.rolling(window, min_periods=window).mean().notna()
    return pd.Series([1. if up else .5 if ok and prev else 0.
                      for up, ok, prev in zip(above, ready, above.shift(1, fill_value=False))], index=close.index)


def trend_positions(close, window=20):
    """研究、提醒、回测共用目标状态；均线未就绪时为False。"""
    if int(window) != window or window < 2:
        raise ValueError('均线周期须为至少2的整数')
    average = close.rolling(int(window), min_periods=int(window)).mean()
    return close > average


def _weekly_below_slow(d: pd.DataFrame, weeks=2) -> bool:
    weekly = d[["close", "ma_slow"]].resample("W-FRI").last().dropna()
    weekly = weekly[weekly.index <= d.index[-1]]  # 仅确认完整周
    return len(weekly) >= weeks and bool(
        (weekly["close"].iloc[-weeks:] < weekly["ma_slow"].iloc[-weeks:]).all()
    )


def analyze_latest(df: pd.DataFrame, profile: dict = None) -> dict:
    p = {**DEFAULT_PROFILE, **(profile or {})}
    if int(p['ma_fast']) != p['ma_fast'] or p['ma_fast'] < 2:
        raise ValueError('均线周期须为至少2的整数')
    window = int(p['ma_fast'])
    minimum = max(window, int(p['min_history']))
    p['min_history'] = minimum
    d = df.copy().sort_index()
    d = d[~d.index.duplicated(keep='last')]
    d['close'] = pd.to_numeric(d['close'], errors='coerce')
    d = d[d['close'].map(lambda x: pd.notna(x) and math.isfinite(x) and x > 0)]
    if d.empty:
        raise ValueError('缺少有效收盘行情')
    close = d.close.astype(float)
    average = close.rolling(window, min_periods=window).mean()
    positions = trend_positions(close, window)
    ready = len(close) >= minimum and pd.notna(average.iloc[-1])
    above = bool(positions.iloc[-1]) if ready else None
    previous_above = bool(positions.iloc[-2]) if len(close) > 1 else False
    previous_ready = len(close) > 1 and pd.notna(average.iloc[-2])
    fresh_entry = bool(ready and above and not previous_above)
    crossed_down = bool(ready and not above and previous_above)
    targets = partial_exit_targets(close, window)
    below_days = 0
    for i in range(len(close)-1, -1, -1):
        if pd.isna(average.iloc[i]) or positions.iloc[i]:
            break
        below_days += 1
    if not ready:
        status, action, reason = 'watch', '观察', f'不足{minimum}个有效交易日，先观察。'
    elif fresh_entry:
        status, action = 'buy', '买入'
        reason = (f'收盘价重新站上{window}日均线，出现买入信号；已有持仓不重复买入。' if previous_ready else
                  f'{window}日均线已就绪，收盘价在均线上方，首次出现买入信号。')
        if len(targets)>1 and targets.iloc[-2]==.5:
            reason = f'减半后重新站上{window}日均线，买回减掉的部分；未持有可按计划买入。'
    elif above:
        status, action, reason = 'watch', '观察', f'收盘价保持在{window}日均线上方，没有新的买入信号；已有持仓保持。'
    elif crossed_down:
        status, action, reason = 'reduce', '减仓', f'收盘价首次回到{window}日均线或下方，下一交易日减半；未持有无需卖出。'
    elif below_days < 2:
        status, action, reason = 'watch', '观察', '均线刚就绪，尚未出现买入信号，先观察。'
    else:
        status, action, reason = 'exit', '退出', f'收盘价连续{below_days}个交易日在{window}日均线或下方，退出剩余持仓；未持有无需卖出。' if below_days >= 2 else f'收盘价在{window}日均线或下方，尚未出现进入信号；未持有无需卖出。'
    return {
        'strategy_type': 'industry', 'strategy_version': STRATEGY_VERSION,
        'date': d.index[-1].date().isoformat(), 'close': round(float(close.iloc[-1]), 4),
        'ma20': round(float(average.iloc[-1]), 4) if ready else None,
        'ma_value': float(average.iloc[-1]) if ready else None,
        'previous_above': previous_above, 'previous_ready': bool(previous_ready),
        'above_ma': above, 'fresh_entry': fresh_entry, 'crossed_down': crossed_down,
        'target_exposure': float(targets.iloc[-1]) if ready else None,
        'below_days': below_days,
        'insufficient_history': not ready, 'history_days': len(close),
        'status': status, 'action': action, 'reason': reason, 'profile': p,
    }


def decide(rep: dict, holding: bool, current_return=None) -> dict:
    """API兼容入口：持仓只解释是否需要卖出，不改变市场条件。"""
    return {'action': rep['status'], 'buy_signal': rep['fresh_entry'],
            'buy_amount': None if rep['fresh_entry'] else 0,
            'buy_tier': '出现买入信号，金额由投资计划预算决定' if rep['fresh_entry'] else '今天不新增买入',
            'sell_advice': rep['reason'] if rep['status'] in ('reduce','exit') and holding else '当前未持有，无需卖出' if not holding else '已有持仓保持',
            'holding': holding, 'current_return': current_return,
            'strategy_version': rep['strategy_version']}
