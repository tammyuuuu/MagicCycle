/* 星循 V1：资金池与买卖金额计算（与 capital_pool.py 同逻辑，纯函数）。 */
(function () {
  const floor2 = x => Math.floor((x + 1e-9) * 100) / 100;
  const round2 = x => Math.round((x + 1e-9) * 100) / 100;

  function parseLimit(text) {
    if (typeof text !== 'string') return null;
    const m = text.match(/([\d.]+)\s*(亿元|万元|元)/);
    if (!m) return null;
    const v = Number(m[1]);
    return v * ({ '亿元': 1e8, '万元': 1e4, '元': 1 }[m[2]]);
  }

  function buyRate(buyPct, tiers, amount) {
    if (Number.isFinite(buyPct)) return Number(buyPct);
    if (!Array.isArray(tiers)) return 0;
    for (const t of tiers) {
      const cond = String(t.condition || '');
      const m = cond.match(/小于([\d.]+)(万元|元)/);
      if (m) {
        const lim = Number(m[1]) * (m[2] === '万元' ? 1e4 : 1);
        if (amount < lim) return Number(t.discount_pct ?? t.original_pct ?? 0);
      }
    }
    return 0;
  }

  function toDays(v, unit) {
    return Number(v) * (unit === '年' ? 365 : unit === '个月' ? 30 : 1);
  }

  function redeemRate(tiers, days) {
    if (!Array.isArray(tiers) || !tiers.length) return 0;
    for (const t of tiers) {
      const cond = String(t.condition || '');
      let lo = 0, loInc = true, hi = Infinity, hiInc = true;
      let m = cond.match(/大于等于([\d.]+)(天|个月|年)/);
      if (m) { lo = toDays(m[1], m[2]); }
      m = cond.match(/小于等于([\d.]+)(天|个月|年)/);
      if (m) { hi = toDays(m[1], m[2]); hiInc = true; }
      else {
        m = cond.match(/小于([\d.]+)(天|个月|年)/);
        if (m) { hi = toDays(m[1], m[2]); hiInc = false; }
      }
      const okLo = loInc ? days >= lo : days > lo;
      const okHi = hiInc ? days <= hi : days < hi;
      if (okLo && okHi) return Number(t.original_pct || 0);
    }
    return 0;
  }

  function conservativeRate(tiers) {
    if (!Array.isArray(tiers)) return 0.5;
    for (const t of tiers) {
      if (String(t.condition || '').includes('大于等于7天') && t.original_pct != null) return Number(t.original_pct);
    }
    return 0.5;
  }

  function poolBudget(totalAssets, poolValue, externalCash, ratio) {
    const target = Number(totalAssets) * Number(ratio);
    const newAllowed = Math.max(0, target - Number(poolValue));
    const used = Math.min(newAllowed, Math.max(0, Number(externalCash) || 0));
    return {
      total_assets: Number(totalAssets), ratio: Number(ratio),
      pool_target: target, pool_value: Number(poolValue),
      over_target: Math.max(0, Number(poolValue) - target),
      new_allowed: newAllowed, external_cash: Math.max(0, Number(externalCash) || 0),
      new_used: used
    };
  }

  function planDay(opts) {
    const o = Object.assign({
      totalAssets: 0, poolCash: 0, positions: [], targets: {}, funds: {},
      externalCash: 0, receivable: 0, ratio: 0.10, minAmount: 10,
      buyBand: 0.01, sellBand: 0.02, priority: 'pro_rata', feeMult: 1, scores: {}
    }, opts || {});
    const positions = o.positions || [];
    const funds = o.funds || {};
    const targets = o.targets || {};
    const sumW = Object.values(targets).reduce((a, b) => a + Number(b || 0), 0);
    if (sumW > 1 + 1e-9) throw Error('目标权重合计不能超过 100%');

    const poolValue = Number(o.poolCash) + positions.reduce((a, p) => a + Number(p.value || 0), 0) + Number(o.receivable || 0);
    const budget = poolBudget(o.totalAssets, poolValue, o.externalCash, o.ratio);
    const investable = poolValue + budget.new_used;
    let spendable = Math.max(0, Number(o.poolCash) + budget.new_used);
    const warnings = [];
    if (budget.over_target > 0) warnings.push(`资金池已超过目标 ${budget.over_target.toFixed(2)} 元：暂停新增投入，不强制卖出。`);

    const posMap = {};
    positions.forEach(p => { posMap[String(p.code)] = p; });
    const rows = [];
    const buys = [];
    const sells = [];
    let sellFees = 0;

    // 未配置持仓也要展示
    positions.forEach(p => {
      if (!(String(p.code) in targets)) {
        rows.push({
          code: String(p.code), name: p.name || String(p.code), weight: null,
          current: Number(p.value || 0), target: Number(p.value || 0),
          delta: 0, action: '未配置', amount: 0, fee: 0, shares: null,
          postValue: Number(p.value || 0), executable: false,
          reason: '未给出目标权重，保持不动（不计入新增投入）'
        });
      }
    });

    Object.keys(targets).forEach(code => {
      const f = funds[code];
      const pos = posMap[code];
      const current = pos ? Number(pos.value || 0) : 0;
      const targetValue = Number(targets[code] || 0) * investable;
      const delta = targetValue - current;
      const row = {
        code, name: f ? f.name : (pos ? pos.name : code), weight: Number(targets[code] || 0),
        current, target: targetValue, delta, action: '无操作', amount: 0,
        fee: 0, shares: null, postValue: current, executable: false, reason: ''
      };
      rows.push(row);
      if (!f) { row.reason = '缺少基金信息'; return; }
      if (!Number.isFinite(f.nav) || f.nav <= 0) { row.reason = '缺少有效净值，不生成交易'; return; }
      if (f.status && String(f.status).includes('暂停')) {
        row.reason = `基金状态为“${f.status}”，不可申购`; return;
      }
      if (delta >= Math.max(o.minAmount, o.buyBand * investable)) {
        buys.push({ row, delta, frac: Number((o.scores || {})[code] || 0) });
      } else if (delta <= -Math.max(o.minAmount, o.sellBand * investable) || (o.liquidateZero && Number(targets[code])===0 && current>0)) {
        if (pos && pos.sellable !== false) {
          sells.push({ row, gap: -delta, pos });
        } else {
          row.reason = '需要减仓，但当前无可卖份额（T+1 确认中）';
        }
      } else {
        row.reason = '偏离在交易带内，不操作';
      }
    });

    sells.forEach(it => {
      const row = it.row, pos = it.pos, f = funds[row.code];
      const amount = Math.min(it.gap, Number(pos.value || 0));
      const unknown = !Number.isFinite(pos.holdDays);
      const pct = unknown ? conservativeRate(f.redeem_tiers) : redeemRate(f.redeem_tiers, pos.holdDays);
      const fee = amount * pct / 100 * o.feeMult;
      row.action = '卖出';
      row.amount = amount;
      row.fee = fee;
      row.shares = amount / f.nav;
      row.postValue = Number(pos.value || 0) - amount;
      row.executable = true;
      row.reason = `目标 ${(row.weight * 100).toFixed(0)}%，超出 ${(amount / Math.max(1e-9, investable) * 100).toFixed(1)}% 权益；` +
        `赎回到账 T+${f.settle_days || 2}` + (unknown ? '；持有期未知，费率按保守估计' : '');
      sellFees += fee;
    });

    const totalWant = buys.reduce((a, b) => a + b.delta, 0);
    if (totalWant > spendable && totalWant > 0) {
      if (o.priority === 'signal' && buys.some(b => b.frac > 0)) {
        const ws = buys.reduce((a, b) => a + b.delta * b.frac, 0);
        buys.forEach(b => { b.alloc = ws > 0 ? spendable * b.delta * b.frac / ws : 0; });
      } else {
        buys.forEach(b => { b.alloc = spendable * b.delta / totalWant; });
      }
      warnings.push(`可用现金 ${spendable.toFixed(2)} 元不足以覆盖全部买点，按 ${o.priority} 分配。`);
    } else {
      buys.forEach(b => { b.alloc = b.delta; });
    }

    buys.forEach(it => {
      const row = it.row, f = funds[row.code];
      let amount = floor2(Math.min(it.alloc, spendable));
      if (amount < o.minAmount) { row.reason = `分配金额 ${amount.toFixed(2)} 元低于最小申购 ${o.minAmount} 元`; return; }
      const limit = parseLimit(f.limit);
      if (limit !== null && amount > limit) {
        amount = floor2(limit);
        row.reason = `受日累计申购限额 ${limit.toFixed(0)} 元限制，已截断；`;
      }
      const rate = buyRate(f.buy_pct, f.buy_tiers, amount) / 100 * o.feeMult;
      const fee = amount - amount / (1 + rate);
      const shares = (amount - fee) / f.nav;
      spendable -= amount;
      row.action = '买入';
      row.amount = amount;
      row.fee = fee;
      row.shares = shares;
      row.postValue = row.current + (amount - fee);
      row.executable = true;
      row.reason = (row.reason || '') +
        `目标 ${(row.weight * 100).toFixed(0)}%，缺口 ${it.delta.toFixed(2)} 元；` +
        `申购费 ${(rate * 100).toFixed(2)}%，${f.confirm || 'T+1'} 确认份额`;
    });

    const buysTotal = rows.filter(r => r.action === '买入').reduce((a, r) => a + r.amount, 0);
    const sellsTotal = rows.filter(r => r.action === '卖出').reduce((a, r) => a + r.amount, 0);
    const fees = rows.reduce((a, r) => a + (r.fee || 0), 0);
    const postCash = Number(o.poolCash) + budget.new_used - buysTotal;
    const postInvested = rows.reduce((a, r) => a + r.postValue, 0);
    const postPool = postCash + postInvested + Number(o.receivable || 0) + sellsTotal - sellFees;
    rows.forEach(r => { r.postWeight = postPool > 0 ? r.postValue / postPool : null; });

    if (postCash < -1e-6) throw Error('资金校验失败：现金为负');
    if (buysTotal > Number(o.poolCash) + budget.new_used + 1e-6) throw Error('资金校验失败：买入超过可用现金');

    return {
      rows, warnings, budget,
      totals: {
        buys: buysTotal, sells: sellsTotal, fees,
        spendable_before: Number(o.poolCash) + budget.new_used,
        post_cash: postCash, post_invested: postInvested, post_pool: postPool,
        post_new_allowed: Math.max(0, budget.pool_target - postPool)
      }
    };
  }

  window.CapitalPool = { poolBudget, planDay, buyRate, redeemRate, parseLimit };
})();

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

/* Live asset allocation adapter; historical weights/results and the old research planner stay intact. */
(function(){
 function plan({profile:p,strategy:s,data:D,date,capitalPool:C,valuation:V,snapshot=window.FUND_ACCESS_MONITOR,totalAssets}){
  if(s.dynamic&&window.DynamicAccountPlan)return window.DynamicAccountPlan.plan({profile:p,strategy:s,data:D,date,capitalPool:C,valuation:V,snapshot,totalAssets});
  const resolved=window.DynamicAllocation?.resolve(s,window.DynamicAllocation.summaries(),date)||{ready:!s.dynamic,weights:s.weights};
  const A=window.ProductAssets,weights=A.weights(s,resolved.weights),pending=(p.entries||[]).filter(e=>e.status==='submitted');
  const baseRows=Object.keys(weights).map(asset=>({asset,code:A.selected(asset,p),name:A.assets[asset]?.name||asset,weight:weights[asset],amount:0,fee:0,current:0,action:'无操作',executable:false}));
  if(!resolved.ready)return {rows:baseRows,reason:resolved.reason||'股票许可待更新，暂停计划。',signalReady:false};
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
   if(!row.navDate||(Date.parse(date)-Date.parse(row.navDate))/86400000>7){row.executable=false;row.reason='实际产品净值缺失或过旧，待核实。';}
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
   if(!point||(Date.parse(date)-Date.parse(point.date))/86400000>7){row.reason='产品净值缺失或过旧，暂停交易建议。';continue;}
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

/* Public fund identity lookup. Identity never implies strategy-asset equivalence. */
(function(){
 const source='https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx';
 function parse(payload,code){
  const row=payload?.Datas?.find(r=>String(r.CODE)===code&&r.CATEGORY===700),base=row?.FundBaseInfo;
  if(payload?.ErrCode!==0||!row||String(base?.FCODE)!==code||typeof row.NAME!=='string'||!row.NAME.trim()||/[<>]/.test(row.NAME))throw Error('未查到代码与名称一致的基金');
  const nav=Number(base.DWJZ),date=base.FSRQ,valid=window.ProductAssets.dateOK(date)&&date<=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())&&Number.isFinite(nav)&&nav>0;
  return {code,name:row.NAME.trim(),identityVerified:true,identitySource:source,identityDate:new Date().toISOString(),nav:valid?[[date,nav]]:[],publicInfo:{minimum:Number.isFinite(base.MINSG)&&base.MINSG>0?base.MINSG:null,status:base.ISBUY||null}};
 }
 function local(code,p){
  const f=window.WORKSPACE_DATA.funds[code],row=window.FUND_ACCESS_MONITOR?.rows?.find(r=>r.code===code),saved=p.productData?.[code];
  if(f)return {code,name:f.name,identityVerified:true,identitySource:'versioned workspace fund catalog',nav:[]};
  if(row?.name)return {code,name:row.name,identityVerified:true,identitySource:'purchase monitor catalog',nav:[]};
  if(saved?.identityVerified&&saved.identitySource===source&&saved.name)return {code,...saved};
  return null;
 }
 function lookup(code,p,refresh=false){
  if(!/^\d{6}$/.test(code))return Promise.reject(Error('请输入六位基金代码'));
  const known=local(code,p);if(known&&!refresh)return Promise.resolve(known);
  return new Promise((resolve,reject)=>{const callback='xingxunFund_'+Date.now()+'_'+Math.random().toString(36).slice(2),script=document.createElement('script');let timer;
   const clean=()=>{clearTimeout(timer);script.remove();delete window[callback];};
   window[callback]=payload=>{try{resolve(parse(payload,code));}catch(e){reject(e);}finally{clean();}};
   script.src=source+'?m=1&key='+code+'&callback='+callback;script.onerror=()=>{clean();reject(Error('基金名称暂无法核实，请联网重试'));};timer=setTimeout(()=>{clean();reject(Error('基金查询超时，未保存交易'));},12000);document.head.append(script);
  });
 }
 window.FundLookup={lookup,parse,refresh:code=>lookup(code,{},true)};
})();

/* Styled fund suggestions; selection still goes through the existing identity checks. */
(function(){
 const opened=new Set();
 document.addEventListener('pointerdown',e=>{for(const picker of [...opened])if(!picker.root.isConnected||!picker.root.contains(e.target))picker.close();});
 function init(root,input,toggle,list,items){
  let options=[],active=-1,isOpen=false;
  input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls',list.id);input.setAttribute('autocomplete','off');list.setAttribute('role','listbox');list.setAttribute('aria-label','基金列表');input.setAttribute('aria-label','基金代码');
  const picker={root,close};
  function close(){isOpen=false;list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');opened.delete(picker);}
  function highlight(index){active=index;[...list.children].forEach((el,i)=>{el.classList.toggle('active',i===active);el.setAttribute('aria-selected',String(i===active));});if(options[active]){input.setAttribute('aria-activedescendant',list.children[active].id);list.children[active].scrollIntoView({block:'nearest'});}}
  function choose(code){input.value=code;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));input.focus();close();}
  function show(query=''){
   for(const other of [...opened])if(other!==picker)other.close();
   options=items.filter(item=>(item.code+' '+item.name).toLowerCase().includes(query.toLowerCase()));active=-1;list.replaceChildren();
   for(const [i,item] of options.entries()){const option=document.createElement('div');option.id=list.id+'-option-'+i;option.className='fund-option';option.setAttribute('role','option');option.setAttribute('aria-selected','false');const name=document.createElement('span'),code=document.createElement('small');name.textContent=item.name;code.textContent=item.code;option.append(name,code);if(item.code===input.value)option.classList.add('chosen');option.onmousedown=e=>e.preventDefault();option.onclick=()=>choose(item.code);list.append(option);}
   if(!options.length){const empty=document.createElement('div');empty.className='fund-picker-empty';empty.textContent='输入完整六位代码可查询其他基金';list.append(empty);}
   isOpen=true;list.hidden=false;input.setAttribute('aria-expanded','true');opened.add(picker);
  }
  input.addEventListener('focus',()=>show());input.addEventListener('input',()=>show(input.value.trim()));
  input.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();close();}else if(e.key==='Tab')close();else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(!isOpen)show();if(options.length)highlight(active<0?(e.key==='ArrowDown'?0:options.length-1):(active+(e.key==='ArrowDown'?1:-1)+options.length)%options.length);}else if(e.key==='Enter'&&isOpen&&active>=0){e.preventDefault();choose(options[active].code);}});
  root.addEventListener('focusout',e=>{if(!root.contains(e.relatedTarget))close();});
  toggle.onclick=()=>{if(isOpen)close();else{input.focus();show();}};
  close();
 }
 window.FundPicker={init};
 // Shared dropdown presentation; native selects retain values and form events.
 const selects=new Map();let activeSelect=null,serial=0;
 function enhance(select){
  if(selects.has(select)||select.multiple||select.size>1)return;
  const root=document.createElement('div'),button=document.createElement('button'),text=document.createElement('span'),menu=document.createElement('div');
  root.className='unified-select';button.type='button';button.className='select-trigger';button.append(text);
  menu.className='select-menu';menu.id='select-menu-'+(++serial);menu.hidden=true;menu.setAttribute('role','listbox');
  const label=select.getAttribute('aria-label')||[...(select.labels?.[0]?.childNodes||[])].filter(n=>n!==select).map(n=>n.textContent).join('').trim()||'选择选项';
  button.setAttribute('role','combobox');button.setAttribute('aria-label',label);button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-controls',menu.id);button.setAttribute('aria-expanded','false');menu.setAttribute('aria-label',label);
  select.before(root);root.append(select,button);document.body.append(menu);select.hidden=true;
  let index=-1,search='',lastKey=0;
  function sync(){const value=select.selectedOptions[0]?.textContent||'请选择';if(text.textContent!==value)text.textContent=value;if(button.disabled!==select.disabled)button.disabled=select.disabled;}
  function close(){menu.hidden=true;button.setAttribute('aria-expanded','false');button.removeAttribute('aria-activedescendant');if(activeSelect===entry)activeSelect=null;}
  function highlight(next){index=next;[...menu.children].forEach((el,i)=>el.classList.toggle('is-active',i===index));const item=menu.children[index];if(item){button.setAttribute('aria-activedescendant',item.id);const top=item.offsetTop,bottom=top+item.offsetHeight;if(top<menu.scrollTop)menu.scrollTop=top;else if(bottom>menu.scrollTop+menu.clientHeight)menu.scrollTop=bottom-menu.clientHeight;}}
  function choose(next){const option=select.options[next];if(!option||option.disabled||option.parentElement.disabled)return;select.value=option.value;sync();close();button.focus();select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));}
  function show(){
   if(select.disabled)return;if(activeSelect)activeSelect.close();for(const picker of [...opened])picker.close();sync();menu.replaceChildren();
   [...select.options].forEach((option,i)=>{const item=document.createElement('div');item.className='select-option';item.id=menu.id+'-'+i;item.textContent=option.textContent;item.setAttribute('role','option');item.setAttribute('aria-selected',String(i===select.selectedIndex));item.setAttribute('aria-disabled',String(option.disabled||!!option.parentElement.disabled));item.onpointerdown=e=>e.preventDefault();item.onclick=()=>choose(i);menu.append(item);});
   const rect=button.getBoundingClientRect(),below=innerHeight-rect.bottom-12,above=rect.top-12,up=below<180&&above>below,height=Math.max(48,Math.min(288,up?above:below));
   menu.style.width=Math.min(rect.width,innerWidth-16)+'px';menu.style.left=Math.max(8,Math.min(rect.left,innerWidth-rect.width-8))+'px';menu.style.maxHeight=height+'px';
   menu.style.top=up?'auto':rect.bottom+5+'px';menu.style.bottom=up?innerHeight-rect.top+5+'px':'auto';menu.hidden=false;button.setAttribute('aria-expanded','true');activeSelect=entry;highlight(select.selectedIndex);
  }
  const entry={root,menu,close,sync,button};selects.set(select,entry);sync();
  button.onclick=()=>menu.hidden?show():close();
  button.onkeydown=e=>{
   if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();if(menu.hidden)show();const enabled=[...select.options].map((o,i)=>!o.disabled&&!o.parentElement.disabled?i:-1).filter(i=>i>=0);if(!enabled.length)return;const pos=enabled.indexOf(index);highlight(e.key==='Home'?enabled[0]:e.key==='End'?enabled.at(-1):enabled[(pos+(e.key==='ArrowDown'?1:-1)+enabled.length)%enabled.length]);}
   else if(e.key==='Escape'){e.preventDefault();close();}
   else if(e.key==='Tab')close();
   else if((e.key==='Enter'||e.key===' ')&&!menu.hidden){e.preventDefault();choose(index);}
   else if(e.key.length===1&&e.key!==' '){e.preventDefault();if(menu.hidden)show();search=Date.now()-lastKey>700?e.key:search+e.key;lastKey=Date.now();const next=[...select.options].findIndex(o=>!o.disabled&&!o.parentElement.disabled&&o.textContent.trim().toLowerCase().startsWith(search.toLowerCase()));if(next>=0)highlight(next);}
  };
  select.addEventListener('change',sync);
 }
 function refreshSelects(){
  for(const [select,entry] of selects){if(!select.isConnected){entry.close();entry.menu.remove();selects.delete(select);}else{entry.sync();if(activeSelect===entry&&!entry.button.getClientRects().length)entry.close();}}
  document.querySelectorAll('.workspace select').forEach(enhance);
 }
 document.addEventListener('pointerdown',e=>{if(activeSelect&&!activeSelect.root.contains(e.target)&&!activeSelect.menu.contains(e.target))activeSelect.close();});
 document.addEventListener('focusin',e=>{if(activeSelect&&!activeSelect.root.contains(e.target))activeSelect.close();});
 window.addEventListener('resize',()=>activeSelect?.close());
 document.addEventListener('scroll',e=>{if(activeSelect&&!activeSelect.menu.contains(e.target))activeSelect.close();},true);
 function start(){refreshSelects();new MutationObserver(refreshSelects).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected','hidden']});}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();

/* User-provided Alipay subscription rates, separate from research fee assumptions. */
(function(){
 const rates=Object.freeze({'008701':0.06,'000015':0.08,'161130':0.12}),asOf='2026-10-22';
 function forCode(code){return rates[code]==null?null:{code,channel:'alipay',buy_pct:rates[code],as_of:asOf,source:'user_provided'};}
 function forTrade(trade){
  const saved=trade.purchaseFeePolicy;if(saved?.code===trade.code&&saved.channel==='alipay'&&Number.isFinite(saved.buy_pct)&&saved.buy_pct>=0&&saved.buy_pct<=100)return saved;
  if(trade.productChannel&&trade.productChannel!=='alipay')return null;
  if((trade.submittedDate||trade.date||'')<asOf)return null;
  return forCode(trade.code);
 }
 function amount(gross,policy){return Math.round((gross-gross/(1+policy.buy_pct/100))*100)/100;}
 window.UserPurchaseFees={forCode,forTrade,amount};
})();

/* Budget is a target, never proof of funded cash. Explicit receipts fund only actual payments. */
(function(){
 const cents=n=>Math.round(n*100)/100;
 function stagePurchase(p,row,S,start){if(p.accountFunding!=='actual_payments')return;const state=S.replay({...p,opening:{...p.opening,date:start||p.opening.date}},row.date),shortfall=cents(Math.max(0,row.amount-state.poolCash));if(shortfall>0)p.flows=[...(p.flows||[]),{id:'actual-payment-'+row.id,date:row.date,type:'deposit',amount:shortfall,source:'actual_trade_payment',tradeId:row.id,note:'按已记录的实际申购付款计入投入资金，非投资收益'}];}
 function candidate(p,snapshots){if(p.accountFunding==='actual_payments'||p.broken||!p.opening||p.opening.positions?.length||(p.flows||[]).length||(p.incomes||[]).length||(p.settlements||[]).length||p.poolCash<=.001)return false;const rows=p.entries||[];if(JSON.stringify(rows)!==JSON.stringify((p.journal||[]).filter(t=>t.action!=='观察')))return false;if(rows.some(t=>t.action!=='买入'||t.status!=='confirmed'||t.source!=='manual_executed_buy'))return false;return snapshots.some(s=>Math.abs(cents(s.total_assets*p.ratio)-p.opening.cash)<.011);}
 function correctLegacyCash(S){const p=S.profile();if(!candidate(p,S.snapshots()))throw Error('账户记录不符合旧版预算现金校正条件，未修改');
  p.journal=(p.journal||[]).map(t=>t.action==='买入'&&!t.amountInputBasis&&Number.isFinite(t.netAmount)&&Math.abs(t.amount-t.netAmount-t.fee)<.011?{...t,enteredAmount:t.netAmount,amountInputBasis:'net_excluding_fee'}:t);p.entries=p.journal.filter(t=>t.action!=='观察');const amount=p.opening.cash;if(amount<=0)throw Error('无可校正的误计预算现金');p.flows=[{id:'legacy-budget-cash-correction',date:p.opening.date,type:'withdraw',amount,source:'budget_cash_correction',note:'冲回旧版误计的全部预算期初现金；非真实转账'}];for(const t of p.entries)p.flows.push({id:'actual-payment-'+t.id,date:t.submittedDate||t.date,type:'deposit',amount:t.amount,source:'actual_trade_payment',tradeId:t.id,note:'按已有真实申购总支出恢复投入，非投资收益'});p.accountFunding='actual_payments';p.budgetCashCorrection={date:p.opening.date,amount,actualCash:0};if(!S.saveProfile(p))throw Error('校正无法保存');return S.profile();
 }
 function alipayRestores(p){return (p.journal||[]).filter(t=>t.amountCorrection==='user_confirmed_legacy_input_basis').map(t=>{const original=[...(p.revisions||[])].reverse().flatMap(r=>r.journal||r.entries||[]).find(o=>o.id===t.id&&o.code===t.code&&o.quantity===t.quantity&&o.date===t.date&&o.fee===t.fee&&!o.amountInputBasis&&Number.isFinite(o.netAmount)&&Math.abs(o.netAmount-t.amount)<.011&&Math.abs(o.amount-o.netAmount-o.fee)<.011);return original?{current:t,original}:null;}).filter(Boolean);}
 function restoreAlipayCosts(S){const p=S.profile(),restores=alipayRestores(p);if(!restores.length)return false;const byId=new Map(restores.map(r=>[r.current.id,r.original]));p.journal=p.journal.map(t=>{const o=byId.get(t.id);if(!o)return t;const restored={...t,amount:o.amount,netAmount:o.netAmount,enteredAmount:o.netAmount,amountInputBasis:'net_excluding_fee',amountCorrection:'restored_original_alipay_cost'};return restored;});p.entries=p.journal.filter(t=>t.action!=='观察');const correction=p.flows?.find(f=>f.source==='budget_cash_correction');if(correction&&p.accountFunding==='actual_payments'&&p.budgetCashCorrection?.actualCash===0&&p.entries.every(t=>t.status==='confirmed'&&t.action==='买入')&&p.flows.every(f=>['budget_cash_correction','actual_trade_payment'].includes(f.source))){p.flows=[{...correction,amount:p.opening.cash},...p.entries.map(t=>({id:'actual-payment-'+t.id,date:t.submittedDate||t.date,type:'deposit',amount:t.amount,source:'actual_trade_payment',tradeId:t.id,note:'按已确认的含费计收益成本恢复实际投入'}))];p.budgetCashCorrection={...p.budgetCashCorrection,amount:p.opening.cash};}else p.flows=(p.flows||[]).map(f=>f.source==='actual_trade_payment'&&byId.has(f.tradeId)?{...f,amount:byId.get(f.tradeId).amount}:f);if(!S.saveProfile(p))throw Error('支付宝原成本恢复失败，原记录未覆盖');return true;}
 window.AccountFunding={stagePurchase,candidate,correctLegacyCash,alipayRestores,restoreAlipayCosts};
})();

/* Read-only presentation of real ledger valuations and confirmed trade provenance. */
(function(){
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const money=x=>Number.isFinite(x)?'¥'+x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
 const pct=x=>Number.isFinite(x)?(x*100).toFixed(2)+'%':'—';
 function provenance(p,D,end){
  const entries=(p.entries||[]).filter(e=>e.status==='confirmed'&&e.confirmedDate<=end&&e.planStrategy).sort((a,b)=>a.confirmedDate.localeCompare(b.confirmedDate)||a.id.localeCompare(b.id));
  const days=new Map();for(const e of entries){const key=e.planStrategy+'@'+(e.planVersion||'未记录版本');if(!days.has(e.confirmedDate))days.set(e.confirmedDate,new Map());days.get(e.confirmedDate).set(key,e);}
  const events=[];let previous='';for(const [date,group] of days){const rows=[...group.values()],signature=[...group.keys()].sort().join('|');if(signature!==previous){events.push({date,entries:rows,label:rows.map(e=>window.StrategyLabels.label(e.planStrategy)).join(' / ')});previous=signature;}}
  const last=events.at(-1),trade=last?.entries.length===1?last.entries[0]:null,definition=D.research.strategies.find(s=>s.id===trade?.planStrategy);
  const weights=trade?.planWeights||(trade?.planVersion&&trade.planVersion===definition?.version?definition.weights:null);
  return {events,trade,weights,first:entries[0]?.confirmedDate,last};
 }
 function allocation(p,D,funds,V,S,end,r,context){
  if(!r.ready)return '<p class="empty">配置估值暂无有效数据</p>';
  const A=window.ProductAssets,state=S.replay(p,end),actual=new Map();
  for(const pos of state.positions){const mark=V.navAt(funds[pos.code],end);if(mark){const asset=A.assetOf(pos.code,p);actual.set(asset,(actual.get(asset)||0)+pos.shares*mark.nav);}}
  const target={};for(const [code,w] of Object.entries(context.weights||{})){const asset=A.assetOf(code,p);target[asset]=(target[asset]||0)+w;}
  const ids=[...new Set([...Object.keys(target),...actual.keys()])],equity=r.summary.equity;
  if(!ids.length)return '<p class="empty">暂无已确认持仓与执行目标</p>';
  const row=(name,w,v)=>`<div class="score-allocation-row"><span>${esc(name)}</span><b>${pct(w)}</b><b>${equity>0?pct(v/equity):'—'}</b></div>`;
  return '<div class="score-allocation-row score-allocation-head"><span>资产</span><span>目标</span><span>实际</span></div>'+ids.map(id=>row(A.assets[id]?.name||'未核实资产 '+id.replace('unmapped-',''),context.weights?(target[id]||0):null,actual.get(id)||0)).join('')+row('现金 / 在途 / 应收',context.weights?Math.max(0,1-Object.values(target).reduce((a,b)=>a+b,0)):null,equity-[...actual.values()].reduce((a,b)=>a+b,0))+'<p class="score-footnote">实际比例以投资账户净资产为分母；未确认申购不计为持仓。'+(context.weights?'目标取已确认交易关联的原始方案。':'未记录可核实的执行目标。')+'</p>';
 }
 function plot(rows,key,percent,events){
  if(rows.length<2)return '<div class="empty">暂无足够的有效收益数据</div>';
  const values=rows.map(r=>r[key]),min=Math.min(0,...values),max=Math.max(0,...values),pad=(max-min)*.08||(percent?.01:1),lo=min-pad,hi=max+pad;
  const first=Date.parse(rows[0].date),last=Date.parse(rows.at(-1).date),x=date=>100+(Date.parse(date)-first)/(last-first||1)*864,y=n=>255-(n-lo)/(hi-lo)*220;
  const axes=[0,1,2,3].map(i=>{const val=lo+(hi-lo)*i/3,yy=y(val);return `<line x1="100" x2="964" y1="${yy}" y2="${yy}" stroke="#e4e5de"/><text x="94" y="${yy+5}" text-anchor="end" fill="#77818d" font-size="24">${percent?(val*100).toFixed(1)+'%':val.toFixed(Math.abs(val)<10?1:0)}</text>`;}).join('');
  const marks=events.filter(e=>e.date>=rows[0].date&&e.date<=rows.at(-1).date).map((e,i)=>`<g><title>${esc(e.date+' 成交关联 '+e.label)}</title><line x1="${x(e.date)}" x2="${x(e.date)}" y1="20" y2="257" stroke="#c3a15d" stroke-dasharray="4 4"/><text x="${x(e.date)}" y="15" text-anchor="middle" fill="#916522" font-size="22">${i+1}</text></g>`).join('');
  return `<svg class="score-plot" viewBox="0 0 1000 300" role="img" tabindex="0" aria-label="${percent?'历史回撤，百分比':'累计投资盈亏，人民币元'}"><title>触摸或左右方向键查看日期与数值</title>${axes}${marks}<path d="${rows.map((r,i)=>`${i?'L':'M'}${x(r.date).toFixed(2)},${y(r[key]).toFixed(2)}`).join(' ')}" fill="none" stroke="${percent?'#b6975b':'#345a8b'}" stroke-width="2" vector-effect="non-scaling-stroke"/><line class="score-cursor" y1="20" y2="257" stroke="#8994a5" stroke-dasharray="3 3"/></svg><div class="chart-axis"><span>${rows[0].date}</span><span>${rows.at(-1).date}</span></div>`;
 }
 function operations(p,plan,strategy){
  const selected=window.StrategyLabels.label(strategy.id),choices=['L5','L6'].map(id=>`<button type="button" data-account-strategy="${id}" aria-pressed="${id===strategy.id}">${esc(window.StrategyLabels.label(id))}</button>`).join('');
  const intro=`<div class="account-strategy-tabs" role="group" aria-label="当前动态配置">${choices}</div><p class="score-footnote">同一真实账户 · ${esc(selected)} · 当前操作日 ${esc(plan.date||'—')}<br>目标投资预算 ${money(plan.targetBudget)} · 可用现金 ${money(p.poolCash||0)} · 赎回待到账 ${money(p.receivable||0)}</p>`;
  if(!plan.rows?.length)return intro+`<p class="empty">${esc(plan.reason||'等待账户估值')}</p>`;
  const signalDates=plan.signalDiagnostics?.map(d=>d.name+' '+d.date).join('；')||plan.signalDate;
  return intro+`<p class="score-footnote">${esc(plan.signalReady?'正式信号：'+signalDates+' · '+plan.signalState:plan.reason)}</p>`+plan.rows.map(row=>{
   const hasOrder=row.pendingBuy>0||row.pendingSell>0,action=hasOrder?'等待确认':row.executable?row.action==='买入'?'建议买入 '+money(row.amount):'建议赎回 '+row.shares.toFixed(2)+'份':row.action==='买入'?'等待申购条件':row.action==='卖出'?'暂缓赎回':'继续持有';
   return `<article class="account-operation" data-operation-code="${esc(row.code)}"><h4>${esc(row.name)} <small>${esc(row.code)}</small></h4><dl><div><dt>目标金额${row.weight!=null?' · '+pct(row.weight):''}</dt><dd>${money(row.target)}</dd></div><div><dt>当前持仓市值</dt><dd>${money(row.current)}</dd></div><div><dt>待确认申购 / 赎回</dt><dd>${money(row.pendingBuy||0)} / ${money(row.pendingSell||0)}</dd></div><div><dt>买卖缺口</dt><dd>${row.delta==null?'—':(row.delta>0?'+':'')+money(row.delta)}</dd></div></dl><strong class="account-operation-action">${esc(action)}</strong><p class="score-footnote">${esc(row.reason)}</p>${row.executable?`<p class="score-footnote">预估手续费 ${money(row.fee)}${row.action==='卖出'?' · 预计到账以渠道为准':''}</p><button type="button" class="link-button" data-account-trade="${esc(row.code)}" data-trade-side="${esc(row.action)}">${row.action==='卖出'?'记录已提交赎回':'登记已成交申购'}</button>`:''}${hasOrder?`<button type="button" class="link-button" data-account-pending="${esc(row.code)}">填写成交确认</button>`:''}</article>`;
  }).join('')+'<p class="score-footnote">目标按总金融资产的投资比例计算，当前金额按已有真实份额估值。差额已扣除待确认申购；建议金额受费用、可用现金、最低金额和额度约束。切换方案不重建账户、不改写成本或既往收益；所有成交及到账仍需手动确认。</p>';
 }
 function bind(rows){
  const readout=document.getElementById('scoreReadout');let index=rows.length-1;
  function show(i){index=Math.max(0,Math.min(rows.length-1,i));const r=rows[index];readout.textContent=r.date+' · 累计盈亏 '+money(r.cumulativePnl)+' · 回撤 '+pct(r.drawdown);const x=100+(Date.parse(r.date)-Date.parse(rows[0].date))/(Date.parse(rows.at(-1).date)-Date.parse(rows[0].date)||1)*864;document.querySelectorAll('.score-cursor').forEach(el=>{el.setAttribute('x1',x);el.setAttribute('x2',x);});}
  for(const svg of document.querySelectorAll('.score-plot')){const inspect=e=>{const box=svg.getBoundingClientRect(),ratio=Math.max(0,Math.min(1,((e.clientX-box.left)/box.width*1000-100)/864));const date=Date.parse(rows[0].date)+ratio*(Date.parse(rows.at(-1).date)-Date.parse(rows[0].date));let nearest=0;for(let i=1;i<rows.length;i++)if(Math.abs(Date.parse(rows[i].date)-date)<Math.abs(Date.parse(rows[nearest].date)-date))nearest=i;show(nearest);};svg.onpointerdown=e=>{svg.setPointerCapture(e.pointerId);inspect(e);};svg.onpointermove=e=>{if(e.buttons||e.pointerType==='mouse')inspect(e);};svg.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();show(index+(e.key==='ArrowLeft'?-1:1));}};}
  if(rows.length)show(index);else readout.textContent='';
 }
 function render({profile:p,data:D,funds,valuation:V,store:S,report:r,end,quoteMessage,strategy,currentPlan}){
  const $=id=>document.getElementById(id),context=provenance(p,D,end),has=(p.opening?.positions||[]).length&&p.opening.date<=end||(p.entries||[]).some(e=>e.status==='confirmed'&&e.confirmedDate<=end),m=r.ready&&has?r.summary:null,rows=m?r.rows:[],month=end.slice(0,7),monthly=m?r.months.find(x=>x.month===month):null;
  $('scoreStrategy').textContent=context.last?context.last.label:'尚无策略关联成交';
  $('scoreStrategyDetail').textContent=context.last?'关联依据：已确认成交':'确认成交后显示对应策略';
  if(strategy?.dynamic){$('scoreStrategy').textContent='真实投资账户 · '+window.StrategyLabels.label(strategy.id);$('scoreStrategyDetail').textContent='持仓、成交与成本沿用原账本；'+(context.last?'历史成交关联：'+context.last.label:'未关联策略的原成交也计入复盘。');}
  $('scoreDates').innerHTML='复盘起止：'+esc(p.opening?.date||'—')+' — '+esc(end)+(context.first?'<br>首次关联成交：'+esc(context.first):'');
  $('scoreEquity').textContent=r.ready?money(r.summary.equity):'—';$('scoreMonthLabel').textContent=month+' 投资盈亏';$('monthlyPnl').textContent=monthly?money(monthly.pnl):'—';
  $('reviewMetrics').innerHTML=[['累计投资盈亏',m?money(m.cumulativePnl):'—'],['累计收益率',m?pct(m.returnRate):'—'],['最大回撤',m?pct(m.mdd):'—'],['累计交易费用',m?money(m.fees):'—']].map(([name,value])=>`<div class="metric"><span>${name}</span><b>${value}</b></div>`).join('');
  $('reviewNotice').textContent=!m?(r.ready&&r.summary.frozen>0?'有待确认申购，尚无有效收益数据。':'暂无有效收益数据。'):(m.estimated?'含沿用净值或待确认款暂估。':'按确认交易与有效净值计算，已剔除外部净流入。');
  if(!r.ready&&p.opening)$('reviewNotice').textContent='净值不足或账本待核对，暂停显示收益。';
  $('scoreAllocation').innerHTML=strategy?.dynamic&&currentPlan?operations(p,currentPlan,strategy):allocation(p,D,funds,V,S,end,r,context);
  $('accountCurve').innerHTML=plot(rows,'cumulativePnl',false,context.events);$('accountDrawdown').innerHTML=plot(rows,'drawdown',true,context.events);bind(rows);
  $('scoreSwitches').innerHTML=context.events.length?'<span>图中金线：已确认成交关联的策略记录。</span>'+context.events.map((e,i)=>`<div>${i+1}. ${esc(e.date)} · ${esc(e.label)}</div>`).join(''):'';
  $('scoreDataDate').textContent=r.ready?'净值截至 '+([...new Set(Object.values(r.latestMarks||{}))].sort().join(' / ')||'暂无已确认持仓净值')+' · 待确认 '+money(r.summary.frozen||0)+' · 应收 '+money((r.summary.receivable||0)+(r.summary.dividendReceivable||0)):'无有效估值';
 }
 window.ReviewScorecard={render,provenance};
})();

/* Four-page account workspace. All writes are explicit manual records, never orders. */
(function(){
 for(const type of ['gesturestart','gesturechange','gestureend'])document.addEventListener(type,event=>event.preventDefault(),{passive:false});
 const S=window.XingxunStore,D=window.WORKSPACE_DATA,V=window.PortfolioValuation,C=window.CapitalPool,A=window.ProductAssets;
 const $=id=>document.getElementById(id);if(!$('investmentPlan'))return;
 let activePage='today';const pageScroll={};let workspaceReady=false;
 try {
 document.querySelectorAll('#topnav a').forEach(a=>{a.onclick=()=>{const name=a.dataset.t||a.dataset.page;navigate(name);if(name==='today'&&window.loadAlerts)window.loadAlerts();};a.setAttribute('role','button');a.tabIndex=0;a.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();a.click();}});});
 // Safari standalone storage or rendering failures must not disable navigation.
 if(!D?.research?.strategies?.length){$('workspaceStatus').textContent='版本化研究或净值文件不可用，已停止计算。';return;}
 S.setContext('real','strategy');let alipayRepairMessage='';try{if(window.AccountFunding.restoreAlipayCosts(S))alipayRepairMessage='已按原支付宝记录恢复转入净额与计收益成本，份额保持不变。';}catch(e){alipayRepairMessage=e.message;}
 let accountFunds=A.catalog(D,window.FUND_ACCESS_MONITOR,S.profile()),quoteMessage='',quotesLoading=false,reviewAutoDate=true;
 function applyAccountQuotes(snapshot){
   const next={};
   for(const [code,f] of Object.entries(A.catalog(D,window.FUND_ACCESS_MONITOR,S.profile()))){
    const points=new Map(f.nav.map(n=>[n[0],n[1]]));
    for(const point of snapshot.funds?.[code]?.nav||[]){
     if(!Array.isArray(point)||!/^\d{4}-\d{2}-\d{2}$/.test(point[0])||!Number.isFinite(Date.parse(point[0]))||new Date(point[0]).toISOString().slice(0,10)!==point[0]||point[0]>today()||!Number.isFinite(point[1])||point[1]<=0)throw Error('净值日期或数值异常');
     points.set(point[0],point[1]);
    }
    next[code]={...f,nav:[...points].sort(([a],[b])=>a.localeCompare(b))};
   }
   accountFunds=next;quoteMessage=Object.keys(snapshot.errors||{}).length?'部分基金更新失败或待核实，沿用已保存净值。':'';
 }
 async function refreshAccountQuotes(){
  if(quotesLoading||!/^https?:$/.test(location.protocol))return;
  quotesLoading=true;
  try{
   const response=await fetch(document.getElementById('sec-today')?'/api/account-nav':'./account_nav.json',{cache:'no-store'});
   if(!response.ok)throw Error('净值更新暂不可用');
   const snapshot=await response.json();if(snapshot.schema!=='xingxun-account-nav-v1')throw Error('净值格式异常');
   applyAccountQuotes(snapshot);
   const saved=S.profile(),codes=[...new Set((saved.positions||[]).map(pos=>pos.code))].filter(code=>saved.productData?.[code]?.identityVerified&&saved.productData[code].identitySource?.startsWith('https://fundsuggest.eastmoney.com/'));
   const updates=await Promise.allSettled(codes.map(code=>window.FundLookup.refresh(code)));if(updates.some(item=>item.status==='fulfilled')){const fresh=S.profile();for(const result of updates){if(result.status!=='fulfilled')continue;const f=result.value,old=fresh.productData?.[f.code];if(!old)continue;const points=new Map(old.nav||[]);for(const point of f.nav||[]){if(points.has(point[0])&&points.get(point[0])!==point[1]){quoteMessage='实际产品同日净值出现冲突，沿用原值，待核实。';continue;}points.set(point[0],point[1]);}fresh.productData[f.code]={...old,...f,nav:[...points].sort(([a],[b])=>a.localeCompare(b))};}S.saveProfile(fresh);}

  }catch(error){quoteMessage='最新净值暂未更新，按已保存净值计算。';}
  finally{quotesLoading=false;if(reviewAutoDate)reviewEnd=today();renderAccount();if(activePage==='review')renderReview();}
 }
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const money=x=>Number.isFinite(x)?'¥'+x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):'待核对';
 const pct=x=>Number.isFinite(x)?(x*100).toFixed(2)+'%':'待核对';
 const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
 const options=(items,selected)=>items.map(([v,t])=>`<option value="${esc(v)}" ${v===selected?'selected':''}>${esc(t)}</option>`).join('');
 const strategies=window.StrategyLabels.ids.map(id=>D.research.strategies.find(s=>s.id===id)).filter(Boolean);
 let allTradesExpanded=false,reviewEnd=today(),latestReport=null,activePlan=null,quickRow=null,statusTimer,budgetDraftDirty=false;
 function status(text,error=false){$('workspaceStatus').textContent=text;$('workspaceStatus').classList.toggle('error',error);clearTimeout(statusTimer);if(text&&!error)statusTimer=setTimeout(()=>{$('workspaceStatus').textContent='';},4500);}
 function act(fn,message){try{fn();renderAccount();renderReview();status(message);}catch(e){status(e.message,true);}}
 function metric(label,value,sub=''){return `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(sub)}</small></div>`;}
 function chart(lines,label,asPct=false){
  const nonempty=lines.filter(l=>l.points.length);if(!nonempty.length)return '<div class="empty">暂无可绘制的确认数据</div>';
  const xs=nonempty.flatMap(l=>l.points.map(p=>Date.parse(p[0]))),ys=nonempty.flatMap(l=>l.points.map(p=>p[1]));
  const xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),pad=(ymax-ymin)*.1||.01;
  const lo=ymin-pad,hi=ymax+pad,x=t=>50+(Date.parse(t)-xmin)/(xmax-xmin||1)*930,y=v=>195-(v-lo)/(hi-lo)*175;
  return `<div class="chart-wrap"><div class="legend">${nonempty.map(l=>`<span><i class="dot" style="background:${l.color}"></i>${esc(l.name)}</span>`).join('')}</div><div class="chart-axis"><span>纵轴范围：${asPct?pct(ymin):ymin.toFixed(3)} — ${asPct?pct(ymax):ymax.toFixed(3)}</span></div><svg class="chart" viewBox="0 0 1000 225" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title>${[0,1,2,3].map(k=>{const val=lo+(hi-lo)*k/3;return `<line x1="50" x2="980" y1="${y(val)}" y2="${y(val)}" stroke="#e4e5de"/>`;}).join('')}${nonempty.map(l=>`<path d="${l.points.map((p,i)=>`${i?'L':'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')}" fill="none" stroke="${l.color}" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`).join('')}</svg><div class="chart-axis"><span>${new Date(xmin).toISOString().slice(0,10)}</span><span>${new Date(xmax).toISOString().slice(0,10)}</span></div></div>`;
 }
 function currentReport(end=today()){const p=S.profile();if(p.broken)return {ready:false,reason:'账本格式异常，禁止继续计算，请导出恢复包。',rows:[],months:[]};return V.report(p,accountFunds,S.replay,end,{calendar:D.calendar});}
 function selectedStrategy(){return strategies.find(s=>s.id===$('candidateSelect').value)||strategies.find(s=>s.id==='L5')||strategies[0];}
 function budgetRatio(){return Number($('budgetRatio').value==='custom'?$('customRatio').value:$('budgetRatio').value)/100;}
 function previewBudget(){const custom=$('budgetRatio').value==='custom';$('customRatioLabel').hidden=!custom;$('customRatio').required=custom;const total=$('assetTotal').value===''?null:Number($('assetTotal').value),ratio=budgetRatio(),valid=total!=null&&Number.isFinite(ratio)&&ratio>=0&&ratio<=1;$('budgetPreview').textContent=valid?money(total*ratio):'待填写';$('budgetPreviewNote').textContent=budgetDraftDirty&&S.profile().opening?'未保存 · 当前计划仍按已保存预算计算':'';}
 function loadBudgetInputs(){const p=S.profile(),snap=S.latestSnapshot();$('assetTotal').value=snap?.total_assets??'';$('ledgerStartDate').value=p.opening?.date||today();$('ledgerStartDate').max=p.opening?.date||today();const percentage=Number((p.ratio*100).toFixed(2));$('budgetRatio').value=[5,10,20].includes(percentage)?String(percentage):'custom';$('customRatio').value=percentage;}
 function allocation(r=currentReport()){
  const p=S.profile(),snap=S.latestSnapshot(),ready=!!p.opening&&!!snap;
  if(!budgetDraftDirty)loadBudgetInputs();$('strategyPanel').hidden=!ready;$('strategyChoice').hidden=!ready;$('investmentPlan').hidden=!ready;$('budgetSummary').hidden=!ready;
  const equity=r.ready?r.summary.equity:null,budget=snap?C.poolBudget(snap.total_assets,equity??0,0,p.ratio):null;
  $('budgetSummary').innerHTML=ready?`<p>更新 ${esc(snap.date)}${snap.date.slice(0,7)!==today().slice(0,7)?' · 本月沿用上次金额':''}<br>账户净资产 ${money(equity)} · 可用现金 ${money(p.poolCash)}<br>可新增额度 ${equity!=null?money(budget.new_allowed):'待估值'}</p>${equity!=null&&budget.over_target>0?'<p>账户已超目标，暂停新增投入，不强制卖出。</p>':''}`:'';
  const resolution=window.DynamicAllocation.resolve(selectedStrategy());
  $('candidateAllocation').textContent=selectedStrategy().dynamic?(resolution.ready?resolution.state+' · 复用今日提醒的正式策略状态':resolution.reason):selectedStrategy().scenario==='nasdaq_available'?'正常申购情景':'纳指不可买情景';
  $('budgetCashCorrection').hidden=!window.AccountFunding.candidate(p,S.snapshots());$('budgetSetupNote').textContent=p.opening?'':'预算仅为投资目标，不会计入账户现金；已成交申购按实际付款登记投入。';previewBudget();renderPlan();
 }
 function renderPlan(){
  const inline=$('quickTradeDialog');if(inline&&$('investmentPlan').contains(inline)){inline.hidden=true;$('planTransactions').append(inline);}
  const profile=S.profile(),strategy=selectedStrategy(),weights=A.weights(strategy),snap=S.latestSnapshot(),budget=(snap?.total_assets??0)*profile.ratio;
  try{activePlan=window.AssetPlanner.plan({profile,strategy,data:{...D,funds:accountFunds},date:today(),capitalPool:C,valuation:V,totalAssets:snap?.total_assets});}catch(e){activePlan={rows:[],reason:e.message};}
  const pending=(profile.entries||[]).filter(e=>e.status==='submitted'),payments=Object.entries(profile.payments||{}).filter(([id,v])=>!v.settled),journal=S.journal();
  const assets=[...new Set([...Object.keys(weights).filter(a=>weights[a]>0),...(activePlan.rows||[]).filter(r=>r.weight>0||r.current>0).map(r=>r.asset),...(profile.positions||[]).map(pos=>A.assetOf(pos.code,profile)),...pending.map(e=>A.assetOf(e.code,profile)),...payments.map(([id])=>A.assetOf(journal.find(e=>e.id===id)?.code,profile))])].filter(Boolean);
  const entries=Object.entries(weights),cents=Math.round(budget*100),targets=entries.map(([a,w])=>Math.floor(cents*w));let remainder=cents-targets.reduce((a,b)=>a+b,0);
  const fractions=entries.map(([a,w],i)=>({i,fraction:cents*w-targets[i]})).sort((a,b)=>b.fraction-a.fraction||a.i-b.i);
  for(let i=0;remainder>0;i=(i+1)%fractions.length){targets[fractions[i].i]++;remainder--;}
  $('investmentPlan').querySelectorAll('.inline-buy').forEach(form=>{const field=id=>form.querySelector('[data-field="'+id+'"]');if(form.dataset.saved!=='true'&&form.dataset.dirty==='true')buyDrafts.set(form.dataset.asset,{code:field('productCode').value,date:field('recordBuyDate').value,amount:field('recordBuyAmount').value,quantity:field('recordBuyQuantity').value,fee:field('recordBuyFee').value,basis:field('recordAmountBasis').value,id:form.dataset.recordId});});
  $('investmentPlan').innerHTML=(strategy.dynamic?`<p class="fine" role="status">${esc(activePlan.reason||'')}</p>`:'')+assets.map(asset=>{
   const i=(activePlan.rows||[]).findIndex(r=>r.asset===asset),r=activePlan.rows?.[i],code=r?.code||A.selected(asset,profile),ti=entries.findIndex(([a])=>a===asset),target=ti>=0?targets[ti]/100:0;
   const held=(profile.positions||[]).filter(pos=>A.assetOf(pos.code,profile)===asset).map(pos=>esc(accountFunds[pos.code]?.name||pos.code)+' '+Number(pos.shares).toFixed(4)+'份').join('；');
   const waiting=pending.filter(e=>A.assetOf(e.code,profile)===asset),receivables=payments.filter(([id])=>A.assetOf(journal.find(e=>e.id===id)?.code,profile)===asset);
   const state=waiting.length||receivables.length?waiting.map(e=>`<div class="trade-waiting"><b>等待确认</b><p>${esc(accountFunds[e.code]?.name||e.code)} · ${esc(e.action)} ${money(e.amount)}</p><button class="btn" type="button" data-confirm="${esc(e.id)}">填写成交结果</button></div>`).join('')+receivables.map(([id,v])=>`<div class="trade-waiting"><b>赎回款等待到账</b><p>${money(v.amount)} · 尚不可用</p><button class="btn" type="button" data-settle="${esc(id)}">记录实际到账</button></div>`).join(''):`${r?.executable&&['买入','卖出'].includes(r.action)?`<p class="operation-amount"><strong>模拟${esc(r.action)} ${money(r.amount)}</strong></p>`:''}${r?.executable&&r.action==='卖出'?`<button class="btn" type="button" data-plan="${i}">记录已提交</button>`:''}`;
   return `<article class="operation-card" data-asset="${esc(asset)}" data-fund="${esc(code||'')}"><h3>${A.assets[asset]?esc(A.assets[asset].name):'待核实资产 · '+esc(code||'')}</h3><p class="fine">目标 ${pct(weights[asset]||0)} · ${money(target)}</p>${held?'<p class="fine">已确认：'+held+'</p>':''}${r?.current>0?`<p class="fine">同资产持仓 / 在途 ${money(r.current)}</p>`:''}${state}${A.assets[asset]&&!waiting.length&&!receivables.length?`<div data-buy-slot="${esc(asset)}"></div>`:''}</article>`;
  }).join('');
  $('investmentPlan').querySelectorAll('[data-buy-slot]').forEach(slot=>{const asset=slot.dataset.buySlot,form=$('buyFormTemplate').content.firstElementChild.cloneNode(true);form.dataset.asset=asset;form.querySelectorAll('[id]').forEach(el=>{el.dataset.field=el.id;el.id+='-'+asset;});form.dataset.field='productForm';form.id='productForm-'+asset;slot.append(form);initBuyForm(form,asset);});
  $('investmentPlan').querySelectorAll('[data-plan]').forEach(b=>b.onclick=()=>{const row=activePlan.rows[Number(b.dataset.plan)];openQuick('submit',String(b.dataset.plan));});
  $('investmentPlan').querySelectorAll('[data-confirm]').forEach(b=>b.onclick=()=>openQuick('confirm',b.dataset.confirm));
  $('investmentPlan').querySelectorAll('[data-settle]').forEach(b=>b.onclick=()=>openQuick('settle',b.dataset.settle));
 }
 const buyDrafts=new Map();
 function initBuyForm(root,asset){
  const $=id=>id==='productForm'?root:root.querySelector('[data-field="'+id+'"]'),draft=buyDrafts.get(asset);
 let buyRecordId=null,buyIdentity=null,buyLookupTimer,buyLookupGeneration=0,buyAmountEdited=false;
 function showSavedFee(){const net=$('recordAmountBasis').value==='net_transfer_excluding_fee',policy=window.UserPurchaseFees.forCode($('productCode').value.trim()),amount=Number($('recordBuyAmount').value);$('recordBuyAmountText').textContent=net?'支付宝转入金额（净额，元）':'申购总额（含申购费，元）';$('recordBuyFeeLabel').firstChild.textContent=net?'确认单已扣转换费（元）':'实际申购费（元）';$('recordBuyFeeLabel').hidden=!net&&!!policy;$('recordBuyFee').required=net||!policy;
 if(net){const fee=$('recordBuyFee').value===''?null:Number($('recordBuyFee').value);$('buyFeeInfo').textContent=fee!=null&&fee>=0&&amount>0?'转入净额 '+money(amount)+' · 已扣转换费 '+money(fee)+' · 计收益成本 '+money(amount+fee):'转换费按确认单填写，不套用普通申购费率。';}else $('buyFeeInfo').textContent=policy&&buyIdentity?'支付宝申购费率 '+policy.buy_pct.toFixed(2)+'%'+(amount>0?' · 申购费 '+money(window.UserPurchaseFees.amount(amount,policy))+' · 净投入 '+money(amount-window.UserPurchaseFees.amount(amount,policy)):''):'该基金未保存费率，请填写确认单实际申购费（元）。';}
 function setup(){
  clearTimeout(buyLookupTimer);++buyLookupGeneration;
  const p=S.profile(),code=A.selected(asset,p),row=activePlan?.rows?.find(r=>r.asset===asset),target=((S.latestSnapshot()?.total_assets||0)*p.ratio)*(A.weights(selectedStrategy())[asset]||0);
  $('productForm').reset();$('productAsset').value=asset;buyRecordId=draft?.id||S.newId();buyIdentity=null;buyAmountEdited=false;$('productCode').value=draft?.code??code??'';$('recordBuyDate').value=draft?.date||today();
  $('recordBuyAmount').value=(row?.action==='买入'&&row.amount>0?Math.min(row.amount,p.poolCash):Math.max(0,Math.round(Math.min(p.poolCash,Math.max(0,target-(row?.current||0)))*100)/100));
  const candidates=[...new Set([...A.candidates(asset,D,window.FUND_ACCESS_MONITOR,p),...Object.keys(accountFunds)])];window.FundPicker.init($('fundPicker'),$('productCode'),$('fundPickerToggle'),$('fundProducts'),candidates.filter(c=>accountFunds[c]?.name).map(c=>({code:c,name:accountFunds[c].name})));
  if(draft){$('recordBuyAmount').value=draft.amount;$('recordBuyQuantity').value=draft.quantity||'';$('recordBuyFee').value=draft.fee||'';$('recordAmountBasis').value=draft.basis||'gross_including_subscription_fee';buyAmountEdited=true;}$('productError').textContent='';resolveBuyFund();
 }
 async function resolveBuyFund(){
  const code=$('productCode').value.trim(),generation=++buyLookupGeneration;buyIdentity=null;$('productInfo').textContent='正在核实基金名称…';
  try{const identity=await window.FundLookup.lookup(code,S.profile());if(generation!==buyLookupGeneration||code!==$('productCode').value.trim())return null;buyIdentity=identity;const profile=S.profile(),asset=A.assetOf(code,profile);if(!buyAmountEdited){const requested=$('productAsset').value,row=activePlan?.rows?.find(r=>r.asset===requested),t=A.terms(code,profile,D,window.FUND_ACCESS_MONITOR,today()),target=((S.latestSnapshot()?.total_assets||0)*profile.ratio)*(A.weights(selectedStrategy())[requested]||0),cap=Number.isFinite(t.limit)?t.limit:Infinity;const reference=asset===requested?Math.max(0,Math.min(profile.poolCash,cap,Math.max(0,target-(row?.current||0)))):0;$('recordBuyAmount').value=reference>0?Math.round(reference*100)/100:'';}$('productInfo').textContent=identity.name+' · '+code+(A.assets[asset]?(asset=== $('productAsset').value?'':' · '+A.assets[asset].name):' · 资产归属待核实，独立记账');showSavedFee();return identity;}
  catch(e){if(generation===buyLookupGeneration)$('productInfo').textContent=e.message;return null;}
 }
 $('recordAmountBasis').onchange=()=>{buyAmountEdited=true;showSavedFee();root.dataset.dirty='true';};$('recordBuyFee').oninput=showSavedFee;
 $('recordBuyAmount').oninput=()=>{buyAmountEdited=true;showSavedFee();};
 $('productCode').oninput=()=>{buyIdentity=null;++buyLookupGeneration;clearTimeout(buyLookupTimer);$('productInfo').textContent='';$('buyFeeInfo').textContent='';if(/^\d{6}$/.test($('productCode').value.trim()))buyLookupTimer=setTimeout(resolveBuyFund,250);};
 $('productCode').onchange=resolveBuyFund;
 $('productForm').onsubmit=async e=>{e.preventDefault();const button=$('saveBuyRecord');if(button.disabled)return;button.disabled=true;try{
  const recordId=buyRecordId,code=$('productCode').value.trim(),date=$('recordBuyDate').value,enteredAmount=Number($('recordBuyAmount').value),basis=$('recordAmountBasis').value,netBasis=basis==='net_transfer_excluding_fee',policy=netBasis?null:window.UserPurchaseFees.forCode(code),fee=policy?window.UserPurchaseFees.amount(enteredAmount,policy):($('recordBuyFee').value===''?NaN:Number($('recordBuyFee').value)),amount=netBasis?Math.round((enteredAmount+fee)*100)/100:enteredAmount,netAmount=netBasis?enteredAmount:Math.round((amount-fee)*100)/100,quantity=Number($('recordBuyQuantity').value),requested=$('productAsset').value;
  if(!Number.isFinite(quantity)||quantity<=0)throw Error('请填写成交单中的真实份额');if(!A.dateOK(date)||date>today())throw Error('请填写今天或过去的成交净值日期');if(!Number.isFinite(enteredAmount)||enteredAmount<=0||Math.abs(enteredAmount*100-Math.round(enteredAmount*100))>1e-7)throw Error('请填写有效支付金额，最多两位小数');
  const identity=buyIdentity?.code===code?buyIdentity:await resolveBuyFund();if(!identity)throw Error('基金代码与名称未核实，暂不能保存');
  if(recordId!==buyRecordId||!root.isConnected)throw Error('记录窗口已变化，请重新核对');const p=S.profile(),asset=A.assetOf(code,p),journal=S.journal();if(!p.opening||p.broken)throw Error('请先保存投资预算并核对账本');const earlierStart=date<p.opening.date?date.slice(0,7)+'-01':null;if(journal.some(t=>t.id===recordId))throw Error('这笔买入已记录');if(journal.some(t=>t.status==='confirmed'&&t.code===code&&t.action==='买入'&&t.date===date&&t.quantity===quantity&&Math.abs(t.amount-amount)<.001))throw Error('相同日期、金额及份额的成交已记录，请勿重复保存');
  if((p.entries||[]).some(t=>t.status==='submitted'&&(t.code===code||(!asset.startsWith('unmapped-')&&A.assetOf(t.code,p)===asset))))throw Error('该基金或同资产已有待确认交易，请先处理，避免重复提交');
  if(!Number.isFinite(fee)||fee<0)throw Error('请填写确认单实际申购费');if(p.accountFunding!=='actual_payments'&&p.poolCash+1e-8<amount)throw Error('实际支付金额超过可用现金，请先核对投资账户资金');
  const previous=p.productData?.[code]||{},points=new Map(previous.nav||[]);for(const n of identity.nav||[])if(!points.has(n[0]))points.set(n[0],n[1]);p.productData={...p.productData,[code]:{...previous,...identity,nav:[...points].sort(([a],[b])=>a.localeCompare(b))}};
  const mapping=A.mapping(code,p),matched=asset===requested;if(matched)p.productChoices={...p.productChoices,[asset]:code};
  if(!Number.isFinite(fee)||fee<0||fee>=amount||Math.abs(fee*100-Math.round(fee*100))>1e-7)throw Error('请核对实际申购费，金额单位为元');const strategy=selectedStrategy(),row={id:recordId,mode:'real',accountId:'strategy',date,submittedDate:date,code,name:identity.name,action:'买入',status:'confirmed',confirmedDate:date,valuationDate:date,netAmount,enteredAmount,amountInputBasis:basis,feeKind:netBasis?'conversion':'subscription',confirmedDateBasis:'user_recorded_nav_date',amount,quantity,fee,feeInput:policy?{unit:'percent',value:policy.buy_pct,source:'user_provided'}:{unit:'amount',value:fee},asset:mapping?.asset||null,identitySource:identity.identitySource,purchaseFeePolicy:!netBasis&&date>='2026-10-22'?window.UserPurchaseFees.forCode(code):null,source:'manual_executed_buy',...(matched?{planStrategy:strategy.id,planVersion:strategy.version,planWeights:{...window.DynamicAllocation.resolve(strategy).weights},executionBasis:'manual_trade_research_plan'}:{})};
  window.AccountFunding.stagePurchase(p,row,S,earlierStart);p.journal=[...journal,row];p.entries=p.journal.filter(t=>t.action!=='观察');if(!(earlierStart?S.saveHistoricalProfile(p,earlierStart):S.saveProfile(p)))throw Error('无法保存账本');root.dataset.saved='true';buyDrafts.delete(root.dataset.asset);renderAccount();renderReview();status('成交已记录，实际份额、现金和复盘已更新。'+(earlierStart?'账本起始日已提前至 '+earlierStart+'，原期初金额不变。':''));
 }catch(err){$('productError').textContent=err.message;}finally{button.disabled=false;}};
 root.addEventListener('input',()=>{root.dataset.dirty='true';});
 setup();root.dataset.recordId=buyRecordId;
 }
 function openQuick(kind,id){
  quickRow=kind==='submit'?{...activePlan.rows[Number(id)]}:S.journal().find(t=>t.id===id);if(!quickRow)return;if(kind==='submit'&&quickRow.action!=='卖出')return;
  const submit=kind==='submit',settle=kind==='settle',buy=quickRow.action==='买入',policy=!submit&&!settle&&buy?window.UserPurchaseFees.forTrade(quickRow):null;
  $('quickKind').value=kind;$('quickId').value=submit?S.newId():id;$('quickDate').value=today();$('quickError').textContent='';
  $('quickTitle').textContent=submit?'记录已提交赎回':settle?'记录实际到账':'填写成交结果';$('quickDateText').textContent=submit?'申请日期':settle?'实际到账日期':'确认日期';
  $('quickDescription').textContent=(accountFunds[quickRow.code]?.name||quickRow.code)+' · '+money(quickRow.amount);
  $('quickAmountText').textContent=submit?'预计净回款（元）':settle?'实际到账金额（元）':buy?'买入总支出（含费，元）':'确认净回款（元）';$('quickAmount').readOnly=!submit&&!settle&&buy;$('quickAmount').value=submit?Math.round((quickRow.amount-quickRow.fee)*100)/100:quickRow.amount;
  $('quickQuantityLabel').hidden=settle;$('quickSellQuantity').required=!settle;$('quickQuantityText').textContent=submit?'赎回申请份额':'实际成交份额';$('quickSellQuantity').value=quickRow.quantity||quickRow.shares||'';
  $('quickFeeLabel').firstChild.textContent=buy?'实际申购费（元）':'实际赎回费（元）';$('quickFeeLabel').hidden=submit||settle||!!policy;$('quickFee').required=!$('quickFeeLabel').hidden;$('quickFee').value='';$('quickFeeInfo').textContent=policy?'申购费 '+money(window.UserPurchaseFees.amount(quickRow.amount,policy))+'（按已保存的支付宝费率）':'';
  $('quickSave').textContent=submit?'记录已提交':settle?'保存到账':'保存成交';const selector=submit?'[data-plan="'+id+'"]':settle?'[data-settle="'+id+'"]':'[data-confirm="'+id+'"]';$('investmentPlan').querySelector(selector)?.closest('article')?.append($('quickTradeDialog'));$('quickTradeDialog').hidden=false;
 }
 function renderAccount(){
  const p=S.profile(),catalog=A.catalog(D,window.FUND_ACCESS_MONITOR,p);accountFunds={...catalog,...accountFunds};for(const [code,f] of Object.entries(catalog)){const points=new Map(accountFunds[code]?.nav||[]);for(const point of f.nav)points.set(point[0],point[1]);accountFunds[code]={...f,nav:[...points].sort(([a],[b])=>a.localeCompare(b))};}const selectedIncome=$('incomeCode').value;$('incomeCode').innerHTML=options(Object.entries(accountFunds).map(([c,f])=>[c,f.name+' '+c]),selectedIncome);const snap=S.latestSnapshot(),r=currentReport();
  $('incomeManagement').hidden=!(r.ready&&r.summary.dividendReceivable>.01);
  $('assetSave').textContent=p.opening?'保存并更新计划':'保存预算，选择策略';
  allocation(r);window.dispatchEvent(new Event('xingxun:account-change'));
 }
 function deleteTrade(id){
  act(()=>{const rows=S.journal();if(!rows.some(e=>e.id===id))return;S.saveJournal(rows.filter(e=>e.id!==id));},'交易已删除，账本已重算。');
 }
 function renderReview(){
  const p=S.profile(),end=reviewEnd,month=end.slice(0,7);let r;
  try{r=currentReport(end);}catch(e){r={ready:false,reason:e.message,rows:[],months:[]};}
  latestReport=r;$('reviewMonth').value=month;
  const strategy=selectedStrategy();
  let currentPlan;
  if(strategy.dynamic)try{currentPlan=window.AssetPlanner.plan({profile:p,strategy,data:{...D,funds:accountFunds},date:today(),capitalPool:C,valuation:V,totalAssets:S.latestSnapshot()?.total_assets});}catch(error){currentPlan={rows:[],reason:error.message,date:today()};}
  window.ReviewScorecard.render({profile:p,data:D,funds:accountFunds,valuation:V,store:S,report:r,end,quoteMessage,strategy,currentPlan});
  $('scoreAllocation').querySelectorAll('[data-account-strategy]').forEach(button=>button.onclick=()=>{chooseStrategy(button.dataset.accountStrategy);});
  $('scoreAllocation').querySelectorAll('[data-account-trade],[data-account-pending]').forEach(button=>button.onclick=async()=>{
   const code=button.dataset.accountTrade||button.dataset.accountPending,side=button.dataset.tradeSide;
   await navigate('plan');
   const pending=(S.profile().entries||[]).find(e=>e.code===code&&e.status==='submitted');
   if(button.dataset.accountPending&&pending){openQuick('confirm',pending.id);return;}
   const index=activePlan?.rows?.findIndex(row=>row.code===code&&row.action==='卖出'&&row.executable);
   if(side==='卖出'&&index>=0){openQuick('submit',String(index));return;}
   const asset=A.assetOf(code,S.profile()),card=$('investmentPlan').querySelector('[data-asset="'+asset+'"]'),field=card?.querySelector('[data-field="productCode"]');
   if(field&&field.value!==code){field.value=code;field.dispatchEvent(new Event('input',{bubbles:true}));}
   card?.scrollIntoView({block:'start',behavior:'smooth'});
  });
  const tx=(p.journal||[]).filter(e=>e.action!=='观察').slice().sort((a,b)=>b.date.localeCompare(a.date));
  const record=e=>`<details class="review-trade"><summary><span><b>${esc(accountFunds[e.code]?.name||e.code)} · ${esc(e.action)}</b><small>${esc(e.date)} · ${esc(p.payments?.[e.id]?.settled?'已到账':({submitted:'等待确认',confirmed:'已确认',cancelled:'已撤销',failed:'失败',pending:'待执行'}[e.status]||e.status))}</small></span><strong>${money(e.amount)}</strong></summary><p class="fine">${esc(e.code)} · ${e.confirmedDateBasis==='user_recorded_nav_date'?'成交净值日期':'确认日期'} ${esc(e.confirmedDate||'尚未确认')}<br>${e.action==='买入'?'申购总额 '+money(e.amount)+' · 净投入 '+(e.status==='confirmed'?money(e.amount-e.fee):'待确认')+'<br>':''}实际份额 ${e.quantity==null?'未确认':esc(e.quantity)} · ${e.action==='买入'?(e.feeKind==='conversion'?'转换费':'申购费'):'赎回费'} ${e.status==='confirmed'?money(e.fee):'待确认'}${e.resolvedDate?'<br>撤销 / 失败日期 '+esc(e.resolvedDate):''}</p><button class="link-button" type="button" data-delete="${esc(e.id)}">删除</button></details>`;
  $('transactionHistory').innerHTML=tx.length?tx.slice(0,3).map(record).join(''):'<div class="empty">暂无交易记录</div>';
  $('allTransactionHistory').innerHTML=tx.slice(3).map(record).join('');$('allTransactionHistory').hidden=!allTradesExpanded;$('allTransactions').hidden=tx.length<=3;$('allTransactions').textContent=allTradesExpanded?'收起较早交易':`查看全部交易（${tx.length}笔）`;
  for(const id of ['transactionHistory','allTransactionHistory'])$(id).querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>deleteTrade(b.dataset.delete));
 }
 let researchReady=false,researchLoading,researchAttempts=0;
 async function renderResearch(){
  if(window.StrategyLab?.ready){researchReady=true;return;}
  if(researchReady)return;
  if(!researchLoading){
   $('labRangeNote').textContent='正在加载历史数据，请稍候…';
   researchLoading=(async()=>{
    await window.XingxunAssets?.research({retry:researchAttempts++>0});
    window.StrategyLab.init(D);
    if(!window.StrategyLab.state.series.length)throw Error('历史数据包没有可用曲线，请刷新后重试');
    researchReady=true;
   })().catch(error=>{
    researchLoading=null;
    $('labRangeNote').innerHTML='<span>历史数据暂未加载，请检查网络后重试。</span> <button type="button" class="btn gray" data-retry-research>重新加载</button>';
    $('labRangeNote').querySelector('[data-retry-research]').onclick=()=>navigate('lab');
    throw error;
   });
  }
  return researchLoading;
 }
 function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function navigate(name){
  document.body.classList.remove('scorecard-capture');$('scoreCapture').textContent='截图视图';
  name=({diary:'review',guide:'lab'}[name]||name);
  pageScroll[activePage]=window.scrollY;
  for(const id of ['plan','review','lab'])$('invest-'+id).classList.toggle('hidden',id!==name);
  for(const id of ['sec-today','page-today']){const el=$(id);if(el)el.classList.toggle('hidden',name!=='today');}
  document.querySelectorAll('#topnav a').forEach(a=>{const n=a.dataset.t||a.dataset.page;a.classList.toggle('active',n===name);a.setAttribute('aria-current',n===name?'page':'false');});
  activePage=name;requestAnimationFrame(()=>window.scrollTo({top:pageScroll[name]||0,behavior:'instant'}));
  if(!workspaceReady)return;
  try{if(name==='review')renderReview();if(name==='plan')renderAccount();if(name==='lab'&&!window.StrategyLab?.ready){status('正在加载研究数据…');await renderResearch();}status('');}
  catch(error){$('workspaceStatus').textContent='页面计算暂不可用：'+error.message;return false;}
 }
 $('incomeDate').value=today();
 $('candidateSelect').innerHTML=options(strategies.map(s=>[s.id,window.StrategyLabels.label(s.id)]));
 $('candidateSelect').value=D.research.default_strategy||'L5';
 $('scoreCapture').onclick=()=>{const active=document.body.classList.toggle('scorecard-capture');$('scoreCapture').textContent=active?'退出截图视图':'截图视图';window.scrollTo(0,0);};
 $('openBackup').onclick=()=>{const panel=$('backupDialog');$('openBackup').closest('.score-tools').after(panel);panel.hidden=!panel.hidden;};$('closeBackup').onclick=()=>{$('backupDialog').hidden=true;};
 $('fixBudgetCash').onclick=()=>act(()=>window.AccountFunding.correctLegacyCash(S),'旧版误计预算现金已校正为0；转入净额与含费成本保持不变，旧版本已保留。');
 $('allTransactions').onclick=()=>{allTradesExpanded=!allTradesExpanded;renderReview();};
 $('ledgerStartDate').onchange=$('budgetRatio').onchange=$('customRatio').oninput=$('assetTotal').oninput=()=>{budgetDraftDirty=true;previewBudget();};
 $('assetSnapshotForm').onsubmit=e=>{e.preventDefault();act(()=>{const ratio=budgetRatio(),total=Number($('assetTotal').value);if(!Number.isFinite(ratio)||ratio<0||ratio>1)throw Error('投资比例必须为0–100%');if(!Number.isFinite(total)||total<0||total>1e9)throw Error('总资产无效');const p=S.profile(),start=$('ledgerStartDate').value;if(p.broken)throw Error('账本异常，停止修改');if(!A.dateOK(start)||start>today()||(p.opening&&start>p.opening.date))throw Error('请选择原起始日或更早日期，不能截掉已有历史');S.addSnapshot(today(),total);p.ratio=ratio;if(!p.opening)p.accountFunding='actual_payments';if(!S.saveProfile(p))throw Error('预算保存失败');if(!p.opening)S.initializeLedger({date:start,cash:0,positions:[]});else if(start<p.opening.date)S.extendLedgerStart(start);budgetDraftDirty=false;},'预算已保存，模拟计划已更新。');};
 $('quickClose').onclick=()=>($('quickTradeDialog').hidden=true);
 $('quickTradeForm').onsubmit=e=>{e.preventDefault();try{
  const kind=$('quickKind').value,id=$('quickId').value,date=$('quickDate').value,p=S.profile();
  if(kind==='submit'){
   if(date!==today())throw Error('当日额度仅用于今天的提交；请核对实际提交日期。');
   // Refresh at save time so an open dialog cannot spend cash using an obsolete plan.
   const fresh=window.AssetPlanner.plan({profile:p,strategy:selectedStrategy(),data:{...D,funds:accountFunds},date:today(),capitalPool:C,valuation:V,totalAssets:S.latestSnapshot()?.total_assets});
   const row=fresh.rows?.find(r=>r.code===quickRow.code&&r.action==='卖出'&&r.executable);
   if(!row||row.asset!==quickRow.asset||row.channel!==quickRow.channel||row.buy_pct!==quickRow.buy_pct||Math.abs(row.amount-quickRow.amount)>.011)throw Error('计划已变化，请收起后重新核对。');
   if(S.journal().some(t=>t.id===id))throw Error('这笔提交已经记录。');
   if((p.entries||[]).some(t=>A.assetOf(t.code,p)===row.asset&&t.status==='submitted'))throw Error('本基金已有等待确认的交易，不可重复提交。');
   const actual=Number($('quickAmount').value);
   if(!Number.isFinite(actual)||actual<=0||Math.abs(Math.round(actual*100)-actual*100)>1e-7)throw Error('请填写有效实际金额，最多两位小数。');
   if(row.action==='买入'&&(actual>row.amount+.001||actual<row.minimum))throw Error('实际金额超过当前可执行额度或低于最低申购金额，请核对渠道与现金。');
   const quantity=row.action==='卖出'?Number($('quickSellQuantity').value):null;
   if(quantity!=null&&quantity>row.shares+.00001)throw Error('赎回申请份额超过本次计划，请核对实际份额。');
   S.saveJournal([...S.journal(),{id,mode:'real',accountId:'strategy',date,submittedDate:date,code:row.code,name:row.name,action:row.action,status:'submitted',amount:actual,quantity,fee:row.action==='买入'?Math.round((actual-actual/(1+row.buy_pct/100))*100)/100:row.fee,asset:row.asset,productChannel:row.channel,productVerification:{...p.productTerms?.[row.code],mapping:A.mapping(row.code,p)},planStrategy:selectedStrategy().id,planVersion:selectedStrategy().version,planWeights:{...window.DynamicAllocation.resolve(selectedStrategy()).weights},executionBasis:'manual_trade_research_plan'}]);
  }else{
   const old=p.journal.find(t=>t.id===id);if(!old)throw Error('交易不存在');
   if(kind==='settle'){if(old.status!=='confirmed'||old.action!=='卖出'||p.payments?.[id]?.settled)throw Error('该交易不可重复登记到账');const amount=Number($('quickAmount').value);if(!Number.isFinite(amount)||amount<=0||Math.abs(amount*100-Math.round(amount*100))>1e-7)throw Error('实际到账金额无效');const updated={...old,amount};p.journal=p.journal.map(t=>t.id===id?updated:t);p.settlements=[...(p.settlements||[]),{id:'settle-'+id,tradeId:id,date,amount}];
   }else if(kind==='confirm'){if(old.status!=='submitted')throw Error('成交已处理，不可重复保存');const policy=old.action==='买入'?window.UserPurchaseFees.forTrade(old):null,fee=policy?window.UserPurchaseFees.amount(old.amount,policy):($('quickFee').value===''?NaN:Number($('quickFee').value));if(!Number.isFinite(fee)||fee<0||Math.abs(fee*100-Math.round(fee*100))>1e-7)throw Error('请填写实际手续费');const updated={...old,status:'confirmed',confirmedDate:date,quantity:Number($('quickSellQuantity').value),amount:old.action==='买入'?old.amount:Number($('quickAmount').value),fee,feeInput:{unit:'amount',value:fee}};p.journal=p.journal.map(t=>t.id===id?updated:t);
   }else throw Error('交易操作无效');p.entries=p.journal.filter(t=>t.action!=='观察');if(!S.saveProfile(p))throw Error('账本校验失败，未保存');
  }
  ($('quickTradeDialog').hidden=true);renderAccount();renderReview();status('已记账并自动更新持仓和复盘；未进行下单。');
 }catch(err){$('quickError').textContent=err.message;}};
 $('incomeForm').onsubmit=e=>{e.preventDefault();act(()=>S.addIncome({id:S.newId(),code:$('incomeCode').value,exDate:$('incomeExDate').value,date:$('incomeDate').value,kind:$('incomeKind').value,amount:Number($('incomeAmount').value),quantity:$('incomeQuantity').value?Number($('incomeQuantity').value):null}),'分红已确认，未计为外部入金。');};
 function chooseStrategy(id){act(()=>{const p=S.profile();p.researchSelection=id;if(!S.saveProfile(p))throw Error('无法保存策略选择');$('candidateSelect').value=id;},'已切换配置方案，继续沿用同一账户持仓、成交和成本。');}
 $('candidateSelect').onchange=()=>chooseStrategy($('candidateSelect').value);
 $('reviewMonth').max=today().slice(0,7);
 $('reviewMonth').onchange=()=>{const month=$('reviewMonth').value;if(!/^\d{4}-\d{2}$/.test(month)||month>today().slice(0,7)){status('请选择当前或过去的月份',true);$('reviewMonth').value=reviewEnd.slice(0,7);return;}reviewAutoDate=month===today().slice(0,7);reviewEnd=reviewAutoDate?today():new Date(Date.UTC(Number(month.slice(0,4)),Number(month.slice(5,7)),0)).toISOString().slice(0,10);allTradesExpanded=false;renderReview();};
 $('refreshReview').onclick=()=>{if(reviewAutoDate)reviewEnd=today();if(activePage==='review')renderReview();refreshAccountQuotes();};
 $('exportAccount').onclick=()=>download(S.exportBackup(),'星循-新策略账本-'+today()+'.json');
 $('importAccount').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;S.restoreBackup(JSON.parse(await file.text()));budgetDraftDirty=false;buyDrafts.clear();$('investmentPlan').querySelectorAll('.inline-buy').forEach(form=>form.dataset.saved='true');renderAccount();renderReview();status('完整账本已恢复。');}catch(err){status(err.message,true);}e.target.value='';};
 if(S.profile().researchSelection&&strategies.some(s=>s.id===S.profile().researchSelection))$('candidateSelect').value=S.profile().researchSelection;
 if(window.ACCOUNT_NAV_SNAPSHOT)try{applyAccountQuotes(window.ACCOUNT_NAV_SNAPSHOT);}catch(error){quoteMessage='保存净值异常，沿用研究快照。';}
 window.XingxunWorkspace={navigate,renderAccount,renderReview,chart,get actualFunds(){return accountFunds;},get plan(){return activePlan;},get report(){return latestReport;}};
 window.addEventListener('strategy-signals-updated',()=>{if(workspaceReady){renderAccount();if(activePage==='review')renderReview();}});
 workspaceReady=true;
 renderAccount();if(alipayRepairMessage)status(alipayRepairMessage);
 refreshAccountQuotes();
 setInterval(()=>{if(document.visibilityState!=='hidden'){if(reviewAutoDate)reviewEnd=today();if(activePage==='review')renderReview();refreshAccountQuotes();}},300000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refreshAccountQuotes();});

 }catch(error){$('workspaceStatus').textContent='账户初始化暂不可用：'+error.message+'。可切换页面查看，请勿清除浏览器数据。';}
})();
