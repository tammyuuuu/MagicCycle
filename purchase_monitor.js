/* Public channel monitoring is independent of ETF signals and formal strategy approval. */
(function(){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function quota(value){
  if(value==null)return null;const s=String(value).trim();
  if(/无代销|无直销|暂停|不可|关闭/.test(s))return 0;
  if(/^(不限|无限额|不限额)$/.test(s))return Infinity;
  const m=s.replace(/,/g,'').match(/^(\d+(?:\.\d+)?)\s*(亿|万)?(?:元)?$/);return m?Number(m[1])*({'亿':1e8,'万':1e4}[m[2]]||1):null;
 }
 function executionJudge({row:r,snapshot,day,strategy,needed,planRow}){
  const asset=window.ProductAssets?.assetOf(r.code,window.XingxunStore?.profile()),matching=window.ProductAssets?!!(asset&&window.ProductAssets.weights(strategy||{weights:{}})[asset]&&window.ProductAssets.selected(asset,window.XingxunStore?.profile())===r.code):!!strategy?.weights?.[r.code],group=r.index==='纳指100'?'161130':'050025',groupMatch=!!strategy?.weights?.[group];
  const selected=matching?'当前资产已选择该实际产品':window.ProductAssets?.mapping(r.code,window.XingxunStore?.profile())&&groupMatch?'资产归属已核实，但未选为当前交易产品':groupMatch?'同指数类别，但产品/份额不同，未验证为替代基金':'不属于当前选定策略';
  const current=snapshot?.updated_at?.slice(0,10)===day&&r.quota?.source_date===day;
  const limits=current?[quota(r.quota.direct_limit),quota(r.quota.retail_limit)]:[null,null];
  const known=limits.filter(v=>v!==null),enough=needed>0&&known.some(v=>v>=needed);
  const navAge=(Date.parse(day)-Date.parse(r.nav_date))/86400000,navOK=Number.isFinite(r.unit_nav)&&r.unit_nav>0&&navAge>=0&&navAge<=7;
  const channel=!current?'待核实：无今日公开额度':known.length===0?'待核实：额度格式不明确':needed<=0?'已取得公开额度；当前策略无此指数的申购目标':needed>0&&!enough?(known.length===2?'公开渠道额度均不足本次参考金额':'已知额度不足；其他渠道待核实'):'公开额度可覆盖参考金额，个人渠道仍待核实';
  if(/暂停申购/.test(r.purchase_status||r.nav_purchase_status||''))return {label:'暂停申购',channel:'暂停申购',selected,reason:'披露申购状态为暂停申购。'};
  if(!current||!navOK)return {label:'待核实',channel,selected,reason:!current?'额度快照过期或缺失；不判断当前可买性。':'净值缺失、过旧或日期异常。'};
  if(needed>0&&known.length===2&&!enough)return {label:'额度不足',channel,selected,reason:'每个渠道的公开日额度都不足'+needed.toFixed(2)+'元，不合并渠道额度。'};
  if(!matching)return {label:'观察',channel,selected,reason:groupMatch?'指数类别相近不等于同一产品；不自动替换当前策略的基金。':'该基金不在当前选定的研究策略中。'};
  if(strategy.simulation_validation!=='passed')return {label:'观察',channel,selected,reason:'选定策略仅为条件性研究，尚未获得模拟执行验收。'};
  if(!planRow?.executable||planRow.action!=='买入')return {label:'观察',channel,selected,reason:'当前没有此基金的有效模拟申购计划。'};
  const verification=r.channel_confirmation;
  if(!enough||!verification?.verified||verification.date!==day||!verification.evidence)return {label:'待核实',channel,selected,reason:'公开公告不能替代个人渠道确认；缺少当日可买证据。'};
  if(r.fee_verified_date!==day||!Number.isFinite(r.buy_pct))return {label:'待核实',channel,selected,reason:'缺少当日核实的费用信息。'};
  return {label:'符合模拟计划',channel,selected,reason:'同一基金、已验收模拟策略、有效计划与当日渠道证据均满足；仍非实盘建议。'};
 }
 function opportunity(signal,day){
  const age=(Date.parse(day)-Date.parse(signal?.date))/86400000;
  if(!signal||signal.details?.strategy_mode!=='us_monthly_trend'||!Number.isFinite(age)||age<0||age>7||signal.details.insufficient_history)
   return {label:'买点待核实',rank:2,reason:'买点行情缺失、过旧或历史不足，先等待有效数据。'};
  const buy=['buy','add'].includes(signal.status)&&['buy','add'].includes(signal.details.new_money_action);
  return {label:buy?'可考虑买入':'暂不买入',rank:buy?0:1,reason:signal.reason||'按现有美股趋势与热度策略判断。',date:signal.date};
 }
 function judge(input){
  const symbol=input.row.index==='纳指100'?'513100':'513500';
  const signal=input.signal||(window.STRATEGY_SUMMARIES||[]).find(s=>s?.symbol===symbol);
  return {...executionJudge(input),opportunity:opportunity(signal,input.day)};
 }
 window.PurchaseMonitorPolicy={quota,judge,opportunity};
 const priority={'符合模拟计划':0,'观察':1,'待核实':2,'额度不足':3};
 function recommendationOrder(a,b){return (a.result.opportunity?.rank??2)-(b.result.opportunity?.rank??2)||(priority[a.result.label]??4)-(priority[b.result.label]??4)||Number(b.matching)-Number(a.matching);}
 window.PurchaseMonitorPolicy.recommendationOrder=recommendationOrder;
 function statusOf(row){
  const text=row.purchase_status||row.nav_purchase_status||'状态缺失';
  return {text:/�/.test(text)?'状态缺失':text,date:row.terms_as_of||row.nav_date};
 }
 function tradeLabel(result){return result.opportunity.rank===0?'买入':result.opportunity.rank===1&&/退出|减仓/.test(result.opportunity.reason)?(/退出/.test(result.opportunity.reason)?'卖出':'减仓'):'观察';}
 function feeLines(row,peers){
  const fields=[['management_pct','管理费'],['custody_pct','托管费'],['service_pct','销售服务费']];
  return fields.filter(([key])=>Number.isFinite(row[key])&&!(peers.length>1&&peers.every(p=>Number.isFinite(p[key])&&p[key]===row[key]))).map(([key,label])=>`<div><dt>${label}</dt><dd>${row[key]}% / 年</dd></div>`).join('');
 }
 window.PurchaseMonitorPolicy.statusOf=statusOf;
 window.PurchaseMonitorPolicy.tradeLabel=tradeLabel;
 window.PurchaseMonitorPolicy.feeLines=feeLines;
 function render(){
  const root=document.getElementById('sec-today')||document.getElementById('page-today');if(!root)return;
  let card=document.getElementById('usPurchaseMonitor');if(!card){card=document.createElement('section');card.id='usPurchaseMonitor';card.className='workspace card';root.appendChild(card);}
  const snap=window.FUND_ACCESS_MONITOR,D=window.WORKSPACE_DATA,selection=document.getElementById('candidateSelect')?.value;
  const strategy=D?.research?.strategies.find(s=>s.id===selection),S=window.XingxunStore,profile=S?.profile(),budget=(S?.latestSnapshot()?.total_assets??0)*(profile?.ratio??.1);
  const day=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
  let plan;try{if(window.XingxunWorkspace?.plan)plan=window.XingxunWorkspace.plan;else if(strategy)plan=window.InvestmentPlanner.plan({profile,strategy,data:D,date:day,capitalPool:window.CapitalPool,valuation:window.PortfolioValuation});}catch(e){}
  const rows=[...(snap?.rows||[])];
  // Retain the original channel list, and show the exact research products without claiming a quota.
  for(const [code,index] of [['161130','纳指100'],['050025','标普500']])if(!rows.some(r=>r.code===code)&&D?.funds?.[code]){
   const f=D.funds[code],c=D.trading_conditions?.[code],nav=f.nav.at(-1);
   rows.push({code,index,kind:'us',name:f.name,channel:'支付宝 / 微信 / 官方渠道需自行核实',unit_nav:nav?.[1],nav_date:nav?.[0],nav_purchase_status:c?.status,nav_state:'保存研究净值',buy_pct:c?.buy_pct,product_url:'https://fundf10.eastmoney.com/jjfl_'+code+'.html',nav_source:'https://fundf10.eastmoney.com/jjjz_'+code+'.html',note:'保存状态：'+(c?.status||'未知')+'（'+(c?.as_of||'无日期')+'）；不代表当前个人渠道可买。'});
  }
  const selectedIndex=card.dataset.selectedIndex||'纳指100';
  const groups=['纳指100','标普500'];
  card.innerHTML=`<h2>美股基金购买监测</h2><div class="today-categories"><div class="guide-tabs" aria-label="美股基金指数分类">${groups.map((index,i)=>`<button type="button" data-monitor-index="${index}" aria-pressed="${index===selectedIndex}" aria-controls="monitor-group-${i}">${index==='纳指100'?'纳指基金':'标普基金'}</button>`).join('')}</div></div><div class="monitor-groups">${groups.map((index,i)=>{
   const peers=rows.filter(r=>r.kind==='us'&&r.index===index);
   const common=[['management_pct','管理费'],['custody_pct','托管费'],['service_pct','销售服务费']].filter(([key])=>peers.length>1&&Number.isFinite(peers[0][key])&&peers.every(r=>r[key]===peers[0][key])).map(([key,label])=>`${label} ${peers[0][key]}% / 年`);
   return `<div id="monitor-group-${i}" ${index===selectedIndex?'':'hidden'}>${common.length?`<p class="monitor-common">本组相同：${common.map(esc).join(' · ')}</p>`:''}${peers.map(r=>{
    const code=index==='纳指100'?'161130':'050025',p=plan?.rows?.find(p=>p.code===r.code),reference=p?.action==='买入'?p.amount:budget*(strategy?.weights?.[code]||0),result=judge({row:r,snapshot:snap,day,strategy,needed:reference,planRow:p});
    return {r,result,matching:!!strategy?.weights?.[r.code]};
   }).sort(recommendationOrder).map(({r,result})=>{
    const q=r.quota,status=statusOf(r),sub=Number.isFinite(r.subscription_pct)?r.subscription_pct:r.buy_pct;
    const date=status.date&&status.date!==day?'（'+status.date+'）':'';
    const quotaText=/暂停申购/.test(status.text)?'暂停期间不可申购':q?`直销 ${q.direct_limit??'未公布'} / 代销 ${q.retail_limit??'未公布'} 元/日${q.source_date!==day||snap?.updated_at?.slice(0,10)!==day?'（保存额度 '+q.source_date+'）':''}`:/暂停申购/.test(status.text)?'暂停期间不可申购':'未取得公开额度';
    const annual=feeLines(r,peers)||(!Number.isFinite(r.management_pct)&&Number.isFinite(r.fee_pct)?`<div><dt>年费合计参考</dt><dd>${r.fee_pct}%</dd></div>`:'');
    return `<article class="monitor-row" data-monitor-code="${esc(r.code)}"><div class="monitor-heading"><a href="${esc(r.product_url)}" target="_blank" rel="noopener">${esc(r.name)} <small>${esc(r.code)}</small></a><strong class="monitor-decision">${tradeLabel(result)}</strong></div><dl class="monitor-facts"><div><dt>额度</dt><dd>${esc(quotaText)}</dd></div><div><dt>申购状态</dt><dd>${esc(status.text+date)}</dd></div><div><dt>申购费</dt><dd>${Number.isFinite(sub)?esc(sub)+'%'+(r.subscription_channel?'（页面参考）':'（保存参考）'):'未取得费率'}</dd></div>${annual}</dl>${r.note?.includes('主动')?'<p class="monitor-exception">主动FOF，另有底层基金费用</p>':''}<details class="monitor-source"><summary>来源</summary><p>申购状态、费率：${esc(r.terms_as_of||r.nav_date||'日期缺失')} · ${esc(r.subscription_channel||'保存资料')}。${esc(r.subscription_basis||'')}<br>${esc(r.channel||'')}<br>买卖信号：${esc(result.opportunity.date||'数据缺失')}，指数策略参考。</p><a href="${esc(r.terms_source||r.nav_source)}" target="_blank" rel="noopener">申购与费率来源</a></details></article>`;
   }).join('')}</div>`;
  }).join('')}</div><p class="monitor-common">额度更新 ${esc(snap?.updated_at?.slice(0,10)||'日期缺失')} · <a href="${esc(snap?.quota_source||'https://qdiilimit.com/')}" target="_blank" rel="noopener">公开额度来源</a></p>${(snap?.future_alerts||[]).map(t=>`<p class="monitor-exception">${esc(t)}</p>`).join('')}`;
 }
 document.addEventListener('click',event=>{
  const button=event.target.closest?.('[data-monitor-index]');if(!button)return;
  const card=button.closest('#usPurchaseMonitor');if(!card)return;
  card.dataset.selectedIndex=button.dataset.monitorIndex;
  card.querySelectorAll('[data-monitor-index]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
  card.querySelectorAll('.monitor-groups>div').forEach(panel=>panel.hidden=panel.id!==button.getAttribute('aria-controls'));
 });
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render);else render();
 window.addEventListener('xingxun:account-change',render);
 window.renderPurchaseMonitor=render;
})();
