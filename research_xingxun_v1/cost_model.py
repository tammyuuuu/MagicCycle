# -*- coding: utf-8 -*-
"""成本模型：把真实费率阶梯换算成“单笔成本 / 年化拖累”。

只使用 clean/fund_meta.csv 里从基金页面解析出的费率；
口径为天天基金页面展示的“前端申购优惠费率”，支付宝/微信渠道费率未核实。
"""
from pathlib import Path
import ast
import re

import pandas as pd

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean"
OUT = ROOT / "out_corr"
OUT.mkdir(exist_ok=True)


def buy_rate(tiers, amount=2000.0):
    if not tiers:
        return 0.0
    for t in tiers:
        cond = t["condition"]
        if cond.startswith("小于"):
            limit = float("".join(ch for ch in cond if ch.isdigit() or ch == "."))
            unit = "万" if "万" in cond else ""
            limit = limit * 10000 if unit == "万" else limit
            if amount < limit:
                return t["discount_pct"] or 0.0
    return 0.0


def _to_days(value, unit):
    return value * {"天": 1, "个月": 30, "年": 365}[unit]


def _parse_cond(cond):
    """把“大于等于7天，小于365天”/“小于1年”等条件转成 (lo, lo_inc, hi, hi_inc)，单位天。"""
    lo, lo_inc = 0.0, True
    hi, hi_inc = float("inf"), True
    m = re.search(r"大于等于([\d.]+)(天|个月|年)", cond)
    if m:
        lo, lo_inc = _to_days(float(m.group(1)), m.group(2)), True
    m = re.search(r"小于等于([\d.]+)(天|个月|年)", cond)
    if m:
        hi, hi_inc = _to_days(float(m.group(1)), m.group(2)), True
    else:
        m = re.search(r"小于([\d.]+)(天|个月|年)", cond)
        if m:
            hi, hi_inc = _to_days(float(m.group(1)), m.group(2)), False
    return lo, lo_inc, hi, hi_inc


def redeem_rate(tiers, days):
    """返回赎回费率（百分数，如 0.5 表示 0.5%）。"""
    if not tiers:
        return 0.0
    for t in tiers:
        lo, lo_inc, hi, hi_inc = _parse_cond(t["condition"])
        if (days >= lo if lo_inc else days > lo) and (days <= hi if hi_inc else days < hi):
            return t["original_pct"] or 0.0
    return 0.0


def main():
    meta = pd.read_csv(CLEAN / "fund_meta.csv", dtype={"code": str})
    holds = [7, 30, 90, 180, 365, 730]
    amounts = [100, 200, 400, 500, 1000, 2000]
    rows, impact = [], []
    for r in meta.itertuples():
        tiers = ast.literal_eval(r.purchase_fee_tiers) if isinstance(r.purchase_fee_tiers, str) else None
        rtiers = ast.literal_eval(r.redeem_fee_tiers) if isinstance(r.redeem_fee_tiers, str) else None
        b = buy_rate(tiers)
        row = dict(code=r.code, name=r.name, buy_pct=b, status=r.purchase_status,
                   daily_limit=r.daily_purchase_limit, confirm=r.buy_confirm)
        for days in holds:
            red = redeem_rate(rtiers, days)
            row[f"redeem_{days}d_pct"] = red
            row[f"roundtrip_{days}d_pct"] = b + red
            if days == 365:
                for amt in amounts:
                    impact.append(dict(code=r.code, name=r.name, amount=amt,
                                       buy_yuan=round(amt * b / 100, 2),
                                       sell_yuan=round(amt * red / 100, 2),
                                       roundtrip_yuan=round(amt * (b + red) / 100, 2),
                                       roundtrip_pct=round(b + red, 3)))
        rows.append(row)
    fees = pd.DataFrame(rows)
    imp = pd.DataFrame(impact)
    fees.to_csv(CLEAN / "fee_table.csv", index=False, encoding="utf-8-sig")
    imp.to_csv(OUT / "cost_impact.csv", index=False, encoding="utf-8-sig")

    # 交易频率敏感性：一年 k 次完整来回，按持有 365 天口径的成本拖累
    freq = []
    for r in fees.itertuples():
        for k in (1, 2, 4, 6, 12):
            freq.append(dict(code=r.code, name=r.name, roundtrips_per_year=k,
                             annual_cost_pct=round(r.roundtrip_365d_pct * k, 3)))
    pd.DataFrame(freq).to_csv(OUT / "cost_frequency.csv", index=False, encoding="utf-8-sig")
    print(fees.to_string(index=False))
    print("\n--- 2000 元单次完整来回成本 ---")
    print(imp[imp.amount == 2000].to_string(index=False))


if __name__ == "__main__":
    main()
