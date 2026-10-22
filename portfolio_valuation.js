/* Read-only retrospective account valuation. Never creates trades or cash flows. */
(function(){
 const prevDay=d=>{const t=new Date(d+'T00:00:00Z');t.setUTCDate(t.getUTCDate()-1);return t.toISOString().slice(0,10);};
 function navAt(f,date){
  if(!f?.nav?.length)return null;
  let lo=0,hi=f.nav.length-1,ans=null;
  while(lo<=hi){let m=(lo+hi)>>1;if(f.nav[m][0]<=date){ans=f.nav[m];lo=m+1;}else hi=m-1;}
  return ans&&Number.isFinite(ans[1])&&ans[1]>0?{date:ans[0],nav:ans[1]}:null;
 }
 function report(p,funds,replay,end,options={}){
  if(!p.opening)return {ready:false,reason:'请先在投资配置确认新账户的空仓期初。',rows:[],months:[]};
  if(end<p.opening.date)return {ready:false,reason:'所选截止日在账户开始之前。',rows:[],months:[]};
  const days=Math.round((Date.parse(end)-Date.parse(p.opening.date))/86400000);
  if(days>10000)throw Error('账户跨度过长，请检查期初日期');
  const errors=[],latestMarks={};
  function mark(state,date){
   let held=0;
   for(const pos of state.positions){
    const point=navAt(funds[pos.code],date);
    const calendar=options.calendar;
    let stale=point&&(Date.parse(date)-Date.parse(point.date))/86400000>7;
    if(point&&calendar?.length&&date<=calendar.at(-1)){
     const upper=x=>{let a=0,b=calendar.length;while(a<b){const m=(a+b)>>1;if(calendar[m]<=x)a=m+1;else b=m;}return a;};
     stale=upper(date)-upper(point.date)>3;
    }
    if(!point||stale){errors.push(`${date} ${pos.code} 缺少可用净值（已跳过日历内休市；异常缺数停算）`);return null;}
    latestMarks[pos.code]=point.date;held+=pos.shares*point.nav;
   }
   return held;
  }
  // Accrue cash/reinvestment entitlement on ex-date. Actual receipt remains a
  // separately confirmed internal income; it is never an external contribution.
  const entitlements=[];
  for(const [code,f] of Object.entries(funds))for(const d of f.dividends||[]){
   if(d.ex_date<p.opening.date||d.ex_date>end)continue;
   const record=d.record_date||prevDay(d.ex_date);
   const state=replay(p,record),q=state.positions.find(x=>x.code===code)?.shares||0;
   if(q>0)entitlements.push({code,exDate:d.ex_date,amount:q*d.per_share,payDate:d.pay_date});
  }
  function dividends(date){
   const accrued=entitlements.filter(x=>x.exDate<=date).reduce((a,x)=>a+x.amount,0);
   let paid=0;
   for(const x of p.incomes||[]){
    if(x.date>date)continue;
    const expected=entitlements.filter(d=>d.code===x.code&&d.exDate===x.exDate).reduce((a,d)=>a+d.amount,0);
    const matched=(p.incomes||[]).filter(y=>y.date<=date&&y.code===x.code&&y.exDate===x.exDate).reduce((a,y)=>a+y.amount,0);
    if(expected===0||Math.abs(matched-expected)>.021){errors.push(`${date} ${x.code} 分红确认与权益记录不符，请核对份额、除息日和分红金额`);return null;}
    paid+=x.amount;
   }
   return Math.max(0,accrued-paid);
  }
  const openingHeld=mark({positions:p.opening.positions||[]},p.opening.date);
  if(openingHeld==null)return {ready:false,reason:errors[0],errors,rows:[],months:[]};
  const initial=p.opening.cash+openingHeld;let previous=initial,unit=1,peak=1,cumulativeFlows=0,cumulativeFees=0;
  const rows=[];
  for(let i=0;i<=days;i++){
   const t=new Date(p.opening.date+'T00:00:00Z');t.setUTCDate(t.getUTCDate()+i);const date=t.toISOString().slice(0,10);
   const state=replay(p,date),held=mark(state,date),dividendReceivable=dividends(date);
   if(held==null||dividendReceivable==null)return {ready:false,reason:errors.at(-1),errors,rows,months:[]};
   const equity=state.poolCash+(state.frozenCash||0)+state.receivable+held+dividendReceivable;
   const netFlow=(p.flows||[]).filter(f=>f.date===date).reduce((a,f)=>a+(f.type==='deposit'?f.amount:-f.amount),0);
   const fee=(p.entries||[]).filter(e=>e.status==='confirmed'&&e.confirmedDate===date).reduce((a,e)=>a+e.fee,0);
   const pnl=equity-previous-netFlow,base=previous+netFlow;
   if(base< -1e-8 || (Math.abs(base)<1e-8 && Math.abs(pnl)>.021))return {ready:false,reason:'资金流时序不足以计算当日收益率，请核对同日顺序。',rows,months:[]};
   const ret=base>1e-8?pnl/base:0;unit*=1+ret;peak=Math.max(peak,unit);cumulativeFlows+=netFlow;cumulativeFees+=fee;
   const navDates=Object.fromEntries(state.positions.map(pos=>[pos.code,navAt(funds[pos.code],date).date])),estimated=Object.values(navDates).some(d=>d!==date)||(state.frozenCash||0)>0;
   rows.push({date,equity,cash:state.poolCash,frozen:state.frozenCash||0,held,receivable:state.receivable,dividendReceivable,netFlow,pnl,unit,drawdown:unit/peak-1,cumulativePnl:equity-initial-cumulativeFlows,fee,fees:cumulativeFees,navDates,estimated});
   previous=equity;
  }
  const groups=new Map();for(const row of rows){const m=row.date.slice(0,7);if(!groups.has(m))groups.set(m,[]);groups.get(m).push(row);}
  const months=[...groups].map(([month,rs])=>({month,pnl:rs.reduce((a,r)=>a+r.pnl,0),netFlow:rs.reduce((a,r)=>a+r.netFlow,0),fees:rs.reduce((a,r)=>a+r.fee,0),equity:rs.at(-1).equity,estimated:rs.at(-1).estimated,partial:rs.at(-1).date!==new Date(Number(month.slice(0,4)),Number(month.slice(5,7)),0).toLocaleDateString('sv-SE')}));
  const last=rows.at(-1);return {ready:true,rows,months,initial,latestMarks,entitlements,summary:{...last,returnRate:last.unit-1,mdd:Math.min(0,...rows.map(r=>r.drawdown))}};
 }
 window.PortfolioValuation={report,navAt};
})();
