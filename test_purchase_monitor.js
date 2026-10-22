const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('purchase_monitor.js','utf8');
function render(updated){const card={dataset:{}};const root={prepend(){}};class FixedDate extends Date{constructor(...args){super(...(args.length?args:['2026-10-14T12:00:00+08:00']));}}
 const row={kind:'us',index:'纳指100',unit_nav:1.2,nav_date:'2026-10-14',name:'南方纳指',code:'021000',channel:'官方',fee_pct:.66,product_url:'https://example.com',note:'仅观察',quota:{source_date:'2026-10-14',direct_limit:'200',retail_limit:'无代销'}};
 vm.runInNewContext(source,{window:{addEventListener(){},FUND_ACCESS_MONITOR:{updated_at:updated,rows:[row],errors:[],future_alerts:['2026-10-15 暂停申购'],quota_source:'https://example.com'}},document:{addEventListener(){},getElementById:id=>id==='sec-today'?root:id==='usPurchaseMonitor'?card:null,createElement:()=>card},Intl,Date:FixedDate});return card.innerHTML;}
assert.ok(render('2026-10-14T11:00:00+08:00').includes('直销 200'));
assert.ok(render('2026-10-14T11:00:00+08:00').includes('2026-10-15 暂停申购'));
assert.ok(render('2026-10-13T11:00:00+08:00').includes('待核实'));
assert.ok(render('2026-10-13T11:00:00+08:00').includes('无今日公开额度'));
console.log('Purchase monitor page: current quota, future notices and expired snapshot OK');
