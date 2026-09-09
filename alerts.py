# -*- coding: utf-8 -*-
"""
今日买卖点提醒
==============
基于最新一个交易日的数据，按当前规则给出：
  1) 定投资格：A/B/D 状态 + 建议金额（无论当天是否周一，都能看“今天能不能投”）
  2) 卖出/仓位提醒：逐条规则给出触发条件与“触发临界参考价”
     （C/E 需要结合你的实际持仓成本/最高价，这里反推“什么价位会触发”）

网页端直接调用 analyze_latest() 渲染“今日消息”，CLI 用 main.py alerts 打印。
"""

import pandas as pd

from dca import (DCA_DEFAULTS, DEFAULT_SELL_RULES, _num, _precompute,
                 _weekly_first_days)


def analyze_latest(df: pd.DataFrame, params: dict = None,
                   sell_rules: list = None) -> dict:
    """对最新一个交易日做规则体检，返回结构化结果（JSON 友好）。"""
    p = dict(DCA_DEFAULTS)
    if params:
        p.update({k: v for k, v in params.items() if v is not None})
    rules = sell_rules if sell_rules is not None else DEFAULT_SELL_RULES

    a_cut = _num(p, "a_cut", 0.5); p_low = _num(p, "p_low", 30)
    g_trig = _num(p, "gain_trigger", 0.5); p_high = _num(p, "p_high", 70)
    dd_mult = _num(p, "dd_mult", 2.0)
    amt_ab = _num(p, "amount_ab", 30); amt_a = _num(p, "amount_a", 20)
    amt_b = _num(p, "amount_b", 10)

    d = _precompute(df, p)
    row = d.iloc[-1]
    close = float(row["close"])
    date = d.index[-1].date()
    hh = float(row["hist_high"]) if row["hist_high"] == row["hist_high"] else None
    ll = float(row["hist_low"]) if row["hist_low"] == row["hist_low"] else None
    mg = float(row["max_gain"]) if row["max_gain"] == row["max_gain"] else None
    pct = float(row["pct"]) if row["pct"] == row["pct"] else None
    vol = float(row["vol"]) if row["vol"] == row["vol"] else None

    # ---- 定投资格 ----
    a_ok = (hh is not None and mg is not None
            and close <= hh * (1 - mg * a_cut))
    b_ok = pct is not None and pct < p_low
    d_ok = pct is not None and pct > p_high
    paused = False
    if d_ok:
        paused = any(r.get("enabled", True) and r.get("action") == "pause"
                     and "D" in r.get("conds", []) for r in rules)
    amount = (amt_ab if a_ok and b_ok
              else amt_a if a_ok
              else amt_b if b_ok else 0.0)

    is_monday = date.weekday() == 0
    # 当日是否为“该周首个交易日”（周一休市时顺延）
    mask = _weekly_first_days(d.index)
    today_is_dca_day = bool(mask[-1])

    # ---- 卖出/仓位规则提醒（给出触发参考价） ----
    sell_hints = []
    for r in sorted(rules, key=lambda x: x.get("priority", 99)):
        if not r.get("enabled", True):
            continue
        need = r.get("conds", [])
        act = r.get("action")
        hint = {"id": r.get("id"), "name": r.get("name"), "action": act,
                "conds": need, "active": False, "note": "", "ref": None}
        # 需要持仓才能判断的条件：给出“什么价位会触发”
        if act == "clear" or act == "trim_half":
            parts = []
            if "E" in need:
                # E 触发需要：持仓期最高价 >= close*(1+日均波动*倍数)
                if vol is not None:
                    ref_peak = close * (1 + vol * dd_mult)
                    hint["ref"] = {"type": "peak", "value": round(ref_peak, 4),
                                   "meaning": "持仓期间最高价 ≥ 此值则触发 E 回撤清仓保护"}
                    parts.append("回撤保护E")
                    # 用近250日最高收盘近似判断是否“有可能在保护区内”
                    hi250 = float(d["close"].rolling(250, min_periods=1).max().iloc[-1])
                    hint["likely"] = bool(hi250 >= ref_peak)
            if "C" in need:
                if mg is not None:
                    # C 触发需要：平均成本 <= close/(1+max_gain*gain_trigger)
                    ref_cost = close / (1 + mg * g_trig)
                    hint["ref2"] = {"type": "cost", "value": round(ref_cost, 4),
                                    "meaning": "你的摊薄平均成本 ≤ 此值则满足 C 涨幅条件"}
                    parts.append("涨幅C")
            # 注：C/E 是否真正触发需结合你的实际持仓（成本/持仓最高价），
            # 见下方 decide_today()。这里仅提示“D 已过热”，不误标已触发。
            if "D" in need and d_ok:
                hint["note"] = "D 已过热"
            # 只有 D 且组合非空(仅 pause 类型走这里)
            hint["name_short"] = "、".join(parts) or (hint["name"])
        elif act == "pause":
            if d_ok:
                hint["active"] = True
                hint["note"] = "当前过热，建议暂停定投、持有观望"
        sell_hints.append(hint)

    return {
        "date": date.isoformat(),
        "is_monday": is_monday,
        "today_is_dca_day": today_is_dca_day,
        "close": round(close, 4),
        "hist_high": round(hh, 4) if hh else None,
        "hist_low": round(ll, 4) if ll else None,
        "max_gain": round(mg, 4) if mg else None,
        "pct": round(pct, 2) if pct is not None else None,
        "vol": round(vol, 4) if vol else None,
        # 定投
        "A_跌幅足够深": a_ok,
        "B_分位点低": b_ok,
        "D_过热": d_ok,
        "暂停定投": paused,
        "建议定投金额": amount,
        "定投档位": ("A且B" if a_ok and b_ok else "仅A" if a_ok
                    else "仅B" if b_ok else "不投"),
        # 卖出
        "sell_hints": sell_hints,
        "params": p,
        "sell_rules": rules,
    }


def render_text(rep: dict, name: str = "") -> str:
    """把 analyze_latest 的结果渲染成适合终端阅读的文本。"""
    lines = []
    header = f"=== {name}  数据日期 {rep['date']}（收盘 {rep['close']}） ==="
    lines.append(header)
    lines.append(f"  市场状态：分位点 {rep['pct']}%（5年窗口）"
                 f"，历史最大涨幅 {rep['max_gain']:.1%}，日均波动 {rep['vol']:.2%}")
    lines.append(f"  历史区间：低 {rep['hist_low']} ~ 高 {rep['hist_high']}")
    lines.append("")
    lines.append("【定投提醒】")
    wd = "周一(定投日)" if rep["today_is_dca_day"] else "非定投日(可自行选择是否提前/补投)"
    lines.append(f"  今天是{rep['date']} {wd}")
    lines.append(f"  A 跌幅足够深: {'满足' if rep['A_跌幅足够深'] else '不满足'}")
    lines.append(f"  B 分位点低(<{rep['params']['p_low']}%): {'满足' if rep['B_分位点低'] else '不满足'}")
    lines.append(f"  D 估值过热(>{rep['params']['p_high']}%): {'过热' if rep['D_过热'] else '正常'}")
    if rep["暂停定投"]:
        lines.append("  >>> 建议：过热暂停定投，持有观望（0 元）")
    else:
        lines.append(f"  >>> 若今天定投，建议金额：{rep['建议定投金额']:g} 元（档位：{rep['定投档位']}）")
    lines.append("")
    lines.append("【卖出/仓位提醒（需结合你的实际持仓）】")
    any_act = False
    for h in rep["sell_hints"]:
        if h.get("active"):
            lines.append(f"  ● {h['name']}  -> {h['action']}   [当前已触发!]")
            any_act = True
        else:
            refs = []
            if h.get("ref"):
                refs.append(f"持仓最高价≥{h['ref']['value']} 触发")
            if h.get("ref2"):
                refs.append(f"平均成本≤{h['ref2']['value']} 触发")
            tail = "；".join(refs)
            lines.append(f"  ○ {h['name']}（{h['name_short']}）  参考：{tail or '—'}")
    if not any_act:
        pass
    return "\n".join(lines)


# =============================================================
# 结合“我的实际持仓”做精确决策（实盘验证用）
# =============================================================
def decide_today(rep: dict, holding: bool = False, avg_cost: float = None,
                 peak: float = None, sell_rules: list = None) -> dict:
    """
    在 rep（analyze_latest 的结果）基础上，给出你实际持仓情况下今天该怎么做的决策。
      holding : 是否持有该 ETF
      avg_cost: 你的摊薄平均成本（持有且做 C 涨幅判断时填）
      peak    : 你持仓期间的收盘最高价（做 E 回撤判断时填）
    返回：{'buy_amount', 'buy_tier', 'decisions':[{rule, action, reason}]}
    """
    p = rep["params"]
    rules = sell_rules if sell_rules is not None else \
        rep.get("sell_rules") or DEFAULT_SELL_RULES

    close = rep["close"]
    mg = rep["max_gain"]
    vol = rep["vol"]
    g_trig = float(p["gain_trigger"])
    dd_mult = float(p["dd_mult"])

    # ---- 计算今天真实满足的条件 ----
    cond = {"A": bool(rep["A_跌幅足够深"]),
            "B": bool(rep["B_分位点低"]),
            "D": bool(rep["D_过热"])}
    if holding and avg_cost and avg_cost > 0 and mg:
        cond["C"] = (close / avg_cost - 1.0) >= mg * g_trig
    if holding and peak and peak > 0 and vol:
        cond["E"] = peak >= close and (peak - close) / peak >= vol * dd_mult

    sat = {k for k, v in cond.items() if v}

    # ---- 买入决策（无论今天是否周一，都给“如果投/该投多少”的参考） ----
    if "D" in sat and any(r.get("enabled", True) and r.get("action") == "pause"
                          and "D" in r.get("conds", []) for r in rules):
        buy_amount, buy_tier = 0.0, "过热暂停定投"
    elif "A" in sat and "B" in sat:
        buy_amount, buy_tier = float(p["amount_ab"]), "A且B（档1）"
    elif "A" in sat:
        buy_amount, buy_tier = float(p["amount_a"]), "仅A（档2）"
    elif "B" in sat:
        buy_amount, buy_tier = float(p["amount_b"]), "仅B（档3）"
    else:
        buy_amount, buy_tier = 0.0, "不满足买入条件"

    # ---- 仓位决策（按优先级取第一个命中的动作） ----
    decisions = []
    for r in sorted(rules, key=lambda x: x.get("priority", 99)):
        if not r.get("enabled", True):
            continue
        need = set(r.get("conds", []))
        if need == {"C"}:
            fire = ("C" in sat) and ("D" not in sat)   # C-only：涨幅足且未过热
        else:
            fire = need <= sat
        if fire:
            act = r["action"]
            label = {"clear": "清仓", "trim_half": "减仓50%",
                     "pause": "暂停定投"}.get(act, act)
            decisions.append({"id": r.get("id"), "name": r.get("name"),
                              "action": act, "label": label})
            break   # 只给出最高优先级的一条仓位建议

    return {"buy_amount": buy_amount, "buy_tier": buy_tier,
            "cond": {k: bool(v) for k, v in cond.items()},
            "holding": bool(holding), "avg_cost": avg_cost, "peak": peak,
            "decisions": decisions}
