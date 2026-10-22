# -*- coding: utf-8 -*-
"""场外基金回测引擎（第二轮）。

与网站现有 `dca.py` 的关键区别：
1. 信号只用 t 日收盘及之前的数据；订单在 t 日收盘后提交，按 **t+1 日未知净值** 成交。
2. 卖出款按 T+settle 到账，到账前不能用于买入（无同日资金复用）。
3. 申购费按真实金额阶梯，赎回费按 FIFO 持有天数阶梯；7 天内赎回 1.5% 会真实扣掉。
4. 空仓现金按货币基金日收益计息。
5. 最小申购 10 元，金额按 0.01 元取整；不生成无法执行的买入。

注意：价格序列使用"含分红再投资的总收益指数"作为份额净值代理。
这等价于"现金分红全部再投资"，与真实分红现金流略有差异，但在总收益口径下一致。
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cost_model import buy_rate, redeem_rate


@dataclass
class FundFee:
    code: str
    buy_tiers: list
    redeem_tiers: list


def load_fee(meta_row) -> FundFee:
    import ast
    bt = ast.literal_eval(meta_row.purchase_fee_tiers) if isinstance(meta_row.purchase_fee_tiers, str) else None
    rt = ast.literal_eval(meta_row.redeem_fee_tiers) if isinstance(meta_row.redeem_fee_tiers, str) else None
    code = str(getattr(meta_row, "name", "") or getattr(meta_row, "code", ""))
    return FundFee(code, bt, rt)


def weekly_decision_mask(dates: pd.DatetimeIndex) -> np.ndarray:
    """每周第一个交易日决策（用当日收盘），次日净值成交。"""
    iso = dates.isocalendar()
    key = iso["year"].to_numpy() * 100 + iso["week"].to_numpy()
    return np.r_[True, key[1:] != key[:-1]]


def run_sleeve(prices, target, dates, cash_ret, capital, fee: FundFee,
               start, end, decision=None, settle=2, min_amount=10.0,
               fee_mult=1.0, band=0.02, trade_log=None):
    """单资产独立账户。

    prices   : 总收益指数（份额净值代理）
    target   : 0..1 目标仓位，已对齐 dates；仅在 decision=True 的日子读取
    cash_ret : 货币基金日收益
    """
    prices = np.asarray(prices, float)
    target = np.asarray(target, float)
    n = len(dates)
    decision = weekly_decision_mask(dates) if decision is None else decision
    cash = float(capital)
    lots = []                     # {shares, idx, avail}
    pending = None
    receivables = []
    equity = np.full(n, np.nan)
    fees_total = 0.0
    trades = []

    for i in range(start, end + 1):
        cash *= 1.0 + (cash_ret[i] if np.isfinite(cash_ret[i]) else 0.0)

        if receivables:
            due = [r for r in receivables if r[0] <= i]
            cash += sum(r[1] for r in due)
            receivables = [r for r in receivables if r[0] > i]

        # ---- 执行昨日收盘提交的订单，成交价 = 今日净值（下单时未知） ----
        if pending is not None:
            px = prices[i]
            if pending["side"] == "buy":
                amount = min(pending["amount"], cash)
                if amount >= min_amount and px > 0:
                    rate = buy_rate(fee.buy_tiers, amount) / 100.0 * fee_mult
                    shares = amount / (1.0 + rate) / px
                    fee_paid = amount - shares * px
                    cash -= amount
                    fees_total += fee_paid
                    lots.append(dict(shares=shares, idx=i, avail=i + 1))
                    trades.append(dict(date=dates[i], side="buy", amount=amount,
                                       nav=px, shares=shares, fee=fee_paid,
                                       signal_date=dates[i - 1]))
            else:
                want = pending["shares"]
                sold = gross = fee_paid = 0.0
                for lot in lots:
                    if want <= 1e-9:
                        break
                    if lot["avail"] > i or lot["shares"] <= 0:
                        continue
                    q = min(lot["shares"], want)
                    hold_days = (dates[i] - dates[lot["idx"]]).days
                    rate = redeem_rate(fee.redeem_tiers, hold_days) / 100.0 * fee_mult
                    gross += q * px
                    fee_paid += q * px * rate
                    lot["shares"] -= q
                    want -= q
                    sold += q
                lots = [l for l in lots if l["shares"] > 1e-9]
                if sold > 0:
                    receivables.append((i + settle, gross - fee_paid))
                    fees_total += fee_paid
                    trades.append(dict(date=dates[i], side="sell", amount=gross - fee_paid,
                                       nav=px, shares=sold, fee=fee_paid,
                                       signal_date=dates[i - 1]))
            pending = None

        value = sum(l["shares"] * prices[i] for l in lots)
        eq = cash + value + sum(a for _, a in receivables)
        equity[i] = eq

        # ---- 收盘后决策，下一交易日执行 ----
        if i < end and decision[i]:
            t = target[i]
            if np.isfinite(t):
                desired = t * eq
                delta = desired - value
                threshold = max(min_amount, band * eq)
                if delta > threshold and cash >= min_amount:
                    pending = dict(side="buy", amount=min(delta, cash))
                elif delta < -threshold:
                    avail = sum(l["shares"] for l in lots if l["avail"] <= i)
                    if avail > 1e-9:
                        pending = dict(side="sell", shares=min(-delta / prices[i], avail))

    if trade_log is not None:
        trade_log.extend(trades)
    return equity, fees_total, trades


def metrics(equity, cash_ret, start, end):
    eq = pd.Series(equity[start:end + 1], index=np.arange(start, end + 1)).dropna()
    if len(eq) < 2:
        return dict(cagr=np.nan, mdd=np.nan, sharpe=np.nan, calmar=np.nan,
                    vol=np.nan, total=np.nan, end_value=np.nan)
    ret = eq.pct_change(fill_method=None).dropna()
    cr = pd.Series(cash_ret[start:end + 1]).iloc[1:]
    yrs = len(eq) / 252.0
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    mdd = float((eq / eq.cummax() - 1).min())
    ex = ret.to_numpy() - cr.to_numpy()
    sharpe = ex.mean() / ex.std(ddof=1) * np.sqrt(252) if ex.std(ddof=1) > 0 else np.nan
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe,
                calmar=cagr / abs(mdd) if mdd < 0 else np.nan,
                vol=ret.std(ddof=1) * np.sqrt(252),
                total=eq.iloc[-1] / eq.iloc[0] - 1,
                end_value=float(eq.iloc[-1]))
