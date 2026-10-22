# -*- coding: utf-8 -*-
"""V2.1 建仓实验引擎：建仓阶段按订单投入，完成后按目标权重复平衡。

与 V2.0 一致：t 收盘决策、t+1 未知净值成交、卖出款 T+settle 到账、
真实申购/赎回阶梯费、最小申购 10 元、不允许负现金。
"""
import numpy as np

from cost_model import buy_rate, redeem_rate
from weight_engine import is_rebalance_day


def run_episode(prices, dates, cash_ret, weights, fees, capital, start, end,
                entry_plan, rebalance="M", band=0.02, min_amount=10.0, settle=2,
                **execution):
    """One execution implementation for both entry and portfolio experiments."""
    from engine_v2 import run_portfolio_v2
    return run_portfolio_v2(prices, dates, cash_ret, weights, capital, fees,
                            start, end, rebalance=rebalance, band=band,
                            min_amount=min_amount, settle=settle,
                            entry_plan=entry_plan, **execution)


class OnceEntry:
    def __init__(self, weights, capital, start):
        self.weights, self.capital, self.start = weights, capital, start
        self.done = False

    def __call__(self, i, cash):
        if self.done or i < self.start:
            return []
        self.done = True
        return [(c, self.capital * w) for c, w in self.weights.items() if w > 0]


class StagedEntry:
    """固定等额分批：每批 capital/months，按基金权重拆分。"""

    def __init__(self, weights, capital, months, dates, start):
        self.weights, self.capital, self.months = weights, capital, months
        self.y0, self.m0 = dates[start].year, dates[start].month
        self.dates, self.start = dates, start
        self.k_done = set()
        self.done = False

    def __call__(self, i, cash):
        if self.done:
            return []
        k = (self.dates[i].year - self.y0) * 12 + (self.dates[i].month - self.m0)
        if k >= self.months:
            self.done = True
            return []
        if k in self.k_done:
            return []
        self.k_done.add(k)
        amt = self.capital / self.months
        if len(self.k_done) >= self.months:
            self.done = True
        return [(c, amt * w) for c, w in self.weights.items() if w > 0]


class PullbackEntry:
    """回调分批：每只基金独立触发，最多 batches 批，deadline 后强制补齐。"""

    def __init__(self, prices, dates, weights, capital, start, window=60,
                 threshold=0.05, batches=3, deadline_months=6):
        self.prices, self.dates, self.weights = prices, dates, weights
        self.capital, self.window = capital, window
        self.threshold, self.batches = threshold, batches
        self.y0, self.m0 = dates[start].year, dates[start].month
        self.deadline = deadline_months
        self.bought = {c: 0 for c in weights}
        self.done = False

    def __call__(self, i, cash):
        if self.done:
            return []
        k = (self.dates[i].year - self.y0) * 12 + (self.dates[i].month - self.m0)
        force = k >= self.deadline
        out = []
        for c, w in self.weights.items():
            if w <= 0 or self.bought.get(c, 0) >= self.batches:
                continue
            if force:
                remain = self.batches - self.bought[c]
                out.append((c, self.capital * w * remain / self.batches))
                self.bought[c] = self.batches
                continue
            arr = self.prices[c][max(0, i - self.window + 1):i + 1]
            hi = float(arr.max())
            if hi > 0 and arr[-1] / hi - 1 <= -self.threshold:
                out.append((c, self.capital * w / self.batches))
                self.bought[c] += 1
        if all(self.bought.get(c, 0) >= self.batches for c, w in self.weights.items() if w > 0):
            self.done = True
        return out
