# -*- coding: utf-8 -*-
"""第四轮：配置方案比较（固定比例 / 等权 / 逆波动率 / ERC）与参数稳定性。

评价标准（按用户要求，不只看全样本收益）：
- 全样本与样本外（2024 起）的年化、最大回撤、Sharpe、Calmar；
- 再平衡频率、波动率窗口、权重扰动下的稳定性；
- 换手与费用。
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from otc_engine import load_fee
from run_round2 import FULL, LABEL, build_panel, cash_equity
from weight_engine import run_portfolio, portfolio_metrics

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out_alloc"
OUT.mkdir(exist_ok=True)

GOLD, HS300, DIV, BOND = "000216", "160706", "090010", "006484"
FOUR = [GOLD, HS300, DIV, BOND]
THREE = [GOLD, HS300, BOND]


def inverse_vol(prices, codes, i, vol_win=120, cap=0.5, floor=0.05):
    """逆波动率加权（不是完整协方差风险平价）。

    w_i ∝ 1/σ_i，σ 为过去 vol_win 日的实现波动；再施加单资产上限/下限并归一。
    这是简化方案，忽略资产间相关性。
    """
    vols = {}
    for c in codes:
        seg = np.asarray(prices[c][max(0, i - vol_win):i + 1], float)
        if len(seg) < 30:
            return {x: 1.0 / len(codes) for x in codes}
        r = np.diff(seg) / seg[:-1]
        vols[c] = max(float(np.std(r, ddof=1)) * np.sqrt(252), 1e-6)
    inv = {c: 1.0 / vols[c] for c in codes}
    tot = sum(inv.values())
    w = {c: inv[c] / tot for c in codes}
    for _ in range(6):
        over = [c for c in codes if w[c] > cap]
        if not over:
            break
        excess = sum(w[c] - cap for c in over)
        for c in over:
            w[c] = cap
        rest = [c for c in codes if w[c] < cap]
        if not rest:
            break
        s = sum(w[c] for c in rest)
        for c in rest:
            w[c] += excess * w[c] / s
    for c in codes:
        w[c] = max(w[c], floor)
    s = sum(w.values())
    return {c: w[c] / s for c in codes}


# 兼容旧调用名；语义上就是逆波动率，不是 ERC。
risk_parity = inverse_vol


def _project_bounded(w, cap, floor, iters=200):
    w = np.clip(np.asarray(w, float), floor, cap)
    for _ in range(iters):
        diff = 1.0 - w.sum()
        if abs(diff) < 1e-12:
            break
        free = (w < cap - 1e-10) if diff > 0 else (w > floor + 1e-10)
        if not free.any():
            break
        w[free] += diff / free.sum()
        w = np.clip(w, floor, cap)
    return w


def erc_weights(prices, codes, i, vol_win=120, cap=0.4, floor=0.05,
                iters=600, tol=1e-10):
    """完整协方差风险平价（Equal Risk Contribution）。

    用样本协方差矩阵，按 Equal Risk Contribution 求解；
    算法为循环坐标下降（无 scipy 依赖），并施加上下限与归一约束。
    """
    n = len(codes)
    if len(prices[codes[0]][max(0, i - vol_win):i + 1]) < 30:
        return {c: 1.0 / n for c in codes}
    rets = []
    for c in codes:
        seg = np.asarray(prices[c][max(0, i - vol_win):i + 1], float)
        rets.append(np.diff(seg) / seg[:-1])
    R = np.vstack(rets)
    cov = np.cov(R) * 252
    cov = np.atleast_2d(cov)
    cov += np.eye(n) * 1e-10
    vols = np.sqrt(np.diag(cov))
    w = (1.0 / np.maximum(vols, 1e-8))
    w = _project_bounded(w / w.sum(), cap, floor)
    for _ in range(iters):
        prev = w.copy()
        for k in range(n):
            a = cov[k, k]
            b = float(cov[k] @ w - a * w[k])
            target = float(w @ cov @ w) / n
            disc = b * b + 4 * a * target
            if a <= 0 or disc < 0:
                continue
            w[k] = (-b + np.sqrt(disc)) / (2 * a)
            w = _project_bounded(w, cap, floor)
        if np.max(np.abs(w - prev)) < tol:
            break
    w = _project_bounded(w, cap, floor)
    return {c: float(w[j]) for j, c in enumerate(codes)}


def main():
    tr, dates, cash, fees, pe = build_panel(FULL, "2019-03-08")
    prices = {c: tr[c].to_numpy(float) for c in FULL}
    pos = {d: i for i, d in enumerate(dates)}
    s_oos = pos[dates[dates >= "2024-01-02"][0]]
    s_full, e_full = 0, len(dates) - 1

    configs = {
        "F1_30_35_15_20": dict(kind="fixed", w={GOLD: .30, HS300: .35, DIV: .15, BOND: .20}),
        "F2_等权四资产": dict(kind="fixed", w={c: .25 for c in FOUR}),
        "F3_三资产等权": dict(kind="fixed", w={c: 1 / 3 for c in THREE}),
        "F3b_40_40_20": dict(kind="fixed", w={GOLD: .40, HS300: .40, BOND: .20}),
        "F4_逆波动率四资产": dict(kind="rp", codes=FOUR, cap=.50),
        "F4b_逆波动率四资产_债40": dict(kind="rp", codes=FOUR, cap=.40),
        "F5_逆波动率三资产": dict(kind="rp", codes=THREE, cap=.60),
        "F6_ERC四资产_债40": dict(kind="erc", codes=FOUR, cap=.40),
        "F7_ERC三资产_债60": dict(kind="erc", codes=THREE, cap=.60),
        "F8_黄金300各半": dict(kind="fixed", w={GOLD: .50, HS300: .50}),
        "F9_全现金": dict(kind="cash", w={}),
    }

    rows, equity_store = [], {}
    for name, cfg in configs.items():
        if cfg["kind"] == "cash":
            eq = cash_equity(2000.0, cash, s_full, e_full)
            eq = np.nan_to_num(eq, nan=0.0)
            ftotal, trades = 0.0, []
        else:
            if cfg["kind"] == "fixed":
                weights = cfg["w"]
            else:
                codes = cfg["codes"]
                fn = inverse_vol if cfg["kind"] == "rp" else erc_weights
                weights = (lambda i, codes=codes, cap=cfg["cap"], fn=fn:
                           fn(prices, codes, i, 120, cap))
            eq, ftotal, trades = run_portfolio(
                prices, dates, cash, weights, 2000.0, fees, s_full, e_full,
                rebalance="M", band=0.02)
        for seg, s, e in (("FULL", s_full, e_full), ("OOS", s_oos, e_full)):
            m = portfolio_metrics(eq, cash, s, e)
            rows.append(dict(config=name, segment=seg, trades=len(trades), fees=ftotal,
                             **m))
        equity_store[name] = eq

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "allocation_compare.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(equity_store).to_csv(OUT / "equity_alloc.csv")
    print(df[df.segment == "FULL"].round(4).to_string(index=False))
    print()
    print(df[df.segment == "OOS"].round(4).to_string(index=False))

    # ---------- 稳定性：再平衡频率 ----------
    stab = []
    for name, cfg in configs.items():
        if cfg["kind"] == "cash":
            continue
        for freq in ("M", "Q", "2Q"):
            if cfg["kind"] == "fixed":
                weights = cfg["w"]
            else:
                codes = cfg["codes"]
                fn = inverse_vol if cfg["kind"] == "rp" else erc_weights
                weights = (lambda i, codes=codes, cap=cfg["cap"], fn=fn:
                           fn(prices, codes, i, 120, cap))
            eq, f, t = run_portfolio(prices, dates, cash, weights, 2000.0, fees,
                                     s_full, e_full, rebalance=freq, band=0.02)
            for seg, s, e in (("FULL", s_full, e_full), ("OOS", s_oos, e_full)):
                m = portfolio_metrics(eq, cash, s, e)
                stab.append(dict(config=name, freq=freq, segment=seg,
                                 trades=len(t), fees=f, **m))
    st = pd.DataFrame(stab)
    st.to_csv(OUT / "stability_frequency.csv", index=False, encoding="utf-8-sig")

    # ---------- 稳定性：逆波动率参数 ----------
    rp = []
    for cfg_name, codes, caps in (("RP4", FOUR, (.40, .50, .60)),
                                  ("RP3", THREE, (.50, .60, .70))):
        for win in (60, 120, 250):
            for cap in caps:
                weights = (lambda i, codes=codes, cap=cap, win=win:
                           inverse_vol(prices, codes, i, win, cap))
                eq, f, t = run_portfolio(prices, dates, cash, weights, 2000.0, fees,
                                         s_full, e_full, rebalance="M", band=0.02)
                for seg, s, e in (("FULL", s_full, e_full), ("OOS", s_oos, e_full)):
                    m = portfolio_metrics(eq, cash, s, e)
                    rp.append(dict(config=cfg_name, vol_win=win, cap=cap, segment=seg,
                                   trades=len(t), fees=f, **m))
    rp_df = pd.DataFrame(rp)
    rp_df.to_csv(OUT / "stability_riskparity.csv", index=False, encoding="utf-8-sig")

    # ---------- 稳定性：ERC 参数 ----------
    erc = []
    for cfg_name, codes, caps in (("ERC4", FOUR, (.40, .50)),
                                  ("ERC3", THREE, (.55, .60))):
        for win in (60, 120, 250):
            for cap in caps:
                weights = (lambda i, codes=codes, cap=cap, win=win:
                           erc_weights(prices, codes, i, win, cap))
                eq, f, t = run_portfolio(prices, dates, cash, weights, 2000.0, fees,
                                         s_full, e_full, rebalance="M", band=0.02)
                for seg, s, e in (("FULL", s_full, e_full), ("OOS", s_oos, e_full)):
                    m = portfolio_metrics(eq, cash, s, e)
                    erc.append(dict(config=cfg_name, vol_win=win, cap=cap, segment=seg,
                                    trades=len(t), fees=f, **m))
    pd.DataFrame(erc).to_csv(OUT / "stability_erc.csv", index=False, encoding="utf-8-sig")

    # ---------- 稳定性：固定权重扰动 ±5pp ----------
    pert = []
    base = {GOLD: .30, HS300: .35, DIV: .15, BOND: .20}
    variants = {}
    for c in FOUR:
        for delta in (-.05, .05):
            w = dict(base)
            w[c] = round(w[c] + delta, 4)
            # 其余按比例吸收，保持合计 100%
            rest = [x for x in FOUR if x != c]
            s = sum(w[x] for x in rest)
            for x in rest:
                w[x] = max(0.0, w[x] - delta * w[x] / s)
            variants[f"{LABEL[c]}{delta:+.0%}"] = w
    for vname, w in variants.items():
        eq, f, t = run_portfolio(prices, dates, cash, w, 2000.0, fees,
                                 s_full, e_full, rebalance="M", band=0.02)
        for seg, s, e in (("FULL", s_full, e_full), ("OOS", s_oos, e_full)):
            m = portfolio_metrics(eq, cash, s, e)
            pert.append(dict(variant=vname, segment=seg, trades=len(t), fees=f, **m))
    pd.DataFrame(pert).to_csv(OUT / "stability_weights.csv", index=False, encoding="utf-8-sig")

    # ---------- 年度收益 ----------
    eqdf = pd.DataFrame(equity_store, index=dates)
    yearly = eqdf.resample("YE").last().pct_change(fill_method=None)
    yearly.iloc[0] = eqdf.resample("YE").last().iloc[0] / 2000.0 - 1
    yearly.index = yearly.index.year
    yearly.to_csv(OUT / "yearly_returns.csv", encoding="utf-8-sig")
    print("\n年度收益：\n", (yearly * 100).round(2).to_string())

    # ---------- 图 ----------
    eng = {"F1_30_35_15_20": "30/35/15/20", "F2_等权四资产": "Equal 4 assets",
           "F3_三资产等权": "Equal 3 assets", "F4b_逆波动率四资产_债40": "Inverse-vol 4 (bond<=40%)",
           "F6_ERC四资产_债40": "ERC 4 (bond<=40%)",
           "F5_逆波动率三资产": "Inverse-vol 3"}
    fig, ax = plt.subplots(figsize=(11, 5.2))
    for k, label in eng.items():
        ax.plot(dates, np.asarray(equity_store[k]) / 2000.0, lw=1.4, label=label)
    ax.set_title("2000 CNY portfolio allocation: equity / initial")
    ax.set_ylabel("equity / initial")
    ax.grid(alpha=.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "allocation_equity.png", dpi=150)
    plt.close(fig)

    print("\nsaved ->", OUT)


if __name__ == "__main__":
    main()
