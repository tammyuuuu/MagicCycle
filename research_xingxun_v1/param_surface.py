# -*- coding: utf-8 -*-
"""第三轮：参数曲面与稳定性。

对 C 类（长期趋势 + 回调买入）与 B 类（单均线）做二维网格，
看优势是"连续稳定区域"还是"孤立最优点"。

注意：曲面用全样本与固定样本外区间展示，只用于判断稳健性，
      不用于再次挑参数；第三轮的推荐仍以 walk-forward 为准。
"""
from pathlib import Path
import itertools

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import strategy_lib as SL
from otc_engine import run_sleeve, metrics
from run_round2 import FULL, LONG, LABEL, build_panel

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out_wf"
OUT.mkdir(exist_ok=True)

ASSETS = ["160706", "160119", "090010", "000216"]


def seg_positions(dates, start, end=None):
    s = int(np.searchsorted(dates, pd.Timestamp(start)))
    e = len(dates) - 1 if end is None else int(np.searchsorted(dates, pd.Timestamp(end), side="right") - 1)
    return s, e


def main():
    rows = []
    for panel, codes, start, oos_start in (("A", FULL, "2019-03-08", "2024-01-02"),
                                           ("B", LONG, "2013-08-22", "2020-01-02")):
        tr, dates, cash, fees, pe = build_panel(codes, start)
        for code in ASSETS:
            prices = tr[code].to_numpy(float)
            for trend, th in itertools.product((150, 200, 250), (0.03, 0.05, 0.08)):
                target = SL.pullback(tr[code], n_trend=trend, threshold=th)
                arr = target.reindex(dates).fillna(0.0).to_numpy(float)
                for seg, (s, e) in (("FULL", (0, len(dates) - 1)),
                                    ("OOS", seg_positions(dates, oos_start))):
                    eq, f, trades = run_sleeve(prices, arr, dates, cash, 2000.0, fees[code], s, e)
                    m = metrics(eq, cash, s, e)
                    rows.append(dict(panel=panel, code=code, asset=LABEL[code], strategy="C_pullback",
                                     n_trend=trend, threshold=th, segment=seg,
                                     trades=len(trades), fees=f, **m))
            for n in (60, 120, 200):
                arr = SL.ma(tr[code], n=n).reindex(dates).fillna(0.0).to_numpy(float)
                for seg, (s, e) in (("FULL", (0, len(dates) - 1)),
                                    ("OOS", seg_positions(dates, oos_start))):
                    eq, f, trades = run_sleeve(prices, arr, dates, cash, 2000.0, fees[code], s, e)
                    m = metrics(eq, cash, s, e)
                    rows.append(dict(panel=panel, code=code, asset=LABEL[code], strategy="B_ma",
                                     n_trend=n, threshold=np.nan, segment=seg,
                                     trades=len(trades), fees=f, **m))
            arr = SL.hold(tr[code]).reindex(dates).fillna(1.0).to_numpy(float)
            for seg, (s, e) in (("FULL", (0, len(dates) - 1)),
                                ("OOS", seg_positions(dates, oos_start))):
                eq, f, trades = run_sleeve(prices, arr, dates, cash, 2000.0, fees[code], s, e)
                m = metrics(eq, cash, s, e)
                rows.append(dict(panel=panel, code=code, asset=LABEL[code], strategy="A_hold",
                                 n_trend=np.nan, threshold=np.nan, segment=seg,
                                 trades=len(trades), fees=f, **m))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "param_surface.csv", index=False, encoding="utf-8-sig")

    # 每个资产：C 网格的离散度 + 持有基准
    summary = []
    for (panel, asset), g in df.groupby(["panel", "asset"]):
        for seg in ("FULL", "OOS"):
            gg = g[(g.segment == seg) & (g.strategy == "C_pullback")]
            hold = g[(g.segment == seg) & (g.strategy == "A_hold")].iloc[0]
            summary.append(dict(panel=panel, asset=asset, segment=seg,
                                cagr_min=gg.cagr.min(), cagr_med=gg.cagr.median(),
                                cagr_max=gg.cagr.max(),
                                sharpe_min=gg.sharpe.min(), sharpe_med=gg.sharpe.median(),
                                sharpe_max=gg.sharpe.max(),
                                hold_cagr=hold.cagr, hold_sharpe=hold.sharpe,
                                cells_cagr_above_hold=int((gg.cagr > hold.cagr).sum()),
                                cells_sharpe_above_hold=int((gg.sharpe > hold.sharpe).sum()),
                                cells=len(gg)))
    sm = pd.DataFrame(summary)
    sm.to_csv(OUT / "param_surface_summary.csv", index=False, encoding="utf-8-sig")
    print(sm.round(4).to_string(index=False))

    # 画 OOS Sharpe 曲面
    for (panel, asset), g in df[(df.segment == "OOS") & (df.strategy == "C_pullback")].groupby(["panel", "asset"]):
        piv = g.pivot(index="n_trend", columns="threshold", values="sharpe")
        fig, ax = plt.subplots(figsize=(5.6, 3.8))
        im = ax.imshow(piv.values, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(piv.columns)), [f"{int(c*100)}%" for c in piv.columns])
        ax.set_yticks(range(len(piv.index)), [str(i) for i in piv.index])
        ax.set_xlabel("pullback threshold")
        ax.set_ylabel("trend MA window")
        for i in range(piv.shape[0]):
            for j in range(piv.shape[1]):
                ax.text(j, i, f"{piv.values[i, j]:.2f}", ha="center", va="center", fontsize=9)
        ax.set_title(f"{asset} ({panel}) OOS Sharpe: trend + pullback")
        fig.colorbar(im, ax=ax, shrink=.8)
        fig.tight_layout()
        fig.savefig(OUT / f"surface_{panel}_{asset}.png", dpi=150)
        plt.close(fig)

    print("\nsaved ->", OUT)


if __name__ == "__main__":
    main()
