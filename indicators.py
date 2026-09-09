# -*- coding: utf-8 -*-
"""
技术指标工具库
==============
输入统一为 pandas.Series（或含 high/low/close 列的 DataFrame），
输出与原索引对齐。所有指标只使用“当前及之前”的数据，不含未来信息，
可直接用于回测。

用法示例：
    df["ma20"] = ma(df["close"], 20)
"""

import pandas as pd


# ------------------------- 均线 -------------------------
def ma(close: pd.Series, n: int = 20) -> pd.Series:
    """简单移动平均 MA，前 n-1 个值为 NaN。"""
    return close.rolling(window=n, min_periods=n).mean()


def ema(close: pd.Series, n: int = 12) -> pd.Series:
    """指数移动平均 EMA，前 n 个值为 NaN。"""
    e = close.ewm(span=n, adjust=False).mean()
    valid = close.notna().cumsum()
    return e.where(valid >= n)


def cross_up(a: pd.Series, b: pd.Series) -> pd.Series:
    """a 上穿 b：昨日 a<=b 且今日 a>b（布尔序列）。"""
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_down(a: pd.Series, b: pd.Series) -> pd.Series:
    """a 下穿 b：昨日 a>=b 且今日 a<b（布尔序列）。"""
    return (a < b) & (a.shift(1) >= b.shift(1))


# ------------------------- RSI -------------------------
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """相对强弱指标 RSI（Wilder 平滑）。"""
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    avg_up = up.ewm(alpha=1 / n, adjust=False).mean()
    avg_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_up / avg_down.replace(0.0, pd.NA)
    out = 100 - 100 / (1 + rs)
    # 数据不足 n 个时输出 NaN
    return out.where(close.notna().cumsum() > n)


# ------------------------- MACD -------------------------
def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    返回 (DIF, DEA, 柱) 三元组。
    DIF = EMA(fast) - EMA(slow)
    DEA = EMA(DIF, signal)
    柱  = 2 * (DIF - DEA)   （国内软件惯例）
    """
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = 2 * (dif - dea)
    return dif, dea, hist


# ------------------------- 布林带 -------------------------
def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    """返回 (上轨, 中轨, 下轨)。"""
    mid = ma(close, n)
    std = close.rolling(window=n, min_periods=n).std(ddof=0)
    return mid + k * std, mid, mid - k * std


# ------------------------- ATR -------------------------
def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """平均真实波幅 ATR（Wilder 平滑）。"""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ------------------------- 区间高低 -------------------------
def highest(close: pd.Series, n: int = 20) -> pd.Series:
    """过去 n 日最高收盘价。"""
    return close.rolling(window=n, min_periods=n).max()


def lowest(close: pd.Series, n: int = 20) -> pd.Series:
    """过去 n 日最低收盘价。"""
    return close.rolling(window=n, min_periods=n).min()
