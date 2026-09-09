# -*- coding: utf-8 -*-
"""
回测引擎与绩效评估
==================
把“信号序列”翻译成持仓与资金变化：

  成交规则
  --------
  - 信号在第 t 天【收盘后】产生；
  - 实际在第 t+1 天【开盘价】成交（避免未来函数）；
  - +1 买入（若已持仓则忽略）、-1 卖出（若已空仓则忽略）；
  - 买入默认“满仓”，按 100 份一手向下取整，并预留交易费用。

  输出
  ----
  equity   : 每日市值曲线（strategy 与 benchmark 两列，绝对金额）
  trades   : 每笔“买入->卖出”完整交易记录
  metrics  : 策略绩效指标（总收益/年化/最大回撤/夏普/胜率等）
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import (FEE_RATE, INIT_CAPITAL, LOT_SIZE, MIN_FEE, SLIPPAGE)

try:
    import matplotlib
    matplotlib.use("Agg")  # 不依赖显示器，直接输出文件
    _MPL_OK = True
except Exception:
    _MPL_OK = False


# --------------------------- 数据结构 ---------------------------
@dataclass
class BacktestResult:
    df: pd.DataFrame                 # 输入行情（绘图用）
    equity: pd.DataFrame             # 列：strategy / benchmark
    trades: pd.DataFrame             # 完整交易记录（空则无交易）
    open_position: dict              # 若最后仍持仓，这里记录未平仓的一笔
    metrics: dict                    # 策略绩效
    benchmark_metrics: dict          # 买入持有绩效
    initial_capital: float = INIT_CAPITAL


# --------------------------- 指标计算 ---------------------------
def compute_metrics(equity: np.ndarray, capital: float, annual_days: int = 252) -> dict:
    """从资金曲线计算常规绩效指标。"""
    eq = np.asarray(equity, dtype=float)
    n = len(eq)
    total = eq[-1] / capital - 1.0
    years = n / annual_days
    annual = (eq[-1] / capital) ** (1 / years) - 1.0 if years > 0 and eq[-1] > 0 else 0.0

    # 最大回撤
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    max_dd = float(dd.min())

    rets = np.diff(eq) / eq[:-1] if n > 1 else np.array([0.0])
    std = rets.std(ddof=1) if len(rets) > 1 else 0.0
    vol = float(std * np.sqrt(annual_days)) if std > 0 else 0.0
    sharpe = float(rets.mean() / std * np.sqrt(annual_days)) if std > 0 else 0.0
    calmar = float(annual / abs(max_dd)) if max_dd < 0 else float("nan")

    return {
        "总收益率": total,
        "年化收益率": annual,
        "最大回撤": max_dd,
        "年化波动率": vol,
        "夏普比率": sharpe,
        "卡玛比率": calmar,
        "期末市值": float(eq[-1]),
    }


def _trade_stats(trades: pd.DataFrame, open_position: dict) -> dict:
    """从交易记录汇总交易层面统计。"""
    n = len(trades)
    out = {"交易次数": n, "胜率": float("nan"), "盈亏比": float("nan"),
           "平均持有天数": float("nan"), "平均单笔收益": float("nan")}
    if n == 0:
        if open_position:
            out["交易次数"] = 1  # 有一笔未平仓
            out["备注"] = "仅有一笔未平仓持仓，无完整交易记录"
        return out
    wins = trades["单笔盈亏"] > 0
    out["胜率"] = float(wins.mean())
    gross_profit = trades.loc[wins, "单笔盈亏"].sum()
    gross_loss = -trades.loc[~wins, "单笔盈亏"].sum()
    out["盈亏比"] = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    out["平均持有天数"] = float(trades["持有天数"].mean())
    out["平均单笔收益"] = float(trades["单笔盈亏"].mean())
    return out


# --------------------------- 核心回测 ---------------------------
def run_backtest(df: pd.DataFrame, signal: pd.Series,
                 initial_capital: float = None, fee_rate: float = None,
                 min_fee: float = None, slippage: float = None,
                 lot_size: int = None) -> BacktestResult:
    """
    在行情 df 上按信号序列执行回测。

    df     : 需含 open / close 列（date 为索引，升序）
    signal : 与 df 索引对齐的 +1/-1/0 信号（由 strategies.generate_signals 产生）
    """
    initial_capital = INIT_CAPITAL if initial_capital is None else float(initial_capital)
    fee_rate = FEE_RATE if fee_rate is None else float(fee_rate)
    min_fee = MIN_FEE if min_fee is None else float(min_fee)
    slippage = SLIPPAGE if slippage is None else float(slippage)
    lot_size = LOT_SIZE if lot_size is None else int(lot_size)

    sig = signal.reindex(df.index).fillna(0).astype(int)
    open_p = df["open"].to_numpy(float)
    close_p = df["close"].to_numpy(float)
    sig_a = sig.to_numpy()
    dates = df.index
    n = len(df)

    def fee(amount: float) -> float:
        return max(amount * fee_rate, min_fee)

    # ---- 策略资金演化（事件驱动，显式现金+份额） ----
    cash = float(initial_capital)
    shares = 0
    entry = None                    # 当前持仓：{entry_date, entry_price, shares, fee}
    equity_vals = np.empty(n)
    trades = []

    for i in range(n):
        # 1) 执行“昨天收盘”产生的信号 -> 今天开盘成交
        if i > 0:
            prev = sig_a[i - 1]
            if prev == 1 and shares == 0 and entry is None:
                fill = open_p[i] * (1 + slippage)
                if fill > 0:
                    # 满仓买入：按一手取整并预留手续费
                    lots = int((cash * 0.999) // (fill * lot_size * (1 + fee_rate)))
                    while lots > 0:
                        buy_shares = lots * lot_size
                        if buy_shares * fill + fee(buy_shares * fill) <= cash:
                            break
                        lots -= 1
                    if lots > 0:
                        buy_shares = lots * lot_size
                        f = fee(buy_shares * fill)
                        cash -= buy_shares * fill + f
                        shares = buy_shares
                        entry = {"entry_date": dates[i], "entry_price": float(fill),
                                 "shares": shares, "fee": f}
            elif prev == -1 and shares > 0 and entry is not None:
                fill = open_p[i] * (1 - slippage)
                f = fee(shares * fill)
                cash += shares * fill - f
                hold_days = (dates[i] - entry["entry_date"]).days
                pnl = shares * (fill - entry["entry_price"]) - entry["fee"] - f
                cost = shares * entry["entry_price"] + entry["fee"]
                trades.append({
                    "买入日期": entry["entry_date"],
                    "买入价": round(entry["entry_price"], 4),
                    "卖出日期": dates[i],
                    "卖出价": round(float(fill), 4),
                    "份额": shares,
                    "持有天数": hold_days,
                    "费用": round(entry["fee"] + f, 2),
                    "单笔盈亏": round(pnl, 2),
                    "单笔收益率": pnl / cost if cost > 0 else 0.0,
                })
                shares = 0
                entry = None

        # 2) 用当日收盘价对持仓估值（市值）
        equity_vals[i] = cash + shares * close_p[i]

    # ---- 买入持有基准：首个交易日开盘一次性满仓 ----
    bh_shares = 0
    if n > 0 and open_p[0] > 0:
        bh_lots = int((initial_capital * 0.999) // (open_p[0] * lot_size * (1 + fee_rate)))
        bh_shares = bh_lots * lot_size
    bench_vals = np.full(n, float(initial_capital))
    for i in range(n):
        bench_vals[i] = bh_shares * close_p[i]  # 全仓，现金为 0

    # ---- 收尾 ----
    trades_df = pd.DataFrame(trades)
    if open_position := entry:
        open_position["mark_price"] = float(close_p[-1])
        open_position["浮动盈亏"] = round(
            shares * (close_p[-1] - entry["entry_price"]) - entry["fee"], 2)

    metrics = compute_metrics(equity_vals, initial_capital)
    bench_metrics = compute_metrics(bench_vals, initial_capital)
    metrics.update(_trade_stats(trades_df, open_position))
    metrics["初始资金"] = initial_capital

    equity = pd.DataFrame({
        "strategy": equity_vals,
        "benchmark": bench_vals,
    }, index=df.index)

    return BacktestResult(
        df=df, equity=equity, trades=trades_df, open_position=open_position,
        metrics=metrics, benchmark_metrics=bench_metrics, initial_capital=initial_capital,
    )


# --------------------------- 展示 ---------------------------
def format_metrics(m: dict) -> str:
    """把指标字典格式化成可打印的多行文本。"""
    pct = ["总收益率", "年化收益率", "最大回撤", "年化波动率"]
    lines = []
    for k, v in m.items():
        if isinstance(v, float) and k in pct:
            lines.append(f"  {k:<8}: {v:>10.2%}")
        elif isinstance(v, float):
            lines.append(f"  {k:<8}: {v:>10.2f}")
        else:
            lines.append(f"  {k:<8}: {v}")
    return "\n".join(lines)


def print_report(result: BacktestResult, title: str = "") -> None:
    """在终端打印一份可读的回测报告。"""
    if title:
        print("=" * 60)
        print(title)
        print("=" * 60)
    print("【策略绩效】")
    print(format_metrics(result.metrics))
    print("\n【买入持有对照】")
    print(format_metrics(result.benchmark_metrics))
    print("\n【交易明细摘要】")
    if result.trades.empty:
        print("  整个回测区间内没有任何完整交易。")
    else:
        head = result.trades.head(15)
        with pd.option_context("display.width", 200, "display.max_columns", 20,
                               "display.float_format", lambda x: f"{x:,.2f}"):
            print(head.to_string(index=False))
        if len(result.trades) > 15:
            print(f"  ... 共 {len(result.trades)} 笔，以上仅显示前 15 笔")
    if result.open_position:
        op = result.open_position
        print(f"\n  期末仍有持仓：{op['entry_date'].date()} 买入 {op['shares']} 份 @ "
              f"{op['entry_price']:.4f}，浮动盈亏 {op['浮动盈亏']:,.2f} 元")
    print("\n")


def plot_result(result: BacktestResult, title: str = "", save_path: str = None):
    """
    绘制：上图为价格 + 买卖点标记，下图为策略 vs 买入持有的资金曲线。
    save_path 给出时保存为 png 文件；否则调用 plt.show()。
    """
    if not _MPL_OK:
        print("matplotlib 不可用，跳过绘图。")
        return
    import matplotlib.pyplot as plt
    try:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "PingFang SC", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    df = result.df
    cap = result.initial_capital

    fig, axes = plt.subplots(2, 1, figsize=(13, 8.5), sharex=True,
                             gridspec_kw={"height_ratios": [2.6, 1.6]})
    ax1, ax2 = axes

    ax1.plot(df.index, df["close"], color="#37474f", lw=1.1, label="收盘价")
    tr = result.trades
    if not tr.empty:
        ax1.scatter(tr["买入日期"], tr["买入价"], marker="^", color="#d32f2f",
                    s=65, zorder=5, label=f"买入（{len(tr)}）")
        ax1.scatter(tr["卖出日期"], tr["卖出价"], marker="v", color="#2e7d32",
                    s=65, zorder=5, label=f"卖出（{len(tr)}）")
    if result.open_position:
        op = result.open_position
        ax1.scatter([op["entry_date"]], [op["entry_price"]], marker="^",
                    color="#d32f2f", s=65, zorder=5)
    ax1.set_title(title)
    ax1.legend(loc="best", fontsize=9)
    ax1.grid(alpha=0.3)
    ax1.set_ylabel("价格")

    net = result.equity / cap
    ax2.plot(net.index, net["strategy"], color="#1565c0", lw=1.6, label="策略")
    ax2.plot(net.index, net["benchmark"], color="#8d6e63", lw=1.2, ls="--", label="买入持有")
    ax2.axhline(1.0, color="gray", lw=0.6, ls=":")
    ax2.legend(loc="best", fontsize=9)
    ax2.grid(alpha=0.3)
    ax2.set_ylabel("净值")
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
