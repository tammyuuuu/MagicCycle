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
