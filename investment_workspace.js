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
  finally{quotesLoading=false;if(reviewAutoDate)reviewEnd=today();renderAccount();renderReview();}
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
 function selectedStrategy(){return strategies.find(s=>s.id===$('candidateSelect').value)||strategies[0];}
 function budgetRatio(){return Number($('budgetRatio').value==='custom'?$('customRatio').value:$('budgetRatio').value)/100;}
 function previewBudget(){const custom=$('budgetRatio').value==='custom';$('customRatioLabel').hidden=!custom;$('customRatio').required=custom;const total=$('assetTotal').value===''?null:Number($('assetTotal').value),ratio=budgetRatio(),valid=total!=null&&Number.isFinite(ratio)&&ratio>=0&&ratio<=1;$('budgetPreview').textContent=valid?money(total*ratio):'待填写';$('budgetPreviewNote').textContent=budgetDraftDirty&&S.profile().opening?'未保存 · 当前计划仍按已保存预算计算':'';}
 function loadBudgetInputs(){const p=S.profile(),snap=S.latestSnapshot();$('assetTotal').value=snap?.total_assets??'';$('ledgerStartDate').value=p.opening?.date||today();$('ledgerStartDate').max=p.opening?.date||today();const percentage=Number((p.ratio*100).toFixed(2));$('budgetRatio').value=[5,10,20].includes(percentage)?String(percentage):'custom';$('customRatio').value=percentage;}
 function allocation(r=currentReport()){
  const p=S.profile(),snap=S.latestSnapshot(),ready=!!p.opening&&!!snap;
  if(!budgetDraftDirty)loadBudgetInputs();$('strategyPanel').hidden=!ready;$('strategyChoice').hidden=!ready;$('investmentPlan').hidden=!ready;$('budgetSummary').hidden=!ready;
  const equity=r.ready?r.summary.equity:null,budget=snap?C.poolBudget(snap.total_assets,equity??0,0,p.ratio):null;
  $('budgetSummary').innerHTML=ready?`<p>更新 ${esc(snap.date)}${snap.date.slice(0,7)!==today().slice(0,7)?' · 本月沿用上次金额':''}<br>账户净资产 ${money(equity)} · 可用现金 ${money(p.poolCash)}<br>可新增额度 ${equity!=null?money(budget.new_allowed):'待估值'}</p>${equity!=null&&budget.over_target>0?'<p>账户已超目标，暂停新增投入，不强制卖出。</p>':''}`:'';
  $('candidateAllocation').textContent=selectedStrategy().scenario==='nasdaq_available'?'正常申购情景':'纳指不可买情景';
  $('budgetCashCorrection').hidden=!window.AccountFunding.candidate(p,S.snapshots());$('budgetSetupNote').textContent=p.opening?'':'预算仅为投资目标，不会计入账户现金；已成交申购按实际付款登记投入。';previewBudget();renderPlan();
 }
 function renderPlan(){
  const inline=$('quickTradeDialog');if(inline&&$('investmentPlan').contains(inline)){inline.hidden=true;$('planTransactions').append(inline);}
  const profile=S.profile(),strategy=selectedStrategy(),weights=A.weights(strategy),snap=S.latestSnapshot(),budget=(snap?.total_assets??0)*profile.ratio;
  try{activePlan=window.AssetPlanner.plan({profile,strategy,data:{...D,funds:accountFunds},date:today(),capitalPool:C,valuation:V,totalAssets:snap?.total_assets});}catch(e){activePlan={rows:[],reason:e.message};}
  const pending=(profile.entries||[]).filter(e=>e.status==='submitted'),payments=Object.entries(profile.payments||{}).filter(([id,v])=>!v.settled),journal=S.journal();
  const assets=[...new Set([...Object.keys(weights),...(activePlan.rows||[]).map(r=>r.asset),...pending.map(e=>A.assetOf(e.code,profile)),...payments.map(([id])=>A.assetOf(journal.find(e=>e.id===id)?.code,profile))])].filter(Boolean);
  const entries=Object.entries(weights),cents=Math.round(budget*100),targets=entries.map(([a,w])=>Math.floor(cents*w));let remainder=cents-targets.reduce((a,b)=>a+b,0);for(let i=0;remainder>0;i=(i+1)%targets.length){targets[i]++;remainder--;}
  $('investmentPlan').querySelectorAll('.inline-buy').forEach(form=>{const field=id=>form.querySelector('[data-field="'+id+'"]');if(form.dataset.saved!=='true'&&form.dataset.dirty==='true')buyDrafts.set(form.dataset.asset,{code:field('productCode').value,date:field('recordBuyDate').value,amount:field('recordBuyAmount').value,quantity:field('recordBuyQuantity').value,fee:field('recordBuyFee').value,basis:field('recordAmountBasis').value,id:form.dataset.recordId});});
  $('investmentPlan').innerHTML=assets.map(asset=>{
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
  if(!Number.isFinite(fee)||fee<0||fee>=amount||Math.abs(fee*100-Math.round(fee*100))>1e-7)throw Error('请核对实际申购费，金额单位为元');const strategy=selectedStrategy(),row={id:recordId,mode:'real',accountId:'strategy',date,submittedDate:date,code,name:identity.name,action:'买入',status:'confirmed',confirmedDate:date,valuationDate:date,netAmount,enteredAmount,amountInputBasis:basis,feeKind:netBasis?'conversion':'subscription',confirmedDateBasis:'user_recorded_nav_date',amount,quantity,fee,feeInput:policy?{unit:'percent',value:policy.buy_pct,source:'user_provided'}:{unit:'amount',value:fee},asset:mapping?.asset||null,identitySource:identity.identitySource,purchaseFeePolicy:!netBasis&&date>='2026-10-22'?window.UserPurchaseFees.forCode(code):null,source:'manual_executed_buy',...(matched?{planStrategy:strategy.id,planVersion:strategy.version,planWeights:{...strategy.weights},executionBasis:'manual_trade_research_plan'}:{})};
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
  window.ReviewScorecard.render({profile:p,data:D,funds:accountFunds,valuation:V,store:S,report:r,end,quoteMessage});
  const tx=(p.journal||[]).filter(e=>e.action!=='观察').slice().sort((a,b)=>b.date.localeCompare(a.date));
  const record=e=>`<details class="review-trade"><summary><span><b>${esc(accountFunds[e.code]?.name||e.code)} · ${esc(e.action)}</b><small>${esc(e.date)} · ${esc(p.payments?.[e.id]?.settled?'已到账':({submitted:'等待确认',confirmed:'已确认',cancelled:'已撤销',failed:'失败',pending:'待执行'}[e.status]||e.status))}</small></span><strong>${money(e.amount)}</strong></summary><p class="fine">${esc(e.code)} · ${e.confirmedDateBasis==='user_recorded_nav_date'?'成交净值日期':'确认日期'} ${esc(e.confirmedDate||'尚未确认')}<br>${e.action==='买入'?'申购总额 '+money(e.amount)+' · 净投入 '+(e.status==='confirmed'?money(e.amount-e.fee):'待确认')+'<br>':''}实际份额 ${e.quantity==null?'未确认':esc(e.quantity)} · ${e.action==='买入'?(e.feeKind==='conversion'?'转换费':'申购费'):'赎回费'} ${e.status==='confirmed'?money(e.fee):'待确认'}${e.resolvedDate?'<br>撤销 / 失败日期 '+esc(e.resolvedDate):''}</p><button class="link-button" type="button" data-delete="${esc(e.id)}">删除</button></details>`;
  $('transactionHistory').innerHTML=tx.length?tx.slice(0,3).map(record).join(''):'<div class="empty">暂无交易记录</div>';
  $('allTransactionHistory').innerHTML=tx.slice(3).map(record).join('');$('allTransactionHistory').hidden=!allTradesExpanded;$('allTransactions').hidden=tx.length<=3;$('allTransactions').textContent=allTradesExpanded?'收起较早交易':`查看全部交易（${tx.length}笔）`;
  for(const id of ['transactionHistory','allTransactionHistory'])$(id).querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>deleteTrade(b.dataset.delete));
 }
 function renderResearch(){window.StrategyLab.init(D);}
 function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 function navigate(name){
  document.body.classList.remove('scorecard-capture');$('scoreCapture').textContent='截图视图';
  name=({diary:'review',guide:'lab'}[name]||name);
  pageScroll[activePage]=window.scrollY;
  for(const id of ['plan','review','lab'])$('invest-'+id).classList.toggle('hidden',id!==name);
  for(const id of ['sec-today','page-today']){const el=$(id);if(el)el.classList.toggle('hidden',name!=='today');}
  document.querySelectorAll('#topnav a').forEach(a=>{const n=a.dataset.t||a.dataset.page;a.classList.toggle('active',n===name);a.setAttribute('aria-current',n===name?'page':'false');});
  activePage=name;requestAnimationFrame(()=>window.scrollTo({top:pageScroll[name]||0,behavior:'instant'}));
  if(!workspaceReady)return;
  try{if(name==='review')renderReview();if(name==='plan'){renderAccount();renderReview();}status('');}
  catch(error){$('workspaceStatus').textContent='页面计算暂不可用：'+error.message;}
 }
 $('incomeDate').value=today();
 $('candidateSelect').innerHTML=options(strategies.map(s=>[s.id,window.StrategyLabels.label(s.id)]));
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
   S.saveJournal([...S.journal(),{id,mode:'real',accountId:'strategy',date,submittedDate:date,code:row.code,name:row.name,action:row.action,status:'submitted',amount:actual,quantity,fee:row.action==='买入'?Math.round((actual-actual/(1+row.buy_pct/100))*100)/100:row.fee,asset:row.asset,productChannel:row.channel,productVerification:{...p.productTerms?.[row.code],mapping:A.mapping(row.code,p)},planStrategy:selectedStrategy().id,planVersion:selectedStrategy().version,planWeights:{...selectedStrategy().weights},executionBasis:'manual_trade_research_plan'}]);
  }else{
   const old=p.journal.find(t=>t.id===id);if(!old)throw Error('交易不存在');
   if(kind==='settle'){if(old.status!=='confirmed'||old.action!=='卖出'||p.payments?.[id]?.settled)throw Error('该交易不可重复登记到账');const amount=Number($('quickAmount').value);if(!Number.isFinite(amount)||amount<=0||Math.abs(amount*100-Math.round(amount*100))>1e-7)throw Error('实际到账金额无效');const updated={...old,amount};p.journal=p.journal.map(t=>t.id===id?updated:t);p.settlements=[...(p.settlements||[]),{id:'settle-'+id,tradeId:id,date,amount}];
   }else if(kind==='confirm'){if(old.status!=='submitted')throw Error('成交已处理，不可重复保存');const policy=old.action==='买入'?window.UserPurchaseFees.forTrade(old):null,fee=policy?window.UserPurchaseFees.amount(old.amount,policy):($('quickFee').value===''?NaN:Number($('quickFee').value));if(!Number.isFinite(fee)||fee<0||Math.abs(fee*100-Math.round(fee*100))>1e-7)throw Error('请填写实际手续费');const updated={...old,status:'confirmed',confirmedDate:date,quantity:Number($('quickSellQuantity').value),amount:old.action==='买入'?old.amount:Number($('quickAmount').value),fee,feeInput:{unit:'amount',value:fee}};p.journal=p.journal.map(t=>t.id===id?updated:t);
   }else throw Error('交易操作无效');p.entries=p.journal.filter(t=>t.action!=='观察');if(!S.saveProfile(p))throw Error('账本校验失败，未保存');
  }
  ($('quickTradeDialog').hidden=true);renderAccount();renderReview();status('已记账并自动更新持仓和复盘；未进行下单。');
 }catch(err){$('quickError').textContent=err.message;}};
 $('incomeForm').onsubmit=e=>{e.preventDefault();act(()=>S.addIncome({id:S.newId(),code:$('incomeCode').value,exDate:$('incomeExDate').value,date:$('incomeDate').value,kind:$('incomeKind').value,amount:Number($('incomeAmount').value),quantity:$('incomeQuantity').value?Number($('incomeQuantity').value):null}),'分红已确认，未计为外部入金。');};
 $('candidateSelect').onchange=()=>act(()=>{const p=S.profile();p.researchSelection=$('candidateSelect').value;if(!S.saveProfile(p))throw Error('无法保存策略选择');},'已保存研究方案选择；正式配置未改变。');
 $('reviewMonth').max=today().slice(0,7);
 $('reviewMonth').onchange=()=>{const month=$('reviewMonth').value;if(!/^\d{4}-\d{2}$/.test(month)||month>today().slice(0,7)){status('请选择当前或过去的月份',true);$('reviewMonth').value=reviewEnd.slice(0,7);return;}reviewAutoDate=month===today().slice(0,7);reviewEnd=reviewAutoDate?today():new Date(Date.UTC(Number(month.slice(0,4)),Number(month.slice(5,7)),0)).toISOString().slice(0,10);allTradesExpanded=false;renderReview();};
 $('refreshReview').onclick=()=>{if(reviewAutoDate)reviewEnd=today();renderReview();refreshAccountQuotes();};
 $('exportAccount').onclick=()=>download(S.exportBackup(),'星循-新策略账本-'+today()+'.json');
 $('importAccount').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;S.restoreBackup(JSON.parse(await file.text()));budgetDraftDirty=false;buyDrafts.clear();$('investmentPlan').querySelectorAll('.inline-buy').forEach(form=>form.dataset.saved='true');renderAccount();renderReview();status('完整账本已恢复。');}catch(err){status(err.message,true);}e.target.value='';};
 if(S.profile().researchSelection&&strategies.some(s=>s.id===S.profile().researchSelection))$('candidateSelect').value=S.profile().researchSelection;
 if(window.ACCOUNT_NAV_SNAPSHOT)try{applyAccountQuotes(window.ACCOUNT_NAV_SNAPSHOT);}catch(error){quoteMessage='保存净值异常，沿用研究快照。';}
 window.XingxunWorkspace={navigate,renderAccount,renderReview,chart,get actualFunds(){return accountFunds;},get plan(){return activePlan;},get report(){return latestReport;}};
 workspaceReady=true;
 renderAccount();renderReview();renderResearch();if(alipayRepairMessage)status(alipayRepairMessage);
 refreshAccountQuotes();
 setInterval(()=>{if(document.visibilityState!=='hidden'){if(reviewAutoDate)reviewEnd=today();renderReview();refreshAccountQuotes();}},300000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refreshAccountQuotes();});

 }catch(error){$('workspaceStatus').textContent='账户初始化暂不可用：'+error.message+'。可切换页面查看，请勿清除浏览器数据。';}
})();