# -*- coding: utf-8 -*-
"""第六轮：相关性、风险来源、边际贡献、类别内选择。"""
import numpy as np
import pandas as pd

from pool6_data import (CATEGORY, CASH, NAMES, OUT, baseline_weights, cat_curves,
                        curve_metrics_monthly, load_long, load_main, load_mid,
                        metrics_from_curve, monthly_returns, portfolio_monthly,
                        risk_contrib)

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)


def describe(panel, tag):
    rows = []
    cash = panel[CASH]
    for c in panel.columns:
        m = metrics_from_curve(panel[c], cash)
        m.update(code=c, name=NAMES.get(c, c), years=len(panel) / 252)
        rows.append(m)
    df = pd.DataFrame(rows)[["code", "name", "cagr", "vol", "mdd", "sharpe", "calmar", "years"]]
    df.to_csv(OUT / f"desc_{tag}.csv", index=False, float_format="%.6f")
    return df


def corr_tables(panel, tag):
    d = panel.pct_change(fill_method=None).dropna()
    w = panel.resample("W-FRI").last().pct_change(fill_method=None).dropna()
    m = monthly_returns(panel)
    d.corr().to_csv(OUT / f"corr_daily_{tag}.csv", float_format="%.4f")
    w.corr().to_csv(OUT / f"corr_weekly_{tag}.csv", float_format="%.4f")
    m.corr().to_csv(OUT / f"corr_monthly_{tag}.csv", float_format="%.4f")
    return d.corr(), w.corr(), m.corr()


def rolling_corr(panel, pairs, window=250):
    ret = panel.pct_change(fill_method=None).dropna()
    rows = []
    for a, b in pairs:
        if a not in ret.columns or b not in ret.columns:
            continue
        s = ret[a].rolling(window).corr(ret[b]).dropna()
        if s.empty:
            continue
        rows.append(dict(pair=f"{NAMES[a]}-{NAMES[b]}", window=window,
                         min=s.min(), p25=s.quantile(.25), median=s.median(),
                         p75=s.quantile(.75), max=s.max(),
                         pct_negative=float((s < 0).mean())))
    return pd.DataFrame(rows)


def crisis_table(panel, episodes):
    w = baseline_weights(panel)
    ser, curve = portfolio_monthly(panel, lambda dt, m: w)
    rows = []
    for name, s, e in episodes:
        sub = panel[(panel.index >= s) & (panel.index <= e)]
        if len(sub) < 5:
            continue
        months = ser[(ser.index > pd.Timestamp(s)) & (ser.index <= pd.Timestamp(e))]
        port = float((1 + months).prod() - 1) if len(months) else np.nan
        row = dict(episode=name, start=s, end=e, portfolio=port)
        for c in panel.columns:
            row[NAMES.get(c, c)] = float(sub[c].iloc[-1] / sub[c].iloc[0] - 1)
        rows.append(row)
    return pd.DataFrame(rows)


def marginal_contribution(panel, base_w, tag):
    cash = panel[CASH]
    base_ser, base_curve = portfolio_monthly(panel, lambda dt, m: base_w)
    base = curve_metrics_monthly(base_ser, base_curve, cash)
    rows = [dict(action="基准组合", removed="", **base)]
    codes = [c for c in base_w if base_w[c] > 0]
    for code in codes:
        w2 = {c: v for c, v in base_w.items() if c != code}
        s = sum(w2.values())
        w2 = {c: v / s for c, v in w2.items()} if s > 0 else {}
        ser, cur = portfolio_monthly(panel, lambda dt, m, w2=w2: w2)
        mt = curve_metrics_monthly(ser, cur, cash)
        rows.append(dict(action=f"移除{NAMES.get(code, code)}", removed=code,
                         **mt,
                         d_cagr=mt["cagr"] - base["cagr"],
                         d_mdd=mt["mdd"] - base["mdd"],
                         d_sharpe=mt["sharpe"] - base["sharpe"]))
    # 留现金版本（不替换）
    for code in codes:
        w2 = dict(base_w)
        w2[code] = 0.0
        ser, cur = portfolio_monthly(panel, lambda dt, m, w2=w2: w2)
        mt = curve_metrics_monthly(ser, cur, cash)
        rows.append(dict(action=f"不买{NAMES.get(code, code)}（留现金）", removed=code,
                         **mt,
                         d_cagr=mt["cagr"] - base["cagr"],
                         d_mdd=mt["mdd"] - base["mdd"],
                         d_sharpe=mt["sharpe"] - base["sharpe"]))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"marginal_{tag}.csv", index=False, float_format="%.6f")
    return base, df


def within_category(panel, tag):
    rows = []
    cash = panel[CASH]
    groups = {
        "美股": [("纳指100", ["270042"]), ("标普500", ["050025"]),
                 ("各半", ["270042", "050025"])],
        "A股": [("中证500", ["160119"]), ("中证1000", ["011860"]),
                ("科创50", ["011612"]), ("三只等权", ["160119", "011860", "011612"]),
                ("500+1000", ["160119", "011860"]), ("500+科创50", ["160119", "011612"])],
        "债券": [("中短债", ["006989"]), ("1-3年国开", ["006484"]),
                 ("7-10年国开", ["003358"]), ("三只等权", ["006989", "006484", "003358"]),
                 ("中短+7-10", ["006989", "003358"]), ("中短+1-3", ["006989", "006484"])],
        "黄金": [("黄金", ["000216"])],
    }
    for cat, items in groups.items():
        for label, codes in items:
            codes = [c for c in codes if c in panel.columns]
            if not codes:
                continue
            curve = (panel[codes] / panel[codes].iloc[0]).mean(axis=1)
            m = metrics_from_curve(curve, cash)
            m.update(category=cat, option=label, codes=",".join(codes))
            rows.append(m)
    df = pd.DataFrame(rows)[["category", "option", "codes", "cagr", "vol", "mdd", "sharpe", "calmar"]]
    df.to_csv(OUT / f"within_category_{tag}.csv", index=False, float_format="%.6f")
    return df


def main():
    main_p = load_main()
    long_p = load_long()
    mid_p = load_mid()
    print("主样本", main_p.index.min().date(), main_p.index.max().date(), main_p.shape)
    print("长样本", long_p.index.min().date(), long_p.index.max().date(), long_p.shape)
    print("中样本", mid_p.index.min().date(), mid_p.index.max().date(), mid_p.shape)

    d_main = describe(main_p, "main")
    d_long = describe(long_p, "long")
    print("\n== 主样本单资产 ==")
    print(d_main.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("\n== 长样本单资产 ==")
    print(d_long.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    cd, cw, cm = corr_tables(main_p, "main")
    corr_tables(long_p, "long")
    print("\n== 主样本月度相关 ==")
    print(cm.round(3).to_string())
    print("\n== 主样本日度相关 ==")
    print(cd.round(3).to_string())

    cc = cat_curves(main_p, freq="M").pct_change().dropna().corr()
    cc.to_csv(OUT / "corr_category_monthly.csv", float_format="%.4f")
    print("\n== 类别层月度相关 ==")
    print(cc.round(3).to_string())

    pairs = [("000216", "270042"), ("000216", "050025"), ("160119", "270042"),
             ("160119", "050025"), ("011860", "270042"), ("011612", "270042"),
             ("160119", "006484"), ("270042", "006484"), ("000216", "006484"),
             ("006484", "003358"), ("006989", "003358"), ("160119", "011860"),
             ("160119", "011612"), ("011860", "011612")]
    rc = rolling_corr(main_p, pairs)
    rc.to_csv(OUT / "rolling_corr_main.csv", index=False, float_format="%.4f")
    print("\n== 250 日滚动相关（主样本） ==")
    print(rc.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    episodes = [
        ("2022 全年（股债双杀）", "2022-01-01", "2022-12-31"),
        ("2024-01~02 A股小盘流动性", "2024-01-01", "2024-02-29"),
        ("2025-04 关税冲击", "2025-04-01", "2025-04-30"),
        ("2024-07~09 A股下跌", "2024-07-01", "2024-09-30"),
    ]
    cr = crisis_table(main_p, episodes)
    cr.to_csv(OUT / "crisis_main.csv", index=False, float_format="%.4f")
    print("\n== 危机区间收益 ==")
    print(cr.round(3).to_string(index=False))

    base_w = baseline_weights(main_p)
    rk = risk_contrib(main_p, base_w)
    rk.to_csv(OUT / "risk_contrib_main.csv", index=False, float_format="%.6f")
    print("\n== 基准组合风险贡献（类别 25/25/30/20，类别内等权） ==")
    print(rk.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    base, mg = marginal_contribution(main_p, base_w, "main")
    print("\n== 边际贡献（归一化替换 / 留现金） ==")
    print(mg[["action", "removed", "cagr", "mdd", "sharpe", "d_cagr", "d_mdd", "d_sharpe"]]
          .to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("基准:", {k: round(v, 4) for k, v in base.items() if k != "years"})

    wc = within_category(main_p, "main")
    print("\n== 类别内选择（主样本） ==")
    print(wc.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    wc_mid = within_category(mid_p, "mid")
    print("\n== 类别内选择（中样本 2019-04 起，含两种债券） ==")
    print(wc_mid.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # 中证1000：长样本基金与新基金在重叠区间的一致性
    ov = main_p[["011860"]].join(long_p[["162413"]], how="inner").dropna()
    if len(ov) > 250:
        r = ov.pct_change(fill_method=None).dropna()
        print("\n== 中证1000 两只产品重叠区间 ==")
        print("重叠", ov.index.min().date(), ov.index.max().date(), "日相关",
              round(float(r["011860"].corr(r["162413"])), 3),
              "年化差", round(float((ov["011860"].iloc[-1] / ov["011860"].iloc[0]) ** (252 / len(ov)) - 1
                                - ((ov["162413"].iloc[-1] / ov["162413"].iloc[0]) ** (252 / len(ov)) - 1)), 4))


if __name__ == "__main__":
    main()
