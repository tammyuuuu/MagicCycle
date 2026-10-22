# -*- coding: utf-8 -*-
"""第六轮：配置方法与美股限购情景。

配置比较统一用「类别层月度再平衡」：
- 类别收益 = 类别内等权（日度再平衡）；
- 每月末用过去数据算下月权重（避免前视）；
- 不计交易费用（另做费用敏感性），因为本脚本比较的是配置结构。
"""
import numpy as np
import pandas as pd

from pool6_data import (CASH, CATEGORY, NAMES, OUT, baseline_weights, cat_curves,
                        load_main)

CATS = ["黄金", "美股", "A股", "债券"]


def month_returns(panel):
    m = panel.resample("ME").last()
    return m.pct_change(fill_method=None).dropna()


def fixed_scheme(w):
    def f(hist):
        return dict(w)
    return f


def inv_vol_scheme(window=120, bounds=None, cash_cap=None):
    def f(hist):
        ret = hist.pct_change(fill_method=None).dropna().iloc[-window:]
        vol = ret.std() * np.sqrt(252)
        inv = {c: (1.0 / vol[c] if vol[c] > 1e-8 else 0.0) for c in CATS}
        s = sum(inv.values())
        w = {c: inv[c] / s for c in CATS} if s > 0 else {c: 0.25 for c in CATS}
        if bounds:
            w = project_bounds(w, bounds)
        return w
    return f


def project_bounds(w, bounds, iters=60):
    """把权重投影到 [lo, hi]，并保持合计 ≤ 1（按比例分配剩余）。"""
    lo = {c: bounds[c][0] for c in w}
    hi = {c: bounds[c][1] for c in w}
    x = np.array([w[c] for c in CATS], dtype=float)
    lo_a = np.array([lo[c] for c in CATS])
    hi_a = np.array([hi[c] for c in CATS])
    for _ in range(iters):
        x = np.clip(x, lo_a, hi_a)
        diff = 1.0 - x.sum()
        if abs(diff) < 1e-10:
            break
        free = (x > lo_a + 1e-12) if diff < 0 else (x < hi_a - 1e-12)
        if not free.any():
            break
        x[free] += diff * x[free] / x[free].sum() if diff > 0 else diff * x[free] / x[free].sum()
        if not np.all(np.isfinite(x)):
            break
    x = np.clip(x, lo_a, hi_a)
    s = x.sum()
    if s > 1:
        x = x / s
    return {c: float(v) for c, v in zip(CATS, x)}


def erc_scheme(window=250, iters=400, lower=0.02):
    def f(hist):
        ret = hist.pct_change(fill_method=None).dropna().iloc[-window:]
        cov = ret[CATS].cov().values * 252
        n = len(CATS)
        w = np.full(n, 1.0 / n)
        for _ in range(iters):
            mctr = cov @ w
            mctr = np.where(np.abs(mctr) < 1e-10, 1e-10, mctr)
            w_new = 1.0 / np.abs(mctr)
            w_new = np.maximum(w_new, lower)
            w_new = w_new / w_new.sum()
            if np.max(np.abs(w_new - w)) < 1e-8:
                w = w_new
                break
            w = 0.5 * w + 0.5 * w_new
        s = w.sum()
        return {c: float(v / s) for c, v in zip(CATS, w)}
    return f


def risk_budget_scheme(budget, window=250, iters=300):
    def f(hist):
        ret = hist.pct_change(fill_method=None).dropna().iloc[-window:]
        cov = ret[CATS].cov().values * 252
        b = np.array([budget[c] for c in CATS], dtype=float)
        b = b / b.sum()
        w = b.copy()
        for _ in range(iters):
            mctr = cov @ w
            mctr = np.where(mctr <= 1e-12, 1e-12, mctr)
            w_new = b / mctr
            w_new = np.maximum(w_new, 0.02)
            w_new = w_new / w_new.sum()
            if np.max(np.abs(w_new - w)) < 1e-8:
                w = w_new
                break
            w = 0.5 * w + 0.5 * w_new
        return {c: float(v) for c, v in zip(CATS, w)}
    return f


# ---------------- 两层法：风险资产内部配权 + 债券固定权重 ----------------
RISK = ["黄金", "美股", "A股"]


def _to_full(w_risk, bond_w):
    out = {c: (1.0 - bond_w) * w_risk[c] for c in RISK}
    out["债券"] = bond_w
    return out


def sub_inv_vol(window=120, bond_w=0.20):
    def f(hist):
        ret = hist.pct_change(fill_method=None).dropna().iloc[-window:]
        vol = ret[RISK].std() * np.sqrt(252)
        inv = {c: (1.0 / vol[c] if vol[c] > 1e-8 else 0.0) for c in RISK}
        s = sum(inv.values())
        w = {c: inv[c] / s for c in RISK} if s > 0 else {c: 1 / 3 for c in RISK}
        return _to_full(w, bond_w)
    return f


def sub_erc(window=250, bond_w=0.20, iters=600):
    def f(hist):
        ret = hist.pct_change(fill_method=None).dropna().iloc[-window:]
        cov = ret[RISK].cov().values * 252
        n = len(RISK)
        w = np.full(n, 1.0 / n)
        for _ in range(iters):
            mctr = cov @ w
            mctr = np.where(mctr <= 1e-10, 1e-10, mctr)
            w_new = 1.0 / mctr
            w_new = w_new / w_new.sum()
            if np.max(np.abs(w_new - w)) < 1e-9:
                w = w_new
                break
            w = 0.5 * w + 0.5 * w_new
        return _to_full({c: float(v) for c, v in zip(RISK, w)}, bond_w)
    return f


def sub_rb(budget, window=250, bond_w=0.20, iters=600):
    """风险预算只作用于风险资产；债券作为降波动层单独定量。"""
    def f(hist):
        ret = hist.pct_change(fill_method=None).dropna().iloc[-window:]
        cov = ret[RISK].cov().values * 252
        b = np.array([budget[c] for c in RISK], dtype=float)
        b = b / b.sum()
        w = b.copy()
        for _ in range(iters):
            mctr = cov @ w
            mctr = np.where(mctr <= 1e-12, 1e-12, mctr)
            w_new = b / mctr
            w_new = w_new / w_new.sum()
            if np.max(np.abs(w_new - w)) < 1e-9:
                w = w_new
                break
            w = 0.5 * w + 0.5 * w_new
        return _to_full({c: float(v) for c, v in zip(RISK, w)}, bond_w)
    return f


def sub_equal(bond_w=0.20):
    def f(hist):
        return _to_full({c: 1 / 3 for c in RISK}, bond_w)
    return f


def weight_table(daily_cat, scheme, warmup=60):
    m = daily_cat.resample("ME").last()
    dates = m.index
    rec = {}
    for dt in dates:
        hist = daily_cat.loc[:dt]
        if len(hist) < warmup:
            continue
        raw = scheme(hist)
        rec[dt] = {c: float(raw.get(c, 0.0)) for c in CATS}
    W = pd.DataFrame.from_dict(rec, orient="index", columns=CATS).reindex(dates)
    return W.shift(1)   # 月末决策 → 下月生效


def evaluate(daily_cat, scheme, start=None, end=None, warmup=60):
    rets = month_returns(daily_cat)
    W = weight_table(daily_cat, scheme, warmup=warmup)
    rows = []
    for dt in rets.index:
        if dt not in W.index:
            continue
        w = W.loc[dt]
        if w is None or (isinstance(w, float) and np.isnan(w)) or w.isna().any():
            continue
        w = {c: float(w.get(c, 0.0)) for c in CATS}
        r = sum(w[c] * rets.loc[dt, c] for c in CATS) + (1 - sum(w.values())) * rets.loc[dt, "现金"]
        rows.append((dt, r, sum(w.values()), w))
    ser = pd.Series({d: r for d, r, _, _ in rows}).sort_index()
    if ser.empty:
        return ser, ser, rows
    if start:
        ser = ser[ser.index >= pd.Timestamp(start)]
    if end:
        ser = ser[ser.index <= pd.Timestamp(end)]
    curve = (1 + ser).cumprod()
    return ser, curve, rows


def metrics(ser, curve, cash_ser):
    if len(ser) < 6:
        return {}
    years = len(ser) / 12.0
    cagr = curve.iloc[-1] ** (1 / years) - 1
    vol = ser.std() * np.sqrt(12)
    mdd = float((curve / curve.cummax() - 1).min())
    cash_cagr = (1 + cash_ser.loc[ser.index]).prod() ** (1 / years) - 1
    sharpe = (cagr - cash_cagr) / vol if vol > 0 else np.nan
    return dict(cagr=cagr, vol=vol, mdd=mdd, sharpe=sharpe,
                calmar=cagr / abs(mdd) if mdd < 0 else np.nan, years=years)


def main():
    panel = load_main()
    daily_cat = cat_curves(panel, freq="D")
    cash_ser = month_returns(daily_cat)["现金"]

    schemes = {
        "F1 25/25/30/20": fixed_scheme({"黄金": .25, "美股": .25, "A股": .30, "债券": .20}),
        "F2 四类等权": fixed_scheme({c: .25 for c in CATS}),
        "F3 20/30/30/20": fixed_scheme({"黄金": .20, "美股": .30, "A股": .30, "债券": .20}),
        "F4 30/20/30/20": fixed_scheme({"黄金": .30, "美股": .20, "A股": .30, "债券": .20}),
        "F5 40/20/30/10（进攻）": fixed_scheme({"黄金": .40, "美股": .20, "A股": .30, "债券": .10}),
        "IV 逆波动120": inv_vol_scheme(120),
        "IV 逆波动120+债≤40%": inv_vol_scheme(120, bounds={"黄金": (0, 1), "美股": (0, 1), "A股": (0, 1), "债券": (0, .40)}),
        "IV 逆波动120+上下限": inv_vol_scheme(120, bounds={"黄金": (.10, .35), "美股": (.10, .35), "A股": (.20, .45), "债券": (.10, .40)}),
        "ERC 完整协方差": erc_scheme(250),
        "RB 风险预算 20/30/40/10": risk_budget_scheme({"黄金": .20, "美股": .30, "A股": .40, "债券": .10}, 250),
        "两层 风险资产逆波动+债20%": sub_inv_vol(120, 0.20),
        "两层 风险资产逆波动+债30%": sub_inv_vol(120, 0.30),
        "两层 风险资产ERC+债20%": sub_erc(250, 0.20),
        "两层 风险预算30/30/40+债20%": sub_rb({"黄金": .30, "美股": .30, "A股": .40}, 250, 0.20),
        "两层 风险资产等权+债20%": sub_equal(0.20),
        "全现金": fixed_scheme({c: 0 for c in CATS}),
    }

    rows = []
    segs = [("全样本", "2021-10-01", "2026-10-21"),
            ("前段 2021-10~2024-03", "2021-10-01", "2024-03-31"),
            ("后段 2024-04~2026-10", "2024-04-01", "2026-10-21")]
    for name, sch in schemes.items():
        for seg, s, e in segs:
            ser, curve, _ = evaluate(daily_cat, sch, start=s, end=e)
            mt = metrics(ser, curve, cash_ser)
            if not mt:
                continue
            mt.update(scheme=name, segment=seg)
            rows.append(mt)
    df = pd.DataFrame(rows)[["scheme", "segment", "cagr", "vol", "mdd", "sharpe", "calmar", "years"]]
    df.to_csv(OUT / "alloc_compare_main.csv", index=False, float_format="%.6f")
    print("== 配置方案（类别层月度再平衡） ==")
    print(df.pivot(index="scheme", columns="segment", values="cagr").round(4).to_string())
    print()
    print(df[df.segment == "全样本"].to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # 最近一次权重
    print("\n== 各方案最近一个月权重 ==")
    for name, sch in schemes.items():
        ser, curve, rows_w = evaluate(daily_cat, sch)
        if not rows_w:
            continue
        last = rows_w[-1]
        print(f"{name:24s}", {k: round(v, 3) for k, v in last[3].items()})

    # 风险贡献（F1 / IV / ERC 的实际风险贡献）
    print("\n== 类别层实际风险贡献 ==")
    rets = month_returns(daily_cat)
    out_rows = []
    for name in ["F1 25/25/30/20", "F2 四类等权", "两层 风险资产逆波动+债20%",
                 "两层 风险资产ERC+债20%", "两层 风险预算30/30/40+债20%",
                 "IV 逆波动120", "ERC 完整协方差"]:
        ser, curve, rows_w = evaluate(daily_cat, schemes[name])
        if not rows_w:
            continue
        w = rows_w[-1][3]
        cov = rets[CATS].cov().values * 12
        wv = np.array([w[c] for c in CATS])
        mctr = cov @ wv
        rc = wv * mctr
        share = rc / rc.sum()
        out_rows.append(dict(scheme=name, **{f"w_{c}": w[c] for c in CATS},
                             **{f"rc_{c}": share[i] for i, c in enumerate(CATS)}))
    rc_df = pd.DataFrame(out_rows)
    rc_df.to_csv(OUT / "alloc_risk_contrib.csv", index=False, float_format="%.6f")
    print(rc_df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    # ---- 美股限购情景（资产层，月度合成） ----
    asset_ret = month_returns(panel)
    base = baseline_weights(panel)
    scen = {}
    scen["S0 理论可买（美股25%）"] = dict(base)
    s1 = dict(base)
    s1["270042"] = 0.025
    s1["050025"] = 0.025
    scen["S1 限额（美股仅5%）"] = s1
    s2 = dict(base)
    s2["270042"] = 0.0
    s2["050025"] = 0.0
    scen["S2 完全不可买（留现金）"] = s2
    s3 = dict(s2)
    s3["000216"] += 0.25
    scen["S3 转黄金"] = s3
    s4 = dict(s2)
    for c in ["160119", "011860", "011612"]:
        s4[c] += 0.25 / 3
    scen["S4 转A股三只"] = s4
    s5 = dict(s2)
    for c in ["006989", "006484", "003358"]:
        s5[c] += 0.25 / 3
    scen["S5 转债券三只"] = s5
    s6 = dict(base)
    s6["270042"] = 0.0
    s6["050025"] = 0.25
    scen["S6 只买标普"] = s6
    s7 = dict(base)
    s7["050025"] = 0.0
    s7["270042"] = 0.25
    scen["S7 只买纳指"] = s7

    rows = []
    base_ser = None
    for name, w in scen.items():
        ser = sum(w.get(c, 0.0) * asset_ret[c] for c in asset_ret.columns if c in w)
        ser += (1 - sum(w.values())) * asset_ret[CASH]
        ser = ser.dropna()
        curve = (1 + ser).cumprod()
        mt = metrics(ser, curve, cash_ser)
        mt.update(scenario=name, equity_w=sum(v for k, v in w.items() if k not in (CASH,)),
                  cash_w=1 - sum(w.values()))
        rows.append(mt)
        if name.startswith("S0"):
            base_ser = ser
    qdf = pd.DataFrame(rows)
    qdf["d_cagr_vs_S0"] = qdf["cagr"] - qdf.loc[0, "cagr"]
    qdf["d_sharpe_vs_S0"] = qdf["sharpe"] - qdf.loc[0, "sharpe"]
    qdf.to_csv(OUT / "limit_scenarios.csv", index=False, float_format="%.6f")
    print("\n== 美股限购情景（组合月度） ==")
    print(qdf[["scenario", "cagr", "vol", "mdd", "sharpe", "d_cagr_vs_S0", "d_sharpe_vs_S0"]]
          .to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # 与 S0 的相关性（替代方案是否提供同样的分散）
    corr_rows = []
    for name, w in scen.items():
        ser = sum(w.get(c, 0.0) * asset_ret[c] for c in asset_ret.columns if c in w)
        ser += (1 - sum(w.values())) * asset_ret[CASH]
        corr_rows.append(dict(scenario=name, corr_with_S0=float(ser.corr(base_ser)),
                              vol=float(ser.std() * np.sqrt(12))))
    pd.DataFrame(corr_rows).to_csv(OUT / "limit_scenario_corr.csv", index=False, float_format="%.6f")
    print(pd.DataFrame(corr_rows).to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    # ---- 债券占比敏感性（风险资产内部按 F1 比例） ----
    risk_ratio = {"黄金": .25 / .80, "美股": .25 / .80, "A股": .30 / .80}
    rows = []
    for bw in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
        w = {c: (1 - bw) * risk_ratio[c] for c in RISK}
        w["债券"] = bw
        ser, curve, _ = evaluate(daily_cat, fixed_scheme(w))
        mt = metrics(ser, curve, cash_ser)
        mt.update(bond_w=bw)
        rows.append(mt)
    bwdf = pd.DataFrame(rows)[["bond_w", "cagr", "vol", "mdd", "sharpe", "calmar"]]
    bwdf.to_csv(OUT / "bond_weight_sensitivity.csv", index=False, float_format="%.6f")
    print("\n== 债券占比敏感性（风险资产 金/美/A = 25/25/30 归一） ==")
    print(bwdf.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ---- 类别内产品选择对整体组合的影响（F1 类别权重） ----
    def combo(us, a, bond):
        w = {"000216": 0.25}
        for c in us:
            w[c] = 0.25 / len(us)
        for c in a:
            w[c] = 0.30 / len(a)
        for c in bond:
            w[c] = 0.20 / len(bond)
        ser = sum(w.get(c, 0.0) * asset_ret[c] for c in asset_ret.columns if c in w)
        ser = ser + (1 - sum(w.values())) * asset_ret[CASH]
        curve = (1 + ser).cumprod()
        return metrics(ser, curve, cash_ser)

    rows = []
    for label, us in {"纳指": ["270042"], "标普": ["050025"], "各半": ["270042", "050025"]}.items():
        m = combo(us, ["160119", "011860", "011612"], ["006989", "006484", "003358"])
        rows.append(dict(block="美股", option=label, **m))
    for label, a in {"中证500": ["160119"], "中证1000": ["011860"], "科创50": ["011612"],
                     "三只等权": ["160119", "011860", "011612"],
                     "500+1000": ["160119", "011860"],
                     "500+科创50": ["160119", "011612"]}.items():
        m = combo(["270042", "050025"], a, ["006989", "006484", "003358"])
        rows.append(dict(block="A股", option=label, **m))
    for label, b in {"中短债": ["006989"], "1-3年国开": ["006484"], "7-10年国开": ["003358"],
                     "三只等权": ["006989", "006484", "003358"],
                     "中短+7-10": ["006989", "003358"]}.items():
        m = combo(["270042", "050025"], ["160119", "011860", "011612"], b)
        rows.append(dict(block="债券", option=label, **m))
    cdf = pd.DataFrame(rows)
    cdf.to_csv(OUT / "within_category_portfolio.csv", index=False, float_format="%.6f")
    print("\n== 类别内产品选择对整体组合的影响（F1 类别权重） ==")
    print(cdf[["block", "option", "cagr", "vol", "mdd", "sharpe", "calmar"]]
          .to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ---- 长样本稳健性（2016-10~2024-12，A股只有中证500） ----
    from pool6_data import load_long
    lp = load_long()
    lc = pd.DataFrame({
        "黄金": lp["000216"] / lp["000216"].iloc[0],
        "美股": (lp[["270042", "050025"]] / lp[["270042", "050025"]].iloc[0]).mean(axis=1),
        "A股": lp["160119"] / lp["160119"].iloc[0],
        "债券": lp["003358"] / lp["003358"].iloc[0],
        "现金": lp["000198"] / lp["000198"].iloc[0],
    })
    lcash = month_returns(lc)["现金"]
    rows = []
    f1 = {"黄金": .25, "美股": .25, "A股": .30, "债券": .20}
    for label, w in {
        "F1 原样": f1,
        "移除A股（归一化）": {"黄金": .25 / .70, "美股": .25 / .70, "债券": .20 / .70},
        "移除A股（留现金）": {"黄金": .25, "美股": .25, "A股": 0.0, "债券": .20},
        "移除黄金（归一化）": {"美股": .25 / .75, "A股": .30 / .75, "债券": .20 / .75},
        "移除美股（归一化）": {"黄金": .25 / .75, "A股": .30 / .75, "债券": .20 / .75},
        "100% 中证500": {"A股": 1.0},
        "100% 纳指100": {"美股": 1.0},
        "100% 黄金": {"黄金": 1.0},
    }.items():
        ser, curve, _ = evaluate(lc, fixed_scheme(w), start="2016-11-01", end="2024-12-31", warmup=20)
        m = metrics(ser, curve, lcash)
        if not m:
            print("跳过（无有效区间）", label)
            continue
        m.update(scheme=label)
        rows.append(m)
    ldf = pd.DataFrame(rows)[["scheme", "cagr", "vol", "mdd", "sharpe", "calmar"]]
    ldf.to_csv(OUT / "long_sample_check.csv", index=False, float_format="%.6f")
    print("\n== 长样本稳健性（2016-11~2024-12，A股=中证500） ==")
    print(ldf.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ---- 费用敏感性（含月度再平衡的权重漂移） ----
    def turnover_estimate(rows_w, rets):
        tot = 0.0
        for i in range(1, len(rows_w)):
            dt = rows_w[i][0]
            prev = rows_w[i - 1][3]
            r = rets.loc[dt]
            denom = 1 + sum(prev[c] * r[c] for c in CATS)
            drift = {c: prev[c] * (1 + r[c]) / denom for c in CATS}
            cur = rows_w[i][3]
            tot += sum(abs(cur[c] - drift[c]) for c in CATS) / 2
        years = max(len(rows_w) / 12, 1e-9)
        return tot / years

    rows = []
    for name in ["F1 25/25/30/20", "两层 风险资产逆波动+债20%", "两层 风险资产ERC+债20%",
                 "F2 四类等权", "F5 40/20/30/10（进攻）"]:
        _, _, rws = evaluate(daily_cat, schemes[name])
        turnover = turnover_estimate(rws, month_returns(daily_cat))
        fee_drag = turnover * 0.003
        rows.append(dict(scheme=name, annual_turnover=turnover, fee_drag_est=fee_drag))
    fdf = pd.DataFrame(rows)
    fdf.to_csv(OUT / "fee_sensitivity.csv", index=False, float_format="%.6f")
    print("\n== 费用敏感性（单边约 0.15%，年度换手×0.3%） ==")
    print(fdf.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # 年度收益（稳定性）
    y = {}
    for name, sch in schemes.items():
        ser, curve, _ = evaluate(daily_cat, sch)
        y[name] = (1 + ser).groupby(ser.index.year).prod() - 1
    pd.DataFrame(y).to_csv(OUT / "alloc_yearly.csv", float_format="%.6f")
    print("\n== 年度收益 ==")
    print(pd.DataFrame(y).round(3).to_string())


if __name__ == "__main__":
    main()
