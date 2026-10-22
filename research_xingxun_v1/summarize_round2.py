# -*- coding: utf-8 -*-
"""把第二轮 CSV 汇总成报告用的 Markdown 表。"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out_bt"
lines = []


def add(s=""):
    lines.append(s)


def fmt(x, pct=True, digits=2):
    if pd.isna(x):
        return "—"
    return f"{x*100:.{digits}f}%" if pct else f"{x:.{digits}f}"


def sh(x):
    return "—" if pd.isna(x) else f"{x:.2f}"


for panel, pname in (("A", "全资产面板（2019-03-08 起）"), ("B", "长期面板（2013-08-22 起）")):
    d = pd.read_csv(OUT / f"grid_{panel}.csv", dtype={"code": str})
    isd = d[(d.segment == "IS") & (d.capital == 2000)]
    oos = d[(d.segment == "OOS") & (d.capital == 2000)]
    pick = pd.read_csv(OUT / "chosen.csv", dtype={"code": str})
    pick = pick[pick.panel == panel].set_index("code")
    add(f"### {pname}：样本内选策略 → 样本外结果")
    add()
    add("| 资产 | IS 持有年化 | IS 最优策略 | IS Sharpe | 选中策略 | 选中 OOS 年化 | 选中 OOS 回撤 | 持有 OOS 年化 | 持有 OOS 回撤 | OOS 最好策略 |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for asset, g in isd.groupby("asset", sort=False):
        h = g[g.strategy == "A_hold"].iloc[0]
        b = g.sort_values("sharpe", ascending=False).iloc[0]
        code = g.code.iloc[0]
        og = oos[oos.code == code]
        oh = og[og.strategy == "A_hold"].iloc[0]
        chosen = pick.loc[code, "strategy"] if code in pick.index else "—"
        oc = og[og.strategy == chosen]
        oc = oc.iloc[0] if len(oc) else None
        ob = og.sort_values("sharpe", ascending=False).iloc[0]
        add(f"| {asset} | {fmt(h.cagr)} | {b.strategy} | {b.sharpe:.2f} | {chosen} | "
            f"{fmt(oc.cagr) if oc is not None else '—'} | {fmt(oc.mdd) if oc is not None else '—'} | "
            f"{fmt(oh.cagr)} | {fmt(oh.mdd)} | {ob.strategy}（{fmt(ob.cagr)}） |")
    add()

    add(f"**{pname}：OOS 各策略年化离散度**（说明策略选择对参数/规则有多敏感）")
    add()
    sens = oos.pivot_table(index="asset", columns="strategy", values="cagr")
    add("| 资产 | 最低 | 中位 | 最高 | 最好 |")
    add("|---|---|---|---|---|")
    for asset, row in sens.iterrows():
        add(f"| {asset} | {fmt(row.min())} | {fmt(row.median())} | {fmt(row.max())} | {row.idxmax()} |")
    add()

# 组合
port = pd.read_csv(OUT / "portfolio.csv")
p = port[port.capital == 2000]
add("### 组合回测（2000 元，2019-03-08 ~ 2026-10-21）")
add()
add("| 组合 | 交易次数 | 累计费用(元) | 年化 | 最大回撤 | Sharpe | Calmar | 样本外年化 | 样本外回撤 | 期末(元) |")
add("|---|---|---|---|---|---|---|---|---|---|")
for r in p.itertuples():
    add(f"| {r.combo} | {r.trades} | {r.fees:.2f} | {fmt(r.full_cagr)} | {fmt(r.full_mdd)} | "
        f"{sh(r.full_sharpe)} | {sh(r.full_calmar)} | {fmt(r.oos_cagr)} | {fmt(r.oos_mdd)} | {r.end_value:.0f} |")
add()

cap = port.pivot_table(index="combo", columns="capital", values="full_cagr")
add("**资金规模敏感性（年化，2000/5000/10000 元）**")
add()
add("| 组合 | 2000 | 5000 | 10000 |")
add("|---|---|---|---|")
for combo, row in cap.iterrows():
    add(f"| {combo} | {fmt(row[2000])} | {fmt(row[5000])} | {fmt(row[10000])} |")
add()

fee = pd.read_csv(OUT / "fee_sensitivity.csv")
piv = fee.pivot_table(index="combo", columns="fee_mult", values="cagr")
add("**费率敏感性（年化）**：费率 ×0.5 / ×1（页面价）/ ×2")
add()
add("| 组合 | ×0.5 | ×1 | ×2 | 最大差异 |")
add("|---|---|---|---|---|")
for combo, row in piv.iterrows():
    add(f"| {combo} | {fmt(row[0.5])} | {fmt(row[1.0])} | {fmt(row[2.0])} | "
        f"{(row[0.5]-row[2.0])*100:.2f}pct |")
add()

pb = pd.read_csv(OUT / "portfolio_B.csv")
add("### 长期面板组合复核（2013-08-22 ~ 2026-10-21，2000 元）")
add()
add("| 组合 | 方式 | 交易次数 | 费用(元) | 年化 | 最大回撤 | Sharpe | 2020 后年化 | 2020 后回撤 | 2020 后 Sharpe |")
add("|---|---|---|---|---|---|---|---|---|---|")
for r in pb.itertuples():
    add(f"| {r.combo} | {'择时' if r.kind=='timing' else '买入持有'} | {r.trades} | {r.fees:.1f} | "
        f"{fmt(r.full_cagr)} | {fmt(r.full_mdd)} | {sh(r.full_sharpe)} | {fmt(r.oos_cagr)} | "
        f"{fmt(r.oos_mdd)} | {sh(r.oos_sharpe)} |")
add()

vt = pd.read_csv(OUT / "band_voltarget.csv")
add("### 关键策略明细（OOS，2000 元）")
add()
key = ["A_hold", "B_ma120", "C_pullback5", "D_donchian120_40", "E_vol15",
       "F_gold_heat", "F_bond_momentum120", "F_ma200_val"]
for panel, pname in (("A", "2019 起"), ("B", "2013 起")):
    d = pd.read_csv(OUT / f"grid_{panel}.csv", dtype={"code": str})
    o = d[(d.segment == "OOS") & (d.capital == 2000)]
    add(f"**{pname}：OOS 年化 / 最大回撤 / Sharpe**")
    add()
    add("| 资产 | " + " | ".join(key) + " |")
    add("|---" * (len(key) + 1) + "|")
    for asset, g in o.groupby("asset", sort=False):
        cells = []
        for k in key:
            row = g[g.strategy == k]
            cells.append(f"{fmt(row.cagr.iloc[0])} / {fmt(row.mdd.iloc[0])} / {row.sharpe.iloc[0]:.2f}"
                         if len(row) else "—")
        add(f"| {asset} | " + " | ".join(cells) + " |")
    add()

add("### 波动率目标策略的换手与成本（E 类，2% 带宽）")
add()
add("| 面板 | 资产 | 交易带宽 | 交易次数 | 次/年 | 费用(元) | 年化 | 最大回撤 |")
add("|---|---|---|---|---|---|---|---|")
for r in vt[vt.band == 0.02].itertuples():
    add(f"| {r.panel} | {r.asset} | 2% | {r.trades} | {r.trades_per_year:.1f} | {r.fees:.1f} | {fmt(r.cagr)} | {fmt(r.mdd)} |")
add()

(OUT / "summary_tables.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
