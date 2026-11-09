/* Live asset allocation adapter; historical weights/results and the old research planner stay intact. */
(function(){
 function plan({profile:p,strategy:s,data:D,date,capitalPool:C,valuation:V,snapshot=window.FUND_ACCESS_MONITOR,totalAssets}){
  if(s.dynamic&&window.DynamicAccountPlan)return window.DynamicAccountPlan.plan({profile:p,strategy:s,data:D,date,capitalPool:C,valuation:V,snapshot,totalAssets});
  const resolved=window.DynamicAllocation?.resolve(s,window.DynamicAllocation.summaries(),date)||{ready:!s.dynamic,weights:s.weights};
  const A=window.ProductAssets,weights=A.weights(s,resolved.weights),pending=(p.entries||[]).filter(e=>e.status==='submitted');
  const baseRows=Object.keys(weights).map(asset=>({asset,code:A.selected(asset,p),name:A.assets[asset]?.name||asset,weight:weights[asset],amount:0,fee:0,current:0,action:'无操作',executable:false}));
  if(!resolved.ready)return {rows:baseRows,reason:resolved.reason||'暂不生成交易计划。',signalReady:false};
  if(p.broken||!p.opening)return {rows:baseRows,reason:'确认总资产后计算操作金额。'};
  const report=V.report(p,D.funds,window.XingxunStore.replay,date,{calendar:D.calendar});
  if(!report.ready)return {rows:baseRows,reason:report.reason+'；净值不足，暂停计划。'};
  const positions=new Map(),funds={},conditions={};
  for(const pos of p.positions||[]){const asset=A.assetOf(pos.code,p),point=V.navAt(D.funds[pos.code],date),current=positions.get(asset)||{code:asset,value:0,sellable:!asset.startsWith('unmapped-')};current.value+=pos.shares*point.nav;positions.set(asset,current);}
  for(const entry of pending.filter(e=>e.action==='买入')){const asset=A.assetOf(entry.code,p),pos=positions.get(asset)||{code:asset,value:0,sellable:false};pos.value+=entry.amount;positions.set(asset,pos);}
  const targets={...weights};for(const asset of positions.keys())targets[asset]??=0;
  for(const asset of Object.keys(targets)){
   const code=A.selected(asset,p)||(p.positions||[]).find(pos=>A.assetOf(pos.code,p)===asset)?.code,t=A.terms(code,p,D,snapshot,date);conditions[asset]={...t,code};
   const used=(p.entries||[]).filter(e=>e.code===code&&e.action==='买入'&&['submitted','confirmed'].includes(e.status)&&(e.submittedDate||e.date)===date).reduce((sum,e)=>sum+e.amount,0);
   const limit=t.limit==null?0:Math.max(0,t.limit-used);
   const needsSell=(s.dynamic&&targets[asset]===0&&(positions.get(asset)?.value||0)>0)||(positions.get(asset)?.value||0)-targets[asset]*report.summary.equity>=Math.max(10,.02*report.summary.equity);
   funds[asset]={name:A.assets[asset]?.name||D.funds[code]?.name||code,nav:1,buy_pct:t.buy_pct,limit:limit===Infinity?'不限额':limit+'元',redeem_tiers:t.redeem_tiers,settle_days:t.settle_days,status:(t.ready||needsSell)&&!pending.some(e=>A.assetOf(e.code,p)===asset)?'':'暂停'};
  }
  const raw=C.planDay({totalAssets:totalAssets??report.summary.equity/(p.ratio||.1),poolCash:p.poolCash,positions:[...positions.values()],targets,funds,buyBand:.02,sellBand:.02,minAmount:s.dynamic?10:.01,liquidateZero:!!s.dynamic,externalCash:0,receivable:p.receivable||0,ratio:p.ratio});
  for(const row of raw.rows){
   const asset=row.code,t=conditions[asset],code=t.code;row.asset=asset;row.code=code;row.name=D.funds[code]?.name||code;row.assetName=A.assets[asset]?.name||'未核实资产';row.status=t.status;row.statusDate=t.as_of;row.minimum=t.minimum;row.limit=t.limit;row.channel=t.channel;row.buy_pct=t.buy_pct;row.navDate=V.navAt(D.funds[code],date)?.date;
   if(!t.ready&&row.action!=='卖出'){row.executable=false;row.reason=t.reason;}
   if(A.assetOf(code,p)!==asset){row.executable=false;row.reason='产品与目标资产的对应关系待核实，不自动视为等价替代。';}
   if(pending.some(e=>A.assetOf(e.code,p)===asset)){row.executable=false;row.reason='同一资产已有等待确认交易，禁止跨基金重复提交。';}
   if(!row.navDate||(Date.parse(date)-Date.parse(row.navDate))/86400000>7){row.executable=false;row.reason='暂不生成交易建议。';}
   if(row.action==='买入'){const point=V.navAt(D.funds[code],date);row.shares=point?(row.amount-row.fee)/point.nav:null;if(s.dynamic&&row.shares!=null)row.shares=Math.round(row.shares*100)/100;}
   if(row.action==='买入'&&row.amount<(t.minimum||Infinity)){row.executable=false;row.reason='剩余额度或可用现金不足最低申购金额。';}
   if(row.action==='卖出'){
    const pos=(p.positions||[]).find(x=>x.code===code),point=V.navAt(D.funds[code],date);
    if(!pos||!point||!t.redeem_tiers?.length){row.executable=false;row.reason='资产超配；请选择已持有且赎回费率已核实的产品。更换产品不会自动卖出。';continue;}
    const acquired=(p.entries||[]).filter(e=>e.code===code&&e.action==='买入'&&e.status==='confirmed').map(e=>(Date.parse(date)-Date.parse(e.confirmedDate))/86400000);
    if(s.dynamic&&(p.entries||[]).some(e=>e.code===code&&e.action==='买入'&&e.status==='confirmed'&&e.confirmedDate>=date)){row.executable=false;row.reason='本基金有刚确认份额，等待可赎回日期后再计算。';continue;}
    const precision=s.dynamic?100:10000;
    row.shares=Math.floor((Math.min((pos.availableShares??pos.shares),row.weight===0?pos.availableShares??pos.shares:row.amount/point.nav)+1e-9)*precision)/precision;row.amount=Math.round(row.shares*point.nav*100)/100;
    if(s.dynamic){
     const available=pos.availableShares??pos.shares,residual=pos.shares-row.shares;
     if(residual>1e-8&&residual<t.minimum_residual){if(available+1e-8>=pos.shares)row.shares=Math.floor((pos.shares+1e-9)*100)/100;else{row.executable=false;row.reason='最低保留份额要求全部赎回，但部分份额尚不可赎。';continue;}}
     if(row.shares<t.minimum_redeem&&Math.abs(row.shares-pos.shares)>1e-8){row.executable=false;row.reason='低于渠道最低赎回份额，暂不提交。';continue;}
     row.amount=Math.round(row.shares*point.nav*100)/100;
    }
    row.fee=Math.round(row.amount*C.redeemRate(t.redeem_tiers,acquired.length?Math.min(...acquired):0))/100;
    row.reason+='；费用按最短已知持有期估计，到账时间以渠道为准，赎回款实际到账后才能申购。';
    if(row.shares<=0)row.executable=false;
   }
  }
  const executable=raw.rows.filter(r=>r.executable),buys=executable.filter(r=>r.action==='买入').reduce((sum,r)=>sum+r.amount,0),sells=executable.filter(r=>r.action==='卖出').reduce((sum,r)=>sum+r.amount,0),fees=executable.reduce((sum,r)=>sum+r.fee,0);
  raw.totals={...raw.totals,buys,sells,fees,post_cash:p.poolCash-buys,post_invested:[...positions.values()].reduce((sum,pos)=>sum+pos.value,0)+buys-executable.filter(r=>r.action==='买入').reduce((sum,r)=>sum+r.fee,0)-sells,post_receivable:(p.receivable||0)+sells-executable.filter(r=>r.action==='卖出').reduce((sum,r)=>sum+r.fee,0),post_pool:report.summary.equity-fees,post_new_allowed:Math.max(0,raw.budget.pool_target-report.summary.equity+fees)};
  return {...raw,signalReady:true,signalState:resolved.state,reason:(resolved.state?resolved.state+' · 信号日 '+resolved.signalDate+'。':'')+'按实际持仓与可用现金计算差额；赎回款实际到账后再申购，不自动补足预算。'};
 }
 window.AssetPlanner={plan};
})();
