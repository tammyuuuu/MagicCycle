# -*- coding: utf-8 -*-
"""第三轮：空仓资金管理对比（货币基金 / 中短债 / 1-3年国开 / 7-10年国开）。

只比较"这笔钱在等待买点时放在哪里"，不把债券基金当无风险现金。
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean"
OUT = ROOT / "out_wf"
OUT.mkdir(exist_ok=True)

FUNDS = {"000198": "货币基金", "006989": "中短债", "006484": "1-3年国开", "003358": "7-10年国开"}
START = "2019-03-08"
END = "2026-10-21"


def load(code):
    d = pd.read_csv(CLEAN / f"{code}.csv", parse_dates=["date"]).set_index("date")
    return d["tr"].astype(float)


def max_drawdown(eq):
    return float((eq / eq.cummax() - 1).min())


def underwater_days(eq):
    peak = eq.cummax()
    below = eq < peak - 1e-12
    longest = cur = 0
    for b in below:
        cur = cur + 1 if b else 0
        longest = max(longest, cur)
    return longest


def main():
    cal = load("160706")
    cal = cal[(cal.index >= pd.Timestamp(START)) & (cal.index <= pd.Timestamp(END))].index
    rows = []
    for code, name in FUNDS.items():
        tr = load(code)
        if code == "000198":
            # 货币基金每日公布收益（含周末），先对齐到交易日，避免多算收益天数
            tr = tr.reindex(tr.index.union(cal)).ffill().reindex(cal)
        else:
            tr = tr.reindex(cal)
        tr = tr.dropna()
        tr = tr / tr.iloc[0]
        ret = tr.pct_change(fill_method=None).dropna()
        yrs = len(ret) / 252
        cagr = tr.iloc[-1] ** (1 / yrs) - 1
        vol = ret.std(ddof=1) * np.sqrt(252)
        # 任意 20 个交易日的最差收益
        roll20 = tr / tr.shift(20) - 1
        rows.append(dict(code=code, name=name, start=str(tr.index[0].date()),
                         years=round(yrs, 1), cagr=cagr, vol=vol,
                         mdd=max_drawdown(tr), worst_20d=float(roll20.min()),
                         underwater_days=underwater_days(tr),
                         total=tr.iloc[-1] - 1))
    df = pd.DataFrame(rows)

    # 退出成本（按真实费率阶梯，2000 元一次性退出）
    exit_cost = {
        "000198": dict(d7=0.0, d30=0.0, d365=0.0, settle="T+1"),
        "006989": dict(d7=1.5, d30=0.1, d365=0.0, settle="T+2"),
        "006484": dict(d7=1.5, d30=0.1, d365=0.0, settle="T+2"),
        "003358": dict(d7=1.5, d30=0.1, d365=0.05, settle="T+2"),
    }
    df["exit_fee_7d_pct"] = df.code.map(lambda c: exit_cost[c]["d7"])
    df["exit_fee_30d_pct"] = df.code.map(lambda c: exit_cost[c]["d30"])
    df["exit_fee_1y_pct"] = df.code.map(lambda c: exit_cost[c]["d365"])
    df["settle"] = df.code.map(lambda c: exit_cost[c]["settle"])
    df["buy_fee_pct"] = df.code.map({"000198": 0.0, "006989": 0.04,
                                     "006484": 0.05, "003358": 0.05})
    df.to_csv(OUT / "cash_compare.csv", index=False, encoding="utf-8-sig")
    print(df.round(4).to_string(index=False))

    # 情景：持有 30 天 / 1 年后退出，扣费后的净年化
    scen = []
    for r in df.itertuples():
        for days, fee in ((30, r.exit_fee_30d_pct), (365, r.exit_fee_1y_pct)):
            gross = (1 + r.cagr) ** (days / 365) - 1
            net = gross - (fee + r.buy_fee_pct) / 100
            scen.append(dict(name=r.name, days=days, gross_pct=gross * 100,
                             fee_pct=fee + r.buy_fee_pct, net_pct=net * 100))
    s = pd.DataFrame(scen)
    s.to_csv(OUT / "cash_scenarios.csv", index=False, encoding="utf-8-sig")
    print()
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
