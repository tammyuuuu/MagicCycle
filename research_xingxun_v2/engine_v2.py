# -*- coding: utf-8 -*-
"""统一日度研究引擎 daily_causal_v3（不写真实账户）。

新增：
1. blocked(i, code)：模拟暂停申购/限额，买单作废、资金留现金；
2. 记录每日现金、持仓市值、因限购未成交金额；
3. 其余执行约束与第四轮一致：
   - 决策按 information_lag 截断，下一可交易日未知净值成交；
   - 卖出款 T+settle 到账，不能当日复用；
   - 真实申购阶梯费、FIFO 赎回费（<7 天 1.5%）；
   - 最小申购 10 元，单笔低于 max(10, band×权益) 不调仓。

现金/应收分别输出；确认与到账可按基金配置。information_lag 默认2个
代理交易日是缺少历史披露时间戳时的模型假设，不是实盘可得性认证。
"""
import numpy as np

from cost_model import buy_rate, redeem_rate
from weight_engine import is_rebalance_day


def run_portfolio_v2(prices, dates, cash_ret, weights, capital, fees, start, end,
                     rebalance="M", band=0.02, min_amount=10.0, settle=2,
                     fee_mult=1.0, blocked=None, blocked_codes=None, once=False,
                     information_lag=2, confirm_days=None, tradable=None,
                     weight_rule=None, entry_plan=None):
    codes = list(prices)
    n = len(dates)
    if not dates.is_monotonic_increasing or dates.has_duplicates:
        raise ValueError('交易日期必须严格递增')
    if not 0 <= start <= end < n or capital < 0 or not np.isfinite(capital):
        raise ValueError('区间或本金无效')
    if not isinstance(information_lag, int) or information_lag < 0:
        raise ValueError('信息滞后必须为非负整数')
    for c in codes:
        if len(prices[c]) != n or np.any(~np.isfinite(prices[c][start:end+1])) or np.any(prices[c][start:end+1] <= 0):
            raise ValueError('净值缺失或无效: ' + c)
        if c not in fees: raise ValueError('缺少费率: ' + c)
    def delay(spec, c, default):
        v = spec.get(c, default) if isinstance(spec, dict) else (default if spec is None else spec)
        if not isinstance(v, int) or v < 1: raise ValueError('确认/到账滞后必须至少1个交易日')
        return v
    for c in codes:
        delay(settle,c,2); delay(confirm_days,c,2)
    if len(cash_ret) != n or np.any(~np.isfinite(cash_ret[start:end+1])) or np.any(cash_ret[start:end+1] <= -1):
        raise ValueError('现金收益无效')
    cash = float(capital)
    lots = {c: [] for c in codes}
    receivables = []
    sells, buys = [], []
    equity = np.full(n, np.nan)
    cash_trace = np.full(n, np.nan)
    held_trace = np.full(n, np.nan)
    fees_total = 0.0
    trades = []
    blocked_total = 0.0
    receivable_trace = np.full(n, np.nan)
    signals = []
    entry_phase = entry_plan is not None
    entry_done, entry_deployed = None, 0.0

    def can_trade(c,i):
        return tradable is None or bool(tradable[c][i])

    def px(c, i):
        return prices[c][i]

    for i in range(start, end + 1):
        if i > start:
            cash *= 1.0 + cash_ret[i]

        if receivables:
            due = [r for r in receivables if r[0] <= i]
            cash += sum(r[1] for r in due)
            receivables = [r for r in receivables if r[0] > i]

        # 执行卖出
        for od in [o for o in sells if o["exec"] <= i and can_trade(o['code'],i)]:
            c, want = od["code"], od["shares"]
            gross = fee_sum = sold = 0.0
            days_sum = 0.0
            for lot in lots[c]:
                if want <= 1e-9:
                    break
                if lot["avail"] > i or lot["shares"] <= 0:
                    continue
                q = min(lot["shares"], want)
                days = (dates[i] - dates[lot["avail"]]).days
                rate = redeem_rate(fees[c].redeem_tiers, days) / 100.0 * fee_mult
                gross += q * px(c, i)
                fee_sum += q * px(c, i) * rate
                days_sum += q * days
                lot["shares"] -= q
                want -= q
                sold += q
            lots[c] = [l for l in lots[c] if l["shares"] > 1e-9]
            if sold > 0:
                due_idx = i + delay(settle,c,2)
                receivables.append((due_idx, gross - fee_sum))
                fees_total += fee_sum
                trades.append(dict(date=dates[i], code=c, side="sell", amount=gross - fee_sum,
                                   shares=sold, fee=fee_sum,
                                   hold_days=days_sum / sold if sold > 0 else 0.0,
                                   decision_date=dates[od['decision']], known_through=dates[od['known']],
                                   settlement_date=dates[due_idx] if due_idx<n else None))
        sells = [o for o in sells if not(o["exec"] <= i and can_trade(o['code'],i))]

        # 执行买入（可被限购阻断）
        for od in [o for o in buys if o["exec"] <= i and can_trade(o['code'],i)]:
            c = od["code"]
            if od.get('funded_by_sale') and cash+1e-8<od['amount'] and (receivables or sells):
                od['exec']=i+1
                continue
            amount = min(od["amount"], cash)
            if (blocked is not None and blocked(i, c)) or c in (blocked_codes or []):
                blocked_total += max(0.0, od["amount"])
                continue
            if amount >= min_amount and px(c, i) > 0:
                rate = buy_rate(fees[c].buy_tiers, amount) / 100.0 * fee_mult
                shares = amount / (1 + rate) / px(c, i)
                fee_paid = amount - shares * px(c, i)
                cash -= amount
                fees_total += fee_paid
                avail_idx=i+delay(confirm_days,c,2)
                lots[c].append(dict(shares=shares, idx=i, avail=avail_idx))
                if od.get('entry'): entry_deployed += amount
                trades.append(dict(date=dates[i], code=c, side="buy", amount=amount,
                                   shares=shares, fee=fee_paid, hold_days=0,
                                   decision_date=dates[od['decision']], known_through=dates[od['known']],
                                   confirmation_date=dates[avail_idx] if avail_idx<n else None))
        buys = [o for o in buys if not(o["exec"] <= i and can_trade(o['code'],i))]

        value = {c: sum(l["shares"] for l in lots[c]) * px(c, i) for c in codes}
        eq = cash + sum(value.values()) + sum(a for _, a in receivables)
        equity[i] = eq
        cash_trace[i] = cash
        receivable_trace[i] = sum(a for _, a in receivables)
        held_trace[i] = sum(value.values())
        if cash < -1e-8: raise AssertionError('现金透支')

        if i >= end:
            continue
        known = i - information_lag
        if known < 0 or any(not np.isfinite(px(c,known)) or px(c,known)<=0 for c in codes):
            continue
        if entry_phase:
            for c,amt in entry_plan(known,cash):
                if c not in prices or not np.isfinite(amt) or amt < 0: raise ValueError('建仓订单无效')
                if amt >= min_amount: buys.append(dict(code=c,amount=amt,exec=i+1,decision=i,known=known,entry=True))
            if entry_plan.done:
                entry_phase=False; entry_done=i+1
            continue
        if once and signals:
            continue
        if not (not signals or is_rebalance_day(dates, i, rebalance)):
            continue

        # New rules receive only an isolated, truncated history; no future arrays.
        w = weight_rule({c: prices[c][:known+1].copy() for c in codes}, dates[:known+1].copy()) if weight_rule else (weights(known) if callable(weights) else weights)
        if any(not np.isfinite(v) or v < 0 for v in w.values()) or any(c not in codes and v != 0 for c,v in w.items()):
            raise ValueError('权重无效或含未知资产')
        w = {c: float(w.get(c, 0.0)) for c in codes}
        if sum(w.values()) > 1 + 1e-9:
            raise ValueError("权重合计超过 100%")
        known_value = {c: sum(l['shares'] for l in lots[c]) * px(c,known) for c in codes}
        total = cash + sum(known_value.values()) + sum(a for _,a in receivables)
        thr = max(min_amount, band * total)
        signals.append(dict(date=dates[i],known_through=dates[known],weights=w.copy()))

        gaps = {}
        for c in codes:
            target = w[c] * total
            delta = target - known_value[c]
            if delta < -thr:
                avail = sum(l["shares"] for l in lots[c] if l["avail"] <= i)
                if avail > 0:
                    q = min(-delta / px(c, known), avail)
                    if q * px(c, known) >= min_amount:
                        sells.append(dict(code=c, shares=q, exec=i + 1,decision=i,known=known))
            elif delta > thr and w[c] > 0:
                gaps[c] = delta

        if not gaps:
            continue
        available_cash = max(0.0, cash)
        total_gap = sum(gaps.values())
        first = min(available_cash, total_gap)
        for c, g in gaps.items():
            amt = first * g / total_gap
            if amt >= min_amount:
                buys.append(dict(code=c, amount=amt, exec=i + 1,decision=i,known=known))
        rest = total_gap - first
        if rest > min_amount and any(o["exec"] == i + 1 for o in sells):
            for c, g in gaps.items():
                amt = rest * g / total_gap
                if amt >= min_amount:
                    # Wait for all scheduled proceeds; cash is still checked on execution.
                    wait=max(delay(settle,o['code'],2) for o in sells if o['exec']==i+1)
                    buys.append(dict(code=c, amount=amt, exec=i + 1 + wait,decision=i,known=known,funded_by_sale=True))

    if cash < -1e-6:
        raise AssertionError("组合现金为负")
    return dict(equity=equity, cash=cash_trace, held=held_trace,receivable=receivable_trace,
                fees=fees_total, trades=trades, blocked=blocked_total,signals=signals,
                entry_done=entry_done,entry_deployed=entry_deployed,
                engine_version='daily_causal_v3',mode='backtest',information_lag=information_lag)
