# -*- coding: utf-8 -*-
"""行业 ETF 的通用基线策略。

行业之间沿用同一套结构（趋势、回撤、反转确认、仓位与退出），阈值由 profile
配置。这里不使用“历史最大涨幅×比例”，避免新品种和高波动行业产生失真阈值。
"""

import pandas as pd


DEFAULT_PROFILE = {
    "ma_fast": 20,
    "ma_mid": 60,
    "ma_slow": 120,
    "drawdown_watch": 0.15,
    "drawdown_strong": 0.25,
    "chase_above_ma60": 0.18,
    "chase_return_20d": 0.20,
    "slow_line_buffer": 0.03,
    "profit_trim": 0.08,
    "profit_clear": 0.15,
    "amount_normal": 10.0,
    "amount_strong": 20.0,
}


def _weekly_below_slow(d: pd.DataFrame) -> bool:
    weekly = d[["close", "ma_slow"]].resample("W-FRI").last().dropna()
    return len(weekly) >= 2 and bool(
        (weekly["close"].iloc[-2:] < weekly["ma_slow"].iloc[-2:]).all()
    )


def analyze_latest(df: pd.DataFrame, profile: dict = None) -> dict:
    p = dict(DEFAULT_PROFILE)
    if profile:
        p.update(profile)
    d = df.copy().sort_index()
    close = d["close"].astype(float)
    d["ma_fast"] = close.rolling(int(p["ma_fast"]), min_periods=10).mean()
    d["ma_mid"] = close.rolling(int(p["ma_mid"]), min_periods=30).mean()
    d["ma_slow"] = close.rolling(int(p["ma_slow"]), min_periods=60).mean()
    row = d.iloc[-1]
    last = float(row["close"])
    ma_fast, ma_mid, ma_slow = (float(row[k]) for k in ("ma_fast", "ma_mid", "ma_slow"))
    high250 = float(close.rolling(250, min_periods=60).max().iloc[-1])
    drawdown = last / high250 - 1
    ret20 = last / float(close.iloc[-21]) - 1 if len(close) > 20 else 0.0
    fast_rising = len(d) > 5 and ma_fast > float(d["ma_fast"].iloc[-6])
    trend_weak = ma_fast < ma_mid and ret20 < 0
    recovered_fast = last > ma_fast and fast_rising
    chasing = last > ma_mid * (1 + p["chase_above_ma60"]) or ret20 > p["chase_return_20d"]
    strong_add = drawdown <= -p["drawdown_strong"] and recovered_fast and not chasing
    normal_add = drawdown <= -p["drawdown_watch"] and recovered_fast and not chasing
    risk_exit = _weekly_below_slow(d) and ma_fast < ma_mid
    defensive_watch = trend_weak and last <= ma_slow * (1 + p["slow_line_buffer"])

    recent = d.tail(10)
    touched_mid = bool((recent["close"] >= recent["ma_mid"] * 0.98).any())
    rebound_failure = touched_mid and last < ma_fast and ret20 < 0
    overheated = chasing
    amount = p["amount_strong"] if strong_add else p["amount_normal"] if normal_add else 0.0
    add_advice = (f"可小额追加 {amount:g} 元" if amount else
                  "暂停追加（等待重新站上 MA20 且 MA20 转升）")

    return {
        "strategy_type": "industry",
        "date": d.index[-1].date().isoformat(),
        "close": round(last, 4),
        "ma20": round(ma_fast, 4), "ma60": round(ma_mid, 4), "ma120": round(ma_slow, 4),
        "ret20": round(ret20, 4), "drawdown250": round(drawdown, 4),
        "trend_weak": trend_weak, "recovered_fast": recovered_fast,
        "chasing": chasing, "risk_exit": risk_exit,
        "defensive_watch": defensive_watch, "rebound_failure": rebound_failure,
        "add_amount": amount, "add_advice": add_advice,
        "profile": p,
        # 兼容现有卡片的公共字段。
        "today_is_dca_day": d.index[-1].weekday() == 0,
        "pct": None, "hist_high": round(high250, 4), "hist_low": round(float(close.tail(250).min()), 4),
        "max_gain": 0.0, "vol": round(float(close.pct_change().tail(60).std()), 4),
        "A_跌幅足够深": drawdown <= -p["drawdown_watch"],
        "B_分位点低": recovered_fast, "D_过热": overheated,
        "暂停定投": amount == 0, "建议定投金额": amount,
        "定投档位": "行业强信号" if strong_add else "行业普通信号" if normal_add else "不投",
        "sell_hints": [], "params": p, "sell_rules": [],
    }


def decide(rep: dict, holding: bool, current_return=None) -> dict:
    rr = float(current_return) / 100 if current_return is not None else None
    if not holding:
        sell = "当前未持有，无需卖出"
        action = "none"
    elif rep["risk_exit"]:
        sell, action = "全部卖出：中期趋势已确认破坏", "clear"
    elif rr is not None and rr >= rep["profile"]["profit_clear"] and (rep["chasing"] or rep["trend_weak"]):
        sell, action = "全部卖出：已达到盈利目标且走势过热或转弱", "clear"
    elif rr is not None and rr >= rep["profile"]["profit_trim"] and rep["chasing"]:
        sell, action = "卖出 50%：盈利后进入过热区", "trim_half"
    elif rr is not None and rr < 0 and rep["rebound_failure"]:
        sell, action = "全部卖出：亏损反弹至压力区后再次转弱", "clear"
    elif rep["defensive_watch"]:
        sell, action = "暂不卖出，进入防守观察；若连续两周跌破 MA120 则退出", "watch"
    else:
        sell, action = "暂不卖出，继续观察", "hold"
    return {"buy_amount": rep["add_amount"], "buy_tier": rep["add_advice"],
            "sell_advice": sell, "action": action, "holding": holding,
            "current_return": current_return}
