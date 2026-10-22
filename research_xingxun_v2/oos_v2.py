# -*- coding: utf-8 -*-
"""V2.0：滚动样本外验证（2 年训练 / 1 年测试，步长 1 年）。

每个折：
- 训练窗内只用该窗口数据，对受控候选集合回测并按 Calmar 选择；
- 测试窗用选出的权重独立回测（资金重置为 2000）；
- 拼接各折测试段日收益，得到真正的样本外序列。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_v2 import (CASH, CODES, OUT, WEIGHT_GRID, backtest, load_fees,
                    load_panel, make_invvol, stats)

CAPITAL = 2000.0


def month_index(dates, ym):
    ts = pd.Timestamp(ym + "-01")
    idx = dates.searchsorted(ts)
    return int(min(idx, len(dates) - 1))


def ym_add(year, month, k):
    total = year * 12 + (month - 1) + k
    return f"{total // 12}-{total % 12 + 1:02d}"


def candidate_set(prices, dates):
    cands = {}
    for k, w in enumerate(WEIGHT_GRID):
        cands[f"W{k:02d}"] = (w, "M", False)
    for win in (60, 120, 250):
        cands[f"IV{win}"] = (make_invvol(prices, dates, win), "M", False)
    cands["S1 债+金+纳"] = ({"000015": 1/3, "008701": 1/3, "161130": 1/3}, "M", False)
    cands["S2 去500(债25/金35/纳40)"] = ({"000015": .25, "008701": .35, "161130": .40}, "M", False)
    cands["S3 金+纳"] = ({"008701": .5, "161130": .5}, "M", False)
    cands["HOLD 等权买入持有"] = ({"000015": .25, "001214": .25, "008701": .25, "161130": .25}, "M", True)
    return cands


def run_one(prices, dates, cash_ret, fees, w, reb, once, i0, i1):
    sub = {c: prices[c] for c in (w if isinstance(w, dict) else CODES)}
    return backtest(sub, dates, cash_ret, w, fees, capital=CAPITAL,
                    rebalance=reb, once=once, start=i0, end=i1)


def main():
    panel = load_panel()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()
    cands = candidate_set(prices, dates)

    folds = []
    for k in range(4):
        tr_s = month_index(dates, ym_add(2020, 7, 12 * k))
        tr_e = month_index(dates, ym_add(2020, 7, 12 * (k + 2)))
        te_e = month_index(dates, ym_add(2020, 7, 12 * (k + 3)))
        if tr_e >= len(dates) - 60:
            break
        folds.append((tr_s, tr_e, te_e))

    rows = []
    oos_rets = {}
    for fi, (tr_s, tr_e, te_e) in enumerate(folds):
        print(f"\n== 折 {fi}: 训练 {dates[tr_s].date()}~{dates[tr_e].date()} "
              f"测试 {dates[tr_e].date()}~{dates[te_e].date()}", flush=True)
        # 训练窗评估
        train = []
        for name, (w, reb, once) in cands.items():
            r = run_one(prices, dates, cash_ret, fees, w, reb, once, tr_s, tr_e)
            m = stats(r["equity"], dates, tr_s, tr_e, cash_ret, CAPITAL)
            if m:
                train.append(dict(name=name, calmar=m["calmar"], cagr=m["cagr"], mdd=m["mdd"]))
        tr_df = pd.DataFrame(train).sort_values("calmar", ascending=False)
        best = tr_df.iloc[0]
        print("训练窗前三:", tr_df.head(3)[["name", "cagr", "mdd", "calmar"]].round(4).to_dict("records"),
              flush=True)

        # 测试窗：选中的方案 + 固定对照
        w, reb, once = cands[best["name"]]
        r = run_one(prices, dates, cash_ret, fees, w, reb, once, tr_e, te_e)
        m = stats(r["equity"], dates, tr_e, te_e, cash_ret, CAPITAL)
        eq = pd.Series(r["equity"], index=dates).loc[dates[tr_e]:dates[te_e]].dropna()
        oos_rets.setdefault("SEARCH", []).append(eq.pct_change().dropna())
        rows.append(dict(fold=fi, scheme=best["name"], role="search",
                         **{k: m[k] for k in ("cagr", "vol", "mdd", "calmar", "sharpe", "final")}))

        for label, (w2, reb2, once2) in {
            "等权月度再平衡": ({"000015": .25, "001214": .25, "008701": .25, "161130": .25}, "M", False),
            "等权买入持有": ({"000015": .25, "001214": .25, "008701": .25, "161130": .25}, "M", True),
            "逆波动120": (make_invvol(prices, dates, 120), "M", False),
        }.items():
            r2 = run_one(prices, dates, cash_ret, fees, w2, reb2, once2, tr_e, te_e)
            m2 = stats(r2["equity"], dates, tr_e, te_e, cash_ret, CAPITAL)
            eq2 = pd.Series(r2["equity"], index=dates).loc[dates[tr_e]:dates[te_e]].dropna()
            oos_rets.setdefault(label, []).append(eq2.pct_change().dropna())
            rows.append(dict(fold=fi, scheme=label, role="fixed",
                             **{k: m2[k] for k in ("cagr", "vol", "mdd", "calmar", "sharpe", "final")}))

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "oos_folds.csv", index=False, float_format="%.6f")
    print("\n== 各折测试窗 ==")
    print(df.round(4).to_string(index=False))

    # 拼接 OOS
    summary = []
    for label, parts in oos_rets.items():
        ser = pd.concat(parts).sort_index()
        ser = ser[~ser.index.duplicated(keep="first")]
        curve = (1 + ser).cumprod()
        years = (curve.index[-1] - curve.index[0]).days / 365.25
        cagr = curve.iloc[-1] ** (1 / years) - 1
        vol = ser.std() * np.sqrt(252)
        mdd = float((curve / curve.cummax() - 1).min())
        summary.append(dict(scheme=label, oos_cagr=cagr, oos_vol=vol, oos_mdd=mdd,
                            oos_calmar=cagr / abs(mdd) if mdd < 0 else np.nan,
                            oos_sharpe=(cagr - 0.015) / vol if vol > 0 else np.nan,
                            final_2000=2000 * curve.iloc[-1]))
    sdf = pd.DataFrame(summary).sort_values("oos_calmar", ascending=False)
    sdf.to_csv(OUT / "oos_summary.csv", index=False, float_format="%.6f")
    print("\n== 拼接样本外 ==")
    print(sdf.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
