# -*- coding: utf-8 -*-
"""
定投 + 估值 / 回撤管理 回测引擎
================================
面向「满足(条件) → 执行(操作)」风格的周定投策略，例如：

    买入(每周一定投, 周一休市顺延到当周首个交易日, 按当日收盘成交)：
      A  跌幅足够深 : close <= 历史最高价 × (1 - 历史最大涨幅 × a_cut)
      B  分位点低   : 当日收盘价在过去 percentile_window(默认5年) 内的分位 < p_low
      金额档：A且B -> amount_ab；仅A -> amount_a；仅B -> amount_b；都不满足 -> 0
      过热 D (分位 > p_high) -> 当周暂停定投，持有观望

    卖出/仓位管理(每个交易日按当日收盘数据判断, 按当日收盘价成交)：
      E     高位回撤保护 : 持仓期最高收盘回撤 ≥ 日均波动 × dd_mult  -> 清仓
      C+D   涨幅足够且过热 : 相对摊薄成本涨 ≥ 最大涨幅×gain_trigger 且分位>p_high -> 清仓
      C(仅) 涨幅足够(未过热) : 同上但分位≤p_high -> 卖出 50% 仓位（一个持仓周期只触发一次）
      D(仅) 过热           : 暂停定投，持有观望

关键定义 / 假设（可配置参数见 DCA_DEFAULTS）：
  - 历史最高/最低价、历史最大涨幅 = 过去 hist_window 个交易日的滚动极值（取“截至昨日”，
    不用当日，避免未来信息；数据不足时退化为自上市以来）。
  - 分位点 = 当日收盘价在过去 percentile_window 个收盘价中的百分位(含当日)。
  - C 涨幅相对“持仓摊薄成本(含费用)”计算。
  - E 日均波动 = 过去 vol_window 个交易日 |日涨跌幅| 的平均(截至昨日)。
  - 减仓类动作(卖50%)同一持仓周期内只触发一次，防止反复减半。
  - 成交均按“当日收盘价”计算，含佣金，按 100 份一手取整。
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import FEE_RATE, MIN_FEE

# ------------------------------------------------------------------
# 默认参数（网页表单里也是这些初值；历史窗口等都可配置）
# ------------------------------------------------------------------
DCA_DEFAULTS = {
    "hist_window": 1260,        # 历史高低点/最大涨幅 滚动窗口（交易日, ~5年）
    "percentile_window": 1260,  # 分位点窗口（~5年）
    "vol_window": 60,           # E 日均波动 的统计窗口（交易日）
    "a_cut": 0.5,               # A: 跌幅阈值 = 历史最大涨幅 × 50%
    "p_low": 30,                # B: 分位点 < 30%
    "gain_trigger": 0.5,        # C: 涨幅阈值 = 历史最大涨幅 × 50%
    "p_high": 70,               # D: 分位点 > 70%
    "dd_mult": 2.0,             # E: 回撤 >= 日均波动 × 2
    "amount_ab": 30,            # A且B 时每期金额（元）
    "amount_a": 20,             # 仅A 时金额
    "amount_b": 10,             # 仅B 时金额
    "initial_cash": 20000,      # 可用于定投的初始资金（元）
    "fee_rate": 0.0001,         # 佣金费率
    "min_fee": 0.0,             # 单笔最低佣金（小额定投建议 0）
    "slippage": 0.0,            # 滑点
    "lot": 1,                   # 最小买入单位(份)：默认 1=按整股买入，
                                 # 便于小额(30/20/10元)定投做收益研究；
                                 # 实盘场内 ETF 请按 100 份一手并相应放大金额
}

# ------------------------------------------------------------------
# 卖出/管理规则（网页里可增删、启停）
#   conds : 需要同时满足的条件子集（A/B/C/D/E）
#   action: clear=清仓 | trim_half=卖出50% | pause=暂停定投(持有)
#   priority: 数值越小越先判断（E 优先）
# ------------------------------------------------------------------
DEFAULT_SELL_RULES = [
    {"id": "e",      "name": "E 高位回撤保护（持仓期高点回撤≥日均波动×N）",
     "conds": ["E"], "action": "clear", "priority": 1, "enabled": True},
    {"id": "cd",     "name": "C 涨幅足够 + D 估值过热",
     "conds": ["C", "D"], "action": "clear", "priority": 2, "enabled": True},
    {"id": "c_only", "name": "C 涨幅足够（未过热，卖出50%）",
     "conds": ["C"], "action": "trim_half", "priority": 3, "enabled": True},
    {"id": "d_only", "name": "D 估值过热（暂停定投，持有观望）",
     "conds": ["D"], "action": "pause", "priority": 4, "enabled": True},
]


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------
def rolling_percentile(close: pd.Series, window: int) -> pd.Series:
    """当日收盘价在过去 window 个收盘价（含当日）中的百分位 [0,100]。
    数据不足 window 时用“自上市以来”的全部可得数据。"""
    from numpy.lib.stride_tricks import sliding_window_view
    vals = close.to_numpy(dtype=float)
    n = len(vals)
    out = np.full(n, np.nan)
    if n >= window:
        w = sliding_window_view(vals, window)          # (n-window+1, window)
        cur = w[:, -1]
        out[window - 1:] = (w <= cur[:, None]).sum(axis=1) / window * 100
    # 早期数据不足：用从起点到当日
    for i in range(min(window - 1, n)):
        seg = vals[:i + 1]
        out[i] = (seg <= vals[i]).mean() * 100
    return pd.Series(out, index=close.index)


def _num(p: dict, k, default):
    try:
        return float(p.get(k, default))
    except (TypeError, ValueError):
        return float(default)


def _int(p: dict, k, default):
    return int(_num(p, k, default))


def _precompute(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """把滚动指标提前算好，追加到 df 上（全部是“截至当日或昨日”的可用信息）。"""
    close = df["close"]
    hw = _int(p, "hist_window", 1260)
    pw = _int(p, "percentile_window", 1260)
    vw = _int(p, "vol_window", 60)

    out = df.copy()
    # 历史极值/最大涨幅：截至昨日（shift 1），数据不足时退化为自上市以来
    hh = close.rolling(hw, min_periods=1).max().shift(1)
    ll = close.rolling(hw, min_periods=1).min().shift(1)
    mg = (hh - ll) / ll
    # 分位点(含当日)
    pct = rolling_percentile(close, pw)
    # 日均波动(截至昨日)
    vol = close.pct_change().abs().rolling(vw, min_periods=1).mean().shift(1)

    out["hist_high"] = hh
    out["hist_low"] = ll
    out["max_gain"] = mg
    out["pct"] = pct
    out["vol"] = vol
    return out


def _weekly_first_days(index: pd.DatetimeIndex) -> np.ndarray:
    """每周的第一个交易日（周一休市则顺延到当周首个交易日）。返回布尔掩码。"""
    iso = index.isocalendar()
    wk = iso["year"].astype(int) * 1000 + iso["week"].astype(int)
    return (~wk.duplicated()).to_numpy()


# ------------------------------------------------------------------
# 结果容器
# ------------------------------------------------------------------
@dataclass
class DcaResult:
    kind: str                       # 'strategy' / 'benchmark'
    df: pd.DataFrame                # 行情 + 滚动指标 + 逐日账户状态列
    events: list                    # [{'date','kind','detail'}]
    metrics: dict                   # 绩效指标
    params: dict
    sell_rules: list = field(default_factory=list)


# ------------------------------------------------------------------
# 核心引擎
# ------------------------------------------------------------------
def run_dca(df: pd.DataFrame, params: dict = None,
            sell_rules: list = None, naive: bool = False) -> DcaResult:
    """
    运行周定投回测。
      naive=True 时跑基准“无脑定投”：每周固定投 amount_ab、不看条件、不减仓。
    返回 DcaResult（df 含逐日账户状态列，events 为逐笔动作日志）。
    """
    p = dict(DCA_DEFAULTS)
    if params:
        p.update({k: v for k, v in params.items() if v is not None})
    rules = sell_rules if sell_rules is not None else DEFAULT_SELL_RULES

    fee_rate = float(p["fee_rate"]); min_fee = float(p["min_fee"])
    slip = float(p["slippage"]); lot = int(p["lot"])
    init_cash = float(p["initial_cash"])
    a_cut = _num(p, "a_cut", 0.5); p_low = _num(p, "p_low", 30)
    g_trig = _num(p, "gain_trigger", 0.5); p_high = _num(p, "p_high", 70)
    dd_mult = _num(p, "dd_mult", 2.0)
    amt_ab = _num(p, "amount_ab", 30); amt_a = _num(p, "amount_a", 20)
    amt_b = _num(p, "amount_b", 10)

    d = _precompute(df, p)
    close = d["close"].to_numpy(float)
    hh = d["hist_high"].to_numpy(float)
    mg = d["max_gain"].to_numpy(float)
    pct = d["pct"].to_numpy(float)
    vol = d["vol"].to_numpy(float)
    is_dca = _weekly_first_days(d.index)

    # 账户状态
    cash = init_cash
    shares = 0.0
    basis = 0.0            # 持仓成本总额(含买入费用)
    peak = 0.0             # 持仓期最高收盘
    invested_cum = 0.0     # 累计定投投入（含费）
    realized = 0.0
    fired = set()          # 本持仓周期内已触发过的非清仓规则 id
    buys = 0; pauses = 0; clears = 0; trims = 0

    n = len(d)
    eq = np.empty(n)
    n_shares = np.empty(n)
    n_cash = np.empty(n)
    events = []

    def fee(amount: float) -> float:
        return max(amount * fee_rate, min_fee)

    # 每周买入条件 A/B/D（用于买入与事件记录）
    for i in range(n):
        px = close[i]

        # ============ 1) 卖出 / 仓位管理（每日，仅持仓时） ============
        if shares > 0 and not naive:
            conds = {}
            mg_i = mg[i]
            # C：相对摊薄成本涨幅达标
            gain_ok = (basis > 0 and shares > 0 and mg_i == mg_i
                       and (px / (basis / shares) - 1) >= mg_i * g_trig)
            # D：过热
            d_ok = pct[i] == pct[i] and pct[i] > p_high
            # E：从持仓期高点回撤 >= 日均波动*倍数
            dd_ok = (peak > 0 and vol[i] == vol[i]
                     and (peak - px) / peak >= vol[i] * dd_mult)
            conds.update({"C": gain_ok, "D": d_ok, "E": dd_ok})

            for r in sorted(rules, key=lambda x: x.get("priority", 99)):
                if not r.get("enabled", True) or r.get("action") == "pause":
                    continue
                need = set(r["conds"])
                if need - set(k for k, v in conds.items() if v):
                    continue
                act = r["action"]
                if act == "clear":
                    f = fee(shares * px)
                    cash += shares * px - f
                    shares = 0.0; basis = 0.0; peak = 0.0
                    fired.clear()
                    clears += 1
                    events.append({"date": d.index[i], "kind": "clear",
                                   "detail": f"清仓 @ {px:.4f}（{r['name']}）"})
                    break
                if act == "trim_half" and r["id"] not in fired:
                    q = int(shares / 2 // lot) * lot
                    if q > 0:
                        f = fee(q * px)
                        basis -= q * (basis / shares) if shares > 0 else 0.0
                        cash += q * px - f
                        shares -= q
                        trims += 1
                        fired.add(r["id"])
                        events.append({"date": d.index[i], "kind": "trim",
                                       "detail": f"减仓50%({int(q)}份) @ {px:.4f}（{r['name']}）"})
                        break

        # ============ 2) 每周定投买入（每周第一个交易日） ============
        if is_dca[i]:
            # 过热暂停（启用的 pause 规则且满足 D 条件）-> 本周暂停定投，持有观望
            paused = False
            if not naive and pct[i] == pct[i] and pct[i] > p_high:
                for r in rules:
                    if r.get("enabled", True) and r.get("action") == "pause" \
                            and "D" in r.get("conds", []):
                        paused = True
                        break

            if paused:
                pauses += 1
                events.append({"date": d.index[i], "kind": "pause",
                               "detail": "暂停定投（估值过热 D）"})
                amount = 0.0
            elif naive:
                amount = amt_ab          # 无脑定投基准：每周固定档1
            else:
                a_ok = (not np.isnan(hh[i]) and not np.isnan(mg[i])
                        and px <= hh[i] * (1 - mg[i] * a_cut))
                b_ok = pct[i] == pct[i] and pct[i] < p_low
                amount = (amt_ab if a_ok and b_ok
                          else amt_a if a_ok
                          else amt_b if b_ok else 0.0)

            if amount > 0 and cash > 0:
                buy_amt = min(amount, cash)
                # 按最小交易单位买入；默认 1 份粒度（小额研究用）
                q = int(buy_amt / (px * lot * (1 + fee_rate)))
                if q > 0:
                    f = fee(q * px)
                    cost = q * px + f
                    cash -= cost
                    basis = basis + cost
                    shares += q
                    invested_cum += cost
                    peak = max(peak, px)
                    buys += 1
                    events.append({"date": d.index[i], "kind": "buy",
                                   "detail": f"定投 {q:.0f}份=¥{cost:.2f} @ {px:.4f}"})

        # ============ 3) 每日市值快照 ============
        eq[i] = cash + shares * px
        n_shares[i] = shares
        n_cash[i] = cash
        if shares > 0 and px > peak:
            peak = px

    d = d.copy()
    d["account_cash"] = n_cash
    d["shares"] = n_shares
    d["equity"] = eq

    # 已实现盈亏：按摊薄成本法统一后算，避免循环内累加误差
    realized = _compute_realized(d, events, fee_rate, min_fee)

    kind = "benchmark" if naive else "strategy"
    metrics = _metrics(d, events, init_cash, invested_cum, realized,
                       shares, basis, kind)
    return DcaResult(kind=kind, df=d, events=events, metrics=metrics,
                     params=p, sell_rules=rules)


def _compute_realized(d, events, fee_rate, min_fee):
    """按“摊薄成本法”从逐日份额变化重建已实现盈亏（含买卖费用）。"""
    shares_s = d["shares"].to_numpy(float)
    close = d["close"].to_numpy(float)
    realized = 0.0
    basis = 0.0
    prev = 0.0
    for i in range(len(shares_s)):
        cur = shares_s[i]
        delta = cur - prev
        if delta > 1e-9:            # 买入
            f = max(delta * close[i] * fee_rate, min_fee)
            basis += delta * close[i] + f
        elif delta < -1e-9:         # 卖出
            q = -delta
            avg = basis / prev if prev > 1e-9 else close[i]
            f = max(q * close[i] * fee_rate, min_fee)
            realized += q * (close[i] - avg) - f
            basis = max(0.0, basis - q * avg)
        prev = cur
    return realized


def _metrics(d, events, init_cash, invested_cum, realized, shares, basis, kind):
    eq = d["equity"].to_numpy(float)
    close = d["close"].to_numpy(float)
    n = len(eq)
    last_close = close[-1]

    unreal = shares * (last_close - (basis / shares)) if shares > 0 and basis > 0 else 0.0
    pnl_total = realized + unreal
    invested_return = pnl_total / invested_cum if invested_cum > 0 else 0.0
    total_return = eq[-1] / init_cash - 1.0

    peak = np.maximum.accumulate(eq)
    mdd = float(((eq / peak) - 1.0).min())

    buys = sum(1 for e in events if e["kind"] == "buy")
    pauses = sum(1 for e in events if e["kind"] == "pause")
    clears = sum(1 for e in events if e["kind"] == "clear")
    trims = sum(1 for e in events if e["kind"] == "trim")

    return {
        "口径": "无脑定投(基准)" if kind == "benchmark" else "条件定投(策略)",
        "区间交易日": n,
        "定投买入次数": buys,
        "累计定投投入": round(invested_cum, 2),
        "期末总资产": round(float(eq[-1]), 2),
        "期末现金(闲置)": round(float(d["account_cash"].iloc[-1]), 2),
        "期末持仓市值": round(float(eq[-1]) - float(d["account_cash"].iloc[-1]), 2),
        "已实现盈亏": round(realized, 2),
        "未实现盈亏": round(unreal, 2),
        "投入总盈亏": round(pnl_total, 2),
        "投入收益率(占总投入)": invested_return,
        "总资产收益率(含闲置资金)": total_return,
        "最大回撤(总资产)": mdd,
        "暂停定投次数": pauses,
        "清仓次数": clears,
        "减仓次数": trims,
    }


# ------------------------------------------------------------------
# 展示与绘图
# ------------------------------------------------------------------
def format_dca_metrics(m: dict) -> str:
    pct = ["投入收益率(占总投入)", "总资产收益率(含闲置资金)", "最大回撤(总资产)"]
    lines = []
    for k, v in m.items():
        if isinstance(v, float) and k in pct:
            lines.append(f"  {k:<18}: {v:>12.2%}")
        elif isinstance(v, float):
            lines.append(f"  {k:<18}: {v:>12,.2f}")
        else:
            lines.append(f"  {k:<18}: {v}")
    return "\n".join(lines)


def print_dca_report(strategy: DcaResult, benchmark: DcaResult, title: str = "") -> None:
    if title:
        print("=" * 66)
        print(title)
        print("=" * 66)
    print("【条件定投策略】")
    print(format_dca_metrics(strategy.metrics))
    print("\n【无脑定投基准（每期固定档1金额、不择时不减仓）】")
    print(format_dca_metrics(benchmark.metrics))
    print("\n【动作日志（最近 25 条）】")
    tail = strategy.events[-25:]
    if not tail:
        print("  （无动作）")
    for e in tail:
        print(f"  {e['date'].date()}  [{e['kind']}] {e['detail']}")
    print("\n")


def plot_dca(strategy: DcaResult, benchmark: DcaResult, title: str = "",
             save_path: str = None):
    import matplotlib
    try:
        matplotlib.use("Agg")
    except Exception:
        pass
    import matplotlib.pyplot as plt
    try:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "PingFang SC", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    df = strategy.df
    fig, axes = plt.subplots(2, 1, figsize=(13, 8.5), sharex=True,
                             gridspec_kw={"height_ratios": [2.4, 1.8]})
    ax1, ax2 = axes

    ax1.plot(df.index, df["close"], color="#37474f", lw=1.1, label="收盘价")
    ev = pd.DataFrame(strategy.events)
    if not ev.empty:
        buys = ev[ev["kind"] == "buy"]
        clears = ev[ev["kind"] == "clear"]
        trims = ev[ev["kind"] == "trim"]
        if not buys.empty:
            yb = df["close"].reindex(buys["date"]).to_numpy()
            ax1.scatter(buys["date"], yb, marker="^", color="#2e7d32", s=30,
                        zorder=5, label=f"定投买入({len(buys)})")
        if not clears.empty:
            yc = df["close"].reindex(clears["date"]).to_numpy()
            ax1.scatter(clears["date"], yc, marker="X", color="#d32f2f", s=70,
                        zorder=5, label=f"清仓({len(clears)})")
        if not trims.empty:
            yt = df["close"].reindex(trims["date"]).to_numpy()
            ax1.scatter(trims["date"], yt, marker="o", facecolors="none",
                        edgecolors="#f57c00", s=60, zorder=5, label=f"减仓50%({len(trims)})")
    ax1.set_title(title)
    ax1.legend(loc="best", fontsize=9)
    ax1.grid(alpha=0.3)
    ax1.set_ylabel("价格")

    ax2.plot(df.index, strategy.df["equity"] / strategy.params["initial_cash"],
             color="#1565c0", lw=1.5, label="条件定投(总资产)")
    ax2.plot(benchmark.df.index, benchmark.df["equity"] / benchmark.params["initial_cash"],
             color="#8d6e63", lw=1.2, ls="--", label="无脑定投基准(总资产)")
    ax2.axhline(1.0, color="gray", lw=0.6, ls=":")
    ax2.legend(loc="best", fontsize=9)
    ax2.grid(alpha=0.3)
    ax2.set_ylabel("总资产/初始资金")
    ax2.set_xlabel("日期")

    fig.tight_layout()
    if save_path:
        import os
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=130, bbox_inches="tight")
        print(f"图表已保存：{save_path}")
        plt.close(fig)
    else:
        plt.show()


def run_dca_backtest(df: pd.DataFrame, params: dict = None,
                     sell_rules: list = None):
    """便捷入口：跑策略 + 基准，返回 (strategy, benchmark)。"""
    strat = run_dca(df, params, sell_rules, naive=False)
    bench = run_dca(df, params, None, naive=True)
    return strat, bench
