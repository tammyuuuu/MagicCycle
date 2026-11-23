"""Au99.99 combination/cap account. The heat signal and its annual fit are independent of the cap."""
import json
from functools import lru_cache

import numpy as np
import pandas as pd

import gold_rolling_strategy as heat

ROOT = heat.ROOT
STRATEGY_VERSION = "au9999_heat_cap6_v1"
MONTHS = 6
WEAK_CAP = .5


@lru_cache(maxsize=1)
def _historical_sessions():
    return pd.DatetimeIndex(pd.read_csv(ROOT / "verified_daily.csv", usecols=["date"]).date)


def next_session(day):
    # Historical as-of queries need the exchange calendar, including holiday-shortened months.
    sessions = _historical_sessions()
    i = sessions.searchsorted(day, side="right")
    if i < len(sessions):
        return sessions[i]
    calendar = json.loads(ROOT.with_name("ashare_calendar.json").read_text(encoding="utf8"))
    candidate = day + pd.offsets.BDay()
    while any(start <= candidate.date().isoformat() <= end for start, end in calendar["closed_ranges"]):
        candidate += pd.offsets.BDay()
    return candidate


def monthly_limits(close, next_day):
    """Cap on today's close, plus the cap due on the next session after the last close."""
    months = close.index.to_period("M")
    ends = close.groupby(months).last()
    comparison = ends.reindex(ends.index - MONTHS).set_axis(ends.index)
    cap_after_month = pd.Series(np.where(ends < comparison, WEAK_CAP, 1.), index=ends.index)
    active = cap_after_month.reindex(months - 1).fillna(1.).set_axis(close.index)
    upcoming = cap_after_month.get(next_day.to_period("M") - 1, 1.)
    return active, float(upcoming)


def replay(close):
    signals = heat.replay(close)
    caps, last_next_cap = monthly_limits(close, next_session(close.index[-1]))
    caps = caps.loc[signals.index]
    active = signals.origin.ne(0)
    target = caps.where(~active, 0.)
    next_cap = caps.shift(-1, fill_value=last_next_cap)
    # A pending restoration closes the heat exit. A new heat sale always clears the ETF.
    next_flat = signals.pending.eq("sell") | (active & signals.pending.eq(""))
    next_target = next_cap.where(~next_flat, 0.)

    # CycleTest inherits unit wealth fully invested at the last pre-test close.
    start = close.index.get_loc(signals.index[0])
    grams = 1. / close.iloc[start - 1]
    cash, previous = 0., 1.
    ledger = []
    for price, goal in zip(signals.close, target):
        asset = grams * price
        trade = 0.
        if goal != previous:
            gap = goal * (asset + cash) - asset
            trade = gap / (1 + np.sign(gap) * heat.FEE * goal)
            grams += trade / price
            cash -= trade + abs(trade) * heat.FEE
        nav = cash + grams * price
        ledger.append((nav, grams * price / nav, trade, grams, cash))
        previous = goal
    signals[["nav","weight","signed_trade","grams","cash"]] = ledger
    signals = signals.rename(columns={"pending":"heat_pending", "executed":"heat_executed"})
    pending = signals.heat_pending.copy()
    pending.loc[next_target.eq(target)] = ""
    pending.loc[next_target.gt(target) & pending.eq("")] = "raise_cap"
    pending.loc[next_target.lt(target) & pending.eq("")] = "lower_cap"
    return signals.assign(cap=caps, next_cap=next_cap, target=target, next_target=next_target,
                          pending=pending, executed=pending.shift(fill_value=""))


def rule_rows(key):
    rows = [("持有", "实际仓位随金价浮动，不每天调仓。"),
            ("上限", f"月末金价低于六个月前月末，仓位上限为{WEAK_CAP:.0%}，否则为100%。上限变更于下一交易日收盘生效。")]
    signal, method, _ = heat.RULES[key]
    if signal is None:
        return rows
    (days, rise), confirm = heat.SIGNALS[signal]
    reversal = ("随后收跌" if confirm == "down" else
                f"随后{heat.PULLBACK_DAYS}个交易日内，收盘价较近期急涨日的最高收盘价回落至少{heat.PULLBACK:.0%}")
    recovery = {
        "recover5": "金价重新超过卖价",
        "discount10": f"金价跌至卖价的{heat.DISCOUNT:.0%}或重新超过卖价",
        "bounce15": f"金价重新超过卖价，或较卖出以来的最低收盘价反弹至少{heat.BOUNCE:.0%}",
    }[method]
    rows.extend([
        ("卖出", f"前{days}日累计上涨至少{rise:.0%}，{reversal}，下一交易日清仓。等待买回期间，上限提高也保持空仓。"),
        ("买回", f"{recovery}，下一交易日买回至当时的仓位上限。"),
        ("期限", f"最迟第{heat.LIMITS[method]}个交易日买回。"),
    ])
    return rows


def analyze(close, as_of):
    close = close.loc[:as_of]
    details = dict(strategy_version=STRATEGY_VERSION, signal_source="上金所 Au99.99",
                   signal_date=str(close.index[-1].date()) if len(close) else None,
                   signal_price=float(close.iloc[-1]) if len(close) else None)
    if close.empty or close.index[-1] != as_of or as_of.year < 2012:
        return "watch","等待金价","缺少对应交易日的 Au99.99 收盘价或五年训练历史。",dict(details,insufficient_history=True)
    row = replay(close).iloc[-1]
    weight = float(np.clip(row.weight, 0, 1))
    position = "满仓" if row.target == 1 else "空仓" if row.target == 0 else "半仓"
    status, action = "watch", position
    if row.next_target != row.target:
        if row.next_target == 0:
            status, action = "exit", "清仓"
        elif row.next_target < row.target:
            status, action = "reduce", "减至半仓"
        else:
            status = "buy"
            action = ("增持" if row.pending == "raise_cap" else "回补") + f"至{row.next_target:.0%}"
    next_action = f"下一交易日收盘{action}。" if row.pending else "下一交易日无买卖提醒。"
    if row.cap != row.next_cap:
        next_action = f"月末比较触发上限调整至{row.next_cap:.0%}。{next_action}"
    reason = (f"Au99.99 收盘 {row.close:g} 元/克，上限{row.cap:.0%}，策略当前{position}"
              f"（实际模拟仓位{weight:.2%}）。{next_action}")
    return status, action, reason, dict(details, insufficient_history=False, model_position=position,
        actual_exposure=weight, target_exposure=float(row.target), next_target_exposure=float(row.next_target),
        momentum_cap=float(row.cap), next_momentum_cap=float(row.next_cap), annual_rule=int(row.rule),
        next_rule=int(row.next_rule), rule_year=as_of.year, origin_rule=int(row.origin),
        sell_price=float(row.sell_price) if row.origin else None, pending=row.pending, executed=row.executed,
        rule_text="".join(text for _,text in rule_rows(row.rule)))


def backtest_summary():
    stats = pd.read_csv(ROOT / "combination/summary.csv").iloc[0].to_dict()
    return dict(stats, annual_method="CAGR", period_label=f"Au99.99 组合回测 {stats['start']} — {stats['end']}",
                note="期初承接持金，以上金所收盘价模拟，单边费率0.10%，现金无息。")
