# -*- coding: utf-8 -*-
"""第二轮图表：组合净值、回撤、月度盈亏。"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out_bt"

eq = pd.read_csv(OUT / "equity_2000.csv", index_col=0, parse_dates=True)
pick = ["4_黄金+沪深300", "4_黄金+沪深300_BH",
        "6_黄金+300+债券", "6_黄金+300+债券_BH",
        "7_黄金+300+红利+债券", "7_黄金+300+红利+债券_BH"]
pick = [c for c in pick if c in eq.columns]
ENG = {"4_黄金+沪深300": "Gold+CSI300 timing",
       "4_黄金+沪深300_BH": "Gold+CSI300 buy&hold",
       "6_黄金+300+债券": "Gold+CSI300+Bond timing",
       "6_黄金+300+债券_BH": "Gold+CSI300+Bond buy&hold",
       "7_黄金+300+红利+债券": "4-asset timing",
       "7_黄金+300+红利+债券_BH": "4-asset buy&hold"}

norm = eq[pick] / 2000.0
fig, ax = plt.subplots(figsize=(11, 5.2))
styles = {"4_黄金+沪深300": "-", "4_黄金+沪深300_BH": "--",
          "6_黄金+300+债券": "-", "6_黄金+300+债券_BH": "--",
          "7_黄金+300+红利+债券": "-", "7_黄金+300+红利+债券_BH": "--"}
for c in pick:
    ax.plot(norm.index, norm[c], lw=1.4, ls=styles.get(c, "-"), label=ENG.get(c, c))
ax.set_title("2000 CNY portfolio: timing (solid) vs same-asset buy&hold (dashed)")
ax.set_ylabel("equity / initial")
ax.grid(alpha=.25)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "equity_curves.png", dpi=150)
plt.close(fig)

fig, ax = plt.subplots(figsize=(11, 4.2))
for c in ("7_黄金+300+红利+债券", "7_黄金+300+红利+债券_BH"):
    if c not in eq:
        continue
    dd = eq[c] / eq[c].cummax() - 1
    ax.plot(dd.index, dd * 100, lw=1.3, label=ENG.get(c, c))
ax.set_title("Drawdown: 4-asset timing vs buy&hold")
ax.set_ylabel("drawdown %")
ax.grid(alpha=.25)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "drawdown.png", dpi=150)
plt.close(fig)

# 月度盈亏（人民币），以 4 资产择时组合为例
col = "7_黄金+300+红利+债券"
m = eq[col].resample("ME").last()
prev = m.shift(1).fillna(2000.0)
monthly = pd.DataFrame({"期末市值": m.round(2), "当月盈亏": (m - prev).round(2),
                        "当月收益率": (m / prev - 1).round(4)})
monthly.index = monthly.index.strftime("%Y-%m")
monthly.to_csv(OUT / "monthly_pnl_2000.csv", encoding="utf-8-sig")
print(monthly.tail(12).to_string())
print("saved:", OUT / "equity_curves.png", OUT / "drawdown.png", OUT / "monthly_pnl_2000.csv")
