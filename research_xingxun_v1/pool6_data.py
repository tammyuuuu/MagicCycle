# -*- coding: utf-8 -*-
"""第六轮：资产池数据加载与基础统计。

口径：
- 用总收益指数（含分红再投资）计算收益；
- 对齐到 A 股交易日历（沪深300 净值日期），缺失日用前值填充，最多 10 个交易日；
- 主样本 2021-10 ~ 2026-10（含中证1000、科创50）；
- 长样本 2013-01 ~ 2024-12（不含 2021 年才成立的两只）。
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean"
OUT = ROOT / "out_v2"
OUT.mkdir(exist_ok=True)

NAMES = {
    "000216": "黄金",
    "270042": "纳指100",
    "050025": "标普500",
    "160213": "纳指100备选",
    "161125": "标普500备选",
    "160119": "中证500",
    "011860": "中证1000",
    "011612": "科创50",
    "162413": "中证1000长样本",
    "160706": "沪深300",
    "090010": "中证红利",
    "006989": "中短债",
    "006484": "1-3年国开",
    "003358": "7-10年国开",
    "000198": "货币基金",
}

MAIN_CODES = ["000216", "270042", "050025", "160119", "011860", "011612",
              "006989", "006484", "003358", "000198"]
LONG_CODES = ["000216", "270042", "050025", "160119", "160706", "090010",
              "003358", "000198", "162413"]
MID_CODES = ["000216", "270042", "050025", "160119", "006989", "006484",
             "003358", "000198"]

CATEGORY = {
    "黄金": ["000216"],
    "美股": ["270042", "050025"],
    "A股": ["160119", "011860", "011612"],
    "债券": ["006989", "006484", "003358"],
}
CASH = "000198"


def load_panel(codes, start, end, calendar_code="160706", ffill_limit=10):
    tr = pd.read_csv(CLEAN / "tr_panel.csv", index_col=0, parse_dates=True)
    cal = tr[calendar_code].dropna().index
    cal = cal[(cal >= pd.Timestamp(start)) & (cal <= pd.Timestamp(end))]
    panel = tr.reindex(cal)[codes].ffill(limit=ffill_limit)
    return panel.dropna(how="any")


def load_main():
    return load_panel(MAIN_CODES, "2021-10-01", "2026-10-21")


def load_long():
    return load_panel(LONG_CODES, "2016-10-01", "2024-12-31")


def load_mid():
    return load_panel(MID_CODES, "2019-04-01", "2026-10-21")


def cat_curves(panel, freq="D"):
    """按类别合成等权指数（类别内等权，日度再平衡）。"""
    out = {}
    for cat, codes in CATEGORY.items():
        use = [c for c in codes if c in panel.columns]
        if not use:
            continue
        sub = panel[use]
        out[cat] = (sub / sub.iloc[0]).mean(axis=1)
    out["现金"] = panel[CASH] / panel[CASH].iloc[0]
    df = pd.DataFrame(out)
    if freq == "M":
        df = df.resample("ME").last()
    return df


def metrics_from_curve(curve, cash_curve=None):
    """曲线（净值，等间隔日频）→ 年化与风险指标。"""
    curve = curve.dropna()
    if len(curve) < 2:
        return {}
    days = (curve.index[-1] - curve.index[0]).days
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (365.25 / max(days, 1)) - 1
    ret = curve.pct_change().dropna()
    vol = ret.std() * np.sqrt(252)
    mdd = float((curve / curve.cummax() - 1).min())
    cash_cagr = 0.0
    if cash_curve is not None and len(cash_curve.dropna()) > 1:
        cc = cash_curve.dropna()
        d2 = (cc.index[-1] - cc.index[0]).days
        cash_cagr = (cc.iloc[-1] / cc.iloc[0]) ** (365.25 / max(d2, 1)) - 1
    sharpe = (cagr - cash_cagr) / vol if vol > 0 else float("nan")
    calmar = cagr / abs(mdd) if mdd < 0 else float("nan")
    return dict(cagr=cagr, vol=vol, mdd=mdd, sharpe=sharpe, calmar=calmar, cash_cagr=cash_cagr)


def monthly_returns(panel):
    m = panel.resample("ME").last()
    return m.pct_change(fill_method=None).dropna()


def portfolio_monthly(panel, weight_func, start=None, end=None):
    """月度再平衡组合：权重按月给定，返回月度收益序列与净值。"""
    m = panel.resample("ME").last()
    m = m[(m.index >= pd.Timestamp(start)) if start else m.index >= m.index[0]]
    m = m[(m.index <= pd.Timestamp(end))] if end else m
    rets = m.pct_change().dropna()
    out = []
    for dt, row in rets.iterrows():
        w = weight_func(dt, m)
        w = {k: float(v) for k, v in w.items()}
        total_w = sum(w.values())
        if total_w > 1 + 1e-9:
            raise ValueError("权重超过 100%")
        r = sum(w.get(c, 0.0) * row[c] for c in rets.columns if np.isfinite(row[c]))
        r += (1 - total_w) * row[CASH]
        out.append((dt, r))
    ser = pd.Series(dict(out)).sort_index()
    curve = (1 + ser).cumprod()
    return ser, curve


def curve_metrics_monthly(ser, curve, cash_curve):
    days = (curve.index[-1] - curve.index[0]).days
    years = max(days / 365.25, 1e-9)
    cagr = curve.iloc[-1] ** (1 / years) - 1
    vol = ser.std() * np.sqrt(12)
    mdd = float((curve / curve.cummax() - 1).min())
    cc = cash_curve.dropna()
    cash_cagr = (cc.iloc[-1] / cc.iloc[0]) ** (365.25 / max((cc.index[-1] - cc.index[0]).days, 1)) - 1
    sharpe = (cagr - cash_cagr) / vol if vol > 0 else float("nan")
    return dict(cagr=cagr, vol=vol, mdd=mdd, sharpe=sharpe,
                calmar=cagr / abs(mdd) if mdd < 0 else float("nan"), years=years)


def risk_contrib(panel, weights):
    """日收益协方差下的边际风险贡献与方差贡献占比。"""
    codes = [c for c in weights if c in panel.columns]
    ret = panel[codes].pct_change().dropna()
    cov = ret.cov().values * 252
    w = np.array([weights[c] for c in codes], dtype=float)
    port_var = float(w @ cov @ w)
    mctr = cov @ w
    rc = w * mctr
    share = rc / rc.sum() if rc.sum() > 0 else rc
    return pd.DataFrame(dict(code=codes, name=[NAMES.get(c, c) for c in codes],
                             weight=w, mctr=mctr, risk_share=share,
                             var_share=rc / port_var),
                        ).sort_values("risk_share", ascending=False)


def baseline_weights(panel, cat_w=None):
    """类别权重 → 资产权重（类别内等权）。"""
    cat_w = cat_w or {"黄金": 0.25, "美股": 0.25, "A股": 0.30, "债券": 0.20}
    w = {}
    for cat, target in cat_w.items():
        codes = [c for c in CATEGORY[cat] if c in panel.columns]
        if not codes:
            continue
        for c in codes:
            w[c] = target / len(codes)
    return w
