# -*- coding: utf-8 -*-
"""V2.3：开放资产池的组合优化与限购替代比较（月度再平衡口径）。"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
V1 = ROOT.parent / "research_xingxun_v1"
OUT = ROOT / "out_v23"
OUT.mkdir(exist_ok=True)

NAMES = {
    "160706": "沪深300", "160119": "中证500", "011860": "中证1000", "011612": "科创50",
    "110026": "创业板", "090010": "中证红利", "161130": "易方达纳指", "270042": "广发纳指",
    "050025": "标普500", "008701": "华夏黄金", "000216": "华安黄金",
    "000015": "华夏纯债", "006989": "中短债", "006484": "1-3年国开", "003358": "7-10年国开",
    "000198": "货币基金", "162413": "中证1000长样本",
}
CASH = "000198"


def load_all():
    tr = pd.read_csv(V1 / "clean" / "tr_panel.csv", index_col=0, parse_dates=True)
    parts = {c: tr[c] for c in tr.columns}
    for code, base in [("000015", "clean_v2"), ("001214", "clean_v2"),
                       ("008701", "clean_v2"), ("161130", "clean_v2")]:
        d = pd.read_csv(ROOT / base / f"{code}.csv", index_col=0, parse_dates=True)
        parts[code] = d["tr"]
    d = pd.read_csv(ROOT / "clean_v23" / "110026.csv", index_col=0, parse_dates=True)
    parts["110026"] = d["tr"]
    cal = tr["160706"].dropna().index
    panel = pd.DataFrame({c: s.reindex(cal).ffill(limit=5) for c, s in parts.items()})
    return panel


def month_ret(panel):
    # Missing unrelated assets must never truncate another portfolio's history.
    return panel.resample("ME").last().pct_change(fill_method=None)


def invvol_w(hist, codes, window=120, cap=0.6):
    vol = {}
    for c in codes:
        r = hist[c].dropna().pct_change(fill_method=None).dropna().iloc[-window:]
        vol[c] = r.std() * np.sqrt(252) if len(r) > 20 else 1.0
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


def erc_w(hist, codes, window=250, iters=300):
    ret = hist[codes].dropna().pct_change(fill_method=None).dropna().iloc[-window:]
    if len(ret) < 40:
        return {c: 1 / len(codes) for c in codes}
    cov = ret.cov().values * 252
    n = len(codes)
    w = np.full(n, 1 / n)
    for _ in range(iters):
        mctr = cov @ w
        mctr = np.where(mctr <= 1e-12, 1e-12, mctr)
        wn = 1 / mctr
        wn = np.maximum(wn, 0.02)
        wn = wn / wn.sum()
        if np.max(np.abs(wn - w)) < 1e-9:
            w = wn
            break
        w = 0.5 * w + 0.5 * wn
    return {c: float(v) for c, v in zip(codes, w)}


def trend_w(hist, fixed, ma=200):
    """风险资产跌破 200 日均线则转现金，债券保留。"""
    w = {}
    for c, wt in fixed.items():
        if c in ("000015", "006989", "006484", "003358"):
            w[c] = wt
            continue
        s = hist[c].dropna()
        w[c] = wt if len(s) >= ma and s.iloc[-1] > s.iloc[-ma:].mean() else 0.0
    return w


def run(panel, rets, w_func, start, end):
    sub = rets[(rets.index >= pd.Timestamp(start)) & (rets.index <= pd.Timestamp(end))]
    if len(sub) < 6:
        return None, None
    rows = []
    for dt in sub.index:
        previous_month = dt.to_period('M').start_time - pd.Timedelta(days=1)
        # Two proxy trading days of disclosure lag; historical publication times
        # are unavailable, so this is an explicit conservative scenario.
        available = panel.index[panel.index <= previous_month]
        if len(available) < 3:
            raise ValueError('没有足够的决策前历史')
        hist = panel.loc[:available[-3]].copy()
        w = w_func(hist, dt)
        required = [c for c,v in w.items() if v != 0] + ([CASH] if sum(w.values()) < 1-1e-9 else [])
        if any(c not in sub or not np.isfinite(sub.loc[dt,c]) for c in required):
            raise ValueError(f'{dt.date()} 组合所需收益缺失: {required}')
        if any(not np.isfinite(v) or v < 0 for v in w.values()) or sum(w.values()) > 1+1e-9:
            raise ValueError('非法权重')
        r = sum(w.get(c, 0.0) * sub.loc[dt, c] for c in w if c in sub.columns)
        r += (1 - sum(w.values())) * sub.loc[dt, CASH]
        rows.append((dt, r, w))
    ser = pd.Series({d: r for d, r, _ in rows}).sort_index()
    curve = (1 + ser).cumprod()
    years = len(ser) / 12
    cagr = curve.iloc[-1] ** (1 / years) - 1
    vol = ser.std() * np.sqrt(12)
    mdd = float((curve / np.maximum.accumulate(np.r_[1.,curve.to_numpy()])[1:] - 1).min())
    cash_cagr = (1 + sub[CASH]).prod() ** (1 / years) - 1
    sharpe = (cagr - cash_cagr) / vol if vol > 0 else np.nan
    return dict(cagr=cagr, vol=vol, mdd=mdd, calmar=cagr / abs(mdd) if mdd < 0 else np.nan,
                sharpe=sharpe, final=2000 * curve.iloc[-1], years=years,
                first_return=str(ser.index[0].date()),last_return=str(ser.index[-1].date()),
                months=len(ser),validation='historical_segment_not_untouched_oos'), (ser, curve, rows)


def main():
    panel = load_all()
    rets = month_ret(panel)
    main_s = ("2021-11-01", "2026-10-21")
    oos_s = ("2023-01-01", "2026-07-01")
    long_s = ("2017-07-03", "2024-12-31")

    print("主样本", panel.loc[main_s[0]:main_s[1]].index.min().date(),
          panel.loc[main_s[0]:main_s[1]].index.max().date())

    # 类别代表（主样本）：债/金/纳 + A股候选
    A_SHARES = {"300": "160706", "500": "160119", "1000": "011860",
                "科创50": "011612", "创业板": "110026", "红利": "090010"}

    fixed = {
        "Core3 债/金/纳 各1/3": {"000015": 1/3, "008701": 1/3, "161130": 1/3},
        "Core4 债/金/纳/标普": {"000015": .25, "008701": .25, "161130": .25, "050025": .25},
        "债/金 50/50": {"000015": .5, "008701": .5},
        "债/金 60/40": {"000015": .6, "008701": .4},
        "债/金 70/30": {"000015": .7, "008701": .3},
        "债/金/现金 50/30/20": {"000015": .5, "008701": .3},
        "100% 黄金": {"008701": 1.0},
        "100% 纳指": {"161130": 1.0},
        "100% 纯债": {"000015": 1.0},
    }
    for tag, code in A_SHARES.items():
        fixed[f"债/金/纳/{tag} 各1/4"] = {"000015": .25, "008701": .25, "161130": .25, code: .25}
        fixed[f"债/金/{tag} 各1/3"] = {"000015": 1/3, "008701": 1/3, code: 1/3}

    schemes = {}
    for name, w in fixed.items():
        schemes[name] = (lambda h, dt, w=w: w)
    schemes["逆波动 Core3"] = (lambda h, dt: invvol_w(h, ["000015", "008701", "161130"], 120, 0.6))
    schemes["逆波动 Core4"] = (lambda h, dt: invvol_w(h, ["000015", "008701", "161130", "050025"], 120, 0.6))
    schemes["逆波动 债/金"] = (lambda h, dt: invvol_w(h, ["000015", "008701"], 120, 0.8))
    schemes["逆波动 债/金/500"] = (lambda h, dt: invvol_w(h, ["000015", "008701", "160119"], 120, 0.6))
    schemes["逆波动 债/金/创业板"] = (lambda h, dt: invvol_w(h, ["000015", "008701", "110026"], 120, 0.6))
    schemes["ERC Core3"] = (lambda h, dt: erc_w(h, ["000015", "008701", "161130"], 250))
    schemes["ERC Core4"] = (lambda h, dt: erc_w(h, ["000015", "008701", "161130", "050025"], 250))
    schemes["趋势 Core3"] = (lambda h, dt: trend_w(h, {"000015": 1/3, "008701": 1/3, "161130": 1/3}))
    schemes["趋势 Core4"] = (lambda h, dt: trend_w(h, {"000015": .25, "008701": .25, "161130": .25, "050025": .25}))

    rows = []
    for name, wf in schemes.items():
        for seg, (s, e) in [("主样本 2021-11~2026-10", main_s), ("样本外 2023-01~2026-07", oos_s)]:
            m, _ = run(panel, rets, wf, s, e)
            if m:
                m.update(scheme=name, segment=seg)
                rows.append(m)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "v23_compare.csv", index=False, float_format="%.6f")
    piv = df.pivot(index="scheme", columns="segment", values=["cagr", "mdd", "calmar"])
    print("\n== 全样本/样本外（CAGR / MDD） ==")
    show = df[df.segment == "主样本 2021-11~2026-10"][["scheme", "cagr", "mdd", "calmar", "sharpe", "final"]]
    print(show.sort_values("cagr", ascending=False).round(4).to_string(index=False))

    print("\n== 样本外 ==")
    show2 = df[df.segment == "样本外 2023-01~2026-07"][["scheme", "cagr", "mdd", "calmar", "sharpe"]]
    print(show2.sort_values("cagr", ascending=False).round(4).to_string(index=False))

    # 长样本（不含 1000/科创/008701，用长历史产品）
    long_panel = panel[["160706", "160119", "090010", "110026", "270042", "050025",
                        "000216", "000015", "003358", "000198", "162413"]]
    lrets = month_ret(long_panel)
    long_fixed = {
        "Long 债/金/纳 各1/3": {"000015": 1/3, "000216": 1/3, "270042": 1/3},
        "Long 债/金/标普 各1/3": {"000015": 1/3, "000216": 1/3, "050025": 1/3},
        "Long 债/金/纳/标普": {"000015": .25, "000216": .25, "270042": .25, "050025": .25},
        "Long 债/金 50/50": {"000015": .5, "000216": .5},
        "Long 债/金/500 各1/3": {"000015": 1/3, "000216": 1/3, "160119": 1/3},
        "Long 债/金/创业板 各1/3": {"000015": 1/3, "000216": 1/3, "110026": 1/3},
    }
    rows = []
    for name, w in long_fixed.items():
        m, _ = run(long_panel, lrets, lambda h, dt, w=w: w, long_s[0], long_s[1])
        if m:
            m.update(scheme=name, segment="长样本 2017-07~2024-12")
            rows.append(m)
    for name, codes in [("Long 逆波动 债/金", ["000015", "000216"]),
                        ("Long 逆波动 债/金/纳", ["000015", "000216", "270042"])]:
        m, _ = run(long_panel, lrets,
                   lambda h, dt, codes=codes: invvol_w(h, codes, 120, 0.8 if len(codes) == 2 else 0.6),
                   long_s[0], long_s[1])
        if m:
            m.update(scheme=name, segment="长样本 2017-07~2024-12")
            rows.append(m)
    ldf = pd.DataFrame(rows)
    ldf.to_csv(OUT / "v23_long.csv", index=False, float_format="%.6f")
    print("\n== 长样本（不含黄金ETF 008701，用 000216） ==")
    print(ldf[["scheme", "cagr", "mdd", "calmar", "sharpe", "final"]]
          .sort_values("cagr", ascending=False).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
