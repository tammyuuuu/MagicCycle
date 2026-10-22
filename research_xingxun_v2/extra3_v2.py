# -*- coding: utf-8 -*-
"""V2.0 补充三：纳指限购状态下的可执行组合（债/500/金）。"""
from pathlib import Path

import numpy as np
import pandas as pd

from run_v2 import CASH, OUT, backtest, load_fees, load_panel, stats

CAPITAL = 2000.0


def make_invvol_sub(prices, codes, window=120, cap=0.6):
    def f(i):
        vol = {}
        for c in codes:
            arr = prices[c][max(0, i - window + 1):i + 1]
            r = np.diff(arr) / arr[:-1]
            vol[c] = np.std(r) * np.sqrt(252) if len(r) > 5 else 1.0
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
    return f


def main():
    panel = load_panel()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()
    n = len(dates)
    o0 = int(dates.searchsorted(pd.Timestamp("2022-07-01")))
    o1 = int(dates.searchsorted(pd.Timestamp("2026-07-01")))

    def line(name, w):
        out = []
        codes = list(w) if isinstance(w, dict) else three
        for seg, i0, i1 in (("全样本", 0, n - 1), ("样本外", o0, o1)):
            sub = {c: prices[c] for c in codes}
            r = backtest(sub, dates, cash_ret, w, fees, capital=CAPITAL,
                         rebalance="M", start=i0, end=i1)
            m = stats(r["equity"], dates, i0, i1, cash_ret, CAPITAL)
            m.update(scheme=name, segment=seg, fees=r["fees"], trades=len(r["trades"]))
            out.append(m)
        return out

    three = ["000015", "001214", "008701"]
    rows = []
    rows += line("K1 债/500/金 等权", {c: 1/3 for c in three})
    rows += line("K2 债40/50030/金30", {"000015": .40, "001214": .30, "008701": .30})
    rows += line("K3 债30/50035/金35", {"000015": .30, "001214": .35, "008701": .35})
    rows += line("K4 三只逆波动120", make_invvol_sub(prices, three, 120))
    rows += line("K5 金/500 50/50", {"001214": .5, "008701": .5})
    rows += line("K6 债50/50025/金25", {"000015": .50, "001214": .25, "008701": .25})

    df = pd.DataFrame(rows)[["scheme", "segment", "cagr", "vol", "mdd", "calmar",
                             "sharpe", "final", "worst_amount", "recovery_days",
                             "fees", "trades"]]
    df.to_csv(OUT / "no_nasdaq_options.csv", index=False, float_format="%.6f")
    print(df.round(4).to_string(index=False))

    # 最近一次逆波动权重
    f = make_invvol_sub(prices, three, 120)
    w = f(n - 1)
    print("\n最近 K4 权重", {k: round(v, 4) for k, v in w.items()},
          "2000 元金额", {k: round(v * CAPITAL, 2) for k, v in w.items()})
    # 逐年
    for name, w in [("K1 等权", {c: 1/3 for c in three}),
                    ("K4 逆波动", f(n - 1))]:
        pass


if __name__ == "__main__":
    main()
