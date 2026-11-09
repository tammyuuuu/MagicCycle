/* Read-only dynamic target planning over the existing real/strategy ledger. */
(function(){
 const floor=x=>Math.floor((Math.max(0,x)+1e-9)*100)/100,round=x=>Math.round((x+1e-9)*100)/100;
 function plan({profile:p,strategy:s,data:D,date,capitalPool:C,valuation:V,snapshot=window.FUND_ACCESS_MONITOR,totalAssets}){
  const A=window.ProductAssets,resolution=window.DynamicAllocation.resolve(s,window.DynamicAllocation.summaries(),date),pending=(p.entries||[]).filter(e=>e.status==='submitted');
  const weights=A.weights(s,resolution.weights),budget=Number.isFinite(totalAssets)?totalAssets*p.ratio:null;
  const result={rows:[],signalReady:resolution.ready,signalState:resolution.state,signalDate:resolution.signalDate,signalDiagnostics:resolution.diagnostics,date,targetBudget:budget,
   reason:resolution.ready?'按当前投资预算计算目标；沿用同一账户持仓、成本和成交，待到账资金不用于申购。':resolution.reason};
  if(p.broken||!p.opening)return {...result,reason:'先确认投资预算与现有真实账户，已有交易无需重复录入。'};
  const report=V.report(p,D.funds,window.XingxunStore.replay,date,{calendar:D.calendar});
  if(!report.ready)return {...result,reason:report.reason+'；估值不足，暂停新建议。'};
  if(budget==null)return {...result,reason:'总金融资产预算待确认，暂不计算新的目标金额。'};
  result.budget=C.poolBudget(totalAssets,report.summary.equity,0,p.ratio);
  const byCode=new Map(),actual=p.positions||[];
  function rowFor(code){if(!byCode.has(code))byCode.set(code,{code,asset:A.assetOf(code,p),name:D.funds[code]?.name||code,current:0,pendingBuy:0,pendingSell:0,target:0,weight:0,delta:0,amount:0,fee:0,shares:0,action:'无操作',executable:false});return byCode.get(code);}
  for(const pos of actual){const point=V.navAt(D.funds[pos.code],date);if(point)rowFor(pos.code).current+=pos.shares*point.nav;}
  for(const e of pending){const row=rowFor(e.code);if(e.action==='买入')row.pendingBuy+=e.amount;else if(['卖出','减仓'].includes(e.action))row.pendingSell+=e.amount;}
  // Preserve existing same-asset products; no duplicate opening purchase just to
  // match the research fund code. Unknown products remain visible for verification.
  for(const [asset,weight] of Object.entries(weights)){
   const held=[...byCode.values()].filter(r=>r.asset===asset&&(r.current+r.pendingBuy)>0);
   const candidates=held.length?held:[rowFor(A.selected(asset,p))];
   const basis=candidates.reduce((n,r)=>n+r.current+r.pendingBuy,0);
   for(const row of candidates){row.weight=weight*(basis>0?(row.current+row.pendingBuy)/basis:1);row.target=budget*row.weight;}
  }
  let cash=Math.max(0,p.poolCash||0);const buyCandidates=[];
  for(const row of byCode.values()){
   const code=row.code,t=A.terms(code,p,D,snapshot,date),pos=actual.find(x=>x.code===code),point=V.navAt(D.funds[code],date);
   row.current=round(row.current);row.pendingBuy=round(row.pendingBuy);row.pendingSell=round(row.pendingSell);
   Object.assign(row,{assetName:A.assets[row.asset]?.name||'待核实资产',channel:t.channel,status:t.status,statusDate:t.as_of,minimum:t.minimum,buy_pct:t.buy_pct,navDate:point?.date});
   row.target=round(row.target);row.delta=round(row.target-row.current-row.pendingBuy);
   row.reason='偏离在2%交易带内，继续持有。';
   if(!A.assets[row.asset]){row.target=null;row.delta=null;row.reason='已有持仓已继承；资产归属待核实，保留原记录，不自动交易。';continue;}
   if(!resolution.ready){row.target=null;row.weight=null;row.delta=null;row.reason=resolution.reason;continue;}
   if(pending.some(e=>A.assetOf(e.code,p)===row.asset)){row.reason='同一资产有待确认订单，先完成确认，不重复交易。';continue;}
   if(!point||(Date.parse(date)-Date.parse(point.date))/86400000>7){row.reason='暂无交易建议。';continue;}
   const band=Math.max(10,budget*.02),zeroExit=row.weight===0&&row.current>0;
   if(row.delta < -band||Math.abs(row.delta+band)<1e-8||zeroExit){
    row.action='卖出';
    if(!pos||!t.redeem_tiers?.length){row.reason='缺少可核实赎回费率或持仓，暂不生成可执行赎回。';continue;}
    if((p.entries||[]).some(e=>e.code===code&&e.action==='买入'&&e.status==='confirmed'&&e.confirmedDate>=date)){row.reason='刚确认份额尚待可赎回日期，不重复提交。';continue;}
    row.shares=floor(Math.min(pos.availableShares??pos.shares,zeroExit?pos.shares:-row.delta/point.nav));
    const remaining=pos.shares-row.shares;
    if(remaining>1e-8&&remaining<t.minimum_residual){
     if((pos.availableShares??pos.shares)+1e-8>=pos.shares)row.shares=floor(pos.shares);
     else{row.reason='最低保留份额要求全赎，但仍有不可赎份额。';continue;}
    }
    if(row.shares<=0||(row.shares<t.minimum_redeem&&Math.abs(row.shares-pos.shares)>1e-8)){row.reason='可赎回份额不足或低于最低赎回限制。';continue;}
    const ages=(p.entries||[]).filter(e=>e.code===code&&e.action==='买入'&&e.status==='confirmed').map(e=>(Date.parse(date)-Date.parse(e.confirmedDate))/86400000);
    row.amount=round(row.shares*point.nav);row.fee=round(row.amount*C.redeemRate(t.redeem_tiers,ages.length?Math.min(...ages):0)/100);row.executable=true;
    row.reason='建议赎回 '+row.shares.toFixed(2)+'份；预估净回款 ¥'+round(row.amount-row.fee).toFixed(2)+'。费用按最短已知持有期估计，须实际到账后再申购。';
   }else if(row.delta>=band){
    row.action='买入';
    const used=(p.entries||[]).filter(e=>e.code===code&&e.action==='买入'&&['submitted','confirmed'].includes(e.status)&&(e.submittedDate||e.date)===date).reduce((n,e)=>n+e.amount,0);
    if(!t.ready){row.reason=t.reason+'，暂不生成可执行申购。';continue;}
    const cap=Math.max(0,(t.limit??0)-used);
    if(cap<Math.max(10,t.minimum)){row.reason='剩余额度低于最低申购金额。';continue;}
    buyCandidates.push({row,point,t,want:Math.min(row.delta,cap)});
   }
  }
  const wanted=buyCandidates.reduce((n,x)=>n+x.want,0),available=cash;
  for(const {row,point,t,want} of buyCandidates){
   row.amount=floor(Math.min(cash,wanted>available?available*want/wanted:want));
   if(row.amount<Math.max(10,t.minimum)){row.reason='可用现金不足最低申购金额；等待实际入金或赎回到账，不垫资。';row.amount=0;continue;}
   row.fee=round(row.amount-row.amount/(1+t.buy_pct/100));row.shares=round((row.amount-row.fee)/point.nav);row.executable=true;cash=round(cash-row.amount);
   row.reason='建议申购 ¥'+row.amount.toFixed(2)+'（含预估申购费 ¥'+row.fee.toFixed(2)+'）；实际份额及确认时间以渠道为准。';
  }
  result.rows=[...byCode.values()].filter(r=>r.current>0||r.pendingBuy>0||r.pendingSell>0||r.weight>0);
  const executed=result.rows.filter(r=>r.executable),buys=executed.filter(r=>r.action==='买入').reduce((n,r)=>n+r.amount,0),sells=executed.filter(r=>r.action==='卖出').reduce((n,r)=>n+r.amount,0),fees=executed.reduce((n,r)=>n+r.fee,0);
  result.totals={buys,sells,fees,post_cash:round((p.poolCash||0)-buys),spendable_before:p.poolCash||0,post_receivable:(p.receivable||0)+sells-executed.filter(r=>r.action==='卖出').reduce((n,r)=>n+r.fee,0)};
  return result;
 }
 window.DynamicAccountPlan={plan};
})();
