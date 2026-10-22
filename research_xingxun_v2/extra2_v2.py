# -*- coding: utf-8 -*-
"""V2.0 补充二：保留 A 股的降权版本 + QDII 限购下的可执行版本。"""
from pathlib import Path
import ast

import pandas as pd

from run_v2 import (CASH, CODES, OUT, backtest, load_fees, load_panel,
                    make_invvol, stats)
from otc_engine import FundFee

CAPITAL = 2000.0
V1 = Path(__file__).resolve().parent.parent / "research_xingxun_v1"


def main():
    panel = load_panel()
    v1 = pd.read_csv(V1 / "clean" / "tr_panel.csv", index_col=0, parse_dates=True)
    for c in ["050025"]:
        panel[c] = v1[c].reindex(panel.index).ffill(limit=5)
    panel = panel.ffill(limit=5).dropna()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()
    m1 = pd.read_csv(V1 / "clean" / "fund_meta.csv", dtype={"code": str})
    r5 = m1[m1.code == "050025"].iloc[0]
    fees["050025"] = FundFee("050025",
                            ast.literal_eval(r5["purchase_fee_tiers"]),
                            ast.literal_eval(r5["redeem_fee_tiers"]))
    n = len(dates)
    o0 = int(dates.searchsorted(pd.Timestamp("2022-07-01")))
    o1 = int(dates.searchsorted(pd.Timestamp("2026-07-01")))

    def run(w, blocked=None, i0=0, i1=n - 1):
        sub = {c: prices[c] for c in w}
        return backtest(sub, dates, cash_ret, w, fees, capital=CAPITAL,
                        rebalance="M", blocked=blocked, start=i0, end=i1)

    def line(name, w, blocked=None):
        out = []
        for seg, i0, i1 in (("全样本", 0, n - 1), ("样本外", o0, o1)):
            r = run(w, blocked, i0, i1)
            m = stats(r["equity"], dates, i0, i1, cash_ret, CAPITAL)
            m.update(scheme=name, segment=seg, fees=r["fees"], trades=len(r["trades"]))
            out.append(m)
        return out

    rows = []
    # 保留 500 的降权版本
    for name, w in {
        "G1 债1/3 500 1/6 金1/4 纳1/4": {"000015": 1/3, "001214": 1/6, "008701": .25, "161130": .25},
        "G2 债30 50015 金27.5 纳27.5": {"000015": .30, "001214": .15, "008701": .275, "161130": .275},
        "G3 债35 50015 金25 纳25": {"000015": .35, "001214": .15, "008701": .25, "161130": .25},
        "E 债/金/纳 各1/3": {"000015": 1/3, "008701": 1/3, "161130": 1/3},
        "F 金/纳 50/50": {"008701": .5, "161130": .5},
    }.items():
        rows += line(name, w)

    # QDII 限购：161130 暂停申购
    blk = lambda i, c: c == "161130"
    rows += line("E-限购 纳指留现金", {"000015": 1/3, "008701": 1/3, "161130": 1/3}, blk)
    rows += line("E-纳指换广发", {"000015": 1/3, "008701": 1/3, "270042": 1/3})
    rows += line("E-纳指换标普", {"000015": 1/3, "008701": 1/3, "050025": 1/3})
    rows += line("F-限购 纳指留现金", {"008701": .5, "161130": .5}, blk)
    rows += line("F-纳指换标普", {"008701": .5, "050025": .5})

    df = pd.DataFrame(rows)[["scheme", "segment", "cagr", "vol", "mdd", "calmar",
                             "sharpe", "final", "worst_amount", "recovery_days",
                             "fees", "trades"]]
    df.to_csv(OUT / "deweight_and_limit.csv", index=False, float_format="%.6f")
    print(df.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
