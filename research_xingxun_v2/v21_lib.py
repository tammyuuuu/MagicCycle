# -*- coding: utf-8 -*-
"""V2.1：组合定义、方法构造与建仓期指标。"""
import numpy as np
import pandas as pd

from entry_engine import OnceEntry, PullbackEntry, StagedEntry, run_episode

CAPITAL = 2000.0
CODES = ["000015", "001214", "008701", "161130"]
THREE = ["000015", "001214", "008701"]
NAMES = {"000015": "华夏纯债A", "001214": "华泰柏瑞500", "008701": "华夏黄金",
         "161130": "易方达纳指"}

COMBOS = {
    "A 黄金+纳指 50/50": {"008701": .5, "161130": .5},
    "B 债/金/纳 各1/3": {"000015": 1/3, "008701": 1/3, "161130": 1/3},
    "EQ 四只等权": {c: .25 for c in CODES},
    "K4 债/500/金 逆波动": None,   # 动态
    "C 四只逆波动": None,          # 动态
}


def invvol(prices, codes, i, window=120, cap=0.6):
    vol = {}
    for c in codes:
        arr = prices[c][max(0, i - window + 1):i + 1]
        r = np.diff(arr) / arr[:-1]
        vol[c] = np.std(r) * np.sqrt(252) if len(r) > 20 else 1.0
    inv = {c: 1.0 / max(v, 1e-6) for c, v in vol.items()}
    tot = sum(inv.values())
    w = {c: inv[c] / tot for c in codes}
    for _ in range(20):
        over = [c for c in w if w[c] > cap]
        if not over:
            break
        excess = sum(w[c] - cap for c in over)
        for c in over:
            w[c] = cap
        free = [c for c in w if w[c] < cap]
        s = sum(w[c] for c in free)
        for c in free:
            w[c] += excess * w[c] / s
    return w


def combo_weights(name, prices, i):
    if COMBOS[name] is not None:
        return COMBOS[name]
    if name == "K4 债/500/金 逆波动":
        return invvol(prices, THREE, i, 120, 0.6)
    return invvol(prices, CODES, i, 120, 0.5)


def make_method(method, weights0, prices, dates, start):
    if method == "once":
        return OnceEntry(weights0, CAPITAL, start)
    if method.startswith("staged"):
        months = int(method.replace("staged", ""))
        return StagedEntry(weights0, CAPITAL, months, dates, start)
    if method.startswith("pb"):
        thr = int(method.replace("pb", "")) / 100.0
        return PullbackEntry(prices, dates, weights0, CAPITAL, start,
                             window=60, threshold=thr, batches=3, deadline_months=6)
    raise ValueError(method)


def episode_stats(res, dates, i0, i1, cash_ret, capital):
    eq = res["equity"]
    s = pd.Series(eq[i0:i1 + 1], index=dates[i0:i1 + 1]).dropna()
    if len(s) < 30:
        return {}
    years = (s.index[-1] - s.index[0]).days / 365.25
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / max(years, 1e-9)) - 1
    mdd = float((s / s.cummax() - 1).min())
    worst = float((s - s.cummax()).min())
    held = pd.Series(res["held"][i0:i1 + 1], index=dates[i0:i1 + 1]).fillna(0)
    util = float((held / s).mean())
    ed = res.get("entry_done")
    entry_days = (dates[ed] - dates[i0]).days if ed else (dates[i1] - dates[i0]).days
    e1 = ed if ed else i1
    es = pd.Series(eq[i0:e1 + 1], index=dates[i0:e1 + 1]).dropna()
    entry_mdd = float((es / es.cummax() - 1).min()) if len(es) > 1 else 0.0
    return dict(cagr=cagr, cum=s.iloc[-1] / s.iloc[0] - 1, mdd=mdd,
                final=s.iloc[-1], worst_amount=worst,
                fees=res["fees"], util=util, entry_days=entry_days,
                entry_mdd=entry_mdd, trades=len(res["trades"]))


def run_start(prices, dates, cash_ret, fees, combo, method, start, end):
    w0 = combo_weights(combo, prices, start)
    plan = make_method(method, w0, prices, dates, start)
    weights = (lambda i: combo_weights(combo, prices, i))
    res = run_episode(prices, dates, cash_ret, weights, fees, CAPITAL, start, end, plan)
    return res, episode_stats(res, dates, start, end, cash_ret, CAPITAL)
