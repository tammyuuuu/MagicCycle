# -*- coding: utf-8 -*-
"""
命令行入口
==========
用法示例
--------
  # 1) 先拉取/刷新数据缓存
  python main.py fetch                     # 刷新所有目标 ETF
  python main.py fetch --etf 510500

  # 2) 历史回测
  python main.py backtest --etf all --strategy ma_cross --start 20180101
  python main.py backtest --etf 510500 --strategy my_strategy --save
  python main.py backtest --etf 588000 --strategy rsi_reversal --params "rsi_n=7,oversold=25"

  # 3) 每日监测当前信号
  python main.py monitor
  python main.py monitor --strategy ma_cross --etf all

  # 4) 查看内置策略
  python main.py list
"""

import argparse
import os
import sys

import pandas as pd

# 让脚本可以在项目根目录直接运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import data_fetcher as fetcher
import strategies
from backtest import plot_result, print_report, run_backtest
from monitor import run_monitor


# --------------------------- 工具函数 ---------------------------
def resolve_etfs(etf_arg: str):
    """把 --etf 参数解析成标的列表：'all' 或 具体代码/名称子串。"""
    if not etf_arg or etf_arg.lower() == "all":
        return config.TARGET_ETFS
    if etf_arg.isdigit():
        match = [e for e in config.TARGET_ETFS if e["code"] == etf_arg]
    else:
        match = [e for e in config.TARGET_ETFS if etf_arg in (e["name"] + e["index"])]
    if not match:
        raise SystemExit(f"未找到标的：{etf_arg}。可选：all / {', '.join(e['code'] for e in config.TARGET_ETFS)}")
    return match


def parse_params(text: str) -> dict:
    """把 'fast=20,slow=60' 解析成 {'fast': 20, 'slow': 60}。"""
    out = {}
    if not text:
        return out
    for pair in text.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        try:
            out[k] = int(v) if float(v).is_integer() else float(v)
        except ValueError:
            out[k] = v
    return out


# --------------------------- 子命令 ---------------------------
def cmd_fetch(args) -> None:
    etfs = resolve_etfs(args.etf)
    for item in etfs:
        code = item["code"]
        print(f"拉取 {code} {item['name']} ...")
        try:
            df = fetcher.fetch_etf_daily(code, start=args.start, end=args.end,
                                         force=args.force)
            print(f"  共 {len(df)} 条，{df.index[0].date()} ~ {df.index[-1].date()}")
        except Exception as e:
            print(f"  失败：{type(e).__name__}: {e}")
    print("完成。")


def cmd_backtest(args) -> None:
    etfs = resolve_etfs(args.etf)
    for item in etfs:
        code, name = item["code"], item["name"]
        print(f"\n>>> 正在回测 {code} {name}，策略 {args.strategy} ...")
        try:
            df = fetcher.fetch_etf_daily(code, start=args.start, end=args.end)
            # 缓存可能比请求区间更宽，按用户指定区间切片
            if args.start != "":
                df = df[df.index >= pd.Timestamp(args.start)]
            if args.end != "":
                df = df[df.index <= pd.Timestamp(args.end)]
            sig = strategies.generate_signals(df, args.strategy, parse_params(args.params))
            res = run_backtest(df, sig, initial_capital=args.capital)

            period = f"{df.index[0].date()} ~ {df.index[-1].date()}（{len(df)} 个交易日）"
            title = f"{code} {name} | 策略: {args.strategy} | {period}"
            print_report(res, title)

            if args.save:
                os.makedirs("results", exist_ok=True)
                base = f"results/{code}_{args.strategy}_{df.index[0]:%Y%m%d}_{df.index[-1]:%Y%m%d}"
                if not res.trades.empty:
                    res.trades.to_csv(base + "_trades.csv", index=False,
                                      encoding="utf-8-sig")
                    print(f"交易明细已保存：{base}_trades.csv")
                if args.plot:
                    plot_result(res, title, save_path=base + ".png")
            elif args.plot:
                plot_result(res, title)  # 弹窗展示
        except Exception as e:
            print(f"  回测失败：{type(e).__name__}: {e}")


def cmd_monitor(args) -> None:
    run_monitor(args.strategy, parse_params(args.params),
                etfs=resolve_etfs(args.etf))


def cmd_list(_args) -> None:
    print("内置策略与默认参数：")
    for name, p in strategies.list_strategies().items():
        print(f"  - {name:<14} 默认参数: {p}")
    print("\n在 my_strategy 中实现你自己的买卖规则后，用 --strategy my_strategy 调用。")


# --------------------------- 定投(DCA)回测 ---------------------------
def cmd_dca(args) -> None:
    import dca as dca_mod
    rules = None
    if args.rules:
        import json
        with open(args.rules, "r", encoding="utf-8") as fp:
            rules = json.load(fp)
    params = parse_params(args.params) if args.params else {}
    etfs = resolve_etfs(args.etf)
    for item in etfs:
        code, name = item["code"], item["name"]
        print(f"\n>>> 正在回测（条件定投） {code} {name} ...")
        try:
            df = fetcher.fetch_etf_daily(code, start=args.start, end=args.end)
            if args.start:
                df = df[df.index >= pd.Timestamp(args.start)]
            if args.end:
                df = df[df.index <= pd.Timestamp(args.end)]
            if len(df) < 60:
                print(f"  数据不足（{len(df)} 条），跳过。")
                continue
            strat, bench = dca_mod.run_dca_backtest(df, params, sell_rules=rules)
            period = f"{df.index[0].date()} ~ {df.index[-1].date()}（{len(df)} 个交易日）"
            title = f"{code} {name} | 条件定投回测 | {period}"
            dca_mod.print_dca_report(strat, bench, title)
            if args.save or args.plot:
                os.makedirs("results", exist_ok=True)
                base = f"results/{code}_dca_{df.index[0]:%Y%m%d}_{df.index[-1]:%Y%m%d}"
                dca_mod.plot_dca(strat, bench, title, save_path=base + ".png"
                                 if args.save else None)
                if args.save:
                    # 动作日志
                    pd.DataFrame(strat.events).to_csv(base + "_events.csv",
                                                      index=False, encoding="utf-8-sig")
                    print(f"动作日志已保存：{base}_events.csv")
        except Exception as e:
            print(f"  回测失败：{type(e).__name__}: {e}")


def cmd_alerts(args) -> None:
    import alerts as alerts_mod
    params = parse_params(args.params) if args.params else {}
    rules = None
    if args.rules:
        import json
        with open(args.rules, "r", encoding="utf-8") as fp:
            rules = json.load(fp)
    etfs = resolve_etfs(args.etf)
    for item in etfs:
        code, name = item["code"], item["name"]
        print("\n" + "-" * 60)
        try:
            df = fetcher.fetch_etf_daily(code, start="20050101", end="20500101")
            rep = alerts_mod.analyze_latest(df.tail(1400), params, sell_rules=rules)
            print(alerts_mod.render_text(rep, f"{code} {name}"))
        except Exception as e:
            print(f"[{code}] {name} 提醒计算失败：{type(e).__name__}: {e}")


# --------------------------- 主入口 ---------------------------
def main() -> None:
    # Windows 控制台中文输出
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="宽基 ETF 数据获取 / 策略回测 / 每日监测工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # fetch
    p_fetch = sub.add_parser("fetch", help="拉取/刷新本地数据缓存")
    p_fetch.add_argument("--etf", default="all", help="ETF 代码/名称，或 all")
    p_fetch.add_argument("--start", default=config.DEFAULT_START)
    p_fetch.add_argument("--end", default=config.DEFAULT_END)
    p_fetch.add_argument("--force", action="store_true", help="忽略缓存强制全量拉取")
    p_fetch.set_defaults(func=cmd_fetch)

    # backtest
    p_bt = sub.add_parser("backtest", help="历史回测")
    p_bt.add_argument("--etf", default="all", help="ETF 代码/名称，或 all")
    p_bt.add_argument("--start", default=config.DEFAULT_START)
    p_bt.add_argument("--end", default=config.DEFAULT_END)
    p_bt.add_argument("--strategy", default="ma_cross",
                      help="策略名（strategies.py 中注册的），默认 ma_cross")
    p_bt.add_argument("--params", default="", help="覆盖策略参数，如 fast=20,slow=60")
    p_bt.add_argument("--capital", type=float, default=config.INIT_CAPITAL)
    p_bt.add_argument("--plot", action="store_true", help="绘制图表（默认 False）")
    p_bt.add_argument("--save", action="store_true",
                      help="把交易明细与图表保存到 results/ 目录")
    p_bt.set_defaults(func=cmd_backtest)

    # monitor
    p_m = sub.add_parser("monitor", help="每日监测当前买卖信号")
    p_m.add_argument("--etf", default="all")
    p_m.add_argument("--strategy", default="ma_cross")
    p_m.add_argument("--params", default="")
    p_m.set_defaults(func=cmd_monitor)

    # list
    sub.add_parser("list", help="列出内置策略").set_defaults(func=cmd_list)

    # dca
    p_dca = sub.add_parser("dca", help="条件定投回测（估值/回撤规则）")
    p_dca.add_argument("--etf", default="all")
    p_dca.add_argument("--start", default="20160101")
    p_dca.add_argument("--end", default="20500101")
    p_dca.add_argument("--params", default="",
                       help="覆盖参数，如 hist_window=1260,amount_ab=300")
    p_dca.add_argument("--rules", default="", help="卖出/管理规则 JSON 文件（可选）")
    p_dca.add_argument("--plot", action="store_true")
    p_dca.add_argument("--save", action="store_true", help="保存图表与动作日志到 results/")
    p_dca.set_defaults(func=cmd_dca)

    # alerts
    p_al = sub.add_parser("alerts", help="今日买卖点提醒")
    p_al.add_argument("--etf", default="all")
    p_al.add_argument("--params", default="")
    p_al.add_argument("--rules", default="")
    p_al.set_defaults(func=cmd_alerts)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
