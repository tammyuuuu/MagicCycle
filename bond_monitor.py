"""Bond presentation: one long-term strategy, independent data status."""
from pathlib import Path
from datetime import date
from html import escape
import json
import math
import csv
ROOT = Path(__file__).resolve().parent

def render_bond_monitor(today=None):
    from asset_states import render_rail
    today = today or date.today()
    try:
        s=json.loads((ROOT/'research_bond_entry/summary.json').read_text(encoding='utf8'))
        if not isinstance(s,dict):s={}
    except (OSError,ValueError,TypeError):s={}
    def num(key,fmt):
        try:
            v=float(s[key]);return format(v,fmt) if math.isfinite(v) else '未更新'
        except (KeyError,ValueError,TypeError):return '未更新'
    def stamp(key):
        try:return date.fromisoformat(s[key])
        except (KeyError,ValueError,TypeError):return None
    nd,rd=stamp('as_of'),stamp('rate_date')
    missing=not nd or not rd or any(num(k,'.2f')=='未更新' for k in ('nav','y10','percentile','trend_bp','drawdown'))
    stale=any(d and ((today-d).days>7 or d>today) for d in (nd,rd))
    update='数据待更新：部分指标缺失或无效。' if missing else '数据待更新：部分指标已超过7个自然日。' if stale else '数据状态：截至所列数据日。'
    trend='未更新'
    try:
        with (ROOT/'research_xingxun_v2/clean_v2/000015.csv').open(encoding='utf8') as source:
            rows=[r for r in csv.DictReader(source) if nd and r['date']<=nd.isoformat()]
        if len(rows)>=120 and rows[-1]['date']==nd.isoformat():
            v=[float(r['tr']) for r in rows[-120:]]
            if all(math.isfinite(x) and x>0 for x in v):
                trend=f"再投资净值{'高于' if v[-1]>sum(v)/120 else '不高于'}120日均线；60日收益 {(v[-1]/v[-61]-1)*100:+.2f}%"
    except (OSError,ValueError,KeyError,TypeError):pass
    rail=render_rail(dict(asset_type='bond_fund',status='buy',action='买入／持有',reason='长期持有是当前主要策略。现有研究尚未证明主动择时能稳定提高风险调整后收益。',details={}))
    return f'''<div class="card" data-asset-symbol="000015"><h2>华夏纯债债券A <span class="muted">000015</span></h2>
<p>数据日 {nd or '未更新'} · 当前 {num('nav','.4f')} · 当日涨跌 {num('day_change_pct','+.2f')}%</p>
{rail}
<p class="muted bond-data-status" role="status">{update} 趋势{'待更新' if trend=='未更新' else '截至净值数据日'}。数据更新状态不改变长期策略。</p>
<details><summary>查看判断依据</summary>
<ul class="strategy-basis">
<li><b>主要策略：</b>买入／持有，以长期持有为主。</li>
<li><b>研究证据：</b>跨五年周期冻结验证中，主动减仓未同时稳定改善Calmar与Sharpe；执行延迟增加后优势减弱。完整冻结验证周期仅一个。</li>
<li><b>利率参考：</b>10年国债 {num('y10','.4f')}%，近5年分位 {num('percentile','.1f')}%；60日变化 {num('trend_bp','+.1f')}bp（{rd or '未更新'}）。</li>
<li><b>净值回撤：</b>距近252个净值日高点 {num('drawdown','.2f')}%。</li>
<li><b>趋势参考：</b>{escape(trend)}。</li></ul>
<p>利率、回撤和趋势仅作辅助信息，不据此自动建议等待、减仓或退出。10年国债是利率代理，基金久期未核实。</p>
<p class="muted">研究采用分红再投资及申赎费用模型，历史渠道费率、披露和确认时间仍有假设，结果不保证未来收益。</p>
<p class="muted">数据：<a href="https://fund.eastmoney.com/000015.html" target="_blank" rel="noopener">东方财富基金净值</a> · <a href="https://data.eastmoney.com/cjsj/zmgzsyl.html" target="_blank" rel="noopener">国债历史收益率</a></p>
</details></div>'''
