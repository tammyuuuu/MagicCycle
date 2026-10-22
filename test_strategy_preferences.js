const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('templates/_status_rail.html','utf8').split('<script>')[1].split('</script>')[0].replace(/\{\{[^}]+\}\}/g,'{}');
const storage=new Map(),select={value:''};
const context={console,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
 document:{addEventListener(){},getElementById:()=>select,querySelector:()=>null},
 setInvestmentSummaries:list=>context.updated=list};
context.window=context;vm.createContext(context);vm.runInContext(source,context);
context.STRATEGY_SUMMARIES=JSON.parse(fs.readFileSync('docs/index.json','utf8'));
const original=JSON.stringify(context.STRATEGY_SUMMARIES);
context.changeValuationYears('10');
assert.equal(select.value,'10');assert.equal(storage.get('valuationYears'),'10');
assert.equal(context.updated.find(s=>s.symbol==='588000').status,context.STRATEGY_SUMMARIES.find(s=>s.symbol==='588000').status);
assert.equal(context.updated.find(s=>s.symbol==='510500').status,context.STRATEGY_SUMMARIES.find(s=>s.symbol==='510500').details.strategy_options['10'].status);
context.changeValuationYears('5');
assert.equal(context.updated.find(s=>s.symbol==='510500').status,context.STRATEGY_SUMMARIES.find(s=>s.symbol==='510500').details.strategy_options['5'].status);
assert.equal(context.updated.find(s=>s.symbol==='588000').status,context.STRATEGY_SUMMARIES.find(s=>s.symbol==='588000').status);
assert.equal(JSON.stringify(context.STRATEGY_SUMMARIES),original);
context.localStorage.setItem=()=>{throw Error('storage unavailable');};
context.changeValuationYears('3');assert.equal(select.value,'3');
assert.equal(context.updated.find(s=>s.symbol==='510300').details.valuation.window_years,3);
console.log('Year selection, recalculation, insufficient history and storage fallback: OK');
const broad=context.STRATEGY_SUMMARIES.find(s=>s.symbol==='510300');
const withoutLongHistory=JSON.parse(JSON.stringify(broad));
withoutLongHistory.details.strategy_options['10']={status:'watch',action:'观察',reason:'历史不足',decision_basis:[['判断前提','历史不足']],decision_conditions:[],valuation:null,valuation_percentile:null,insufficient_history:true};
assert.equal(context.summaryWithValuationYears(withoutLongHistory,10).status,'watch');
assert.equal(context.summaryWithValuationYears(withoutLongHistory,10).details.insufficient_history,true);
assert.equal(context.updated.find(s=>s.symbol==='510300').details.strategy_version,'csi300_value_confirm_v2');
assert.equal(context.updated.find(s=>s.symbol==='510500').details.strategy_version,'csi500_value_trend_v2');
assert.equal(context.updated.find(s=>s.symbol==='510500').details.parameters.trend_entry_ceiling,60);
// 行业买点不随持仓改成加仓，三个启用决策仍对应原轴线颜色。
context.ASSET_STATE_CATALOG={sector_etf:[['add','加仓','','未启用'],['buy','买入','','新买点'],['watch','观察','','保持'],['reduce','减仓','','未启用'],['exit','退出','','线下']]};
context.ASSET_DISPLAY_STATUS_MAP={sector_etf:{}};
for(const [status,pos,color] of [['add',0,'#7146aa'],['buy',25,'#5265b6'],['watch',50,'#347ac2'],['reduce',75,'#8faaa0'],['exit',100,'#e8bd4b']]){
 const summary={asset_type:'sector_etf',status,reason:'test',details:{holding:true}};
 const html=context.assetStateRail(summary);
 assert(html.includes('--current-pos:'+pos+'%;--axis-color:'+color));
 assert.equal((html.match(/class="current-arrow"/g)||[]).length,1);
 assert.equal((html.match(/aria-current="step"/g)||[]).length,1);
 assert.equal((html.match(/class="state-step/g)||[]).length,5);
}
vm.runInContext(fs.readFileSync('archive/legacy_ui/investment_tools.js','utf8'),context);
const sector=context.STRATEGY_SUMMARIES.find(s=>s.symbol==='588170');
assert.equal(sector.details.strategy_version,'sector_ma20_partial_v2');
const base={...sector,risk_level:'normal',details:{...sector.details,insufficient_history:false,data_warning:null}};
for(const [status,expected] of [['buy',500],['watch',0],['exit',0]]){
 const calculation=context.InvestmentLogic.calculate(1000,[0,100,0,0,0],context.InvestmentLogic.defaults,[{...base,status}],{date:base.date,tradingDay:true});
 assert.equal(calculation.spent,expected);
}
console.log('Sector axis, holding independence and plan signal amounts: OK');
context.ASSET_STATE_CATALOG.macro_asset=context.ASSET_STATE_CATALOG.sector_etf;
for(const [status,pos,color] of [['add',0,'#7146aa'],['buy',25,'#5265b6'],['watch',50,'#347ac2'],['reduce',75,'#8faaa0']]){
 const summary={asset_type:'macro_asset',status,reason:'test',details:{holding:true}};
 assert(context.assetStateRail(summary).includes('--current-pos:'+pos+'%;--axis-color:'+color));
}
const gold=context.STRATEGY_SUMMARIES.find(s=>s.symbol==='518850');
assert.equal(gold.details.strategy_version,'gold_heat_actions_v2');
const restored={...gold,status:'add',risk_level:'normal',details:{...gold.details,fresh_add:true,insufficient_history:false,data_warning:null}};
const goldPlan=context.InvestmentLogic.calculate(1000,[0,0,100,0,0],context.InvestmentLogic.defaults,[restored],{date:gold.date,tradingDay:true});
assert.equal(goldPlan.spent,500);
assert.equal(goldPlan.rows[2].allocations[0].reason,gold.reason);
console.log('Gold axis and restoration budget: OK');

for(const code of ['513500','513100']){
 const summary=context.STRATEGY_SUMMARIES.find(s=>s.symbol===code);
 assert.equal(context.summaryWithValuationYears(summary,10),summary);
 assert.equal(summary.details.strategy_mode,'us_monthly_trend');
}
console.log('US monthly strategy remains independent of A-share valuation preferences: OK');
