# -*- coding: utf-8 -*-
"""生成网站用的 portfolio_data.json（只读数据，不含用户资产）。

数据来源：research_xingxun_v1/clean 下的场外基金净值与费率快照。
输出：docs/portfolio_data.json
"""
from pathlib import Path
import ast
import json
import datetime as dt

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "research_xingxun_v1" / "clean"
OUT = ROOT / "docs" / "portfolio_data.json"

ASSETS = ["000216", "160706", "090010", "006484"]
CASH = "000198"
LABEL = {"000216": "黄金", "160706": "沪深300", "090010": "中证红利", "006484": "1-3年国开"}
BOND_CAP = 0.40
VOL_WINDOW = 120


def load_nav(code):
    d = pd.read_csv(CLEAN / f"{code}.csv", parse_dates=["date"]).set_index("date")
    return d


def inverse_vol(tr, dates, i, cap=BOND_CAP, floor=0.05, window=VOL_WINDOW):
    codes = list(tr.columns)
    vols = {}
    for c in codes:
        seg = tr[c].to_numpy(float)[max(0, i - window):i + 1]
        r = np.diff(seg) / seg[:-1]
        vols[c] = max(float(np.std(r, ddof=1)) * np.sqrt(252), 1e-6)
    inv = {c: 1.0 / vols[c] for c in codes}
    s = sum(inv.values())
    w = {c: inv[c] / s for c in codes}
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
        sr = sum(w[c] for c in rest)
        for c in rest:
            w[c] += excess * w[c] / sr
    for c in codes:
        w[c] = max(w[c], floor)
    s = sum(w.values())
    return {c: w[c] / s for c in codes}


def main():
    meta = pd.read_csv(CLEAN / "fund_meta.csv", dtype={"code": str}).set_index("code")
    navs = {c: load_nav(c) for c in ASSETS + [CASH]}
    tr = pd.DataFrame({c: navs[c]["tr"] for c in ASSETS}).dropna(how="any")
    dates = tr.index

    funds = {}
    nav_dates = []
    for c in ASSETS + [CASH]:
        d = navs[c]
        last = d.dropna(subset=["nav"]).iloc[-1] if c != CASH else d.iloc[-1]
        nav = float(last["nav"]) if c != CASH else 1.0
        r = meta.loc[c]
        funds[c] = dict(
            code=c, name=r["name"], label=LABEL.get(c, "货币基金"),
            nav=nav, nav_date=str(last.name.date()),
            buy_pct=float(r["current_rate_pct"]) if pd.notna(r["current_rate_pct"]) else 0.0,
            redeem_tiers=ast.literal_eval(r["redeem_fee_tiers"]) if isinstance(r["redeem_fee_tiers"], str) else [],
            status=r["purchase_status"] if isinstance(r["purchase_status"], str) else None,
            limit=r["daily_purchase_limit"] if isinstance(r["daily_purchase_limit"], str) else None,
            confirm=r["buy_confirm"] if isinstance(r["buy_confirm"], str) else "T+1",
            settle_days=1 if c == CASH else 2,
            asset_class="cash" if c == CASH else "risk",
        )
        nav_dates.append(funds[c]["nav_date"])

    w = inverse_vol(tr, dates, len(dates) - 1)
    hist = {}
    for c in ASSETS:
        d = navs[c].dropna(subset=["nav"]).tail(900)
        hist[c] = [[str(idx.date()), round(float(row["nav"]), 6), round(float(row["tr"]), 6)]
                   for idx, row in d.iterrows()]
    payload = dict(
        generated_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        data_date=str(dates[-1].date()),
        newest_nav_date=max(nav_dates),
        oldest_nav_date=min(nav_dates),
        mode="simulation",
        feature_flag=True,
        allocation=dict(
            id="invvol4_cap40_v1",
            name="四资产逆波动率（债券上限 40%）",
            method="inverse_vol_120",
            bond_cap=BOND_CAP,
            vol_window=VOL_WINDOW,
            rebalance="monthly",
            codes=ASSETS,
            weights={c: round(w[c], 6) for c in ASSETS},
            as_of=str(dates[-1].date()),
            note="权重由 120 日实现波动率决定，不含协方差；月度再平衡。",
        ),
        signals={c: dict(strategy="A_hold", version="hold_v1", target=1.0,
                         signal_date=str(dates[-1].date())) for c in ASSETS},
        funds=funds,
        cash_fund=CASH,
        nav_history=hist,
        disclaimer="模拟模式：所有金额仅为研究建议，不会自动下单；历史回测不代表未来收益。",
    )
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(data_date=payload["data_date"], weights=payload["allocation"]["weights"]),
                     ensure_ascii=False, indent=2))
    print("saved ->", OUT)


if __name__ == "__main__":
    main()
