# -*- coding: utf-8 -*-
"""V2.1：多起点结果统计、配对比较、热力图与前沿。"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "out_v21"
g = pd.read_csv(OUT / "v21_grid.csv")
g["start"] = pd.to_datetime(g["start"])
g["start_year"] = g["start"].dt.year
g["ym"] = g["start"].dt.strftime("%Y-%m")
KEY = ["combo", "horizon", "start"]
METHOD_ORDER = ["once", "staged3", "staged6", "staged12", "pb8"]


def q10(x):
    return float(np.percentile(x, 10))


def summarize(df):
    rows = []
    for (combo, h, method), sub in df.groupby(["combo", "horizon", "method"]):
        rows.append(dict(
            combo=combo, horizon=h, method=method, n=len(sub),
            med_cagr=sub.cagr.median(), mean_cagr=sub.cagr.mean(),
            p10_cagr=q10(sub.cagr), worst_final=sub.final.min(),
            med_final=sub.final.median(), med_mdd=sub.mdd.median(),
            p10_mdd=q10(sub.mdd), med_fees=sub.fees.median(),
            med_util=sub.util.median(), med_entry_days=sub.entry_days.median(),
            med_entry_mdd=sub.entry_mdd.median(),
        ))
    return pd.DataFrame(rows)


summ = summarize(g)
summ.to_csv(OUT / "v21_summary.csv", index=False, float_format="%.6f")
print("== 汇总（3 年期） ==")
print(summ[summ.horizon == 3].round(4).to_string(index=False))

# 配对比较：以 once 为基准
rows = []
for (combo, h), sub in g.groupby(["combo", "horizon"]):
    p_c = sub.pivot_table(index="start", columns="method", values="cagr")
    p_m = sub.pivot_table(index="start", columns="method", values="mdd")
    p_f = sub.pivot_table(index="start", columns="method", values="final")
    for method in METHOD_ORDER:
        if method not in p_c.columns:
            continue
        dc = (p_c[method] - p_c["once"]).dropna()
        dm = (p_m[method] - p_m["once"]).dropna()
        dfin = (p_f[method] - p_f["once"]).dropna()
        rows.append(dict(combo=combo, horizon=h, method=method, n=len(dc),
                         win_cagr=float((dc > 0).mean()),
                         win_mdd=float((dm > 0).mean()),
                         win_both=float(((dc > 0) & (dm > 0)).mean()),
                         med_d_cagr=float(dc.median()), mean_d_cagr=float(dc.mean()),
                         med_d_mdd=float(dm.median()),
                         med_d_final=float(dfin.median()),
                         p10_d_cagr=float(q10(dc))))
paired = pd.DataFrame(rows)
paired.to_csv(OUT / "v21_paired.csv", index=False, float_format="%.6f")
print("\n== 配对比较（相对一次性） ==")
print(paired[paired.horizon == 3].round(4).to_string(index=False))

# 年份热力图（3 年期，各方法 median CAGR）
yrows = []
for (combo, method, year), sub in g[g.horizon == 3].groupby(["combo", "method", "start_year"]):
    yrows.append(dict(combo=combo, method=method, year=year, n=len(sub),
                      med_cagr=sub.cagr.median(), med_mdd=sub.mdd.median()))
ydf = pd.DataFrame(yrows)
ydf.to_csv(OUT / "v21_yearly.csv", index=False, float_format="%.6f")

# 低重叠：每年 1 月起点
lo = g[g.start.dt.month == 1]
lo_summ = summarize(lo)
lo_summ.to_csv(OUT / "v21_low_overlap.csv", index=False, float_format="%.6f")
print("\n== 低重叠（每年 1 月起点，3 年期） ==")
print(lo_summ[lo_summ.horizon == 3].round(4).to_string(index=False))

# 分阶段
rows = []
for (combo, h, phase), sub in g.assign(phase=np.where(g.train, "训练起点 2020-07~2022-12", "测试起点 2023-01 起")).groupby(["combo", "horizon", "phase"]):
    for method, s2 in sub.groupby("method"):
        rows.append(dict(combo=combo, horizon=h, phase=phase, method=method, n=len(s2),
                         med_cagr=s2.cagr.median(), med_mdd=s2.mdd.median(),
                         med_final=s2.final.median()))
ph = pd.DataFrame(rows)
ph.to_csv(OUT / "v21_phase.csv", index=False, float_format="%.6f")
print("\n== 分阶段（3 年期） ==")
print(ph[ph.horizon == 3].round(4).to_string(index=False))

# 前沿：3 年期各组合/方法
fig, ax = plt.subplots(figsize=(9, 6))
for combo, sub in summ[summ.horizon == 3].groupby("combo"):
    sub = sub.set_index("method").reindex([m for m in METHOD_ORDER if m in sub.method.values])
    ax.plot(-sub.med_mdd * 100, sub.med_cagr * 100, marker="o", label=combo, linewidth=1.2)
    for m, r in sub.iterrows():
        ax.annotate(m, (-r.med_mdd * 100, r.med_cagr * 100), fontsize=7, alpha=.7)
ax.set_xlabel("Median MDD (%)")
ax.set_ylabel("Median CAGR (%)")
ax.set_title("V2.1 entry methods, 3-year horizon, all start months")
ax.grid(alpha=.3)
ax.legend(fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "frontier_h3.png", dpi=130)

# 热力图：水平 = 方法，垂直 = 起点年份（组合 B，3 年）
piv = ydf[ydf.combo == "B 债/金/纳 各1/3"].pivot(index="year", columns="method", values="med_cagr")
piv = piv.reindex(columns=[m for m in METHOD_ORDER if m in piv.columns])
fig, ax = plt.subplots(figsize=(7, 5))
im = ax.imshow(piv.values * 100, aspect="auto", cmap="RdYlGn")
ax.set_xticks(range(len(piv.columns)))
ax.set_xticklabels(piv.columns)
ax.set_yticks(range(len(piv.index)))
ax.set_yticklabels(piv.index)
for i in range(piv.shape[0]):
    for j in range(piv.shape[1]):
        v = piv.values[i, j]
        if np.isfinite(v):
            ax.text(j, i, f"{v*100:.1f}", ha="center", va="center", fontsize=8)
ax.set_title("B combo: median CAGR (%) by start year, 3-year horizon")
fig.colorbar(im, ax=ax, label="CAGR %")
fig.tight_layout()
fig.savefig(OUT / "heatmap_B_h3.png", dpi=130)

# 最差 10% 起点（3 年，组合 B / EQ）
for combo in ["B 债/金/纳 各1/3", "EQ 四只等权"]:
    sub = g[(g.combo == combo) & (g.horizon == 3)].copy()
    worst = sub.sort_values("cagr").groupby("method").head(6)
    print(f"\n== 最差起点（{combo}，3 年，每方法前 6 个） ==")
    print(worst[["method", "start", "cagr", "mdd", "final"]].round(4).to_string(index=False))

print("\n图与表已写入", OUT)
