# -*- coding: utf-8 -*-
"""V2.0 补充：候选方案样本外、限购替代、成本敏感性、参数稳定性。"""
from pathlib import Path

import numpy as np
import pandas as pd

from run_v2 import (CASH, CODES, OUT, backtest, load_fees, load_panel,
                    make_invvol, make_staged, stats)

CAPITAL = 2000.0
OOS_S = "2022-07-01"
OOS_E = "2026-07-01"


def main():
    panel = load_panel()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()

    def idx(ts):
        return int(min(dates.searchsorted(pd.Timestamp(ts)), len(dates) - 1))

    o0, o1 = idx(OOS_S), idx(OOS_E)
    n = len(dates)

    EQ = {"000015": .25, "001214": .25, "008701": .25, "161130": .25}
    C01 = {"000015": .40, "001214": .20, "008701": .20, "161130": .20}
    C02 = {"000015": .35, "001214": .25, "008701": .20, "161130": .20}
    H8 = {"000015": 1/3, "008701": 1/3, "161130": 1/3}
    H12 = {"008701": .5, "161130": .5}
    H6 = {"001214": 1/3, "008701": 1/3, "161130": 1/3}

    def run(w, reb="M", once=False, blocked=None, i0=0, i1=n - 1, capital=CAPITAL):
        sub = {c: prices[c] for c in (w if isinstance(w, dict) else CODES)}
        return backtest(sub, dates, cash_ret, w, fees, capital=capital,
                        rebalance=reb, once=once, blocked=blocked, start=i0, end=i1)

    def line(name, res, i0, i1, capital=CAPITAL, **extra):
        m = stats(res["equity"], dates, i0, i1, cash_ret, capital)
        m.update(scheme=name, fees=res["fees"], trades=len(res["trades"]),
                 blocked=res["blocked"], **extra)
        return m

    # 1) 候选方案全样本 + 样本外
    rows = []
    cands = {
        "A 四只等权 买入持有": (EQ, "M", True, None),
        "B1 四只等权 月度再平衡": (EQ, "M", False, None),
        "B2 四只等权 季度再平衡": (EQ, "Q", False, None),
        "C01 债40/50020/金20/纳20": (C01, "M", False, None),
        "C02 债35/50025/金20/纳20": (C02, "M", False, None),
        "D60 逆波动60": (make_invvol(prices, dates, 60), "M", False, None),
        "D120 逆波动120": (make_invvol(prices, dates, 120), "M", False, None),
        "D250 逆波动250": (make_invvol(prices, dates, 250), "M", False, None),
        "E3 分批3月+持有": (make_staged(EQ, 3, dates, 0), "M", False, None),
        "H3 黄金换华安": ({"000015": .25, "001214": .25, "000216": .25, "161130": .25}, "M", False, None),
        "H8 三只 去500": (H8, "M", False, None),
        "H12 两只 金+纳": (H12, "M", False, None),
        "H6 三只 去纯债": (H6, "M", False, None),
    }
    for name, (w, reb, once, blk) in cands.items():
        full = line(name, run(w, reb, once, blk), 0, n - 1, segment="全样本")
        oos = line(name, run(w, reb, once, blk, o0, o1), o0, o1, segment="样本外2022-07~2026-07")
        rows += [full, oos]
    df = pd.DataFrame(rows)[["scheme", "segment", "cagr", "vol", "mdd", "calmar", "sharpe",
                             "final", "worst_amount", "recovery_days", "fees", "trades"]]
    df.to_csv(OUT / "candidates_full_oos.csv", index=False, float_format="%.6f")
    print("== 候选方案 全样本 vs 样本外 ==")
    print(df.round(4).to_string(index=False))

    # 2) 限购替代（161130 暂停申购）
    alt = {
        "L0 理论可买": (EQ, None),
        "L1 限购 留现金": (EQ, lambda i, c: c == "161130"),
    }
    w2 = dict(EQ); w2["161130"] = 0.0; w2["001214"] = 0.50
    alt["L2 转中证500"] = (w2, None)
    w3 = dict(EQ); w3["161130"] = 0.0; w3["008701"] = 0.50
    alt["L3 转黄金"] = (w3, None)
    w4 = dict(EQ); w4["161130"] = 0.0; w4["000015"] = 0.50
    alt["L4 转纯债"] = (w4, None)
    w5 = dict(EQ); w5["161130"] = 0.0; w5["270042"] = 0.25
    alt["L5 换广发纳指"] = (w5, None)

    rows = []
    for name, (w, blk) in alt.items():
        f = line(name, run(w, blocked=blk), 0, n - 1, segment="全样本")
        o = line(name, run(w, blocked=blk, i0=o0, i1=o1), o0, o1, segment="样本外")
        rows += [f, o]
    ldf = pd.DataFrame(rows)[["scheme", "segment", "cagr", "mdd", "calmar", "sharpe", "final", "blocked"]]
    ldf.to_csv(OUT / "limit_alts.csv", index=False, float_format="%.6f")
    print("\n== 限购替代 ==")
    print(ldf.round(4).to_string(index=False))

    # 3) 资金规模敏感性
    rows = []
    for cap in (2000, 5000, 10000):
        for name, w, reb, once in [("等权月度再平衡", EQ, "M", False),
                                   ("逆波动120", make_invvol(prices, dates, 120), "M", False),
                                   ("买入持有", EQ, "M", True)]:
            r = run(w, reb, once, capital=cap)
            m = line(name, r, 0, n - 1, capital=cap)
            m.update(capital=cap)
            rows.append(m)
    cdf = pd.DataFrame(rows)[["scheme", "capital", "cagr", "mdd", "final", "fees", "trades"]]
    cdf["fee_pct"] = cdf["fees"] / cdf["capital"]
    cdf.to_csv(OUT / "capital_sensitivity.csv", index=False, float_format="%.6f")
    print("\n== 资金规模敏感性 ==")
    print(cdf.round(5).to_string(index=False))

    # 4) 参数稳定性：权重 ±5pp（等权基准）
    rows = []
    for shift in (-0.05, 0.0, 0.05):
        for c in CODES:
            w = dict(EQ)
            w[c] = max(0.0, w[c] + shift)
            rest = [x for x in CODES if x != c]
            gap = 1 - sum(w.values())
            for x in rest:
                w[x] += gap / len(rest)
            r = run(w)
            m = line(f"等权 {c} {shift:+.0%}", r, 0, n - 1)
            m.update(capital=CAPITAL, shift=shift, code=c)
            rows.append(m)
    pdb = pd.DataFrame(rows)[["scheme", "code", "shift", "cagr", "mdd", "calmar", "sharpe"]]
    pdb.to_csv(OUT / "weight_perturbation.csv", index=False, float_format="%.6f")
    print("\n== 权重 ±5pp 扰动 ==")
    print(pdb.round(4).to_string(index=False))

    # 5) 逐笔交易（等权月度再平衡，供报告引用）
    r = run(EQ)
    t = pd.DataFrame(r["trades"])
    if not t.empty:
        t["code_name"] = t["code"].map({"000015": "华夏纯债A", "001214": "华泰柏瑞500",
                                        "008701": "华夏黄金", "161130": "易方达纳指"})
        t.to_csv(OUT / "trades_equal_weight.csv", index=False, float_format="%.6f")
        print("\n== 前 12 笔交易（等权月度再平衡） ==")
        print(t.head(12)[["date", "code_name", "side", "amount", "shares", "fee", "hold_days"]]
              .round(4).to_string(index=False))


if __name__ == "__main__":
    main()
