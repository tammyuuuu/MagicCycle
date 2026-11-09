"""卡片状态说明：本地页面与静态页面共用，不参与策略计算。"""
STATE_CATALOG = {
 "broad_etf": [
  ("buy_more","增加投入","green","价格较低且调整较充分，可以比平时多投入一些。"),
  ("normal_buy","正常投入","blue","没有明显过热，按原定长期计划投入。"),
  ("hold","继续持有","blue","保留已有仓位，今天不需要继续增加投入。"),
  ("pause","暂时等待","amber","今天先不加钱，等待更合适的投入位置；已有持仓是否减仓，需要结合实际收益判断。"),
  ("reduce","适度减仓","red","已有明显盈利且价格偏高，可考虑卖出一部分。")],
 "sector_etf": [
  ("wait","暂不追入","amber","价格或走势还不适合进入，先不追着上涨买。"),
  ("watch","观察区","amber","已经跌了一段，但还没确认止跌，先观察。"),
  ("small_buy","小额尝试","green","开始出现企稳迹象，可以少量分批尝试。"),
  ("buy","买入改善","green","恢复迹象进一步确认，可考虑分批买入。"),
  ("stop_add","停止加仓","amber","短期走势又变弱，先不往已有仓位里加钱。"),
  ("reduce","部分减仓","red","已有盈利且过热或转弱，可考虑卖出一部分。"),
  ("exit","考虑退出","red","长期走势破坏或退出纪律触发，结合实际持仓考虑退出。")],
 "macro_asset": [
  ("allocate","分批配置","green","出现回调，但中长期趋势仍在，可分几次配置。"),
  ("normal_hold","正常持有","blue","长期趋势尚未确认破坏，保留配置，先不追买。"),
  ("pause","暂缓追高","amber","近期上涨过快或价格偏高，等一等再增加配置。"),
  ("reduce","适度减仓","red","已有明显盈利且偏离长期趋势，可考虑减少一部分配置。"),
  ("risk","风险上升","red","长期走势持续变弱，应重新检查配置比例和风险承受能力。")],
}

# 从投入较多到减少/退出排序；观察与等待都是零新增投入。
ORDER = {
 'broad_etf':['buy_more','normal_buy','hold','pause','reduce'],
 'sector_etf':['buy','small_buy','watch','wait','stop_add','reduce','exit'],
 'macro_asset':['allocate','normal_hold','pause','reduce','risk'],
}
for asset, order in ORDER.items():
 entries={e[0]:e for e in STATE_CATALOG[asset]}
 STATE_CATALOG[asset]=[entries[code] for code in order]

# 页面合并同类操作，后台保留更细的买卖触发条件。
DISPLAY_STATUS_MAP={'sector_etf':{'small_buy':'buy','wait':'watch','stop_add':'pause'}}
STATE_CATALOG['sector_etf']=[
 ('buy','分批买入','green','恢复初步确认时小额尝试，恢复进一步确认后再分批投入。'),
 ('watch','继续观察','blue','暂不新增投入：可能还没止跌，也可能位置不够合适。具体原因看当前建议。'),
 ('pause','暂停加仓','amber','已有仓位走势转弱，先停止追加，继续检查退出条件。'),
 ('reduce','部分减仓','red','已有盈利且过热或转弱，考虑卖出一部分。'),
 ('exit','考虑退出','red','长期走势破坏或退出纪律触发，结合实际持仓考虑退出。')]


# 五个统一操作，买入与加仓由实际持仓区分。
DISPLAY_STATUS_MAP={
 'broad_etf':{'buy_more':'add','normal_buy':'buy','hold':'watch','pause':'watch'},
 'sector_etf':{'small_buy':'buy','wait':'watch','stop_add':'watch'},
 'macro_asset':{'allocate':'buy','normal_hold':'watch','pause':'watch','risk':'watch'},
}
for asset in STATE_CATALOG:
 STATE_CATALOG[asset]=[
  ('add','加仓','green','已有这个标的的仓位，且新增投入条件满足，可以考虑追加资金。'),
  ('buy','买入','blue','尚未持有这个标的，买入条件满足，可以考虑建立仓位。'),
  ('watch','观察','amber','今天不新增交易：已有仓位先保持，未持有则等待机会；具体原因看当前建议。'),
  ('reduce','减仓','red','卖出部分已有仓位，降低仓位。'),
  ('exit','退出','red','退出条件触发，结合实际持仓考虑卖出剩余仓位。')]

STATE_CATALOG['broad_etf']=[('add','加仓','green','估值低，且回撤较大。'),('buy','买入','blue','估值低，且回撤中等。'),('watch','观察','amber','买卖条件未成立，或数据不足。'),('reduce','减仓','red','估值偏高，考虑卖出部分已有持仓。'),('exit','退出','red','估值达到极高区间，考虑退出已有持仓。')]
STATE_CATALOG['sector_etf']=[
 ('add','加仓','green','本策略暂不单独触发加仓。'),
 ('buy','买入','blue','收盘价转到20日均线上方；减半后恢复时只买回减掉的部分。'),
 ('watch','观察','amber','保持在20日均线上方且没有新买点，已有持仓保持；数据不足也先观察。'),
 ('reduce','减仓','red','首次收盘回到20日均线或下方，减半一次。'),
 ('exit','退出','red','连续两个交易日收盘不高于20日均线，退出剩余持仓。')]


STATE_CATALOG['macro_asset']=[
 ('buy','买入／持有','blue','允许长期持有；双指标均冷却至5%以内后，可买回并恢复仓位。'),
 ('reduce','减仓','red','双指标均达到15%时减半一次；其后等待冷却，暂不买回，不重复减仓。')]



STATE_CATALOG['us_equity']=[
 ('add','加仓','green','长期方向向上；过热后偏离降至5%以内，且价格高于20日均价，可加大本期投入。'),
 ('buy','买入','blue','过去12个月涨幅为正，未处于过热阶段，且价格高于20日均价；新资金可买，已有持仓不重复交易。'),
 ('watch','观察','amber','过热尚未消化或短期价格未恢复，先不新增投入；已减仓不重复卖出。数据不足或溢价公告当日也先观察。'),
 ('reduce','减仓','red','长期方向向上时，首次高于60日均价至少15%，已有持仓减半一次。'),
 ('exit','退出','red','最近完整月份的过去12个月涨幅不为正，考虑退出已有持仓。')]

# 分标的策略沿用五步轴线；未验证的加仓、减仓不触发。
for strategy_id,buy,exit_ in [
 ('pe_or_pb5_pe_exit','PE五年分位低于60%且收盘高于MA120，或PB五年分位低于10%；退出优先，进入后保持许可。','PE五年分位至少30%且收盘不高于MA120，退出剩余持仓；PB低估不覆盖退出。'),
 ('value_confirmed_exit','PE分位低于30%且高于60日均价，进入买入阶段；退出前保持许可。','PE分位至少90%且不高于80日均价，退出剩余持仓。'),
 ('value_or_trend120','PE分位低于30%，或低于60%且高于120日均价时进入买入阶段。','PE分位至少30%且不高于120日均价，退出剩余持仓。'),
 ('value_trend_confirm120','PE分位低于60%且收盘高于120日均价才进入；低估也需确认。进入后保持许可。','PE分位至少30%且不高于120日均价，退出剩余持仓；低于30%时跌回线下不单独退出。'),
 ('trend20','收盘高于20日均价时允许新资金买入。','收盘不高于20日均价，退出剩余持仓。'),
 ('trend16_buffer2','收盘高于16日均价的102%进入；退出前允许新资金买入。','收盘不高于16日均价的98%，退出剩余持仓。')]:
 STATE_CATALOG[strategy_id]=[
  ('add','加仓','green','本轮只验证买入与退出，暂不单独触发加仓。'),
  ('buy','买入','blue',buy),('watch','观察','amber','等待入场条件或足够数据。'),
  ('reduce','减仓','red','本轮不单独触发减仓。'),('exit','退出','red',exit_)]


STATE_CATALOG['bond_fund']=[('buy','买入／持有','blue','长期持有是当前主要策略；辅助指标不触发等待、减仓或退出。')]
STATE_CATALOG['stock']=[
 ('buy','买入','blue','月末估值达到买入条件，下一交易日开盘模拟买入。'),
 ('watch','持有/观察','blue','没有新的月末交易信号，维持模拟仓位；数据不足时观察。'),
 ('exit','卖出','red','月末估值达到卖出条件，下一交易日开盘模拟卖出。')]
STATE_CATALOG['nvda_entry']=[('buy','买入／持有','blue','长期持有为主；估值和买点研究仅供参考。')]
STATE_CATALOG['stock_long_term']=[
 ('buy','买入/持有','blue','长期持有基准；不因价格上涨自动卖出。'),
 ('wait','等待','amber','行情或规则所需数据不足时等待。')]
STATE_CATALOG['aapl_observe']=[('watch','观察','blue','公司和策略研究中，暂不生成买卖信号。')]
STATE_CATALOG['aapl_add']=[('watch','持有/观察','blue','维持基础仓位，等待新的月末加仓条件。'),('add','加仓','green','月末回撤达到阈值且模拟预留资金足够时，下一交易日开盘加仓。')]


def display_status(summary):
 if summary['asset_type']=='bond_fund':return 'buy'
 if summary['asset_type']=='macro_asset':
  return 'watch' if summary.get('details',{}).get('insufficient_history') else 'reduce' if summary.get('details',{}).get('heat_phase') else 'buy'
 code=DISPLAY_STATUS_MAP.get(summary['asset_type'],{}).get(summary['status'],summary['status'])
 if summary['asset_type'] not in ('broad_etf','sector_etf','macro_asset') and code=='buy' and summary.get('details',{}).get('holding'):code='add'
 return code


def display_action(summary):
 code=display_status(summary)
 return next((e[1] for e in STATE_CATALOG.get(summary['asset_type'],[]) if e[0]==code),summary['action'])


def _update_notice(text):
 return any(token in str(text) for token in ('未更新','待更新','更新失败','更新受限','等待数据更新','待数据更新','过期','过旧','网络异常'))

def display_reason(text):
 return '暂时观察。' if _update_notice(text) else text

def processed_basis(summary):
 return [('估值参考' if _update_notice(key) else key,'暂无' if _update_notice(key) or _update_notice(value) else value) for key,value in summary.get('decision_basis',[])
         if not (key=='行情前提' and _update_notice(value))]


def render_basis(summary):
 from html import escape
 from strategy_presentation import presentation,render
 return render(summary.get('details',{}).get('strategy_presentation') or presentation(summary))+'<ul class="strategy-basis">'+''.join('<li><b>'+escape(k)+('</b>' if v=='满足' else '：</b>'+escape(v))+'</li>' for k,v in processed_basis(summary))+'</ul>'


def render_rail(summary):
 from html import escape
 colors=['#7146aa','#5265b6','#347ac2','#8faaa0','#e8bd4b']
 catalog=STATE_CATALOG.get(summary.get('details',{}).get('strategy_id') or ('us_equity' if summary.get('details',{}).get('strategy_mode')=='us_monthly_trend' else summary['asset_type']),[])
 current_status=display_status(summary)
 if summary['asset_type']=='macro_asset':colors=['#5265b6','#e8bd4b']
 if summary['asset_type']=='bond_fund':colors=['#5265b6']
 current_index=next((i for i,e in enumerate(catalog) if e[0]==current_status),0)
 active=next((e for e in catalog if e[0]==current_status),None)
 buttons=''.join(f'<button type="button" class="state-step{ " is-current" if code==current_status else ""}" style="--axis-pos:{i/max(1,len(catalog)-1)*100:.1f}%;--axis-color:{colors[i]}" data-meaning="{escape(meaning,quote=True)}" data-label="{escape(label,quote=True)}" onclick="inspectAssetState(this)"'+(' aria-current="step"' if code==current_status else '')+f'><span class="state-dot" aria-hidden="true"></span>{escape(display_action(summary) if code==current_status else label)}'+('<span class="current-arrow" aria-hidden="true"></span>' if code==current_status else '')+'</button>' for i,(code,label,tone,meaning) in enumerate(catalog))
 risk_badge=''
 axis_labels='<b>买入／持有</b><span>减仓</span>' if summary['asset_type']=='macro_asset' else '<b>买入</b><span>卖出</span>'
 if summary['asset_type'] in ('bond_fund','nvda_entry'):axis_labels='<b>长期持有策略</b>'
 if summary['asset_type']=='stock_long_term':axis_labels='<b>长期持有策略</b>'
 if summary['asset_type']=='aapl_observe':axis_labels='<b>研究观察</b>'
 if summary['asset_type']=='aapl_add':axis_labels='<b>候选加仓策略</b>'
 return f'<div class="state-position" style="--current-pos:{current_index/max(1,len(catalog)-1)*100:.1f}%;--axis-color:{colors[current_index]}"><div class="axis-labels">{axis_labels}</div>'+risk_badge+'<div class="axis-scroll"><div class="state-rail">'+buttons+'</div></div><p class="current-reason"><b>当前建议：'+escape(active[1] if active else summary['action'])+'</b><span class="recommendation-reason">'+escape(display_reason(summary['reason']))+'</span></p><p class="state-explanation" aria-live="polite"></p></div>'


def render_today_categories(contents=None):
 from html import escape
 contents=contents or {}
 from bond_monitor import render_bond_monitor
 contents={**contents, 'bond':render_bond_monitor()}
 if 'stock' not in contents:
  from stock_monitor import render as render_stocks
  contents={**contents, 'stock':render_stocks()}
 categories=[('broad','宽基 ETF'),('us','美股宽基 ETF'),('industry','行业 ETF'),('macro','黄金/大类资产'),('bond','债券监测'),('stock','个股')]
 output='<div class="today-categories etf-monitor" style="grid-column:1/-1"><h2 class="etf-monitor-title">买卖监测</h2><nav class="guide-tabs" aria-label="今日提醒资产类别">'
 for index,(key,label) in enumerate(categories):
  output+=f'<button type="button" data-category="{key}" aria-pressed="'+('true' if index==0 else 'false')+f'" aria-controls="today-category-{key}" onclick="selectTodayCategory(this)">{escape(label)}</button>'
 output+='</nav>'
 for index,(key,label) in enumerate(categories):
  output+=f'<section class="asset-section today-category" id="today-category-{key}"'+(' hidden' if index else '')+f' aria-label="{escape(label)}"><div class="asset-list" id="{key}List">'+contents.get(key,'')+'</div></section>'
 return output+'</div>'



def render_guide():
 from strategy_presentation import render_guide
 return render_guide()
