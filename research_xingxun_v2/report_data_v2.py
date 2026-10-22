# -*- coding: utf-8 -*-
"""V2.0：报告用数据（逐年、逐月、净值与回撤图）。"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from run_v2 import CASH, CODES, OUT, backtest, load_fees, load_panel, make_invvol, stats

CAPITAL = 2000.0


def main():
    panel = load_panel()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()

    schemes = {
        "A_HoldEqual": ({"000015": .25, "001214": .25, "008701": .25, "161130": .25}, True),
        "B_EqualMonthly": ({"000015": .25, "001214": .25, "008701": .25, "161130": .25}, False),
        "C_LowDD_Bond40": ({"000015": .40, "001214": .20, "008701": .20, "161130": .20}, False),
        "D_InvVol120": (make_invvol(prices, dates, 120), False),
        "E_ThreeNo500": ({"000015": 1/3, "008701": 1/3, "161130": 1/3}, False),
        "F_GoldNasdaq": ({"008701": .5, "161130": .5}, False),
    }

    curves, rows = {}, []
    for name, (w, once) in schemes.items():
        sub = {c: prices[c] for c in (w if isinstance(w, dict) else CODES)}
        r = backtest(sub, dates, cash_ret, w, fees, capital=CAPITAL,
                     rebalance="M", once=once)
        eq = pd.Series(r["equity"], index=dates).dropna()
        curves[name] = eq / eq.iloc[0] * CAPITAL
        curves[name].to_csv(OUT / f"equity_{name}.csv", header=["equity"], float_format="%.6f")
        y = (1 + eq.pct_change().dropna()).groupby(eq.pct_change().dropna().index.year).prod() - 1
        m = stats(r["equity"], dates, 0, len(dates) - 1, cash_ret, CAPITAL)
        rows.append(dict(scheme=name, **{f"y{int(k)}": v for k, v in y.items()},
                         cagr=m["cagr"], mdd=m["mdd"], final=m["final"]))
        eq.resample("ME").last().pct_change().dropna().to_csv(
            OUT / f"monthly_ret_{name}.csv", header=["ret"], float_format="%.6f")

    ydf = pd.DataFrame(rows)
    ydf.to_csv(OUT / "yearly_returns.csv", index=False, float_format="%.6f")
    print("== 逐年收益 ==")
    print(ydf.round(4).to_string(index=False))

    # 净值与回撤图
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    for name, s in curves.items():
        axes[0].plot(s.index, s.values, label=name, linewidth=1.2)
        dd = s / s.cummax() - 1
        axes[1].plot(dd.index, dd.values * 100, linewidth=1.0)
    axes[0].set_title("Xingxun V2: portfolio value of 2000 CNY (net of fees)")
    axes[0].set_ylabel("CNY")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=.3)
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(OUT / "equity_drawdown.png", dpi=130)
    print("saved", OUT / "equity_drawdown.png")

    # 方案 E（三只去500）与 B 的月收益差异
    mB = pd.read_csv(OUT / "monthly_ret_B_EqualMonthly.csv", index_col=0, parse_dates=True)["ret"]
    mE = pd.read_csv(OUT / "monthly_ret_E_ThreeNo500.csv", index_col=0, parse_dates=True)["ret"]
    diff = (mE - mB).dropna()
    print("\nE-B 月度差：均值 %.4f%% 最差 %.4f%% (%s) 最好 %.4f%% (%s)" % (
        diff.mean() * 100, diff.min() * 100, diff.idxmin().date(),
        diff.max() * 100, diff.idxmax().date()))

    # 三方案 2000 元首笔金额
    print("\n== 2000 元首笔金额 ==")
    for name, w in {
        "收益优先（金+纳 50/50）": {"008701": .5, "161130": .5},
        "均衡（债/金/纳 各 1/3）": {"000015": 1/3, "008701": 1/3, "161130": 1/3},
        "低回撤（逆波动120，示例权重）": None,
    }.items():
        if w is None:
            # 用最后一天的逆波动权重估算
            i = len(dates) - 1
            f = make_invvol(prices, dates, 120)
            w = f(i)
        amt = {c: round(CAPITAL * wt, 2) for c, wt in w.items()}
        print(name, amt, "合计", round(sum(amt.values()), 2))


if __name__ == "__main__":
    main()
