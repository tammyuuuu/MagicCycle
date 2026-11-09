"""Version-checked strategy explanations and locally reproduced backtests."""
from pathlib import Path
import json

RESULTS = Path(__file__).resolve().parent / 'results/active_strategy_backtests/summary.json'
RULES = {
 '510300': ('估值与趋势确认', 'PE分位低于30%且收盘高于MA60时进入；持有至PE分位至少90%且收盘不高于MA80时退出。'),
 '510500': ('PE或PB5买入、PE退出', 'PE、PB固定5年。PE分位低于60%且收盘高于MA120，或PB分位低于10%时进入；PE分位至少30%且收盘不高于MA120时退出。退出优先，其余时间保持原状态。'),
 '588000': ('16日均线缓冲', '收盘高于MA16的102%时进入；不高于MA16的98%时退出；缓冲区内保持原阶段。'),
 '513500': ('长期方向与热度', '完整月份12个月涨幅为正、未过热且高于MA20时可买；首次偏离MA60至少15%减半，冷却至5%且恢复MA20后买回；长期方向转弱退出。'),
 '513100': ('长期方向与热度', '完整月份12个月涨幅为正、未过热且高于MA20时可买；首次偏离MA60至少15%减半，冷却至5%且恢复MA20后买回；长期方向转弱退出。'),
 '588170': ('20日趋势分步退出', '转到MA20上方时买入；首次回到均线或下方减半，连续两日线下退出；减半后恢复线上只买回减掉部分。'),
 '518850': ('长期持有与过热减仓', '允许长期持有；20日涨幅与MA60偏离均至少15%时减半一次，两者均冷却至5%以内后买回；等待期间不重复减仓。'),
 '000015': ('长期持有', '以长期持有为主；利率、净值回撤和趋势仅作参考，不自动触发等待、减仓或退出。'),
}


def presentation(summary, years=5):
    code = summary.get('symbol')
    if code not in RULES:
        return None
    title, method = RULES[code]
    if code == '510500':
        years = 5
        title += ' · PE/PB固定5年'
    if code == '510300':
        title += f' · {years}年估值参考'
    version = summary.get('details', {}).get('strategy_version')
    out = dict(title=title, method=method, version=version, backtest=None)
    try:
        asset = json.loads(RESULTS.read_text(encoding='utf8'))['assets'][code]
        if asset['version'] == version:
            out['backtest'] = asset['backtests'].get(str(years)) or asset['backtests'].get('default')
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if code == '510500' and version != 'csi500_pe_or_pb5_pe_exit_v4':
        out['method'] = '历史版本；不展示新版本的回测数字。'
    params = summary.get('details', {}).get('parameters', {})
    if code == '518850' and any(params.get(k, v) != v for k,v in {'heat_threshold':.15,'cooling_threshold':.05,'return_window':20,'ma_window':60,'min_history':120}.items()):
        out.update(method='当前使用自定义黄金参数，以本次判断条件为准；默认参数回测不适用。',backtest=None)
    if code == '588170' and params.get('ma_fast',20) != 20:
        out.update(method=f'当前使用{params["ma_fast"]}日均线分步退出，以本次判断条件为准。',backtest=None)
    return out


def attach(summary):
    details = summary.setdefault('details', {})
    info = presentation(summary, details.get('parameters', {}).get('valuation_years', 5))
    if info:
        details['strategy_presentation'] = info
        for years, option in details.get('strategy_options', {}).items():
            option['strategy_presentation'] = presentation(summary, int(years))
    return summary


def render(info):
    from html import escape
    if not info:
        return ''
    bt = info.get('backtest')
    annual_label=escape(bt.get('annual_label','历史年化（CAGR）')) if bt else ''
    drawdown_label=escape(bt.get('drawdown_label','最大回撤')) if bt else ''
    period_label=escape(bt.get('period_label',f'回测 {bt["start"]} — {bt["end"]}')) if bt else ''
    stats = (f'<dl class="strategy-stats"><div><dt>{annual_label}</dt><dd>{bt["annual_pct"]:.2f}%</dd></div>'
             f'<div><dt>{drawdown_label}</dt><dd>{bt["max_drawdown_pct"]:.2f}%</dd></div></dl>'
             f'<p class="strategy-period">{period_label}</p>') if bt else '<p class="strategy-note">当前版本尚无已核对回测，不展示其他策略数字。</p>'
    return (f'<div class="strategy-summary"><p class="strategy-name">{escape(info["title"])}</p>'
            f'{stats}</div>')


def render_guide():
    from html import escape
    try:
        assets = json.loads(RESULTS.read_text(encoding='utf8'))['assets']
    except (OSError, ValueError, KeyError):
        assets = {}
    groups = [('宽基 ETF',['510300','510500','588000']),('美股宽基 ETF',['513500','513100']),('行业 ETF',['588170']),('黄金 ETF',['518850'])]
    output = '<section class="card strategy-guide"><h2>当前策略</h2>'
    for i,(label,codes) in enumerate(groups):
        output += f'<section id="guide-category-{i}"><h3>{escape(label)}</h3>'
        for code in codes:
            asset = assets.get(code,{})
            summary = dict(symbol=code,details={'strategy_version':asset.get('version')})
            output += f'<table><caption>{escape(code)}</caption><tbody><tr><td>'+render(presentation(summary))+'</td></tr></tbody></table>'
        output += '</section>'
    return output+'</section>'
