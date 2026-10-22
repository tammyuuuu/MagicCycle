# -*- coding: utf-8 -*-
"""第二轮策略库：每类资产的基础策略 A–F。

统一约定：
- 输入是含分红再投资的总收益指数；
- 所有 rolling/shift 只使用当日及之前的数据；
- 输出 0..1 的目标仓位，不直接产生买卖金额；
- 不做空、不加杠杆。
"""
import numpy as np
import pandas as pd


# ---------------- A. 买入持有 ----------------
def hold(tr, **kw):
    return pd.Series(1.0, index=tr.index)


# ---------------- B. 双均线趋势 ----------------
def ma(tr, n=120, **kw):
    line = tr.rolling(n, min_periods=n).mean()
    return (tr > line).astype(float).where(line.notna(), 0.0)


# ---------------- C. 长期趋势 + 回调买入 ----------------
def pullback(tr, n_trend=200, n_high=20, threshold=0.05, **kw):
    """长期均线上方才允许持仓；从 20 日高点回调 threshold 后买入，跌破长期均线清仓。

    进入后一直持有（不因小幅波动卖出），避免把"回调买入"变成高频交易。
    """
    trend = tr.rolling(n_trend, min_periods=n_trend).mean()
    high = tr.rolling(n_high, min_periods=n_high).max()
    out = np.zeros(len(tr))
    state = 0.0
    p = tr.to_numpy(float)
    m = trend.to_numpy(float)
    h = high.to_numpy(float)
    for i in range(len(p)):
        if not np.isfinite(m[i]):
            state = 0.0
        elif p[i] <= m[i]:
            state = 0.0
        elif np.isfinite(h[i]) and p[i] <= h[i] * (1 - threshold):
            state = 1.0
        out[i] = state
    return pd.Series(out, index=tr.index)


# ---------------- D. 唐奇安通道突破 ----------------
def donchian(tr, n_high=60, n_low=20, **kw):
    hi = tr.rolling(n_high, min_periods=n_high).max().shift(1)
    lo = tr.rolling(n_low, min_periods=n_low).min().shift(1)
    out = np.zeros(len(tr))
    state = 0.0
    p = tr.to_numpy(float)
    a = hi.to_numpy(float)
    b = lo.to_numpy(float)
    for i in range(len(p)):
        if np.isfinite(a[i]) and p[i] > a[i]:
            state = 1.0
        elif np.isfinite(b[i]) and p[i] < b[i]:
            state = 0.0
        out[i] = state
    return pd.Series(out, index=tr.index)


# ---------------- E. 波动率目标仓位 ----------------
def vol_target(tr, n_ma=120, n_vol=60, target_vol=0.15, **kw):
    ma_line = tr.rolling(n_ma, min_periods=n_ma).mean()
    vol = tr.pct_change(fill_method=None).rolling(n_vol, min_periods=n_vol).std() * np.sqrt(252)
    raw = (target_vol / vol).clip(upper=1.0)
    return raw.where((tr > ma_line) & vol.notna(), 0.0).fillna(0.0)


# ---------------- F1. 黄金过热降温 ----------------
def gold_heat(tr, return_window=20, ma_window=60, heat=0.15, cool=0.05,
              min_history=120, **kw):
    rise = tr.pct_change(return_window, fill_method=None)
    dev = tr / tr.rolling(ma_window, min_periods=ma_window).mean() - 1
    hot = (rise >= heat) & (dev >= heat)
    cold = (rise <= cool) & (dev <= cool)
    out = np.ones(len(tr))
    state = 1.0
    for i in range(len(tr)):
        if i + 1 < min_history:
            state = 0.0
        elif bool(cold.iloc[i]):
            state = 1.0
        elif bool(hot.iloc[i]):
            state = 0.5
        out[i] = state
    return pd.Series(out, index=tr.index)


# ---------------- F2. 债券趋势 / 久期动量 ----------------
def bond_momentum(tr, n=120, **kw):
    mom = tr.pct_change(n, fill_method=None)
    return (mom > 0).astype(float).where(mom.notna(), 0.0)


# ---------------- F3. 估值过滤（股票指数） ----------------
def pe_percentile_monthly(pe: pd.Series, years=5):
    """月度 PE 的滚动分位（中秩）。返回月末日期 -> 分位。"""
    pe = pe.dropna().sort_index()
    s = pe.groupby(pe.index.to_period("M")).last()
    win = years * 12
    vals = s.to_numpy(float)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        if i + 1 < win:
            continue
        w = vals[i - win + 1:i + 1]
        cur = w[-1]
        out[i] = ((w < cur).sum() + 0.5 * (w == cur).sum()) / len(w) * 100
    return pd.Series(out, index=s.index)


def valuation_overlay(pe: pd.Series, dates: pd.DatetimeIndex, years=5, lag_months=1):
    """把月末 PE 分位滞后一个月后前向填充到日频（只用当时已可见的数据）。"""
    pct = pe_percentile_monthly(pe, years)
    pct.index = pct.index.to_timestamp(how="end").normalize()
    pct = pct.shift(lag_months)               # 次月才可用
    daily = pct.reindex(dates, method="ffill")
    return daily


def ma_valuation(tr, pe_pct, n_ma=200, high_pct=90, **kw):
    """趋势为主，估值过热时降到半仓；估值极低且趋势向上时满仓。"""
    base = ma(tr, n_ma)
    out = base.copy()
    hot = pe_pct >= high_pct
    out[hot] = np.minimum(out[hot], 0.5)
    return out.fillna(0.0)
