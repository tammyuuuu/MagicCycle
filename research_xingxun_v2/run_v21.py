# -*- coding: utf-8 -*-
"""V2.1：多起点滚动建仓主实验。

- 起点：每个自然月首个交易日（2020-07~2026-10）
- 组合：A / B / C / EQ / K4（与 V2.0 定义一致）
- 方法：一次性、3/6/12 月固定等额、回调（阈值由训练段选择）
- 期限：1/3/5 年，每起点须有完整期限
"""
from pathlib import Path

import numpy as np
import pandas as pd

from run_v2 import CASH, load_fees, load_panel
from v21_lib import COMBOS, run_start

OUT = Path(__file__).resolve().parent / "out_v21"
OUT.mkdir(exist_ok=True)

METHODS = ["once", "staged3", "staged6", "staged12"]
TRAIN_S = pd.Timestamp("2020-07-01")
TRAIN_E = pd.Timestamp("2022-12-31")


def month_starts(dates):
    out = []
    for i in range(len(dates)):
        if i == 0 or (dates[i].year, dates[i].month) != (dates[i - 1].year, dates[i - 1].month):
            out.append(i)
    return out


def horizon_end(dates, s, years):
    target = dates[s] + pd.DateOffset(years=years)
    if target > dates[-1]:
        return None
    idx = int(dates.searchsorted(target, side="right") - 1)
    return max(idx, s + 20)


def training_episode_allowed(dates, start, end, cutoff=TRAIN_E):
    return end is not None and TRAIN_S <= dates[start] <= cutoff and dates[end] <= cutoff


def main():
    panel = load_panel()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()
    starts = month_starts(dates)
    print("起点数", len(starts), dates[starts[0]].date(), dates[starts[-1]].date(), flush=True)

    # ---------- 1) 回调阈值：训练段选择（组合 B，3 年期） ----------
    rows = []
    for thr in (3, 5, 8):
        vals = []
        for s in starts:
            if not (TRAIN_S <= dates[s] <= TRAIN_E):
                continue
            end = horizon_end(dates, s, 3)
            if not training_episode_allowed(dates, s, end):
                continue
            _, st = run_start(prices, dates, cash_ret, fees, "B 债/金/纳 各1/3", f"pb{thr}", s, end)
            if st:
                vals.append(st)
        if vals:
            med_cagr = float(np.median([v["cagr"] for v in vals]))
            med_mdd = float(np.median([v["mdd"] for v in vals]))
            med_calmar = med_cagr / abs(med_mdd) if med_mdd < 0 else np.nan
            rows.append(dict(threshold=thr, n=len(vals), med_cagr=med_cagr,
                             med_mdd=med_mdd, med_calmar=med_calmar))
    if not rows:
        raise ValueError('训练截止日前没有完整三年持有窗口，禁止用测试期收益选参；请重新设计训练/测试期限')
    sel = pd.DataFrame(rows).sort_values("med_calmar", ascending=False)
    sel.to_csv(OUT / "train_threshold_selection.csv", index=False, float_format="%.6f")
    print("\n== 训练段回调阈值选择（组合 B，3 年） ==")
    print(sel.round(4).to_string(index=False))
    best_thr = int(sel.iloc[0]["threshold"])
    methods = METHODS + [f"pb{best_thr}"]
    print("选中阈值", best_thr, "%", flush=True)

    # ---------- 2) 主网格 ----------
    out = []
    for combo in COMBOS:
        for method in methods:
            for h in (1, 3, 5):
                for s in starts:
                    end = horizon_end(dates, s, h)
                    if end is None:
                        continue
                    try:
                        _, st = run_start(prices, dates, cash_ret, fees, combo, method, s, end)
                    except Exception as e:
                        print("ERR", combo, method, h, dates[s].date(), type(e).__name__, e, flush=True)
                        continue
                    if not st:
                        continue
                    st.update(combo=combo, method=method, horizon=h,
                              start=dates[s].date().isoformat(),
                              train=training_episode_allowed(dates,s,end))
                    out.append(st)
        print("done", combo, flush=True)

    df = pd.DataFrame(out)
    df.to_csv(OUT / "v21_grid.csv", index=False, float_format="%.6f")
    print("\n结果行数", len(df), "->", OUT / "v21_grid.csv")


if __name__ == "__main__":
    main()
