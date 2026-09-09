# -*- coding: utf-8 -*-
"""
网页版工具（Flask 本地服务）
============================
- 在网页里以「满足(条件) → 执行(操作)」的方式录入你的买卖规则；
- 一键跑“条件定投回测”，看收益结果；
- 打开网页即可看“今日买卖提醒”，可填上你的实际持仓做精确判断。

启动： python app.py
然后浏览器打开 http://127.0.0.1:5000
"""

import base64
import io
import json
import os

import pandas as pd
from flask import Flask, jsonify, render_template, request

import config as cfg
import data_fetcher as fetcher
import dca
import alerts
from dca import DCA_DEFAULTS, DEFAULT_SELL_RULES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(BASE_DIR, "rules.json")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# 服务内存中的行情缓存（避免每次请求都联网；东财源不可达时会自动切新浪）
_DATA = {}


def _get_df(code: str, force: bool = False) -> pd.DataFrame:
    df = _DATA.get(code)
    if force or df is None or df.empty:
        df = fetcher.fetch_etf_daily(code, start="20100101", end="20500101")
        _DATA[code] = df
    return df


def _load_saved():
    """读取上一次保存的规则（若存在）。"""
    if os.path.exists(RULES_PATH):
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _as_plain(o):
    """把 numpy 标量转成 JSON 可用类型。"""
    if isinstance(o, dict):
        return {k: _as_plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_as_plain(x) for x in o]
    if hasattr(o, "item"):
        return o.item()
    return o


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(_as_plain({
        "defaults": DCA_DEFAULTS,
        "sell_rules": DEFAULT_SELL_RULES,
        "etfs": cfg.TARGET_ETFS,
        "saved": _load_saved(),
        "params_label": {  # 供前端展示的中文名
            "hist_window": "历史极值/最大涨幅窗口(交易日)",
            "percentile_window": "分位点窗口(交易日)",
            "vol_window": "日均波动窗口(交易日)",
            "a_cut": "A 跌幅阈值(×最大涨幅)",
            "p_low": "B 分位点阈值(%)",
            "gain_trigger": "C 涨幅阈值(×最大涨幅)",
            "p_high": "D 分位点阈值(%)",
            "dd_mult": "E 回撤倍数(×日均波动)",
            "amount_ab": "定投金额-A且B(元)",
            "amount_a": "定投金额-仅A(元)",
            "amount_b": "定投金额-仅B(元)",
            "initial_cash": "定投资金池(元)",
            "fee_rate": "佣金费率",
            "min_fee": "最低佣金(元)",
            "lot": "最小买入单位(份)",
        },
        "rule_actions": [
            {"value": "clear", "label": "清仓(全部卖出)"},
            {"value": "trim_half", "label": "卖出50%仓位"},
            {"value": "pause", "label": "暂停定投(持有观望)"},
        ],
        "rule_conditions": [
            {"value": "A", "label": "A 跌幅足够深"},
            {"value": "B", "label": "B 分位点低"},
            {"value": "C", "label": "C 涨幅足够大"},
            {"value": "D", "label": "D 估值过热"},
            {"value": "E", "label": "E 高位回撤保护"},
        ],
    }))


@app.route("/api/save", methods=["POST"])
def api_save():
    payload = request.get_json(force=True) or {}
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "path": RULES_PATH})


def _load_data(etf: str) -> pd.DataFrame:
    item = next((e for e in cfg.TARGET_ETFS if e["code"] == etf), None)
    if item is None:
        raise ValueError(f"未知 ETF：{etf}")
    return _get_df(item["code"]), item


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    body = request.get_json(force=True) or {}
    etf = body.get("etf", cfg.TARGET_ETFS[0]["code"])
    params = body.get("params") or {}
    rules = body.get("sell_rules") or DEFAULT_SELL_RULES
    start = body.get("start", "20160101")
    try:
        df, item = _load_data(etf)
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if len(df) < 60:
            return jsonify({"error": f"数据不足（{len(df)} 条），请调整起始日期"}), 400

        strat, bench = dca.run_dca_backtest(df, params, sell_rules=rules)
        chart = None
        if body.get("plot"):
            tmp = os.path.join(RESULTS_DIR, "_web_dca.png")
            title = f"{etf} {item['name']} | 条件定投回测 | {df.index[0].date()} ~ {df.index[-1].date()}"
            dca.plot_dca(strat, bench, title, save_path=tmp)
            with open(tmp, "rb") as f:
                chart = "data:image/png;base64," + base64.b64encode(f.read()).decode()

        return jsonify(_as_plain({
            "ok": True,
            "etf": etf,
            "name": item["name"],
            "period": f"{df.index[0].date()} ~ {df.index[-1].date()}（{len(df)} 个交易日）",
            "strategy": strat.metrics,
            "benchmark": bench.metrics,
            "events": strat.events[-30:][::-1],   # 最近 30 条，新的在前
            "chart": chart,
        }))
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/alerts", methods=["POST"])
def api_alerts():
    body = request.get_json(force=True) or {}
    params = body.get("params") or {}
    rules = body.get("sell_rules") or DEFAULT_SELL_RULES
    etf_arg = body.get("etf") or "all"
    etfs = [e for e in cfg.TARGET_ETFS
            if etf_arg == "all" or e["code"] == etf_arg]
    out = []
    for item in etfs:
        try:
            df = _get_df(item["code"])
            rep = alerts.analyze_latest(df.tail(1400), params, sell_rules=rules)
            out.append({"code": item["code"], "name": item["name"],
                        "index": item["index"], "rep": rep,
                        "text": alerts.render_text(rep, f"{item['code']} {item['name']}")})
        except Exception as e:
            out.append({"code": item["code"], "name": item["name"],
                        "error": f"{type(e).__name__}: {e}"})
    return jsonify(_as_plain(out))


@app.route("/api/decide", methods=["POST"])
def api_decide():
    body = request.get_json(force=True) or {}
    params = body.get("params") or {}
    rules = body.get("sell_rules") or DEFAULT_SELL_RULES
    etf = body.get("etf")
    try:
        df, item = _load_data(etf)
        rep = alerts.analyze_latest(df.tail(1400), params, sell_rules=rules)
        dec = alerts.decide_today(
            rep,
            holding=bool(body.get("holding", False)),
            avg_cost=body.get("avg_cost"),
            peak=body.get("peak"),
            sell_rules=rules)
        return jsonify(_as_plain({"ok": True, "rep": rep, "decision": dec,
                                  "name": item["name"]}))
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    body = request.get_json(force=True) or {}
    etf = body.get("etf")
    if etf and etf != "all":
        item = next((e for e in cfg.TARGET_ETFS if e["code"] == etf), None)
        if item is None:
            return jsonify({"error": f"未知 ETF：{etf}"}), 400
        try:
            _get_df(item["code"], force=True)   # 强制重拉
            return jsonify({"ok": True, "msg": f"{etf} 已强制刷新"})
        except Exception as e:
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    return jsonify({"ok": True, "msg": "无需刷新"})


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("*" * 56)
    print("*  宽基 ETF 监测与规则回测 网页版")
    print("*  请用浏览器打开： http://127.0.0.1:5000")
    print("*  Ctrl+C 停止服务")
    print("*" * 56)
    app.run(host="127.0.0.1", port=5000, debug=False)
