# -*- coding: utf-8 -*-
"""带再平衡的场外组合引擎（第四轮）。

与第二轮的区别：第二轮是"每个资产独立账户、资金上限固定"；
本引擎是"一个现金池 + 按目标权重再平衡"，用于比较不同配置方案。

执行约束：
- t 日收盘计算目标权重（只用 ≤t 的数据），t+1 卖出，卖出款 t+1+settle 到账；
- 买入分两批：t+1 用池内已有现金，t+1+settle 用卖出回款；
- 买入按金额申购，费用按真实阶梯；赎回按 FIFO 持有天数；
- 单笔调仓低于 max(10 元, band × 组合权益) 不执行。
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cost_model import buy_rate, redeem_rate


def is_rebalance_day(dates, i, rule="M"):
    if i == 0:
        return True
    prev, cur = dates[i - 1], dates[i]
    if rule == "M":
        return (prev.year, prev.month) != (cur.year, cur.month)
    if rule == "Q":
        return cur.month in (1, 4, 7, 10) and (prev.year, prev.month) != (cur.year, cur.month)
    if rule == "2Q":
        return cur.month in (1, 7) and (prev.year, prev.month) != (cur.year, cur.month)
    raise ValueError(rule)


def run_portfolio(prices, dates, cash_ret, weights, capital, fees, start, end,
                  rebalance="M", band=0.02, min_amount=10.0, settle=2,
                  fee_mult=1.0):
    """weights: dict（固定权重）或 callable(i)->dict（时变权重，需只用过去数据）。"""
    codes = list(prices)
    n = len(dates)
    cash = float(capital)
    lots = {c: [] for c in codes}          # {shares, idx, avail}
    receivables = []                       # (due_idx, amount)
    sells, buys = [], []                   # 待执行订单
    equity = np.full(n, np.nan)
    fees_total = 0.0
    trades = []

    def px(c, i):
        return prices[c][i]

    for i in range(start, end + 1):
        cash *= 1.0 + (cash_ret[i] if np.isfinite(cash_ret[i]) else 0.0)

        if receivables:
            due = [r for r in receivables if r[0] <= i]
            cash += sum(r[1] for r in due)
            receivables = [r for r in receivables if r[0] > i]

        # ---- 执行卖出（t+1） ----
        for od in [o for o in sells if o["exec"] == i]:
            c, want = od["code"], od["shares"]
            gross = fee_sum = sold = 0.0
            for lot in lots[c]:
                if want <= 1e-9:
                    break
                if lot["avail"] > i or lot["shares"] <= 0:
                    continue
                q = min(lot["shares"], want)
                days = (dates[i] - dates[lot["idx"]]).days
                rate = redeem_rate(fees[c].redeem_tiers, days) / 100.0 * fee_mult
                gross += q * px(c, i)
                fee_sum += q * px(c, i) * rate
                lot["shares"] -= q
                want -= q
                sold += q
            lots[c] = [l for l in lots[c] if l["shares"] > 1e-9]
            if sold > 0:
                receivables.append((i + settle, gross - fee_sum))
                fees_total += fee_sum
                trades.append(dict(date=dates[i], code=c, side="sell", amount=gross - fee_sum,
                                   shares=sold, fee=fee_sum))
        sells = [o for o in sells if o["exec"] != i]

        # ---- 执行买入（t+1 或 t+1+settle） ----
        for od in [o for o in buys if o["exec"] == i]:
            c = od["code"]
            amount = min(od["amount"], cash)
            if amount >= min_amount and px(c, i) > 0:
                rate = buy_rate(fees[c].buy_tiers, amount) / 100.0 * fee_mult
                shares = amount / (1 + rate) / px(c, i)
                fee_paid = amount - shares * px(c, i)
                cash -= amount
                fees_total += fee_paid
                lots[c].append(dict(shares=shares, idx=i, avail=i + 1))
                trades.append(dict(date=dates[i], code=c, side="buy", amount=amount,
                                   shares=shares, fee=fee_paid))
        buys = [o for o in buys if o["exec"] != i]

        value = {c: sum(l["shares"] for l in lots[c]) * px(c, i) for c in codes}
        eq = cash + sum(value.values()) + sum(a for _, a in receivables)
        equity[i] = eq

        if i >= end or not is_rebalance_day(dates, i, rebalance):
            continue

        w = weights(i) if callable(weights) else weights
        w = {c: float(w.get(c, 0.0)) for c in codes}
        if sum(w.values()) > 1 + 1e-9:
            raise ValueError("权重合计超过 100%")
        total = eq
        thr = max(min_amount, band * total)

        gaps = {}
        for c in codes:
            target = w[c] * total
            delta = target - value[c]
            if delta < -thr:
                avail = sum(l["shares"] for l in lots[c] if l["avail"] <= i)
                if avail > 0:
                    q = min(-delta / px(c, i), avail)
                    if q * px(c, i) >= min_amount:
                        sells.append(dict(code=c, shares=q, exec=i + 1))
            elif delta > thr and w[c] > 0:
                gaps[c] = delta

        if not gaps:
            continue
        # 第一批：用池内已有现金，按缺口比例
        available_cash = max(0.0, cash)
        total_gap = sum(gaps.values())
        first = min(available_cash, total_gap)
        for c, g in gaps.items():
            amt = first * g / total_gap
            if amt >= min_amount:
                buys.append(dict(code=c, amount=amt, exec=i + 1))
        # 第二批：等到卖出回款到账后再买
        rest = total_gap - first
        if rest > min_amount and any(o["exec"] == i + 1 for o in sells):
            for c, g in gaps.items():
                amt = rest * g / total_gap
                if amt >= min_amount:
                    buys.append(dict(code=c, amount=amt, exec=i + 1 + settle))

    if cash < -1e-6:
        raise AssertionError("组合现金为负")
    return equity, fees_total, trades


def portfolio_metrics(eq, cash_ret, start, end):
    eqs = pd.Series(eq[start:end + 1]).dropna()
    ret = eqs.pct_change(fill_method=None).dropna()
    cr = pd.Series(cash_ret[start:end + 1]).iloc[1:]
    yrs = len(eqs) / 252
    cagr = (eqs.iloc[-1] / eqs.iloc[0]) ** (1 / yrs) - 1
    mdd = float((eqs / eqs.cummax() - 1).min())
    ex = ret.to_numpy() - cr.to_numpy()
    sharpe = ex.mean() / ex.std(ddof=1) * np.sqrt(252) if ex.std(ddof=1) > 0 else np.nan
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe,
                calmar=cagr / abs(mdd) if mdd < 0 else np.nan,
                vol=ret.std(ddof=1) * np.sqrt(252),
                total=eqs.iloc[-1] / eqs.iloc[0] - 1,
                end_value=float(eqs.iloc[-1]))
