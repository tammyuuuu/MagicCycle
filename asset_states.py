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
 ('watch','继续观察','blue','暂不新增投入：可能还没止跌，也可能位置不够合适。具体原因看当前判断。'),
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
  ('watch','观察','amber','今天不新增交易：已有仓位先保持，未持有则等待机会；具体原因看当前判断。'),
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
 ('add','加仓','green','过热后两个指标均冷却至5%以内，按本期预算加仓；未持有可买入。'),
 ('buy','买入','blue','首次指标就绪、未处于过热阶段时，可开始配置。'),
 ('watch','观察','amber','没有新信号时保持；减仓后等待冷却，不重复卖出。'),
 ('reduce','减仓','red','20日涨幅与60日均线偏离均至少15%，减半一次。'),
 ('exit','退出','red','本策略不自动全部退出，允许长期持有。')]



STATE_CATALOG['us_equity']=[
 ('add','加仓','green','长期方向向上；过热后偏离降至5%以内，且价格高于20日均价，可加大本期投入。'),
 ('buy','买入','blue','过去12个月涨幅为正，未处于过热阶段，且价格高于20日均价；新资金可买，已有持仓不重复交易。'),
 ('watch','观察','amber','过热尚未消化或短期价格未恢复，先不新增投入；已减仓不重复卖出。数据不足或溢价公告当日也先观察。'),
 ('reduce','减仓','red','长期方向向上时，首次高于60日均价至少15%，已有持仓减半一次。'),
 ('exit','退出','red','最近完整月份的过去12个月涨幅不为正，考虑退出已有持仓。')]

# 分标的策略沿用五步轴线；未验证的加仓、减仓不触发。
for strategy_id,buy,exit_ in [
 ('value_confirmed_exit','PE分位低于30%且高于60日均价，进入买入阶段；退出前保持许可。','PE分位至少90%且不高于80日均价，退出剩余持仓。'),
 ('value_or_trend120','PE分位低于30%，或低于60%且高于120日均价时进入买入阶段。','PE分位至少30%且不高于120日均价，退出剩余持仓。'),
 ('trend20','收盘高于20日均价时允许新资金买入。','收盘不高于20日均价，退出剩余持仓。'),
 ('trend16_buffer2','收盘高于16日均价的102%进入；退出前允许新资金买入。','收盘不高于16日均价的98%，退出剩余持仓。')]:
 STATE_CATALOG[strategy_id]=[
  ('add','加仓','green','本轮只验证买入与退出，暂不单独触发加仓。'),
  ('buy','买入','blue',buy),('watch','观察','amber','等待入场条件或足够数据。'),
  ('reduce','减仓','red','本轮不单独触发减仓。'),('exit','退出','red',exit_)]


def display_status(summary):
 code=DISPLAY_STATUS_MAP.get(summary['asset_type'],{}).get(summary['status'],summary['status'])
 if summary['asset_type'] not in ('broad_etf','sector_etf','macro_asset') and code=='buy' and summary.get('details',{}).get('holding'):code='add'
 return code


def display_action(summary):
 code=display_status(summary)
 return next((e[1] for e in STATE_CATALOG.get(summary['asset_type'],[]) if e[0]==code),summary['action'])


def processed_basis(summary):
 return summary.get('decision_basis',[])


def render_basis(summary):
 from html import escape
 return '<ul class="strategy-basis">'+''.join('<li><b>'+escape(k)+('</b>' if v=='满足' else '：</b>'+escape(v))+'</li>' for k,v in processed_basis(summary))+'</ul>'


def render_rail(summary):
 from html import escape
 colors=['#7146aa','#5265b6','#347ac2','#8faaa0','#e8bd4b']
 catalog=STATE_CATALOG.get(summary.get('details',{}).get('strategy_id') or ('us_equity' if summary.get('details',{}).get('strategy_mode')=='us_monthly_trend' else summary['asset_type']),[])
 current_status=display_status(summary)
 current_index=next((i for i,e in enumerate(catalog) if e[0]==current_status),0)
 active=next((e for e in catalog if e[0]==current_status),None)
 buttons=''.join(f'<button type="button" class="state-step{ " is-current" if code==current_status else ""}" style="--axis-pos:{i/max(1,len(catalog)-1)*100:.1f}%;--axis-color:{colors[i]}" data-meaning="{escape(meaning,quote=True)}" data-label="{escape(label,quote=True)}" onclick="inspectAssetState(this)"'+(' aria-current="step"' if code==current_status else '')+f'><span class="state-dot" aria-hidden="true"></span>{escape(display_action(summary) if code==current_status else label)}'+('<span class="current-arrow" aria-hidden="true"></span>' if code==current_status else '')+'</button>' for i,(code,label,tone,meaning) in enumerate(catalog))
 risk_badge=''
 return f'<div class="state-position" style="--current-pos:{current_index/max(1,len(catalog)-1)*100:.1f}%;--axis-color:{colors[current_index]}"><div class="axis-labels"><b>买入</b><span>卖出</span></div>'+risk_badge+'<div class="axis-scroll"><div class="state-rail">'+buttons+'</div></div><p class="current-reason"><b>当前判断：</b>'+escape(summary['reason'])+'</p><p class="state-explanation" aria-live="polite">'+escape(active[3] if active else summary['reason'])+'</p></div>'


def render_today_categories(contents=None):
 from html import escape
 contents=contents or {}
 categories=[('broad','宽基 ETF'),('us','美股宽基 ETF'),('industry','行业 ETF'),('macro','黄金/大类资产')]
 output='<div class="today-categories etf-monitor" style="grid-column:1/-1"><h2 class="etf-monitor-title">ETF买卖监测</h2><nav class="guide-tabs" aria-label="今日提醒资产类别">'
 for index,(key,label) in enumerate(categories):
  output+=f'<button type="button" data-category="{key}" aria-pressed="'+('true' if index==0 else 'false')+f'" aria-controls="today-category-{key}" onclick="selectTodayCategory(this)">{escape(label)}</button>'
 output+='</nav>'
 for index,(key,label) in enumerate(categories):
  output+=f'<section class="asset-section today-category" id="today-category-{key}"'+(' hidden' if index else '')+f' aria-label="{escape(label)}"><div class="asset-list" id="{key}List">'+contents.get(key,'')+'</div></section>'
 return output+'</div>'


def render_guide():
 """关键条件配简短用语解释，不重复列出决策。"""
 from html import escape
 from strategy_config import STRATEGY_CONFIG
 b=STRATEGY_CONFIG['broad_etf'];s=STRATEGY_CONFIG['sector_etf'];g=STRATEGY_CONFIG['macro_asset']['gold']
 sections=[
  ('宽基 ETF',[
   ('加仓','本轮暂不单独触发。'),('买入','按各标的条件判断。'),
   ('观察','等待入场或足够数据。'),('减仓','本轮暂不单独触发。'),('退出','按各标的条件判断。')],
   '收盘判断，下一交易日执行。买入是本期新资金许可，已有持仓不必重复交易；本轮只验证买入与退出。'),
  ('美股宽基 ETF · 513500 / 513100',[
   ('加仓','长期向上；过热消化至5%以内，且价格高于20日均价。'),
   ('买入','长期向上，未过热，且价格高于20日均价。'),
   ('观察','过热未解除、短期未恢复、数据不足，或溢价公告当日。'),
   ('减仓','长期向上时，首次高于60日均价至少15%，减半一次。'),
   ('退出','最近完整月份的过去12个月涨幅≤0。')],
   '长期向上：最近完整月份的过去12个月涨幅＞0。收盘判断，下一交易日执行；买入是新资金许可，已有持仓不重复买。冷却还需价格恢复，避免下跌中机械加仓。'),
  ('行业 ETF · 588170',[
   ('加仓','本策略暂不单独触发。'),
   ('买入',f"收盘价转到{s['ma_fast']}日均线上方。"),
   ('观察','仍在均线上方，没有新买点；或数据不足。'),
   ('减仓',f"首次收盘回到{s['ma_fast']}日均线或下方，减半一次。"),
   ('退出',f"连续两个交易日收盘不高于{s['ma_fast']}日均线，退出剩余持仓。")],
   '每日收盘判断，下一交易日执行；减半后回到线上，只买回减掉的部分。不足一手无法减半时跳过部分卖出。'),
  ('黄金 ETF',[
   ('加仓',f"过热后，短期涨幅与均线偏离均不高于{g['cooling_threshold']*100:g}%，按本期预算加仓。"),
   ('买入','首次指标就绪、未过热时可开始配置；未持有时加仓信号也可用于买入。'),
   ('观察','没有新信号时保持；减仓后尚未冷却，不重复卖出。'),
   ('减仓',f"近{g['return_window']}个交易日涨幅与{g['ma_window']}日均线偏离均至少{g['heat_threshold']*100:g}%，减半一次。"),
   ('退出','本策略不自动全部退出，允许长期持有。')],
   '收盘判断，下一交易日执行。同一阶段不重复交易，不设固定目标仓位，也不要求之前实际卖出过。'),
 ]
 research={'宽基 ETF': '<p><b>沪深300：低估且价格恢复时买入，高估转弱时退出。</b>用60日均线确认入场、80日均线确认退出，减少低估时过早买入。2013—2026年固定10万元条件模拟收益约373%、最大回撤31%，上一版本约306%、35%，同期持有约161%、53%。逐月起点的5年比较中，86%同时胜过持有、97%同时胜过普通定投；3年为74%、77%。</p><p>本轮比较450组参数与替代策略，再检查40/60/80/120日邻近条件和更高交易成本。80日退出比60日退出更常改善两项，比120日退出的最差回撤小；但这是事后选择的试行方案，短期仍可能落后，5年后段仅9个重叠起点，不能称为全局最优或未来胜率。</p><p><b>中证500：低估优先，估值不过高时跟随120日趋势。</b>将趋势入场的PE分位上限从90%降为60%，减少估值偏高时追入。2014—2026年固定10万元条件模拟收益约246%、最大回撤58%；上一版本约217%、59%，持有约151%、66%。每月1000元的利润/本金由59%升至70%，普通定投约43%。</p><p>第一轮531组及追加192组探索中，严格趋势保护降低回撤但损失收益，前段首选在后段失效，未采用。新版本在逐月3/5年起点、较高交易成本和小额资金检查中改善，但回撤下降有限；低估仍可直接买入，邻近周期并不都有效。这是事后选择的试行方案，5年后段只有9个重叠起点，不能称为最优或未来保证。</p><p><b>科创50：16日均线，留出上下2%的缓冲。</b>突破上沿进入买入阶段，跌到下沿退出，减少围绕均线反复交易。2021年11月至2026年9月，固定10万元模拟收益约99%、最大回撤24%；上一版20日均线约87%、30%，持有约6%、56%。每月1000元利润/本金约73%，上一版64%、普通定投46%；交易次数由128次减至50次。</p><p>稳定性复查：又比较148组简单均线、指数均线与多周期方案，按前段相邻参数共同有效、后段收益和回撤均改善筛选。两组通过前段门槛，但都未通过后段检查，未找到合格替代。原试行方案在2025年单独区间两项落后持有，参数仍较敏感；没有完整5年窗口或采用后的新行情，目前只能试行观察，尚未证明稳定更优。</p><p>与最初原策略相比，沪深300提高收益但回撤仍由约29%升至31%；中证500收益由35%升至246%，回撤由42%升至58%。这两项并非都优于最初原策略。科创50本轮在价格样本比较，不能与最初需要估值预热的短区间混比。买入/退出模型使用10万元固定本金、次日成交并计入费用；投资配置的新资金配比另按现有预算规则计算，不等于该回测的资金曲线。历史PE缺少发布版本，结果为条件模拟，不保证未来。</p><p>参考：<a href="https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Market-Timing-Sin-a-Little.pdf" target="_blank" rel="noopener noreferrer">估值择时研究</a>；具体参数为本App试行。</p>', '美股宽基 ETF · 513500 / 513100': '<p><b>与长期持有比较：目前未同时改善收益与回撤。</b>2015—2026年固定10万元模拟，标普策略收益约306%、回撤30%，持有约359%、30%；纳指策略约683%、24%，持有约710%、28%。标普回撤几乎不变，纳指回撤较小，但两者收益都低于持有。</p><p>选择长期方向与短期热度，是为了给持续下跌和过热设置处理依据。更长美元价格指数样本也主要是降低大回撤、牺牲部分收益，不能称为全面胜过持有。每月1000元预算模拟也未优于普通定投；资金方式不同，不能混用收益。</p><p>标普本轮另比较78组趋势与9组热度参数，均未同时胜过持有。10%过热、3%冷却的候选约342%收益、24%回撤，比现行规则改善，但仍低于持有约359%的收益；月度预算也低于普通定投，暂作研究候选。纳指另比较78组趋势与9组热度参数：20%过热、3%冷却候选在2014年6月至2026年9月约948%收益、24%回撤，同期持有约851%、28%；但后段33个完整3年起点固定资金两项胜出率为0%，全区间月度投入利润也低于定投，暂不替换。15%/5%仍是现行试行假设，不是最优参数。参考：<a href="https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf" target="_blank" rel="noopener noreferrer">长期趋势研究</a>，资料不背书本App参数。</p>', '行业 ETF · 588170': '<p><b>与长期持有比较：588170目前只改善回撤。</b>2025年5月至2026年9月，20日均线先减半、再退出的固定10万元模拟收益约105%、最大回撤30%，同期持有约169%、41%。收益明显较低，不能称为两项都更好。</p><p>20日均线提供清楚的趋势入场与退出依据，避免在持续下跌时一直等待回本；代价是震荡中反复交易、错过部分上涨。512760较长参考样本中同样规则两项改善，但不能代替588170本身的短样本验证。1000元固定本金及月度预算检查也未显示588170全面优于持有。</p><p>参考：<a href="https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation" target="_blank" rel="noopener noreferrer">回测与敏感性检验方法</a>；小额交易需考虑最低佣金，历史结果不保证未来。</p>', '黄金 ETF': '<p><b>与长期持有比较：固定资金从首次买点参与时，两项改善。</b>2020年12月至2026年9月，10万元模拟收益约161%、最大回撤26%，持有约132%、30%；但只有3次减仓，改善集中在后段，前半段与持有相同。</p><p>黄金没有企业盈利，选择短期涨幅与均线偏离，是为了识别大涨后的减仓点，保留部分持仓参与上涨。这个优势依赖入场与资金安排：2021年6月空仓进入、等待实际新买点的模拟收益约30%，持有约131%；每月1000元预算模拟利润/本金约23%，普通定投约76%。不能将旧“买回卖出资金”模型的收益直接用于当前自由预算加仓。</p><p>允许长期持有、不设固定仓位；提前减仓也可能少赚。15%过热、5%冷却为试行阈值。参考：<a href="https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation" target="_blank" rel="noopener noreferrer">回测与敏感性检验方法</a>，资料不背书参数。</p>'}
 output='''<section class="card strategy-guide"><h2>策略说明</h2>
 <style>.guide-tabs{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 22px}.guide-tabs button{padding:9px 15px;border:1px solid #d5dce5;border-radius:7px;background:#fffefa;color:#526174;font:inherit;cursor:pointer}.guide-tabs button[aria-pressed="true"]{background:#e8eff8;border-color:#347ac2;color:#204d80;font-weight:700}.guide-panel[hidden]{display:none}</style>
 <nav class="guide-tabs" aria-label="策略资产类别">'''
 labels=['宽基 ETF','美股宽基 ETF','行业 ETF','黄金/大类资产']
 for index,label in enumerate(labels):
  selected='true' if index==0 else 'false'
  output+=f'''<button type="button" aria-pressed="{selected}" aria-controls="guide-category-{index}" onclick="var guide=this.closest('.strategy-guide');guide.querySelectorAll('.guide-tabs button').forEach(function(button){{button.setAttribute('aria-pressed',button===this?'true':'false')}},this);guide.querySelectorAll('.guide-panel').forEach(function(panel){{panel.hidden=panel.id!==this.getAttribute('aria-controls')}},this)">{escape(label)}</button>'''
 output+='</nav>'
 for index,(title,rows,note) in enumerate(sections):
  output+=f'<section class="guide-panel" id="guide-category-{index}"'+(' hidden' if index else '')+'>'
  output+='<h3>'+escape(title)+'</h3>'
  if title=='宽基 ETF':output+='<p>沪深300看估值与买卖确认，中证500结合估值与趋势，科创50看16日均线与2%缓冲。</p>'
  if title=='美股宽基 ETF · 513500 / 513100':output+='<p>方向与热度型：长期向上时买入，短期过热时减仓，长期转弱时退出。</p>'
  if title=='行业 ETF · 588170':output+='<p>趋势型：用20日均线判断买卖点，转弱时先减仓，再确认退出。</p>'
  if title=='黄金 ETF':output+='<p>过热与冷却型：大涨后减仓，热度消化后加仓，允许长期持有。</p>'
  if title=='宽基 ETF':output+='<p><label for="valuationYears">估值参考年限：</label><select id="valuationYears" onchange="changeValuationYears(this.value)"><option value="3">近3年</option><option value="5" selected>近5年</option><option value="10">近10年</option></select></p><p class="muted">年限只影响沪深300与中证500，默认5年；历史不足时观察。科创50不使用估值。</p>'
  groups=[(None,rows)]
  if title=='宽基 ETF':
   groups=[]
   for name,buy,exit_ in [
    ('沪深300 · 510300','PE分位低于30%，且收盘高于60日均价；进入后保持买入许可。','PE分位至少90%，且收盘不高于80日均价。'),
    ('中证500 · 510500','PE分位低于30%，或低于60%且收盘高于120日均价；进入后保持许可。','PE分位至少30%，且收盘不高于120日均价。'),
    ('科创50 · 588000','收盘高于16日均价的102%；进入后保持许可。','收盘不高于16日均价的98%；缓冲区内保持原判断。')]:
    groups.append((name,[('加仓','本轮暂不单独触发。'),('买入',buy),('观察','等待入场或足够数据。'),('减仓','本轮暂不单独触发。'),('退出',exit_)]))
  for name,group_rows in groups:
   if name:output+='<h4>'+escape(name)+'</h4>'
   output+='<div class="guide-table"><table><tr><th>决策</th><th>关键条件</th></tr>'
   output+=''.join('<tr><td>'+escape(label)+'</td><td>'+escape(text)+'</td></tr>' for label,text in group_rows)
   output+='</table></div>'
  if note:output+='<p class="muted">'+escape(note)+'</p>'
  output+='<details><summary>研究依据</summary>'+research[title]+'</details>'
  output+='</section>'
 output+='</section>'
 return output
