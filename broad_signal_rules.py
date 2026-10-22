"""宽基分标的纯行情规则，实时提醒与研究共用。"""
import numpy as np
import pandas as pd
from valuation_data import summarize


def signal_frame(prices, history, years=5, lag=1, drawdown_filter=True):
    """同生产月度中秩分位、250日回撤；主检验估值多延迟一个交易日。"""
    if lag < 0 or int(lag) != lag:
        raise ValueError('估值延迟必须为非负整数')
    history = history.sort_values('date')
    if history.date.duplicated().any():
        raise ValueError('估值日期重复')
    # 缓存保留月内的历次更新；summarize 按每个可见时点选取月度样本。
    records = []
    for date in history.date:
        result = summarize(history, date, years)
        records.append({'date': date, 'percentile': result['percentile'], 'valuation_date': date})
    monthly = pd.DataFrame(records).set_index('date')
    aligned = monthly.reindex(prices.index, method='ffill')
    age = (pd.Series(prices.index, index=prices.index) - aligned.valuation_date).dt.days
    percentile = aligned.percentile.where(age.between(0, 35)).shift(lag)
    high = prices.close.rolling(250, min_periods=250).max()
    dd = (1 - prices.close / high).clip(lower=0)
    ready = high.notna() & percentile.notna()
    status = pd.Series('watch', index=prices.index)
    low = percentile < 30
    if drawdown_filter:
        status.loc[ready & low & (dd >= .10)] = 'buy'
        status.loc[ready & low & (dd >= .20)] = 'add'
    else:
        status.loc[ready & low] = 'add'
    status.loc[ready & (percentile > 70)] = 'reduce'
    status.loc[ready & (percentile >= 90)] = 'exit'
    return pd.DataFrame({'percentile': percentile, 'drawdown': dd, 'ready': ready,
                         'status': status}, index=prices.index)


def valuation_positions(percentile, close, entry=30, exit=90, confirm_exit=False,
                        protect=False, exit_ma=60, entry_ma=None):
    """估值低买入，持有到卖出条件；只用此前数据，仓位不产生买卖信号。"""
    ma60 = close.rolling(exit_ma, min_periods=exit_ma).mean()
    ma120 = close.rolling(120, min_periods=120).mean()
    buy_average = close.rolling(entry_ma, min_periods=entry_ma).mean() if entry_ma else close * 0
    held = False
    result = []
    for pct, price, short, long, buy in zip(percentile, close, ma60, ma120, buy_average):
        if np.isfinite(pct):
            high_exit = pct >= exit and (not confirm_exit or price <= short)
            weak_exit = protect and pct >= entry and price <= long
            if held and (high_exit or weak_exit):
                held = False
            elif not held and pct < entry and (entry_ma is None or price > buy):
                held = True
        result.append(float(held))
    return pd.Series(result, index=close.index)


def low_value_or_trend(close, pct, window, entry=30, ceiling=90):
    ma = close.rolling(window).mean()
    held = False
    states = []
    for value, price, average in zip(pct, close, ma):
        if np.isfinite(value) and np.isfinite(average):
            if held and value >= entry and price <= average:
                held = False
            elif not held and (value < entry or value < ceiling and price > average):
                held = True
        states.append(float(held))
    return pd.Series(states, index=close.index)


def price_band_positions(close, window=16, buffer=.02):
    """价格突破上沿进入、跌到下沿退出；中间保持行情许可。"""
    average = close.rolling(window, min_periods=window).mean()
    allowed = False
    values = []
    for price, ma in zip(close, average):
        if not np.isfinite(ma):
            allowed = False
        elif price > ma * (1 + buffer):
            allowed = True
        elif price <= ma * (1 - buffer):
            allowed = False
        values.append(float(allowed))
    return pd.Series(values, index=close.index)
