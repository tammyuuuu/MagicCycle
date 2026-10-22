/* Research-only target arithmetic. Never creates ledger shares or sends orders. */
(function(){
 function plan({profile:p,strategy:s,data:D,date,capitalPool:C,valuation:V}){
  const pending=(p.entries||[]).filter(e=>e.status==='submitted'),frozen=p.frozenCash||0;
  if(p.broken||!p.opening)return {rows:[],reason:'先确认一次总金融资产，系统会自动建立空仓账户。'};
  const report=V.report(p,D.funds,window.XingxunStore.replay,date,{calendar:D.calendar});
  if(!report.ready)return {rows:[],reason:report.reason+'；暂停计算计划，请先核对数据。'};
  const positions=(p.positions||[]).map(pos=>{
   const nav=V.navAt(D.funds[pos.code],date),dates=(p.entries||[]).filter(e=>e.code===pos.code&&e.action==='买入'&&e.status==='confirmed').map(e=>e.confirmedDate);
   return {...pos,value:pos.shares*nav.nav,holdDays:dates.length?Math.min(...dates.map(d=>(Date.parse(date)-Date.parse(d))/86400000)):0};
  });
  // Pending subscriptions count only as projected target exposure, never actual shares.
  for(const e of pending.filter(e=>e.action==='买入')){
   const pos=positions.find(x=>x.code===e.code);if(pos)pos.value+=e.amount;else positions.push({code:e.code,value:e.amount,shares:0,availableShares:0,holdDays:0});
  }
  const funds={};
  const targets={...s.weights};for(const pos of positions)if(!(pos.code in targets))targets[pos.code]=0;
  for(const code of Object.keys(targets)){
   const nav=V.navAt(D.funds[code],date),condition=D.trading_conditions?.[code];
   if(!nav||!condition)return {rows:[],reason:'缺少净值或费率快照，暂停计算。'};
   // C's status guard applies to both directions; enforce purchase status below instead.
   const limit=C.parseLimit(condition.limit),used=(p.entries||[]).filter(e=>e.code===code&&['买入','加仓'].includes(e.action)&&['submitted','confirmed'].includes(e.status)&&(e.submittedDate||e.date)===date).reduce((a,e)=>a+e.amount,0);
   funds[code]={...condition,limit:limit==null?condition.limit:Math.max(0,limit-used)+'元',name:D.funds[code].name,nav:nav.nav,status:'',confirm:'以渠道确认日为准'};
  }
  const raw=C.planDay({totalAssets:report.summary.equity*10,poolCash:p.poolCash,positions,targets,funds,buyBand:.02,sellBand:.02,externalCash:0,receivable:p.receivable||0,ratio:.1});
  for(const row of raw.rows){
   const condition=D.trading_conditions?.[row.code];row.status=condition?.status||'状态未知';row.statusDate=condition?.as_of;
   row.navDate=V.navAt(D.funds[row.code],date)?.date;
   if(pending.some(e=>e.code===row.code)){row.executable=false;row.reason='本基金有待确认交易，先完成确认；不重复提交。';}
   if(row.action==='买入'&&(!condition?.status||!['开放申购','限大额'].includes(condition.status)||condition.as_of!==date)){
    row.executable=false;row.reason=condition?.status?.includes('暂停')?'保存快照为暂停申购，跳过；可选择限购替代方案。':'申购状态快照不是今天或尚未核实，暂不生成可记录的申购。';
   }
   if(row.action==='买入'&&row.amount<10){row.executable=false;row.reason='当日剩余额度或可用现金不足最低10元，不提交。';}
   if(row.action==='卖出'){
    const pos=(p.positions||[]).find(x=>x.code===row.code),available=pos?.availableShares??0,estimatedRate=row.amount>0?row.fee/row.amount:0;
    row.shares=Math.floor(Math.min(row.shares||0,available)*10000)/10000;
    row.amount=Math.round(row.shares*(funds[row.code]?.nav||0)*100)/100;
    // Unknown opening lots use zero holding days; known lots use the shortest recorded age.
    row.fee=Math.round(row.amount*estimatedRate*100)/100;
    row.reason+='；费用按最短已知持有期保守估算，以渠道为准。';
    if(row.shares<=0){row.executable=false;row.reason='暂无可赎回确认份额。';}
   }
  }
  return {...raw,reason:'按账户现有净资产与可用现金计算；不假设卖出款提前到账，不自动补足预算。',projectedFrozen:frozen};
 }
 window.InvestmentPlanner={plan};
})();
