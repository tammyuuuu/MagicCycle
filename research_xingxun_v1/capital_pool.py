# -*- coding: utf-8 -*-
"""第三轮：统一资金池与买卖金额计算（纯函数，不下单、不联网）。

概念严格区分：
    总金融资产 total_assets
    投资资金池目标 pool_target = total_assets × ratio
    投资资金池实际 pool_value = 池内现金 + 持仓市值 + 在途资金
    允许新增投入 new_allowed = max(0, pool_target − pool_value)
    可花费现金 spendable = 池内现金 + min(new_allowed, 外部可用现金)

规则（与用户资金管理规则一致）：
1. 池子超过目标（总资产下降导致）→ 暂停新增，不强制卖出；
2. 内部调仓不算新增投入；
3. 新增投入不得超过可用现金；
4. 当日卖出款 T+settle 到账，不能用于当日买入；
5. 买入金额不足 10 元不下单；
6. 基金暂停申购/限购/价格缺失 → 不生成买入建议，并写明原因。
"""
from dataclasses import dataclass, field
from pathlib import Path
import math

import pandas as pd

from cost_model import buy_rate, redeem_rate

ROOT = Path(__file__).resolve().parent


@dataclass
class Position:
    code: str
    name: str
    value: float                 # 当前市值（元）
    hold_days: int | None = None  # 加权持有天数；未知则按保守费率估算
    sellable: bool = True


@dataclass
class FundInfo:
    code: str
    name: str
    price: float | None
    status: str | None
    buy_tiers: list | None
    redeem_tiers: list | None
    buy_confirm: str = "T+1"
    sell_settle_days: int = 2
    daily_limit: float | None = None    # 元；None = 页面未标注


def _limit_yuan(text):
    import re
    if not isinstance(text, str):
        return None
    m = re.search(r"([\d.]+)\s*(亿元|万元|元)", text)
    if not m:
        return None
    v = float(m.group(1))
    return v * {"亿元": 1e8, "万元": 1e4, "元": 1}[m.group(2)]


def load_funds(meta_path: Path = ROOT / "clean" / "fund_meta.csv"):
    import ast
    m = pd.read_csv(meta_path, dtype={"code": str}).set_index("code")
    out = {}
    for code, r in m.iterrows():
        bt = ast.literal_eval(r["purchase_fee_tiers"]) if isinstance(r["purchase_fee_tiers"], str) else None
        rt = ast.literal_eval(r["redeem_fee_tiers"]) if isinstance(r["redeem_fee_tiers"], str) else None
        out[code] = FundInfo(code=code, name=r["name"], price=None,
                             status=r["purchase_status"], buy_tiers=bt, redeem_tiers=rt,
                             buy_confirm=r["buy_confirm"] if isinstance(r["buy_confirm"], str) else "T+1",
                             sell_settle_days=1 if code == "000198" else 2,
                             daily_limit=_limit_yuan(r["daily_purchase_limit"]))
    return out


def pool_budget(total_assets, pool_value, external_cash, ratio=0.10):
    target = float(total_assets) * float(ratio)
    new_allowed = max(0.0, target - float(pool_value))
    used = min(new_allowed, max(0.0, float(external_cash)))
    return dict(total_assets=float(total_assets), ratio=float(ratio),
                pool_target=target, pool_value=float(pool_value),
                over_target=max(0.0, float(pool_value) - target),
                new_allowed=new_allowed, external_cash=max(0.0, float(external_cash)),
                new_used=used)


def _fee_buy(amount, tiers, mult=1.0):
    rate = buy_rate(tiers, amount) / 100.0 * mult
    fee = amount - amount / (1 + rate)
    return fee, rate


def _fee_sell(value, tiers, days, mult=1.0):
    if days is None:
        # 持有期未知：按 7 天–1 年档的保守值；没有该档则取最高非惩罚档
        known = [t["original_pct"] for t in (tiers or [])
                 if "大于等于7天" in t["condition"] and t["original_pct"] is not None]
        pct = known[0] if known else 0.5
        return value * pct / 100.0 * mult, pct, True
    pct = redeem_rate(tiers, days) * mult
    return value * pct / 100.0, pct, False


def plan_day(total_assets, pool_cash, positions, targets, funds, external_cash=0.0,
             receivable=0.0, ratio=0.10, min_amount=10.0, buy_band=0.01,
             sell_band=0.02, priority="pro_rata", fee_mult=1.0, scores=None):
    """生成当日执行计划。

    targets : {code: 目标权重 0..1}，sum <= 1，未分配部分留现金
    scores  : priority='signal' 时的优先级分数（越大越先买）
    返回 dict(rows, totals, budget, warnings)
    """
    pos_map = {p.code: p for p in positions}
    pool_value = float(pool_cash) + sum(p.value for p in positions) + float(receivable)
    budget = pool_budget(total_assets, pool_value, external_cash, ratio)
    if sum(targets.values()) > 1.0 + 1e-9:
        raise ValueError("目标权重合计不能超过 100%")

    investable = pool_value + budget["new_used"]
    spendable = float(pool_cash) + budget["new_used"]
    warnings = []
    if budget["over_target"] > 0:
        warnings.append(f"资金池已超过目标 {budget['over_target']:.2f} 元：暂停新增投入，不强制卖出。")

    rows = []
    buy_intents, sell_intents = [], []
    sell_fees = 0.0

    # 未给出目标权重的持仓：保持不动，但必须显式提示
    for p in positions:
        if p.code not in targets:
            rows.append(dict(code=p.code, name=p.name, weight=None, current=p.value,
                             target=p.value, delta_theoretical=0.0, price=None,
                             action="未配置", amount=0.0, shares_est=None, fee_est=0.0,
                             post_value=p.value, post_weight=None, executable=False,
                             reason="未给出目标权重，保持不动（不计入新增投入）"))

    for code, w in targets.items():
        info = funds.get(code)
        pos = pos_map.get(code)
        current = float(pos.value) if pos else 0.0
        target_value = float(w) * investable
        delta = target_value - current
        row = dict(code=code, name=(info.name if info else (pos.name if pos else code)),
                   weight=float(w), current=current, target=target_value,
                   delta_theoretical=delta, price=(info.price if info else None),
                   action="无操作", amount=0.0, shares_est=None, fee_est=0.0,
                   post_value=current, post_weight=None,
                   executable=False, reason="")
        if info is None:
            row["reason"] = "缺少基金信息"
            rows.append(row)
            continue
        if info.price is None or not math.isfinite(info.price) or info.price <= 0:
            row["reason"] = "缺少有效净值，不生成交易"
            rows.append(row)
            continue
        if info.status and "暂停" in str(info.status):
            row["reason"] = f"基金状态为“{info.status}”，不可申购"
            rows.append(row)
            continue

        if delta >= max(min_amount, buy_band * investable):
            frac = 0.0
            if priority == "signal" and scores:
                frac = max(0.0, float(scores.get(code, 0.0)))
            buy_intents.append(dict(code=code, delta=delta, frac=frac, row=row))
        elif delta <= -max(min_amount, sell_band * investable):
            if pos and pos.sellable:
                sell_intents.append(dict(code=code, delta=-delta, row=row, pos=pos))
            else:
                row["reason"] = "需要减仓，但当前无可卖份额（T+1 确认中）"
        else:
            row["reason"] = "偏离在交易带内，不操作"
        rows.append(row)

    # ---- 卖出：只记录，款项 T+settle 到账，不用于今日买入 ----
    for it in sell_intents:
        r, pos, info = it["row"], it["pos"], funds[it["code"]]
        amount = min(it["delta"], pos.value)
        fee, pct, assumed = _fee_sell(amount, info.redeem_tiers, pos.hold_days, fee_mult)
        r.update(action="卖出", amount=amount, fee_est=fee,
                 shares_est=amount / info.price, post_value=pos.value - amount,
                 executable=True,
                 reason=(f"目标 {r['weight']*100:.0f}%，超出 "
                         f"{abs(it['delta'])/max(1e-9, investable)*100:.1f}% 权益；"
                         f"赎回到账 T+{info.sell_settle_days}"
                         + ("；持有期未知，费率按保守估计" if assumed else "")))
        r["redeem_rate_pct"] = pct
        sell_fees += fee
        spendable += 0  # 明确：当日不增加可用现金

    # ---- 买入：受可花费现金约束，按预设优先级分配 ----
    total_want = sum(it["delta"] for it in buy_intents)
    if total_want > spendable and total_want > 0:
        if priority == "signal" and any(it["frac"] > 0 for it in buy_intents):
            weight_sum = sum(it["delta"] * it["frac"] for it in buy_intents)
            for it in buy_intents:
                it["alloc"] = spendable * it["delta"] * it["frac"] / weight_sum if weight_sum > 0 else 0.0
        else:
            for it in buy_intents:
                it["alloc"] = spendable * it["delta"] / total_want
        warnings.append(f"可用现金 {spendable:.2f} 元不足以覆盖全部买点，按 {priority} 分配。")
    else:
        for it in buy_intents:
            it["alloc"] = it["delta"]

    for it in buy_intents:
        r, info = it["row"], funds[it["code"]]
        amount = math.floor(min(it["alloc"], spendable) * 100) / 100
        if amount < min_amount:
            r["reason"] = f"分配金额 {amount:.2f} 元低于最小申购 {min_amount:.0f} 元"
            continue
        if info.daily_limit is not None and amount > info.daily_limit:
            amount = math.floor(info.daily_limit * 100) / 100
            r["reason"] = f"受日累计申购限额 {info.daily_limit:.0f} 元限制，已截断；"
        fee, rate = _fee_buy(amount, info.buy_tiers, fee_mult)
        shares = (amount - fee) / info.price
        spendable -= amount
        r.update(action="买入", amount=amount, fee_est=fee, shares_est=shares,
                 post_value=r["current"] + (amount - fee), executable=True,
                 reason=(r["reason"] + f"目标 {r['weight']*100:.0f}%，缺口 {it['delta']:.2f} 元；"
                         f"申购费 {rate*100:.2f}%，{info.buy_confirm} 确认份额"))

    # 汇总
    buys = sum(r["amount"] for r in rows if r["action"] == "买入")
    sells = sum(r["amount"] for r in rows if r["action"] == "卖出")
    fees = sum(r["fee_est"] for r in rows)
    post_cash = float(pool_cash) + budget["new_used"] - buys
    post_invested = sum(r["post_value"] for r in rows)
    post_pool = post_cash + post_invested + float(receivable) + sells - sell_fees
    for r in rows:
        r["post_weight"] = r["post_value"] / post_pool if post_pool > 0 else None

    if post_cash < -1e-6:
        raise AssertionError("资金校验失败：现金为负")
    if buys > float(pool_cash) + budget["new_used"] + 1e-6:
        raise AssertionError("资金校验失败：买入超过可用现金")

    return dict(rows=rows, budget=budget,
                totals=dict(buys=buys, sells=sells, fees=fees,
                            spendable_before=float(pool_cash) + budget["new_used"],
                            post_cash=post_cash, post_invested=post_invested,
                            post_pool=post_pool,
                            post_new_allowed=max(0.0, budget["pool_target"] - post_pool)),
                warnings=warnings)


def describe(result):
    b = result["budget"]
    t = result["totals"]
    out = []
    out.append(f"总金融资产 {b['total_assets']:.2f} → 资金池目标 {b['pool_target']:.2f}"
               f"（{b['ratio']*100:.0f}%）；当前池子 {b['pool_value']:.2f}")
    out.append(f"允许新增 {b['new_allowed']:.2f}；外部可用现金 {b['external_cash']:.2f}；"
               f"本次实际新增 {b['new_used']:.2f}")
    for w in result["warnings"]:
        out.append("[提示] " + w)
    out.append(f"{'代码':<8}{'名称':<16}{'现市值':>9}{'目标':>9}{'动作':>6}{'金额':>9}{'费用':>7}  说明")
    for r in result["rows"]:
        out.append(f"{r['code']:<8}{r['name'][:14]:<16}{r['current']:>9.2f}{r['target']:>9.2f}"
                   f"{r['action']:>6}{r['amount']:>9.2f}{r['fee_est']:>7.2f}  {r['reason']}")
    out.append(f"合计：买入 {t['buys']:.2f}，卖出 {t['sells']:.2f}，费用 {t['fees']:.2f}，"
               f"交易后现金 {t['post_cash']:.2f}，交易后池子 {t['post_pool']:.2f}")
    return "\n".join(out)
