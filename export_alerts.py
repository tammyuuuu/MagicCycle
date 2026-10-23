from pathlib import Path
# -*- coding: utf-8 -*-
"""
今日提醒 → 导出为手机友好的静态网页（用于 GitHub Pages / 任意静态托管）
========================================================================
运行： python export_alerts.py [--out docs/index.html]
生成包含现有四页与关键样式的自包含 HTML。
然后把它提交推送到仓库，并在 GitHub 仓库 Settings → Pages 里选
“Deploy from a branch: main / docs”，即可用手机访问
https://<你的用户名>.github.io/<仓库名>/ 查看。

规则来源：优先读取 rules.json（网页里保存的规则）；没有则用内置默认。
"""

import valuation_data
import json
import os
import sys
import shutil
from datetime import datetime, timezone, timedelta

import config as cfg
import data_fetcher as fetcher
import strategies
from asset_states import STATE_CATALOG, render_rail, render_basis, render_today_categories, DISPLAY_STATUS_MAP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(BASE_DIR, "rules.json")
DEFAULT_OUT = os.path.join(BASE_DIR, "docs", "index.html")


def _load_rules():
    """优先读网页保存的规则；否则用内置默认。返回 (params, sell_rules)。"""
    if os.path.exists(RULES_PATH):
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            params = saved.get("params")
            rules = saved.get("sell_rules")
            if params and rules:
                return params, rules
        except Exception:
            pass
    return None, None


def _summary_card(summary, extra=""):
    from html import escape
    metric = summary["metrics"]
    delta = metric["day_change_pct"]
    change = f"{delta:+.2f}%" if delta is not None else "暂无"
    return (f'<div class="card" data-asset-symbol="{escape(summary["symbol"], quote=True)}"><h2>{escape(summary["name"])} <span class="muted">{escape(summary["symbol"])}</span></h2>'
            f'<p>数据日 {summary["date"]} · 当前 {metric["price"]} · 当日涨跌 {change}</p>'
            f'{render_rail(summary)}'
            f'<details><summary>查看判断依据</summary>{render_basis(summary)}</details>{extra}</div>')


def _build_page(etfs_reps, gen_time: str, using_saved: bool,
                stale_note: str = None, access_snapshot=None, *, output_dir=None) -> str:
    """生成单文件 HTML 字符串。etfs_reps 结构见下方 main()。

    stale_note: 有 ETF 因网络故障沿用旧缓存时的提示文案（正常情况为 None）。
    """
    cards = []
    for i, item in enumerate(etfs_reps):
        code, name, idx = item["code"], item["name"], item["index"]
        signal_code = item.get("signal_code")
        rep = item["rep"]
        if rep.get("error"):
            cards.append(f'<div class="card"><h2>{code} {name}</h2>'
                         f'<div class="err">数据/计算失败：{rep["error"]}</div></div>')
            continue
        summary = item.get("summary")
        if summary:
            extra = ""
            if item.get("signal_code"):
                extra += f'<p class="muted">参考行情：{item["signal_code"]}；并非联接基金实际净值。</p>'
            cards.append(_summary_card(summary, extra))
            continue
        # Legacy card fields are not part of the current signal UI.
        cards.append('<div class="card"><p class="err">信号摘要暂不可用，请重新生成。</p></div>')
    from correlation_data import investment_script as build_investment_script
    investment_script = build_investment_script(access_snapshot) if output_dir is None else ''
    with open(os.path.join(BASE_DIR, "templates", "_invest_tools.html"), encoding="utf-8") as f:
        investment_tools = f.read().replace("{{ investment_script | safe }}", investment_script)
    if output_dir is not None:
        from correlation_data import static_investment_scripts
        tags,assets=static_investment_scripts(access_snapshot,output_dir)
        investment_tools=investment_tools.replace('<script></script>',tags)
        Path(output_dir,'bundle-assets.json').write_text(json.dumps(assets),encoding='utf8')
    categories = {'broad': [], 'us': [], 'industry': [], 'macro': []}
    for card, item in zip(cards, etfs_reps):
        key = ('us' if item.get('strategy_mode') == 'us_monthly_trend' else
               {'sector_etf': 'industry', 'macro_asset': 'macro'}.get(item.get('asset_type'), 'broad'))
        categories[key].append(card)
    today_page = render_today_categories({key: ''.join(value) for key, value in categories.items()})
    body = (f'<section id="page-today" class="page-section">{today_page}</section>'
            f'{investment_tools}')
    notice = ""  # Dates and stale-data state are shown on each asset card.
    with open(os.path.join(BASE_DIR, "templates", "_status_rail.html"), encoding="utf-8") as f:
        status_assets = f.read().replace("{{ asset_state_catalog | tojson }}", json.dumps(STATE_CATALOG, ensure_ascii=False)).replace("{{ asset_state_map | tojson }}", json.dumps(DISPLAY_STATUS_MAP, ensure_ascii=False))
    page_styles = Path(BASE_DIR, "templates", "_styles.html").read_text(encoding="utf8")
    return f"""<!DOCTYPE html>
<!-- 自动生成文件：请勿直接编辑。账户页面在 templates/_invest_tools.html，研究数据由 workspace_data/manifest.json 指定。 -->
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#202e4b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="星循">
<link rel="apple-touch-icon" sizes="180x180" href="./icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="./icons/favicon-32.png">
<link rel="manifest" href="./manifest.webmanifest">
<script src="./pwa.js" defer></script>
<title>星循 · 观察周期，记录投资</title>
{page_styles}</head><body>{status_assets}
<header class="site-header"><div class="brand-lockup"><img class="brand-emblem" src="./assets/brand-badge.png" width="64" height="64" alt="" aria-hidden="true"><div class="brand-copy"><div class="brand-heading"><h1>星循</h1><span class="brand-tagline">观察周期，记录投资</span></div><div class="brand-updated"><span class="brand-clock" aria-hidden="true"></span>更新于 <time>{gen_time}</time></div></div></div>
<nav id="topnav"><a data-page="today" class="active"><svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2m6 2V2M8 10h8m-8 4h5"/></svg><span>今日提醒</span></a><a data-page="plan"><svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h16M6 16v-5m6 5V5m6 11V8"/></svg><span>投资配置</span></a><a data-page="review"><svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 6C9 4 5 4 3 5v15c3-1 6-1 9 1 3-2 6-2 9-1V5c-2-1-6-1-9 1v15Z"/></svg><span>投资复盘</span></a><a data-page="lab"><svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m16 8-2 6-6 2 2-6 6-2Z"/></svg><span>策略实验</span></a></nav></header>
<div class="wrap">{notice}{body}
<footer>数据：AkShare（东方财富/新浪）· 仅供策略研究，非投资建议</footer></div>
<script>
window.STRATEGY_SUMMARIES={json.dumps([i.get("summary") for i in etfs_reps], ensure_ascii=False)};
refreshValuationPreference();
</script></body></html>"""


def main(out_path: str = DEFAULT_OUT, offline: bool = False, *, _local_only: bool = False):
    # Local maintenance builds use the same renderer and signal calculations.
    if offline:
        import pandas as pd
        from unittest.mock import patch
        def cached_price(code, **kwargs):
            paths = sorted(Path(BASE_DIR, "data_cache").glob(f"etf_{code}_*.csv"))
            if not paths:
                raise ValueError("本地行情缓存缺失")
            selected = next((p for p in paths if "tencent" in p.name), paths[0])
            frame = pd.read_csv(selected, index_col=0, parse_dates=True).sort_index()
            frame.attrs["stale_note"] = f"{code} 缓存截至 {frame.index[-1].date()}"
            return frame
        def cached_valuation(item, as_of, force=False):
            code = item.get("valuation_index") or valuation_data.INDEX_CODES.get(item.get("index"))
            source = Path(valuation_data.CACHE_DIR, "valuation_" + code.replace(".", "_") + ".csv") if code else None
            if source is None or not source.exists():
                return {"error": "本地估值缓存缺失"}
            history = pd.read_csv(source, parse_dates=["date"])
            result = valuation_data.summarize(history, as_of)
            result["windows"] = {str(y): valuation_data.summarize(history, as_of, y) for y in (3, 5, 10)}
            return result
        def cached_access(*args, **kwargs):
            return json.loads(Path(BASE_DIR, "docs", "purchase_monitor.json").read_text(encoding="utf8"))
        with patch.object(fetcher, "fetch_etf_daily", cached_price), patch.object(valuation_data, "get_valuation", cached_valuation), patch("purchase_monitor.update_snapshot", cached_access):
            return main(out_path, _local_only=True)

    params, rules = _load_rules()
    using_saved = params is not None and rules is not None

    etfs_reps = []
    stale_notes = []
    for item in cfg.TARGET_ETFS:
        try:
            df = fetcher.fetch_etf_daily(item["code"], start="20100101",
                                         end="20500101")
            # 网络故障时 fetch_etf_daily 会退回本地旧缓存，并在 attrs 里留标记
            if df.attrs.get("stale_note"):
                stale_notes.append(df.attrs["stale_note"])
            summary = strategies.analyze_asset(df, valuation_data.attach_valuation(item, df.index[-1].date().isoformat()), overrides=params if item.get("asset_type") == "broad_etf" else None, sell_rules=rules)
            rep = summary["details"]["legacy"] or {"date": summary["date"], "close": summary["metrics"]["price"]}
            etfs_reps.append({**item, "rep": rep, "summary": summary})
        except Exception as e:
            etfs_reps.append({**item,
                              "rep": {"error": f"{type(e).__name__}: {e}"}})

    gen_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    stale_note = (("本地缓存构建：未联网核实最新行情（" if _local_only else "⚠ 网络异常：使用本地缓存，是否为最新交易日尚未核实；休市期间无新增行情（")
                  + "；".join(stale_notes) + "）") if stale_notes else None
    from purchase_monitor import update_snapshot
    access_snapshot = update_snapshot(os.path.join(os.path.dirname(os.path.abspath(out_path)), 'purchase_monitor.json'))
    from account_nav import build_snapshot
    account_quotes = build_snapshot(refresh=not _local_only)
    html = _build_page(etfs_reps, gen_time, using_saved, stale_note, access_snapshot, output_dir=os.path.dirname(os.path.abspath(out_path)))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # PWA resources live beside the exported HTML, including for --out.
    output_dir = os.path.dirname(os.path.abspath(out_path))
    source_dir = os.path.join(BASE_DIR, "docs")
    if os.path.normcase(output_dir) != os.path.normcase(source_dir):
        for asset in ("pwa.js", "sw.js", "manifest.webmanifest"):
            shutil.copy2(os.path.join(source_dir, asset), output_dir)
        shutil.copytree(os.path.join(source_dir, "icons"), os.path.join(output_dir, "icons"), dirs_exist_ok=True)
        shutil.copytree(os.path.join(source_dir, "assets"), os.path.join(output_dir, "assets"), dirs_exist_ok=True)
    with open(os.path.join(output_dir, "account_nav.json"), "w", encoding="utf8") as f:
        json.dump(account_quotes, f, ensure_ascii=False, allow_nan=False)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    from build_pwa_release import build_release
    build_release(output_dir)
    json_path = os.path.splitext(out_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([i.get("summary") or {"symbol": i["code"], "name": i["name"], "asset_type": i.get("asset_type"), "status": "error", "action": "数据暂不可用", "reason": "行情获取或计算失败，请稍后刷新。", "risk_level": "unknown", "metrics": {}, "details": {"error": i["rep"].get("error")}} for i in etfs_reps], f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"已生成：{out_path} 和 {json_path}")
    print("本地文件生成完成。")
    if not using_saved:
        print("[提示] 未找到 rules.json，使用的是内置默认规则。可在网页里“保存为默认规则”后重新导出。")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="导出今日提醒静态页")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出 HTML 路径")
    parser.add_argument("--offline", action="store_true", help="仅使用本地行情、估值和渠道缓存，不联网、不发布")
    args = parser.parse_args()
    main(args.out, offline=args.offline)
