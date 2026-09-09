# -*- coding: utf-8 -*-
"""
每日监测模块
============
对每个目标 ETF：拉取近期数据 -> 运行策略生成信号 -> 打印当前建议与状态。
适合每个交易日收盘后运行一次（`python main.py monitor`），
也可配置为定时任务，或将来接入消息推送。

注意：策略信号基于“今天收盘”计算，买/卖需按提示在“次日开盘”执行。
"""

from datetime import date

import pandas as pd

import data_fetcher as fetcher
import strategies
from config import MONITOR_LOOKBACK, TARGET_ETFS


def current_state(sig: pd.Series) -> tuple:
    """
    根据最近信号序列推断当前应处状态。
    返回 (文字说明, 状态码)：
      状态码 1=建议次日买入并持有，-1=建议次日卖出，0=观望/空仓
    """
    s = sig.dropna()
    if s.empty:
        return "数据不足，暂无信号", 0
    last = int(s.iloc[-1])
    if last == 1:
        return "★ 买入信号：建议次日开盘买入", 1
    if last == -1:
        return "★ 卖出信号：建议次日开盘卖出", -1
    # 今天无操作 -> 回溯最近一次非零信号判断持仓状态
    nz = s[s != 0]
    if nz.empty:
        return "尚无买入过，空仓观望", 0
    if int(nz.iloc[-1]) == 1:
        return "持有中：最近一次为买入，今日无卖出信号", 1
    return "空仓：最近一次为卖出，今日无买入信号", 0


def _realtime_price(code: str):
    """
    取实时价（可选增强）。用腾讯行情接口，单次请求、5 秒超时，
    失败返回 None（东财 spot 接口在源不可达时会分页重试导致卡死，故不使用）。
    """
    symbol = ("sh" if code[0] in ("5", "6") else "sz") + code
    try:
        import requests
        r = requests.get(f"https://qt.gtimg.cn/q={symbol}",
                         timeout=5,
                         headers={"User-Agent": "Mozilla/5.0"})
        # 返回形如：v_sh588000="1~科创50ETF华夏~588000~1.671~1.681~..."
        body = r.text.split('="', 1)[1].rsplit('"', 1)[0]
        return float(body.split("~")[3])  # 第 4 个字段是现价
    except Exception:
        return None


def monitor_etf(item: dict, strategy_name: str, params: dict = None,
                lookback: int = MONITOR_LOOKBACK) -> None:
    """对单只 ETF 输出监测结果。"""
    code, name, idx = item["code"], item["name"], item["index"]
    try:
        df = fetcher.fetch_etf_daily(code, start="20050101", end="20500101")
        window = df.tail(lookback).copy()
        sig = strategies.generate_signals(window, strategy_name, params)

        last_date = window.index[-1].date()
        last_close = float(window["close"].iloc[-1])
        today = date.today()
        text, state = current_state(sig)

        print(f"[{code}] {name}（{idx}）")
        print(f"  数据截至: {last_date}   最近收盘: {last_close:.3f}")
        if last_date < today:
            real = _realtime_price(code)
            if real is not None:
                chg = (real / last_close - 1) * 100
                print(f"  实时价格: {real:.3f}（较最近收盘 {chg:+.2f}%）")
            else:
                print("  提示: 数据尚未更新到今日（周末/休市/未收盘）")
        print(f"  建议: {text}")

        # 附带最近 5 个交易日的信号，便于人工核对
        tail = pd.DataFrame({"日期": window.index.date, "收盘": window["close"],
                             "信号": sig.values})[["日期", "收盘", "信号"]].tail(5)
        print("  最近5日: " + " | ".join(
            f"{r['日期']}({['持','买','卖'][int(r['信号'])]}:{r['收盘']:.3f})"
            for _, r in tail.iterrows()))
        print()
    except Exception as e:
        print(f"[{code}] {name} 监测失败：{type(e).__name__}: {e}\n")


def run_monitor(strategy_name: str = "ma_cross", params: dict = None,
                etfs: list = None) -> None:
    """监测 TARGET_ETFS（或传入的子集）。"""
    etfs = etfs if etfs is not None else TARGET_ETFS
    print("=" * 64)
    print(f"宽基 ETF 每日监测  策略: {strategy_name}   "
          f"信号基于当日收盘，次日开盘执行")
    print("=" * 64)
    for item in etfs:
        monitor_etf(item, strategy_name, params)
