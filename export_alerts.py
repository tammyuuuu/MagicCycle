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
import industry_strategy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(BASE_DIR, "rules.json")
DEFAULT_OUT = os.path.join(BASE_DIR, "docs", "index.html")
GUIDE_PATH = os.path.join(BASE_DIR, "templates", "_strategy_guide.html")


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
        signal_code = item.get("signal_code")
        rep = item["rep"]
        if rep.get("error"):
            cards.append(f'<div class="card"><div class="t">{code} {name}</div>'
                         f'<div class="err">数据/计算失败：{rep["error"]}</div></div>')
            continue
        chips = ("<span class='chip " + ("on" if rep["A_跌幅足够深"] else "off") + "'>大幅回撤（A）</span>"
                 + "<span class='chip " + ("on" if rep["B_分位点低"] else "off") + "'>历史低位（B）</span>"
                 + "<span class='chip " + ("on red" if rep["D_过热"] else "off") + "'>历史高位（D）</span>")
        if rep.get("strategy_type") == "industry":
            chips = (f"<span class='chip {'on red' if rep['trend_weak'] else 'off'}'>短期趋势转弱</span>"
                     f"<span class='chip {'on' if rep['recovered_fast'] else 'off'}'>MA20恢复</span>"
                     f"<span class='chip {'on red' if rep['defensive_watch'] else 'off'}'>防守观察</span>")
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

        if rep.get("strategy_type") == "industry":
            metrics_html = (f'数据日 {rep["date"]} · 收盘 <b>{rep["close"]}</b> · '
                            f'MA20 <b>{rep["ma20"]}</b> · MA60 <b>{rep["ma60"]}</b> · '
                            f'MA120 <b>{rep["ma120"]}</b> · 250日高点回撤 '
                            f'<b>{rep["drawdown250"]*100:.1f}%</b>')
        else:
            metrics_html = (f'数据日 {rep["date"]} · 收盘 <b>{rep["close"]}</b> · '
                            f'分位 <b>{rep["pct"] if rep["pct"] is None else str(rep["pct"])+"%"}</b> · '
                            f'历史最大涨幅 <b>{rep["max_gain"]*100:.0f}%</b> · '
                            f'日均波动 <b>{rep["vol"]*100:.2f}%</b>')
        cards.append(f"""
<div class="card">
  <div class="t"><span class="code">{code}</span> {name} <span class="muted">{idx}</span>
      <span class="chip {'on' if rep['today_is_dca_day'] else 'off'}">{'本周定投日' if rep['today_is_dca_day'] else '非定投日'}</span></div>
  <div class="meta">{metrics_html}</div>
  <div class="meta muted">{'250日区间' if rep.get('strategy_type') == 'industry' else '5年区间'}：{rep['hist_low']} ~ {rep['hist_high']}</div>
  <div style="margin:6px 0">{chips} {'<span class="muted">C涨幅/E回撤需填持仓判断</span>' if rep.get('strategy_type') != 'industry' else ''}</div>
  {advise}
  <div id="holding_summary_{i}"></div>
  {f'<div class="meta">择时信号参考场内 {signal_code} {item.get("signal_name", "")}；实际申购、赎回按 {code} 的确认净值为准。</div>' if signal_code else ''}
  <details>
    <summary>填我的实际持仓，精判断今天该买/卖</summary>
    <div class="posrow">
      <label><input type="checkbox" id="hol_{i}"> 持有</label>
      <span><label>当前持有金额（可不填）</label><input type="number" step="0.01" id="mv_{i}"></span>
      <span><label>平均成本</label><input type="number" step="0.0001" id="ac_{i}" placeholder="如 5.2"></span>
      <span><label>支付宝当前收益率 %</label><input type="number" step="0.01" id="rr_{i}"></span>
      <span><label>{'参考ETF持有期最高价（可不填）' if signal_code else '持仓期最高价'}</label><input type="number" step="0.001" id="pk_{i}" placeholder="可不填"></span>
      <button class="btn" onclick="decide({i})">判断</button>
      <button class="btn gray" onclick="saveHolding({i})">保存持仓</button>
      <button class="btn red" onclick="deleteHolding({i})">删除持仓</button>
    </div>
    <div id="dec_{i}"></div>
  </details>
  <details>
    <summary>卖出规则触发参考</summary>
    {ref_html}
  </details>
</div>""")
    broad_cards = [c for c, item in zip(cards, etfs_reps)
                   if item.get("strategy_type") != "industry"]
    industry_cards = [c for c, item in zip(cards, etfs_reps)
                      if item.get("strategy_type") == "industry"]
    with open(GUIDE_PATH, "r", encoding="utf-8") as f:
        guide = f.read()
    today_page = (f'<section class="asset-section"><h2>宽基 ETF</h2><div class="asset-list">'
                  f'{"".join(broad_cards)}</div></section>'
                  f'<section class="asset-section"><h2>行业 ETF</h2><div class="asset-list">'
                  f'{"".join(industry_cards)}</div></section>')
    body = (f'<section id="page-today" class="page-section">{today_page}</section>'
            f'<section id="page-guide" class="page-section hidden">{guide}</section>')
    notice = (f'<div class="notice">{stale_note}</div>' if stale_note else "")
    rep_json = json.dumps([i["rep"] for i in etfs_reps], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<!-- 自动生成文件：请勿直接编辑。源页面在 templates/index.html，策略说明在 templates/_strategy_guide.html。 -->
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ETF 策略观察 {gen_time[:10]}</title>
<style>

/* Gallery palette: warm paper, ultramarine and restrained ochre. */
:root{{--night:#202e4b;--ultra:#253e69;--cobalt:#345a8b;--gold:#c3a15d;--gold-lt:#dbc595;--amber:#916522;--crimson:#a04c42;--cypress:#416858;--canvas:#f5f4ef;--card:#fffefa;--ink:#293344;--line:#e4e5de;--vg-night:var(--night);--vg-ultra:var(--ultra);--vg-cobalt:var(--cobalt);--vg-gold:var(--gold);--vg-amber:var(--amber);--vg-crimson:var(--crimson);--vg-cypress:var(--cypress);--vg-canvas:var(--canvas);--vg-card:var(--card);--vg-ink:var(--ink);--vg-line:var(--line);--bg:var(--canvas);--c1:var(--cobalt);--c2:var(--cypress);--c3:var(--crimson)}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--canvas);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.7;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}}
body::after{{display:none}}
header{{position:relative;padding:44px max(24px,calc((100vw - 1120px)/2)) 32px;background:var(--night);color:#f8f5e9;border:0;box-shadow:none;overflow:hidden}}
header::before{{content:"";position:absolute;right:7%;top:-155px;width:340px;height:340px;border:1px solid #c3a15d40;border-radius:50%;box-shadow:0 0 0 32px #c3a15d09,0 0 0 65px #c3a15d07;pointer-events:none}}
header h1,h1{{position:relative;font-family:Georgia,"Songti SC","SimSun",serif;font-size:28px;font-weight:500;letter-spacing:2px;line-height:1.5;margin:0 0 10px}}
header>div{{color:#c8d1de;letter-spacing:.5px}}
.wrap,main{{max-width:1168px;margin:0 auto;padding:28px 24px 40px}}
.wrap{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;align-items:start}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:26px;margin:0 0 22px;box-shadow:0 4px 20px #202e4b04}}
.wrap>.card{{margin:0;min-width:0;border-top:3px solid #8b9bb2}}
.t{{font-family:inherit;font-size:18px;font-weight:650;line-height:1.7;margin:0 0 16px}}
.code{{display:block;color:#6e7e92;font-size:12px;font-weight:600;letter-spacing:2px;margin-bottom:2px}}
.t>.muted{{font-weight:400;margin-left:5px}}
.meta{{font-size:13px;line-height:1.95;color:#677181;margin:4px 0;overflow-wrap:anywhere}}
.meta b{{color:#2c3d54;font-weight:600}}
.muted{{color:#78818a;font-size:12px;font-weight:400}}
.chip{{display:inline-block;padding:3px 10px;border-radius:5px;font-size:11px;margin:3px 4px 3px 0;border:1px solid transparent;line-height:1.6;font-weight:500}}
.chip.off{{background:#f0f1ed;color:#777f83;border-color:transparent}}
.chip.on{{background:#eaf1ea;color:var(--cypress);border-color:transparent}}
.chip.on.red,.chip.red{{background:#f6ebe5;color:var(--crimson);border-color:transparent}}
.adv{{font-family:inherit;font-size:15px;font-weight:600;background:#f5f3eb;border-left:3px solid var(--gold);border-radius:0 7px 7px 0;padding:13px 14px;margin:18px 0}}
.ok,.adv.ok{{color:var(--cypress)}}.warn,.adv.warn{{color:var(--amber)}}.bad,.red,.err{{color:var(--crimson)}}
details{{border-top:1px solid var(--line);padding-top:12px;margin-top:14px}}
summary{{cursor:pointer;font-size:13px;color:var(--cobalt);padding:5px 0;font-weight:500}}
.refs{{padding-left:20px;margin:12px 0;color:#687180;font-size:12px;line-height:2}}
.posrow{{display:flex;gap:12px;flex-wrap:wrap;align-items:end;padding:12px 0}}
label,.posrow label{{display:block;font-size:12px;color:#677181;margin-bottom:6px}}
input[type=number],input[type=text],input[type=date],select{{padding:10px 12px;border:1px solid #dce0e2;border-radius:7px;background:#fffefa;color:var(--ink);font:inherit;font-size:13px;min-height:40px;max-width:100%}}
input[type=number]{{width:110px}}input[type=checkbox]{{accent-color:var(--cobalt)}}
button,.btn{{font-family:inherit}}
.btn,.btn.primary,.btn.green{{display:inline-block;background:var(--cobalt);color:white;border:1px solid transparent;border-radius:7px;padding:10px 17px;min-height:40px;cursor:pointer;font-size:13px;font-weight:500;box-shadow:none;margin-right:5px;transition:background .15s}}
.btn.gray{{background:#edf0f1;color:#46576b;border-color:#e0e4e5}}.btn.red{{background:var(--crimson);color:white}}
.btn:hover{{filter:brightness(.93)}}
:focus-visible{{outline:3px solid #c3a15d;outline-offset:3px}}
.notice{{grid-column:1/-1;background:#f8f0de;border:1px solid #e8d9b7;border-left:3px solid var(--gold);border-radius:8px;padding:14px 18px;margin:0;font-size:13px;color:#85632e;line-height:1.8}}
footer{{color:#78818a!important;font-size:12px;text-align:center;padding:24px!important;border-top:1px solid var(--line);line-height:1.9}}
nav{{display:flex;gap:8px;position:relative;margin-top:16px;flex-wrap:wrap}}
nav a{{display:inline-block;text-decoration:none;color:#b8c6d8;padding:7px 15px;border:1px solid transparent;border-radius:6px;font-size:13px;cursor:pointer;margin:0}}
nav a.active{{color:#f5e5bf;background:#ffffff0d;border-color:#c3a15d66}}
.card h2{{font-family:inherit;color:var(--ultra);font-size:17px;font-weight:600;margin:0 0 20px;line-height:2}}
.grid{{display:grid;gap:18px}}.g2{{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}}.grid input,.grid select{{width:100%}}
.row{{display:flex;align-items:center;gap:10px;padding:16px 0;border-bottom:1px solid var(--line);flex-wrap:wrap}}.row .conds{{white-space:normal!important}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:0;border-bottom:1px solid var(--line);padding:12px;text-align:left}}th{{background:#f0f2ef;color:#536174;font-weight:500}}tr:nth-child(even) td{{background:#fafaf6}}
pre{{background:#f2f3ef;border:1px solid var(--line);border-radius:8px;padding:16px;overflow:auto;font-size:12px;white-space:pre-wrap;line-height:1.8}}
.hidden{{display:none}}.bignum{{font-size:26px;font-weight:600;margin:8px 8px 0 0}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
.tabs{{display:flex;border-bottom:1px solid var(--line);gap:8px;margin-bottom:20px}}.tabs button{{background:none;border:0;border-bottom:2px solid transparent;padding:12px;color:#677181;cursor:pointer}}.tabs button.active{{border-bottom-color:var(--gold);color:var(--cobalt)}}
.asset-section{{grid-column:1/-1;margin:0 0 12px}}.asset-section>h2{{font-family:Georgia,"Songti SC",serif;font-size:20px;color:var(--night);font-weight:500;margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid var(--line)}}
.asset-list{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}}.asset-list>.card{{margin:0}}
.strategy-guide{{grid-column:1/-1}}.strategy-guide h3{{font-size:15px;color:var(--cobalt);margin:4px 0 12px}}.strategy-guide p{{margin:8px 0 18px}}
.page-section{{grid-column:1/-1;min-width:0}}.hidden{{display:none!important}}
@media(max-width:760px){{header{{padding:30px 20px 24px}}header h1,h1{{font-size:22px;letter-spacing:1px}}.wrap,main{{padding:18px 14px 28px}}.wrap,.two,.asset-list{{grid-template-columns:1fr;gap:16px}}.card{{padding:20px;border-radius:12px}}.t{{font-size:17px}}.g2{{grid-template-columns:repeat(auto-fit,minmax(145px,1fr))}}.card h2 .btn{{margin-top:8px}}th,td{{padding:8px 5px;font-size:12px}}header::before{{right:-230px}}}}
</style></head><body>
<header><h1>ETF 策略观察</h1><div style="font-size:12px;opacity:.8">生成于 {gen_time}{' · 使用网页保存的规则' if using_saved else ' · 使用内置默认规则'}</div>
<nav id="topnav"><a data-page="today" class="active">今日提醒</a><a data-page="guide">策略说明</a></nav></header>
<div class="wrap">{notice}{body}
<footer>数据：AkShare（东方财富/新浪）· 仅供策略研究，非投资建议</footer></div>
<script>
var REPS = {rep_json};
var CODES = {json.dumps([i['code'] for i in etfs_reps], ensure_ascii=False)};
var LABEL = {{clear:'清仓(全部卖出)',trim_half:'卖出50%',pause:'暂停定投'}};
document.querySelectorAll('#topnav a').forEach(function(a){{
  a.onclick=function(){{
    document.querySelectorAll('#topnav a').forEach(function(x){{x.classList.remove('active');}});
    a.classList.add('active');
    ['today','guide'].forEach(function(name){{
      document.getElementById('page-'+name).classList.toggle('hidden',name!==a.dataset.page);
    }});
  }};
}});
function holdingKey(i){{return 'etf_holding_'+CODES[i];}}
function savedHolding(i){{try{{return JSON.parse(localStorage.getItem(holdingKey(i)))||null;}}catch(e){{return null;}}}}
function fillHolding(i){{
  var p=savedHolding(i); if(!p)return;
  document.getElementById('hol_'+i).checked=true;
  document.getElementById('mv_'+i).value=p.market_value==null?'':p.market_value;
  document.getElementById('ac_'+i).value=p.avg_cost;
  document.getElementById('rr_'+i).value=p.return_rate;
  document.getElementById('pk_'+i).value=p.peak==null?'':p.peak;
  var principal=p.market_value!=null&&p.return_rate>-100?p.market_value/(1+p.return_rate/100):null;
  var recovery=p.return_rate<0?-p.return_rate/(100+p.return_rate)*100:0;
  var text='已保存持仓'+(p.market_value!=null?' '+Number(p.market_value).toFixed(2)+' 元':'')+' · 成本价 '+Number(p.avg_cost).toFixed(4)+' · 收益率 '+Number(p.return_rate).toFixed(2)+'%';
  if(principal!=null) text+='<br><span class="muted">估算投入 '+principal.toFixed(2)+' 元，浮盈亏 '+(p.market_value-principal).toFixed(2)+' 元；回到成本价还需上涨 '+recovery.toFixed(2)+'%</span>';
  document.getElementById('holding_summary_'+i).innerHTML='<div class="adv '+(p.return_rate<0?'warn':'ok')+'">'+text+'</div>';
}}
function saveHolding(i){{
  var avg=parseFloat(document.getElementById('ac_'+i).value),rr=parseFloat(document.getElementById('rr_'+i).value);
  var value=parseFloat(document.getElementById('mv_'+i).value),peak=parseFloat(document.getElementById('pk_'+i).value);
  if(!document.getElementById('hol_'+i).checked||!(avg>0)||!Number.isFinite(rr)){{alert('请勾选“持有”，并填写有效的平均成本和当前收益率。');return;}}
  localStorage.setItem(holdingKey(i),JSON.stringify({{holding:true,avg_cost:avg,return_rate:rr,market_value:Number.isFinite(value)?value:null,peak:Number.isFinite(peak)?peak:null}}));
  fillHolding(i); decide(i);
}}
function deleteHolding(i){{
  localStorage.removeItem(holdingKey(i));
  ['hol_','mv_','ac_','rr_','pk_'].forEach(function(prefix){{var e=document.getElementById(prefix+i);if(e) e.type==='checkbox'?e.checked=false:e.value='';}});
  document.getElementById('holding_summary_'+i).innerHTML='';
  document.getElementById('dec_'+i).innerHTML='<div class="muted">持仓已删除。</div>';
}}
function decide(i){{
  var rep=REPS[i], p=rep.params;
  var hol=document.getElementById('hol_'+i).checked;
  var ac=parseFloat(document.getElementById('ac_'+i).value), rr=parseFloat(document.getElementById('rr_'+i).value), pk=parseFloat(document.getElementById('pk_'+i).value);
  var close=rep.close, mg=rep.max_gain, vol=rep.vol;
  if(rep.strategy_type==='industry'){{
    var sell='暂不卖出，继续观察', color='ok';
    if(rep.risk_exit){{sell='全部卖出：中期趋势已确认破坏';color='bad';}}
    else if(!isNaN(rr)&&rr/100>=rep.profile.profit_clear&&(rep.chasing||rep.trend_weak)){{sell='全部卖出：盈利后走势过热或转弱';color='bad';}}
    else if(!isNaN(rr)&&rr/100>=rep.profile.profit_trim&&rep.chasing){{sell='卖出 50%：盈利后进入过热区';color='warn';}}
    else if(!isNaN(rr)&&rr<0&&rep.rebound_failure){{sell='全部卖出：反弹至压力区后再次转弱';color='bad';}}
    else if(rep.defensive_watch) sell='暂不卖出，防守观察；连续两周跌破 MA120 则退出';
    document.getElementById('dec_'+i).innerHTML='<div>加仓建议：<b>'+rep.add_advice+'</b></div><div class="'+color+'">卖出建议：<b>'+sell+'</b></div>';
    return;
  }}
  var cond={{A:rep['A_跌幅足够深'],B:rep['B_分位点低'],D:rep['D_过热']}};
  if(hol&&!isNaN(rr)&&mg) cond.C = rr/100 >= mg*p.gain_trigger;
  else if(hol&&ac>0&&mg) cond.C = (close/ac-1) >= mg*p.gain_trigger;
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
  c+='<div class="'+cls+'">加仓建议：'+(amt>0?'可投 '+amt+' 元（'+tier+'）':tier)+'</div>';
  if(!hol) c+='<div class="muted">卖出建议：当前未持有，无需卖出。</div>';
  else if(decision&&decision.action==='clear') c+='<div class="bad">卖出建议：全部卖出（'+decision.name.split('（')[0]+'）</div>';
  else if(decision&&decision.action==='trim_half') c+='<div class="warn">卖出建议：卖出 50%（'+decision.name.split('（')[0]+'）</div>';
  else c+='<div class="ok">卖出建议：暂不卖出，继续观察。今日没有触发退出信号。</div>';
  box.innerHTML=c;
}}
for(var i=0;i<REPS.length;i++) fillHolding(i);
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
            rep = (industry_strategy.analyze_latest(df.tail(1400), item.get("industry_profile"))
                   if item.get("strategy_type") == "industry"
                   else alerts.analyze_latest(df.tail(1400), params, sell_rules=rules))
            etfs_reps.append({**item, "rep": rep})
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
