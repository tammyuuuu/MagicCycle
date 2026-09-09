# -*- coding: utf-8 -*-
"""
策略模块
========
【重要】这是你日后填写“自己的买卖规则”的地方：只需改写下方 my_strategy 函数。

每个策略都是一个函数：
    def strategy(df, params) -> pd.Series
      - df    : 按日期升序的日线 DataFrame（含 open/high/low/close/volume 列）
      - params: 参数字典（DEFAULT_PARAMS 里定义，命令行可 --params 覆盖）
      - 返回 与 df 等长的信号序列，取值含义：
            +1  -> 买入信号（空仓时次日开盘全仓买入）
            -1  -> 卖出信号（持仓时次日开盘清仓）
             0  -> 无操作

时间约定：信号在第 t 天【收盘后】产生，实际在第 t+1 天【开盘价】成交，
不包含未来数据，可直接用于回测。

内置了 3 个可直接运行的示例策略作对照：ma_cross / rsi_reversal / macd_cross。
"""

import pandas as pd

import indicators as ta

# 各策略默认参数（命令行可用 --params k=v,k=v 覆盖）
DEFAULT_PARAMS = {
    "ma_cross":     {"fast": 20, "slow": 60},
    "rsi_reversal": {"rsi_n": 14, "oversold": 30, "overbought": 70},
    "macd_cross":   {"fast": 12, "slow": 26, "signal": 9},
    "my_strategy":  {"ma_n": 60},
}


# ---------------------------------------------------------------
# 示例策略 1：双均线 —— MA(fast) 上穿 MA(slow) 买入，下穿卖出（趋势跟随）
# ---------------------------------------------------------------
def ma_cross(df, params):
    fast_n = int(params.get("fast", 20))
    slow_n = int(params.get("slow", 60))
    fast = ta.ma(df["close"], fast_n)
    slow = ta.ma(df["close"], slow_n)
    buy = ta.cross_up(fast, slow)
    sell = ta.cross_down(fast, slow)
    return buy.astype(int) - sell.astype(int)


# ---------------------------------------------------------------
# 示例策略 2：RSI 均值回归 —— 从超卖区回升买入，从超买区回落卖出
# ---------------------------------------------------------------
def rsi_reversal(df, params):
    n = int(params.get("rsi_n", 14))
    buy_th = float(params.get("oversold", 30))
    sell_th = float(params.get("overbought", 70))
    r = ta.rsi(df["close"], n)
    buy = (r > buy_th) & (r.shift(1) <= buy_th)
    sell = (r < sell_th) & (r.shift(1) >= sell_th)
    return buy.astype(int) - sell.astype(int)


# ---------------------------------------------------------------
# 示例策略 3：MACD —— DIF 上穿 DEA 买入，下穿卖出（趋势跟随）
# ---------------------------------------------------------------
def macd_cross(df, params):
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    sig_n = int(params.get("signal", 9))
    dif, dea, _ = ta.macd(df["close"], fast, slow, sig_n)
    buy = ta.cross_up(dif, dea)
    sell = ta.cross_down(dif, dea)
    return buy.astype(int) - sell.astype(int)


# ===============================================================
# 【你的策略】my_strategy
# ---------------------------------------------------------------
# 目前先放一个能跑的示例（收盘价上穿 MA60 买入 / 下穿 MA60 卖出）。
# 等把你的具体买卖规则告诉我，我帮你在这里替换成真正的规则即可。
#
# 编写时可自由使用：
#   - df 里的列：open/high/low/close/volume/pct_chg
#   - indicators 里的现成函数：ma/ema/rsi/macd/bollinger/atr/highest/lowest
#     cross_up/cross_down
#   - params 字典里自定义参数，并同步加到上方 DEFAULT_PARAMS
# ===============================================================
def my_strategy(df, params):
    ma_n = int(params.get("ma_n", 60))
    ma_line = ta.ma(df["close"], ma_n)

    # TODO: 在这里实现你自己的买卖规则 ------------------------------
    #   buy  = <你的买入条件>（布尔 Series，True 处发买入信号）
    #   sell = <你的卖出条件>（布尔 Series，True 处发卖出信号）
    # -----------------------------------------------------------------
    buy = (df["close"] > ma_line) & (df["close"].shift(1) <= ma_line.shift(1))
    sell = (df["close"] < ma_line) & (df["close"].shift(1) >= ma_line.shift(1))

    return buy.astype(int) - sell.astype(int)


# ------------------------- 策略注册表 -------------------------
STRATEGIES = {
    "ma_cross":     ma_cross,
    "rsi_reversal": rsi_reversal,
    "macd_cross":   macd_cross,
    "my_strategy":  my_strategy,
}


def list_strategies():
    """列出所有策略及其默认参数（用于命令行展示）。"""
    return {name: dict(DEFAULT_PARAMS.get(name, {})) for name in STRATEGIES}


def generate_signals(df: pd.DataFrame, name: str, params: dict = None) -> pd.Series:
    """
    统一的信号生成入口。
    params 为空时使用该策略的默认参数；返回 +1/-1/0 的整型 Series，
    指标未就绪的前段一律填 0（视为不操作）。
    """
    if name not in STRATEGIES:
        raise KeyError(f"未知策略：{name}，可用：{list(STRATEGIES)}")
    p = dict(DEFAULT_PARAMS.get(name, {}))
    if params:
        p.update(params)
    sig = STRATEGIES[name](df, p)
    return sig.fillna(0).astype(int)
