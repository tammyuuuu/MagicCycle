const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),{test}=require('node:test');
function setup(){const W={ASHARE_CALENDAR:JSON.parse(fs.readFileSync('ashare_calendar.json','utf8'))},ctx={window:W,Intl,Date};vm.createContext(ctx);vm.runInContext(fs.readFileSync('dynamic_allocation.js','utf8'),ctx);const strategy={id:'L5',dynamic:true,weights:{'000015':.5,'008701':.5}};return {W,A:W.DynamicAllocation,strategy,run:(list,date='2026-10-31',s=strategy)=>W.DynamicAllocation.resolve(s,list,date)};}
const signal=(symbol,status,date='2026-10-30',extra={})=>({symbol,status,date,details:{strategy_version:symbol==='510300'?'csi300_value_confirm_v2':'csi500_pe_or_pb5_pe_exit_v4',...extra}});
test('frozen Today summaries with 29/30 October dates compute L1 rather than failing',()=>{
 const {run}=setup(),rows=JSON.parse(fs.readFileSync('test_fixtures/today_20261031.json','utf8')),before=JSON.stringify(rows),r=run(rows);assert.equal(r.ready,true);assert.equal(r.p500,false);assert.equal(r.p300,false);assert.equal(r.weights['000015'],.5);assert.equal(r.diagnostics.find(x=>x.symbol==='510300').missedSessions,1);assert.equal(JSON.stringify(rows),before);
});
test('weekends and long official holidays do not age a last-session permission',()=>{
 const {run}=setup();for(const [date,last] of [['2026-11-01','2026-10-30'],['2026-10-07','2026-09-30'],['2026-02-23','2026-02-13']]){
  const r=run([signal('510500','hold',last),signal('510300','holding',last)],date);assert.equal(r.ready,true,date);assert.equal(r.p500,true);assert.equal(r.p300,true);assert.ok(r.diagnostics.every(x=>x.missedSessions===0));
 }
});
test('buy/add/hold permissions persist; explicit exit overrides personal ownership and prior state',()=>{
 const {run,A}=setup();for(const status of ['buy','add','hold','holding','持有'])assert.equal(run([signal('510500',status),signal('510300','exit')]).p500,true);
 assert.equal(A.permission(signal('510500','watch','2026-10-30',{holding:true})),false);
 assert.equal(A.permission(signal('510500','watch','2026-10-30',{strategy_position:1})),true);
 assert.equal(A.permission(signal('510500','exit','2026-10-30',{holding:true,strategy_position:1})),false);
});
test('genuine stale, missing, future, unknown states and inconsistent version metadata still block',()=>{
 const {run}=setup();for(const bad of [null,signal('510300','buy','2026-10-27'),signal('510300','buy','2026-11-02'),signal('510300','unknown'),signal('510300','buy','2026-10-30',{strategy_version:'csi500_wrong'}),signal('510300','buy','2026-10-30',{strategy_presentation:{version:'conflicting'}})]){
  const r=run([signal('510500','buy'),bad].filter(Boolean));assert.equal(r.ready,false);assert.match(r.reason,/沪深300/);assert.ok(r.diagnostics.some(d=>!d.ready));
 }
});
test('unrelated market dates do not determine A-share signal validity; current official versions flow through',()=>{
 const {run}=setup();const rows=[signal('510500','hold'),signal('510300','buy','2026-10-29',{strategy_version:'csi300_value_confirm_v3'}),{symbol:'513100',date:'2026-10-31',details:{strategy_version:'us_version'},status:'buy'}];assert.equal(run(rows).ready,true);
});
test('Today published states are reused, while replaced raw feeds never reuse the previous displayed cache',()=>{
 const {W,A,strategy}=setup();const raw=[signal('510500','exit'),signal('510300','watch')];W.STRATEGY_SUMMARIES=raw;W.TODAY_STRATEGY_SOURCE=raw;W.TODAY_STRATEGY_SUMMARIES=[signal('510500','exit'),signal('510300','hold')];assert.equal(A.resolve(strategy,undefined,'2026-10-31').p300,true);
 W.STRATEGY_SUMMARIES=[signal('510500','exit'),signal('510300','exit')];assert.equal(A.resolve(strategy,undefined,'2026-10-31').p300,false);
});
test('all permission combinations retain original frozen L5/L6 allocation weights',()=>{
 const {A}=setup();for(const id of ['L5','L6'])for(const a of [false,true])for(const b of [false,true]){
  const w=A.weights(id,a,b);assert.ok(Math.abs(Object.values(w).reduce((n,v)=>n+v,0)-1)<1e-12);assert.equal(w['008701'],.5);
  if(a&&b&&id==='L6'){assert.equal(w['001214'],.4/3);assert.equal(w['160706'],.8/3);}else if(b)assert.equal(w['160706'],.4);else if(a)assert.equal(w['001214'],.2);else assert.equal(w['000015'],.5);
 }
});
