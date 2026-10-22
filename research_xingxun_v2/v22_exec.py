# -*- coding: utf-8 -*-
"""V2.2：最新权重、2000 元建仓表、K4→B 切换模拟、限购节奏。"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from run_v2 import CASH, backtest, load_fees, load_panel, stats
from v21_lib import THREE, invvol

OUT = Path(__file__).resolve().parent / "out_v22"
OUT.mkdir(exist_ok=True)
CAP = 2000.0

NAME = {"000015": "华夏纯债债券A", "001214": "华泰柏瑞中证500ETF联接A",
        "008701": "华夏黄金ETF联接A", "161130": "易方达纳斯达克100ETF联接A(人民币)"}


def buy_fee(amount, pct):
    rate = pct / 100.0
    fee = amount - amount / (1 + rate)
    return round(fee, 4), round(amount - fee, 4)


def main():
    panel = load_panel()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()
    n = len(dates)

    # 1) 最新 K4 权重与金额
    i = n - 1
    k4 = invvol(prices, THREE, i, 120, 0.6)
    print("数据日", dates[i].date(), "K4 权重", {k: round(v, 4) for k, v in k4.items()})
    rows = []
    rates = {"000015": 0.08, "001214": 0.10, "008701": 0.06, "161130": 0.12}
    for c, w in k4.items():
        amt = round(CAP * w, 2)
        fee, net = buy_fee(amt, rates[c])
        rows.append(dict(code=c, name=NAME[c], weight=w, amount=amt,
                         buy_rate_pct=rates[c], fee_est=fee, net_amount=net))
    k4df = pd.DataFrame(rows)
    total_amt = k4df.amount.sum()
    if abs(total_amt - CAP) > 0.01:
        # 把差额并入债基，保证正好 2000
        k4df.loc[k4df.code == "000015", "amount"] = round(
            k4df.loc[k4df.code == "000015", "amount"].iloc[0] + (CAP - total_amt), 2)
    k4df.to_csv(OUT / "k4_entry_2000.csv", index=False, float_format="%.4f")
    print("\n== K4 2000 元建仓表 ==")
    print(k4df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    # 2) B 方案 2000 元（理论，纳指恢复后）
    b = {"000015": 1/3, "008701": 1/3, "161130": 1/3}
    rows = []
    for c, w in b.items():
        amt = round(CAP * w, 2)
        fee, net = buy_fee(amt, rates[c])
        rows.append(dict(code=c, name=NAME[c], weight=w, amount=amt,
                         buy_rate_pct=rates[c], fee_est=fee, net_amount=net))
    bdf = pd.DataFrame(rows)
    bdf.loc[bdf.code == "000015", "amount"] = round(
        bdf.loc[bdf.code == "000015", "amount"].iloc[0] + (CAP - bdf.amount.sum()), 2)
    bdf.to_csv(OUT / "b_entry_2000.csv", index=False, float_format="%.4f")
    print("\n== B 2000 元建仓表（纳指恢复后） ==")
    print(bdf.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    # 3) K4 -> B 切换模拟
    def switch_weights(switch_idx):
        def f(i):
            if i < switch_idx:
                return invvol(prices, THREE, i, 120, 0.6)
            return b
        return f

    starts = [int(dates.searchsorted(pd.Timestamp(x))) for x in
              ["2021-01-04", "2022-01-04", "2023-01-03", "2024-01-02", "2025-01-02"]]
    rows = []
    for s in starts:
        end = int(dates.searchsorted(dates[s] + pd.DateOffset(years=1), side="right") - 1)
        for label, days in [("K4 一直持有", None), ("K4 30 天后切 B", 30),
                            ("K4 60 天后切 B", 60), ("K4 90 天后切 B", 90),
                            ("B 一直持有", 0)]:
            if days is None:
                wf = lambda i, s=s: invvol(prices, THREE, i, 120, 0.6)
            elif days == 0:
                wf = lambda i, s=s: b
            else:
                sw = int(dates.searchsorted(dates[s] + pd.Timedelta(days=days)))
                wf = switch_weights(sw)
            r = backtest({c: prices[c] for c in panel.columns}, dates, cash_ret, wf, fees,
                         capital=CAP, rebalance="M", start=s, end=end)
            m = stats(r["equity"], dates, s, end, cash_ret, CAP)
            rows.append(dict(start=dates[s].date().isoformat(), scheme=label,
                             cagr=m["cagr"], mdd=m["mdd"], final=m["final"],
                             fees=r["fees"], trades=len(r["trades"])))
    sw = pd.DataFrame(rows)
    sw.to_csv(OUT / "switch_k4_to_b.csv", index=False, float_format="%.6f")
    print("\n== K4 → B 切换（1 年期，5 个起点） ==")
    print(sw.pivot(index="scheme", columns="start", values="final").round(2).to_string())
    print("\n平均费用：")
    print(sw.groupby("scheme")[["fees", "trades"]].mean().round(3).to_string())

    # 4) 限购节奏
    nasdaq_amt = round(CAP / 3, 2)
    rows = []
    for label, per_day in [("暂停申购（当前）", 0), ("每日 10 元", 10),
                           ("每日 100 元", 100), ("每日 500 元", 500), ("正常申购", None)]:
        if per_day is None:
            days_needed = 1
        elif per_day == 0:
            days_needed = None
        else:
            days_needed = int(np.ceil(nasdaq_amt / per_day))
        rows.append(dict(scenario=label, daily_cap=per_day, target_amount=nasdaq_amt,
                         trading_days=days_needed,
                         calendar_months=round(days_needed / 21, 1) if days_needed else None,
                         fee_total=round(nasdaq_amt * 0.12 / 100, 2),
                         manual_orders=(days_needed if per_day else 1) if days_needed else None))
    lim = pd.DataFrame(rows)
    lim.to_csv(OUT / "limit_schedule.csv", index=False)
    print("\n== 纳指腿（666.67 元）限购节奏 ==")
    print(lim.to_string(index=False))

    # 5) 最近一年 B / K4 表现（截至最新）
    s0 = int(dates.searchsorted(dates[-1] - pd.DateOffset(years=1)))
    for label, wf in [("B", lambda i: b), ("K4", lambda i: invvol(prices, THREE, i, 120, 0.6))]:
        r = backtest({c: prices[c] for c in panel.columns}, dates, cash_ret, wf, fees,
                     capital=CAP, rebalance="M", start=s0, end=n - 1)
        m = stats(r["equity"], dates, s0, n - 1, cash_ret, CAP)
        print(f"最近一年 {label}: CAGR {m['cagr']*100:.2f}% MDD {m['mdd']*100:.2f}% 终值 {m['final']:.2f}")

    meta = dict(data_date=dates[-1].date().isoformat(),
                k4_weights={k: float(v) for k, v in k4.items()},
                k4_entry=k4df.to_dict("records"), b_entry=bdf.to_dict("records"),
                limit_schedule=lim.to_dict("records"))
    (OUT / "v22_plan.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
