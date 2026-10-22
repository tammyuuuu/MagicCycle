# -*- coding: utf-8 -*-
"""V2.0：四基金组合策略竞争（真实费用、T+1/T+2、限购、滚动样本外）。

评价：CAGR、MDD、Calmar、Sharpe、2000 元终值、最差浮亏、最长恢复、费用、交易次数。
"""
from pathlib import Path
import ast
import itertools
import json

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research_xingxun_v1"))
from engine_v2 import run_portfolio_v2  # noqa: E402
from otc_engine import FundFee  # noqa: E402

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean_v2"
V1 = ROOT.parent / "research_xingxun_v1"
OUT = ROOT / "out_v2"
OUT.mkdir(exist_ok=True)

CODES = ["000015", "001214", "008701", "161130"]
CASH = "000198"
NAMES = {"000015": "华夏纯债A", "001214": "华泰柏瑞500", "008701": "华夏黄金",
         "161130": "易方达纳指", "000216": "华安黄金", "160119": "南方500",
         "270042": "广发纳指", "006989": "建信中短债", "006484": "1-3年国开",
         CASH: "货基"}

# 受控候选权重集合（债/500/金/纳），不穷举
WEIGHT_GRID = [
    {"000015": .25, "001214": .25, "008701": .25, "161130": .25},
    {"000015": .40, "001214": .20, "008701": .20, "161130": .20},
    {"000015": .35, "001214": .25, "008701": .20, "161130": .20},
    {"000015": .30, "001214": .25, "008701": .25, "161130": .20},
    {"000015": .30, "001214": .30, "008701": .20, "161130": .20},
    {"000015": .20, "001214": .30, "008701": .25, "161130": .25},
    {"000015": .20, "001214": .25, "008701": .30, "161130": .25},
    {"000015": .15, "001214": .30, "008701": .25, "161130": .30},
    {"000015": .10, "001214": .30, "008701": .30, "161130": .30},
    {"000015": .40, "001214": .15, "008701": .30, "161130": .15},
    {"000015": .50, "001214": .15, "008701": .25, "161130": .10},
    {"000015": .35, "001214": .35, "008701": .15, "161130": .15},
]


def load_panel():
    p = pd.read_csv(CLEAN / "panel_v2.csv", index_col=0, parse_dates=True)
    v1 = pd.read_csv(V1 / "clean" / "tr_panel.csv", index_col=0, parse_dates=True)
    extra = ["000216", "160119", "270042", "006989", "006484"]
    for c in extra:
        p[c] = v1[c].reindex(p.index).ffill(limit=5)
    return p.ffill(limit=5).dropna()


def load_fees():
    out = {}
    m = pd.read_csv(CLEAN / "fund_meta_v2.csv", dtype={"code": str})
    for _, r in m.iterrows():
        bt = ast.literal_eval(r["purchase_fee_tiers"]) if isinstance(r["purchase_fee_tiers"], str) else None
        rt = ast.literal_eval(r["redeem_fee_tiers"]) if isinstance(r["redeem_fee_tiers"], str) else None
        out[str(r["code"])] = FundFee(str(r["code"]), bt, rt)
    m1 = pd.read_csv(V1 / "clean" / "fund_meta.csv", dtype={"code": str})
    for c in ["000216", "160119", "270042", "006989", "006484"]:
        r = m1[m1.code == c].iloc[0]
        bt = ast.literal_eval(r["purchase_fee_tiers"]) if isinstance(r["purchase_fee_tiers"], str) else None
        rt = ast.literal_eval(r["redeem_fee_tiers"]) if isinstance(r["redeem_fee_tiers"], str) else None
        out[c] = FundFee(c, bt, rt)
    return out


def stats(eq, dates, i0, i1, cash_ret, capital):
    s = pd.Series(eq[i0:i1 + 1], index=dates[i0:i1 + 1]).dropna()
    if len(s) < 20:
        return {}
    years = (s.index[-1] - s.index[0]).days / 365.25
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / max(years, 1e-9)) - 1
    ret = s.pct_change().dropna()
    vol = ret.std() * np.sqrt(252)
    mdd = float((s / s.cummax() - 1).min())
    cc = pd.Series(cash_ret[i0:i1 + 1]).dropna()
    if len(cc) > 2:
        cum = float((1 + cc).prod())
        cash_cagr = cum ** (365.25 / max((s.index[-1] - s.index[0]).days, 1)) - 1
    else:
        cash_cagr = 0.0
    sharpe = (cagr - cash_cagr) / vol if vol > 0 else np.nan
    newhigh = s[s >= s.cummax()]
    peak = s.cummax()
    under = (s < peak).to_numpy()
    idx = s.index
    max_days, start_under = 0, None
    for k, u in enumerate(under):
        if u and start_under is None:
            start_under = idx[k]
        elif not u and start_under is not None:
            max_days = max(max_days, (idx[k] - start_under).days)
            start_under = None
    if start_under is not None:
        max_days = max(max_days, (idx[-1] - start_under).days)
    worst = float((s - s.cummax()).min())
    return dict(cagr=cagr, vol=vol, mdd=mdd, calmar=cagr / abs(mdd) if mdd < 0 else np.nan,
                sharpe=sharpe, years=years, final=s.iloc[-1] / s.iloc[0] * capital,
                worst_amount=worst / s.iloc[0] * capital, recovery_days=max_days)


def make_staged(base, months, dates, start_idx):
    y0, m0 = dates[start_idx].year, dates[start_idx].month
    def f(i):
        k = (dates[i].year - y0) * 12 + (dates[i].month - m0)
        frac = min(1.0, (k + 1) / months)
        return {c: v * frac for c, v in base.items()}
    return f


def make_invvol(prices, dates, window=120, cap=0.5):
    def f(i):
        hist = {c: prices[c][max(0, i - window + 1):i + 1] for c in CODES}
        vol = {}
        for c, arr in hist.items():
            r = np.diff(arr) / arr[:-1]
            vol[c] = np.std(r) * np.sqrt(252) if len(r) > 5 else 1.0
        inv = {c: 1.0 / max(v, 1e-6) for c, v in vol.items()}
        tot = sum(inv.values())
        w = {c: inv[c] / tot for c in CODES}
        # 单资产上限
        for _ in range(10):
            over = {c: w[c] for c in w if w[c] > cap}
            if not over:
                break
            excess = sum(w[c] - cap for c in over)
            for c in over:
                w[c] = cap
            free = [c for c in w if w[c] < cap]
            if not free:
                break
            s = sum(w[c] for c in free)
            for c in free:
                w[c] += excess * w[c] / s
        return w
    return f


def make_timing(prices, dates, ma=200, bond_w=0.20):
    risk = ["001214", "008701", "161130"]
    base = {c: (1 - bond_w) / len(risk) for c in risk}
    def f(i):
        w = {"000015": bond_w}
        for c in risk:
            arr = prices[c][max(0, i - ma + 1):i + 1]
            w[c] = base[c] if arr[-1] > np.mean(arr) else 0.0
        return w
    return f


def make_momentum(prices, dates, lookback=126, bond_w=0.30, top=2):
    risk = ["001214", "008701", "161130"]
    def f(i):
        if i < lookback:
            return {"000015": bond_w}
        score = {c: prices[c][i] / prices[c][i - lookback] - 1 for c in risk}
        pick = [c for c in sorted(score, key=score.get, reverse=True) if score[c] > 0][:top]
        w = {"000015": bond_w}
        for c in pick:
            w[c] = (1 - bond_w) / len(pick)
        return w
    return f


def backtest(prices, dates, cash_ret, w, fees, capital=2000.0, rebalance="M",
             band=0.02, once=False, blocked=None, start=0, end=None):
    end = len(dates) - 1 if end is None else end
    return run_portfolio_v2(prices, dates, cash_ret, w, capital, fees, start, end,
                            rebalance=rebalance, band=band, once=once, blocked=blocked)


def main():
    panel = load_panel()
    dates = panel.index
    prices = {c: panel[c].to_numpy(float) for c in panel.columns}
    cash_ret = panel[CASH].pct_change().fillna(0).to_numpy(float)
    fees = load_fees()
    capital = 2000.0
    n = len(dates)
    print("样本", dates[0].date(), dates[-1].date(), n, flush=True)

    results = {}

    def record(name, res, start=0, end=None):
        end = n - 1 if end is None else end
        m = stats(res["equity"], dates, start, end, cash_ret, capital)
        m.update(strategy=name, fees=res["fees"], trades=len(res["trades"]),
                 blocked=res["blocked"])
        results[name] = dict(metrics=m, res=res, start=start, end=end)
        print(f"{name:28s} CAGR {m['cagr']*100:6.2f}% MDD {m['mdd']*100:7.2f}% "
              f"Calmar {m['calmar']:5.2f} Sharpe {m['sharpe']:5.2f} "
              f"终值 {m['final']:8.2f} 费用 {res['fees']:.2f} 交易 {len(res['trades'])}", flush=True)

    # A 原始四只等权买入持有
    base = {"000015": .25, "001214": .25, "008701": .25, "161130": .25}
    record("A 四只等权 买入持有", backtest(prices, dates, cash_ret, base, fees,
                                          rebalance="M", once=True))
    # A2 四只固定比例（债40/500 20/金20/纳20）买入持有
    pref = {"000015": .40, "001214": .20, "008701": .20, "161130": .20}
    record("A2 债40/50020/金20/纳20 买入持有", backtest(prices, dates, cash_ret, pref, fees,
                                                        rebalance="M", once=True))
    # B 等权 + 月度/季度再平衡
    record("B1 等权 月度再平衡", backtest(prices, dates, cash_ret, base, fees, rebalance="M"))
    record("B2 等权 季度再平衡", backtest(prices, dates, cash_ret, base, fees, rebalance="Q"))
    record("B3 等权 2%带 月度", backtest(prices, dates, cash_ret, base, fees, rebalance="M", band=0.02))
    record("B4 等权 5%带 月度", backtest(prices, dates, cash_ret, base, fees, rebalance="M", band=0.05))
    # C 固定权重（全样本最优，仅作参照，非样本外）
    for k, w in enumerate(WEIGHT_GRID):
        record(f"C{k:02d} 固定权重", backtest(prices, dates, cash_ret, w, fees, rebalance="M"))
    # D 逆波动
    for win in (60, 120, 250):
        record(f"D 逆波动{win}", backtest(prices, dates, cash_ret,
                                          make_invvol(prices, dates, win), fees, rebalance="M"))
    # E 分批建仓（等权，3/6/12 月）
    for mo in (3, 6, 12):
        record(f"E 分批{mo}月+持有", backtest(prices, dates, cash_ret,
                                              make_staged(base, mo, dates, 0), fees))
    # F 择时（200日均线）
    record("F1 200日均线 债20", backtest(prices, dates, cash_ret,
                                        make_timing(prices, dates, 200, 0.20), fees))
    record("F2 200日均线 债40", backtest(prices, dates, cash_ret,
                                        make_timing(prices, dates, 200, 0.40), fees))
    # G 动量
    record("G1 动量top2 债30", backtest(prices, dates, cash_ret,
                                       make_momentum(prices, dates, 126, 0.30, 2), fees))
    record("G2 动量top1 债30", backtest(prices, dates, cash_ret,
                                       make_momentum(prices, dates, 126, 0.30, 1), fees))
    # 限购情景（161130 完全买不到）
    blocked = lambda i, c: c == "161130"
    record("B1 限购 纳指留现金", backtest(prices, dates, cash_ret, base, fees,
                                          rebalance="M", blocked=blocked))

    # ---- 替换 / 精简（同等权重下比较） ----
    sub = panel
    alt_prices = {c: sub[c].to_numpy(float) for c in sub.columns}
    def combo(weights, blocked=None, once=False, reb="M"):
        return backtest(alt_prices, dates, cash_ret, weights, fees, rebalance=reb,
                        once=once, blocked=blocked)

    replace_sets = {
        "H0 原四只等权": {"000015": .25, "001214": .25, "008701": .25, "161130": .25},
        "H1 纳指换广发": {"000015": .25, "001214": .25, "008701": .25, "270042": .25},
        "H2 500换南方": {"000015": .25, "160119": .25, "008701": .25, "161130": .25},
        "H3 黄金换华安": {"000015": .25, "001214": .25, "000216": .25, "161130": .25},
        "H4 纯债换中短债": {"006989": .25, "001214": .25, "008701": .25, "161130": .25},
        "H5 纯债换1-3国开": {"006484": .25, "001214": .25, "008701": .25, "161130": .25},
        "H6 三只（去纯债）": {"001214": 1/3, "008701": 1/3, "161130": 1/3},
        "H7 三只（去黄金）": {"000015": 1/3, "001214": 1/3, "161130": 1/3},
        "H8 三只（去500）": {"000015": 1/3, "008701": 1/3, "161130": 1/3},
        "H9 三只（去纳指）": {"000015": 1/3, "001214": 1/3, "008701": 1/3},
        "H10 两只 债+纳": {"000015": .5, "161130": .5},
        "H11 两只 债+500": {"000015": .5, "001214": .5},
        "H12 两只 金+纳": {"008701": .5, "161130": .5},
    }
    for name, w in replace_sets.items():
        need = list(w)
        sub2 = {c: prices[c] for c in need}
        res = run_portfolio_v2(sub2, dates, cash_ret, w, capital, fees, 0, n - 1,
                               rebalance="M", band=0.02)
        record(name, res)

    df = pd.DataFrame([v["metrics"] for v in results.values()])
    df = df[["strategy", "cagr", "vol", "mdd", "calmar", "sharpe", "final",
             "worst_amount", "recovery_days", "fees", "trades", "blocked"]]
    df.to_csv(OUT / "summary_full.csv", index=False, float_format="%.6f")
    print("\n写入", OUT / "summary_full.csv")

    # 保存主要策略净值与逐月
    keep = ["A 四只等权 买入持有", "B1 等权 月度再平衡", "D 逆波动120",
            "E 分批3月+持有", "F1 200日均线 债20", "B1 限购 纳指留现金"]
    for name in keep:
        res = results[name]["res"]
        eq = pd.Series(res["equity"], index=dates).dropna()
        eq.to_csv(OUT / f"equity_{name.split(' ')[0]}_{abs(hash(name)) % 10000}.csv",
                  header=["equity"], float_format="%.6f")
        eq.resample("ME").last().pct_change().dropna().to_csv(
            OUT / f"monthly_{name.split(' ')[0]}_{abs(hash(name)) % 10000}.csv",
            header=["ret"], float_format="%.6f")

    with open(OUT / "results_meta.json", "w", encoding="utf-8") as f:
        json.dump({k: v["metrics"] for k, v in results.items()}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
