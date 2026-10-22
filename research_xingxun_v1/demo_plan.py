# -*- coding: utf-8 -*-
"""资金池演示：用最新净值生成"今天买多少"的示例计划。

注意：策略选择来自第二轮/第三轮的规则，
      这里的数字是演示，不是投资建议，也不会下单。
"""
from pathlib import Path

import pandas as pd

import strategy_lib as SL
from allocation_study import inverse_vol, FOUR
from capital_pool import load_funds, Position, plan_day, describe
from run_round2 import build_panel, make_targets, FULL, LABEL

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out_wf"

# 推荐配置：四资产逆波动率加权，债券权重上限 40%（参数稳定性最好的一档）
BOND_CAP = 0.40
STRATEGY = {"000216": "A_hold", "160706": "A_hold", "090010": "A_hold",
            "006484": "D_donchian120_40"}
VERSIONS = {"A_hold": "hold_v1", "D_donchian120_40": "donchian_120_40_v1"}


def latest_targets():
    tr, dates, cash, fees, pe = build_panel(FULL, "2019-03-08")
    out = {}
    for code, sname in STRATEGY.items():
        t = make_targets(tr[code], code, pe)[sname]
        out[code] = float(t.reindex(dates).fillna(0.0).iloc[-1])
    prices = {c: tr[c].to_numpy(float) for c in FOUR}
    weights = inverse_vol(prices, FOUR, len(dates) - 1, 120, BOND_CAP)
    return out, tr, weights


def main():
    tmap, tr, WEIGHTS = latest_targets()
    prices = {c: float(tr[c].iloc[-1]) for c in WEIGHTS}
    data_date = str(tr.index[-1].date())
    funds = load_funds()
    for c, p in prices.items():
        funds[c].price = p

    lines = [f"数据日期 {data_date}",
             "推荐配置（四资产逆波动率，债券上限 40%）：" +
             "，".join(f"{LABEL[c]} {WEIGHTS[c]:.1%}" for c in WEIGHTS),
             "策略最新目标仓位：" + "，".join(f"{LABEL[c]} {tmap[c]:.0%}" for c in WEIGHTS),
             ""]

    snap = pd.DataFrame([dict(date=data_date, code=c, asset=LABEL[c],
                              strategy=STRATEGY[c], strategy_version=VERSIONS[STRATEGY[c]],
                              target_position=tmap[c], weight=WEIGHTS[c],
                              target_weight=WEIGHTS[c] * tmap[c], price=prices[c])
                         for c in WEIGHTS])
    snap.to_csv(OUT / "signals_latest.csv", index=False, encoding="utf-8-sig")

    # 情景 1：首次建仓，池内已有 2000 元现金
    r1 = plan_day(total_assets=20000, pool_cash=2000, positions=[],
                  targets={c: WEIGHTS[c] * tmap[c] for c in WEIGHTS}, funds=funds)
    lines += ["【情景 1】总资产 20000，投资池 2000 元现金，首次建仓", describe(r1), ""]

    # 情景 2：运行一段时间后，触发调仓；池子略超 10%，无新增资金
    positions = [
        Position("000216", "华安黄金ETF联接A", 780, hold_days=420),
        Position("160706", "嘉实沪深300ETF联接A", 640, hold_days=210),
        Position("160119", "南方中证500ETF联接(LOF)A", 300, hold_days=90),
        Position("006484", "广发中债1-3年国开债指数A", 280, hold_days=60),
    ]
    r2 = plan_day(total_assets=20000, pool_cash=100, positions=positions,
                  targets={c: WEIGHTS[c] * tmap[c] for c in WEIGHTS}, funds=funds,
                  external_cash=0)
    lines += ["【情景 2】池内现金 100，持仓合计 2000，总资产 20000（池子超 10% 目标）",
              describe(r2), ""]

    # 情景 3：多个买点但钱不够（按缺口比例分配）
    funds3 = {c: load_funds()[c] for c in WEIGHTS}
    for c in WEIGHTS:
        funds3[c].price = prices[c]
    r3 = plan_day(total_assets=20000, pool_cash=300, positions=[],
                  targets={c: WEIGHTS[c] for c in WEIGHTS}, funds=funds3,
                  external_cash=0)
    lines += ["【情景 3】只有 300 元可用，多个买点同时出现（按缺口比例分配）",
              describe(r3), ""]

    text = "\n".join(lines)
    (OUT / "plan_demo.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
