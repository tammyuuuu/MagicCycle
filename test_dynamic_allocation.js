const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),{test}=require('node:test');
function setup(){
 const storage=new Map(),ctx={window:{PRODUCT_ASSETS:JSON.parse(fs.readFileSync('product_assets.json')),addEventListener(){}},document:{readyState:'loading',addEventListener(){}},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},Intl,Date,crypto:require('crypto').webcrypto};vm.createContext(ctx);
 for(const file of ['portfolio_store.js','capital_pool.js','portfolio_valuation.js','purchase_monitor.js','dynamic_allocation.js','product_assets.js','asset_planner.js','dynamic_account_plan.js'])vm.runInContext(fs.readFileSync(file,'utf8'),ctx);
 const W=ctx.window,S=W.XingxunStore;S.setContext('real','strategy');S.initializeLedger({date:'2026-10-01',cash:2000,positions:[]});
 const m=JSON.parse(fs.readFileSync('workspace_data/manifest.json')),D=JSON.parse(fs.readFileSync('workspace_data/'+m.current));
 function signals(a,b){W.STRATEGY_SUMMARIES=[['510500',a,'csi500_pe_or_pb5_pe_exit_v4'],['510300',b,'csi300_value_confirm_v2']].map(([symbol,on,version])=>({symbol,status:on?'buy':'watch',date:'2026-10-21',details:{strategy_version:version}}));}
 function terms(code,extra={}){let p=S.profile();p.productTerms={...p.productTerms,[code]:{date:'2026-10-22',verified:true,evidence:'channel test fixture',channel:'alipay',status:'开放申购',limit:'不限额',minimum:10,buy_pct:D.trading_conditions[code].buy_pct,...extra}};S.saveProfile(p);}
 for(const code of ['000015','008701','001214','160706'])terms(code);
 const run=(id='L5')=>W.AssetPlanner.plan({profile:S.profile(),strategy:D.research.strategies.find(s=>s.id===id),data:D,date:'2026-10-22',capitalPool:W.CapitalPool,valuation:W.PortfolioValuation,totalAssets:20000,snapshot:null});
 signals(false,false);return {W,S,D,signals,run,terms};
}
test('all four permission states preserve budget and frozen priority/shared weights',()=>{
 const {W,signals,run}=setup();for(const [a,b] of [[false,false],[true,false],[false,true],[true,true]]){
  signals(a,b);for(const id of ['L5','L6']){
   const w=W.DynamicAllocation.weights(id,a,b);assert.ok(Math.abs(Object.values(w).reduce((n,x)=>n+x,0)-1)<1e-12);assert.equal(w['008701'],.5);
   const r=run(id);assert.equal(r.budget.pool_target,2000);assert.ok(r.totals.buys<=2000);assert.ok(r.totals.fees>0);
   if(a&&b&&id==='L6'){assert.equal(w['001214'],.4/3);assert.equal(w['160706'],.8/3);}else if(b){assert.equal(w['160706'],.4);assert.equal(w['001214'],0);}
  }
 }
});
test('unknown, stale, wrong-version and insufficient signals cannot turn into exit orders',()=>{
 const {W,run}=setup();for(const mutate of [()=>W.STRATEGY_SUMMARIES=[],()=>W.STRATEGY_SUMMARIES[0].date='2026-09-01',()=>W.STRATEGY_SUMMARIES[0].details.strategy_version='old',()=>W.STRATEGY_SUMMARIES[0].details.insufficient_history=true]){
  const old=JSON.stringify(W.STRATEGY_SUMMARIES);mutate();const r=run();assert.equal(r.signalReady,false);assert.ok(r.rows.every(x=>!x.executable));W.STRATEGY_SUMMARIES=JSON.parse(old);
 }
});
test('minimum, paused status and pending confirmation suppress repeat subscriptions',()=>{
 const {S,signals,run,terms}=setup();signals(true,false);terms('001214',{minimum:500});assert.equal(run().rows.find(r=>r.asset==='csi500').executable,false);
 terms('001214',{status:'暂停申购'});assert.equal(run().rows.find(r=>r.asset==='csi500').executable,false);
 S.saveJournal([{id:'p',mode:'real',accountId:'strategy',date:'2026-10-22',code:'001214',action:'买入',status:'submitted',amount:400,quantity:null,fee:.4}]);
 assert.equal(run().rows.find(r=>r.asset==='csi500').executable,false);assert.ok(run().totals.buys<=1600);
});
test('stock switch uses confirmed holdings; no reuse of redemption receivable or budget top-up',()=>{
 const {S,signals,run}=setup();S.saveJournal([{id:'b',mode:'real',accountId:'strategy',date:'2026-10-02',confirmedDate:'2026-10-05',code:'001214',action:'买入',status:'confirmed',amount:2000,quantity:300,fee:2}]);signals(false,true);
 const r=run(),sale=r.rows.find(r=>r.asset==='csi500');assert.equal(sale.action,'卖出');assert.ok(sale.shares<=300);assert.equal(Math.round(sale.shares*100),sale.shares*100);assert.equal(r.totals.buys,0);assert.equal(S.profile().poolCash,0);
});
test('zero-target stock dust exits below the rebalance band',()=>{
 const {S,signals,run}=setup();S.saveJournal([{id:'dust',mode:'real',accountId:'strategy',date:'2026-10-02',confirmedDate:'2026-10-05',code:'001214',action:'买入',status:'confirmed',amount:10,quantity:1,fee:0}]);signals(false,false);
 const row=run().rows.find(r=>r.asset==='csi500');assert.equal(row.action,'卖出');assert.equal(row.shares,1);assert.equal(row.executable,true);
});
test('channel minimum redemption can block a partial sale without using its proceeds',()=>{
 const {S,signals,run,terms}=setup();S.saveJournal([{id:'holding',mode:'real',accountId:'strategy',date:'2026-10-02',confirmedDate:'2026-10-05',code:'001214',action:'买入',status:'confirmed',amount:2000,quantity:3000,fee:2}]);signals(true,false);terms('001214',{minimum_redeem:10000});
 const r=run(),sale=r.rows.find(r=>r.asset==='csi500');assert.equal(sale.executable,false);assert.match(sale.reason,/最低赎回/);assert.equal(r.totals.buys,0);
});
test('targets use financial budget rather than replacing it with account equity',()=>{
 const {S,signals,run}=setup();S.saveJournal([{id:'small',mode:'real',accountId:'strategy',date:'2026-10-02',confirmedDate:'2026-10-05',code:'001214',action:'买入',status:'confirmed',amount:2000,quantity:300,fee:2}]);signals(true,false);
 const row=run().rows.find(r=>r.asset==='csi500');assert.equal(row.target,400);assert.ok(row.current>0&&row.current<400);assert.equal(row.executable,false);assert.equal(run().totals.buys,0);
});
test('switching L5/L6 changes only targets, never confirmed shares, costs, orders or account PnL',()=>{
 const {W,S,D,signals,run}=setup();S.saveJournal([{id:'original',mode:'real',accountId:'strategy',date:'2026-10-02',confirmedDate:'2026-10-05',code:'008701',action:'买入',status:'confirmed',amount:1000,quantity:450,fee:.6}]);signals(true,true);
 const before=JSON.stringify(S.profile()),mark=()=>JSON.stringify(W.PortfolioValuation.report(S.profile(),D.funds,S.replay,'2026-10-22',{calendar:D.calendar}));const perf=mark();
 const a=run('L5'),b=run('L6');assert.equal(a.rows.find(r=>r.code==='160706').target,800);assert.equal(b.rows.find(r=>r.code==='160706').target,533.33);
 assert.equal(JSON.stringify(S.profile()),before);assert.equal(mark(),perf);assert.equal(S.journal().length,1);
});
test('existing verified alternative fund inherits its target instead of buying the research code',()=>{
 const {S,D,signals,run}=setup();const code='991214';D.funds[code]=structuredClone(D.funds['001214']);D.trading_conditions[code]=structuredClone(D.trading_conditions['001214']);const p=S.profile();
 p.productMappings={[code]:{asset:'csi500',verified:true,currency:'CNY',date:'2026-10-22',source:'https://example.com/verified-fixture'}};S.saveProfile(p);
 S.saveJournal([{id:'alternative',mode:'real',accountId:'strategy',date:'2026-10-02',confirmedDate:'2026-10-05',code,action:'买入',status:'confirmed',amount:400,quantity:500,fee:.4}]);signals(true,false);
 const r=run(),row=r.rows.find(r=>r.code===code);assert.equal(row.target,400);assert.ok(row.current>0);assert.equal(r.rows.some(r=>r.code==='001214'),false);
});
test('latest official summary date guards against a missing newer stock signal',()=>{
 const {W,run}=setup();W.STRATEGY_SUMMARIES[0].date='2026-10-20';assert.equal(run().signalReady,false);assert.ok(run().rows.every(r=>!r.executable));
});
test('a uniformly old snapshot within seven calendar days cannot create a new buy',()=>{
 const {W,run}=setup();for(const s of W.STRATEGY_SUMMARIES){s.date='2026-10-19';s.status='buy';}
 const result=run();assert.equal(result.signalReady,false);assert.ok(result.rows.every(row=>!row.executable));
});
