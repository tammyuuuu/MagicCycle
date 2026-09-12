# -*- coding: utf-8 -*-
"""
今日提醒 → 导出为手机友好的静态网页（用于 GitHub Pages / 任意静态托管）
========================================================================
运行： python export_alerts.py [--out docs/index.html]
生成一个自包含的单文件 HTML（含内嵌 JS，可填“我的持仓”做精确买卖判断）。
然后把它提交推送到仓库，并在 GitHub 仓库 Settings → Pages 里选
“Deploy from a branch: main / docs”，即可用手机访问
https://<你的用户名>.github.io/<仓库名>/ 查看。

规则来源：优先读取 rules.json（网页里保存的规则）；没有则用内置默认。
"""

import json
import os
import sys
from datetime import datetime

import config as cfg
import data_fetcher as fetcher
import alerts

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


def _build_page(etfs_reps, gen_time: str, using_saved: bool,
                stale_note: str = None) -> str:
    """生成单文件 HTML 字符串。etfs_reps 结构见下方 main()。

    stale_note: 有 ETF 因网络故障沿用旧缓存时的提示文案（正常情况为 None）。
    """
    cards = []
    for i, item in enumerate(etfs_reps):
        code, name, idx = item["code"], item["name"], item["index"]
        rep = item["rep"]
        if rep.get("error"):
            cards.append(f'<div class="card"><div class="t">{code} {name}</div>'
                         f'<div class="err">数据/计算失败：{rep["error"]}</div></div>')
            continue
        chips = ("<span class='chip " + ("on" if rep["A_跌幅足够深"] else "off") + "'>跌幅深 A</span>"
                 + "<span class='chip " + ("on" if rep["B_分位点低"] else "off") + "'>低位 B</span>"
                 + "<span class='chip " + ("on red" if rep["D_过热"] else "off") + "'>过热 D</span>")
        if rep["暂停定投"]:
            advise = "<div class='adv warn'>🛑 过热 → 暂停定投，持有观望（0 元）</div>"
        else:
            advise = ("<div class='adv ok'>✅ 若定投：<b>%g 元</b>（%s）</div>"
                      % (rep["建议定投金额"], rep["定投档位"]))
        # 规则参考（只读）
        refs = []
        for h in rep["sell_hints"]:
            r = []
            if h.get("ref"):
                r.append("E触发：持仓最高≥%s" % h["ref"]["value"])
            if h.get("ref2"):
                r.append("C触发：成本≤%s" % h["ref2"]["value"])
            if h.get("note"):
                r.append("D过热")
            tag = ("<b class='red'>●</b>" if h.get("active")
                   else "<span class='muted'>○</span>")
            refs.append("<li>%s %s：%s</li>" % (tag, h["name"].split("（")[0], "；".join(r) or "需填持仓判断"))
        ref_html = "<ul class='refs'>%s</ul>" % "".join(refs)

        cards.append(f"""
<div class="card">
  <div class="t"><span class="code">{code}</span> {name} <span class="muted">{idx}</span>
      <span class="chip {'on' if rep['today_is_dca_day'] else 'off'}">{'本周定投日' if rep['today_is_dca_day'] else '非定投日'}</span></div>
  <div class="meta">数据日 {rep['date']} · 收盘 <b>{rep['close']}</b> ·
      分位 <b>{rep['pct'] if rep['pct'] is None else str(rep['pct'])+'%'}</b> ·
      历史最大涨幅 <b>{'%d%%' % (rep['max_gain']*100)}</b> ·
      日均波动 <b>{'%.2f%%' % (rep['vol']*100)}</b></div>
  <div class="meta muted">5年区间：{rep['hist_low']} ~ {rep['hist_high']}</div>
  <div style="margin:6px 0">{chips} <span class="muted">C涨幅/E回撤需填持仓判断</span></div>
  {advise}
  <details>
    <summary>填我的实际持仓，精判断今天该买/卖</summary>
    <div class="posrow">
      <label><input type="checkbox" id="hol_{i}"> 持有</label>
      <span><label>平均成本</label><input type="number" step="0.001" id="ac_{i}" placeholder="如 5.2"></span>
      <span><label>持仓期最高价</label><input type="number" step="0.001" id="pk_{i}" placeholder="如 8.0"></span>
      <button class="btn" onclick="decide({i})">判断</button>
    </div>
    <div id="dec_{i}"></div>
  </details>
  <details>
    <summary>卖出规则触发参考</summary>
    {ref_html}
  </details>
</div>""")
    body = "\n".join(cards)
    notice = (f'<div class="notice">{stale_note}</div>' if stale_note else "")
    rep_json = json.dumps([i["rep"] for i in etfs_reps], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ETF 今日提醒 {gen_time[:10]}</title>
<style>
 /* 梵高油画配色：群青夜空 + 麦金 + 米白画布（中度浓度） */
 :root{{--night:#141f45;--ultra:#1e2d63;--cobalt:#2f5aa8;--gold:#e8b21f;--gold-lt:#f2c744;
   --amber:#a8620a;--crimson:#9c2f24;--cypress:#2f5a3c;--canvas:#f4ecda;--card:#fbf6ea;
   --ink:#2b1f14;--line:#d8c9a8}}
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);
   background:
     radial-gradient(120% 80% at 10% 0%,rgba(47,90,168,.18) 0%,rgba(47,90,168,0) 55%),
     radial-gradient(90% 60% at 90% 6%,rgba(232,178,31,.20) 0%,rgba(232,178,31,0) 60%),
     radial-gradient(100% 70% at 80% 100%,rgba(30,45,99,.14) 0%,rgba(30,45,99,0) 65%),
     repeating-linear-gradient(45deg,rgba(43,31,20,.022) 0 2px,rgba(43,31,20,0) 2px 5px),
     repeating-linear-gradient(-45deg,rgba(43,31,20,.018) 0 2px,rgba(43,31,20,0) 2px 5px),
     var(--canvas)}}
 /* 暗角，像画布边缘压深 */
 body::after{{content:"";position:fixed;inset:0;pointer-events:none;z-index:9;
   background:radial-gradient(125% 105% at 50% 42%,rgba(0,0,0,0) 55%,rgba(20,31,69,.13) 100%)}}
 .wrap{{max-width:640px;margin:0 auto;padding:12px;position:relative;z-index:1}}
 header{{position:relative;z-index:2;background:linear-gradient(135deg,var(--night) 0%,var(--ultra) 55%,#2a3f7d 100%);
   color:#fdf6e3;padding:13px 16px;border-bottom:3px solid var(--gold);box-shadow:0 2px 6px rgba(20,31,69,.28)}}
 h1{{font-family:Georgia,"Songti SC","SimSun",serif;font-size:19px;margin:4px 0;font-weight:600;letter-spacing:.4px}}
 .card{{background:linear-gradient(160deg,#fdf9ee 0%,var(--card) 50%,#f7efdd 100%);border:1px solid var(--line);
   border-radius:10px;padding:14px;margin:12px 0;
   box-shadow:0 2px 6px rgba(43,31,20,.10),inset 0 1px 0 rgba(255,255,255,.85)}}
 .t{{font-size:16px;font-weight:700;margin-bottom:6px;font-family:Georgia,"Songti SC",serif}}
 .code{{color:var(--cobalt);letter-spacing:.5px}}
 .meta{{font-size:13px;color:#5c4a35;margin:2px 0}}
 .chip{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;margin:3px 3px 0 0;border:1px solid transparent}}
 .chip.on{{background:#d9e3c6;color:#315a35;border-color:#bccfa3}}
 .chip.on.red{{background:#f1d5c9;color:var(--crimson);border-color:#dfb4a4}}
 .chip.off{{background:#ece2cd;color:#9c8f79;border-color:#ddd0b6}}
 .adv{{font-size:16px;font-weight:700;margin:8px 0;font-family:Georgia,"Songti SC",serif}}
 .adv.ok{{color:var(--cypress)}} .adv.warn{{color:var(--amber)}}
 .muted{{color:#9c8f79;font-size:12px}}
 .red{{color:var(--crimson)}}
 details{{margin-top:6px}}
 summary{{cursor:pointer;font-size:13.5px;color:var(--cobalt);padding:4px 0}}
 .refs{{margin:6px 0 2px 0;padding-left:18px;font-size:13px}}
 .posrow{{display:flex;gap:10px;flex-wrap:wrap;align-items:end;padding:6px 0}}
 .posrow label{{font-size:12px;color:#6b5a44;display:block}}
 input[type=number]{{width:96px;padding:5px;border:1px solid var(--line);border-radius:6px;background:#fdfaf1;color:var(--ink);font-family:Georgia,serif}}
 .btn{{background:linear-gradient(180deg,#3a6ac0,var(--cobalt));color:#fdf6e3;border:1px solid #24487f;
   border-radius:7px;padding:7px 14px;cursor:pointer;font-weight:600;box-shadow:0 2px 5px rgba(20,31,69,.22)}}
 .ok{{color:var(--cypress);font-weight:600}} .warn{{color:var(--amber);font-weight:600}} .bad{{color:var(--crimson);font-weight:600}}
 .err{{color:var(--crimson);font-size:13px}}
 .notice{{background:#f8ecc9;color:#8a5a10;border:1px solid #e6cf94;border-left:4px solid var(--gold);
   border-radius:10px;padding:10px 12px;margin:12px 0;font-size:13px;font-weight:600;line-height:1.5}}
 footer{{color:#9c8f79;font-size:12px;text-align:center;padding:16px}}
</style></head><body>
<header><h1>📈 宽基 ETF 今日买卖提醒</h1><div style="font-size:12px;opacity:.8">生成于 {gen_time}{' · 使用网页保存的规则' if using_saved else ' · 使用内置默认规则'}</div></header>
<div class="wrap">{notice}{body}
<footer>数据：AkShare（东方财富/新浪）· 仅供策略研究，非投资建议</footer></div>
<script>
var REPS = {rep_json};
var LABEL = {{clear:'清仓(全部卖出)',trim_half:'卖出50%',pause:'暂停定投'}};
function decide(i){{
  var rep=REPS[i], p=rep.params;
  var hol=document.getElementById('hol_'+i).checked;
  var ac=parseFloat(document.getElementById('ac_'+i).value), pk=parseFloat(document.getElementById('pk_'+i).value);
  var close=rep.close, mg=rep.max_gain, vol=rep.vol;
  var cond={{A:rep['A_跌幅足够深'],B:rep['B_分位点低'],D:rep['D_过热']}};
  if(hol&&ac>0&&mg) cond.C = (close/ac-1) >= mg*p.gain_trigger;
  if(hol&&pk>0&&vol) cond.E = pk>=close && (pk-close)/pk >= vol*p.dd_mult;
  // 定投判断
  var paused = cond.D && rep.sell_rules.some(r=>r.enabled&&r.action==='pause'&&(r.conds||[]).indexOf('D')>=0);
  var amt=0, tier='', cls='ok';
  if(paused){{tier='🛑 过热→暂停定投(0元)';cls='warn';}}
  else if(cond.A&&cond.B){{amt=p.amount_ab;tier='A且B';}}
  else if(cond.A){{amt=p.amount_a;tier='仅A';}}
  else if(cond.B){{amt=p.amount_b;tier='仅B';}}
  else {{tier='不满足买入条件';cls='warn';}}
  // 仓位决策（首个命中）
  var sats=Object.keys(cond).filter(k=>cond[k]); var decision=null;
  var rules=rep.sell_rules.slice().sort((a,b)=>a.priority-b.priority);
  for(var j=0;j<rules.length;j++){{var r=rules[j]; if(!r.enabled) continue; var need=r.conds||[];
    var fire = (need.length===1&&need[0]==='C') ? (cond.C&&!cond.D) : need.every(x=>cond[x]);
    if(fire){{decision=r; break;}} }}
  var box=document.getElementById('dec_'+i);
  var c='<div class="meta">'+'当前条件：'+Object.keys(cond).filter(k=>cond[k]).map(k=>k+'✓').join(' ')||'—'+'</div>';
  c+='<div class="'+cls+'">定投：'+(amt>0?'可投 '+amt+' 元（'+tier+'）':tier)+'</div>';
  if(!hol) c+='<div class="muted">未填“持有”，仅看定投资格。</div>';
  else if(decision) c+='<div class="bad">卖出建议：'+LABEL[decision.action]+'（'+decision.name.split('（')[0]+'）</div>';
  else c+='<div class="ok">无卖出/减仓信号，继续持有。</div>';
  box.innerHTML=c;
}}
</script></body></html>"""


def main(out_path: str = DEFAULT_OUT):
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
            rep = alerts.analyze_latest(df.tail(1400), params, sell_rules=rules)
            etfs_reps.append({"code": item["code"], "name": item["name"],
                              "index": item["index"], "rep": rep})
        except Exception as e:
            etfs_reps.append({"code": item["code"], "name": item["name"],
                              "index": item["index"],
                              "rep": {"error": f"{type(e).__name__}: {e}"}})

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    stale_note = ("⚠ 网络异常：以下为本地旧数据，未能更新到最新交易日（"
                  + "；".join(stale_notes) + "）") if stale_notes else None
    html = _build_page(etfs_reps, gen_time, using_saved, stale_note)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成：{out_path}")
    print("下一步：把 docs/ 提交推送后，在 GitHub 仓库 Settings → Pages")
    print("        选 Deploy from a branch: main / docs，即可手机访问")
    print("        https://<你的用户名>.github.io/<仓库名>/")
    if not using_saved:
        print("[提示] 未找到 rules.json，使用的是内置默认规则。可在网页里“保存为默认规则”后重新导出。")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="导出今日提醒静态页")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出 HTML 路径")
    args = parser.parse_args()
    main(args.out)
