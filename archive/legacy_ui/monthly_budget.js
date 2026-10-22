(function(){
const money=x=>Math.floor((x+1e-9)*100)/100;
const PREMIUM_URL='https://push2delay.eastmoney.com/api/qt/ulist.np/get?secids=1.513100,1.513500&fields=f12,f14,f2,f441,f124&fltt=2&invt=2';
function parsePremiums(payload){
 if(payload?.rc!==0||!Array.isArray(payload?.data?.diff))throw Error('溢价行情格式异常');
 const quotes={};
 for(const row of payload.data.diff){
  if(!['513100','513500'].includes(row.f12))continue;
  if(typeof row.f2!=='number'||typeof row.f441!=='number'||typeof row.f124!=='number'||!Number.isFinite(row.f2)||!Number.isFinite(row.f441)||row.f2<=0||row.f441<=0||!Number.isFinite(row.f124)||row.f124<=0)continue;
  quotes[row.f12]={code:row.f12,price:row.f2,iopv:row.f441,timestamp:row.f124,premium:(row.f2/row.f441-1)*100};
 }
 return quotes;
}
function premiumFresh(quote,now=new Date()){
 if(!quote||!Number.isFinite(quote.premium)||!Number.isFinite(quote.timestamp))return false;
 const stamp=new Date(quote.timestamp*1000),format=d=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(d),current=format(now);
 if(format(stamp).slice(0,10)!==current.slice(0,10)||stamp.getTime()>now.getTime()+60000)return false;
 const minute=Number(current.slice(11,13))*60+Number(current.slice(14,16));
 if(minute<570)return false;
 return minute>=900||now.getTime()-stamp.getTime()<=20*60000;
}
function orderFor(amount,price,minimumFee=5,feeRate=.0001){
 if(!Number.isFinite(amount)||amount<0||!Number.isFinite(price)||price<=0||!Number.isFinite(minimumFee)||minimumFee<0||!Number.isFinite(feeRate)||feeRate<0)return {quantity:0,cost:0,fee:0,total:0};
 let quantity=Math.floor(amount/(price*(1+feeRate))/100)*100;
 while(quantity>0&&quantity*price+Math.max(minimumFee,quantity*price*feeRate)>amount+1e-9)quantity-=100;
 const cost=quantity*price,fee=quantity?Math.max(minimumFee,cost*feeRate):0;
 return {quantity,cost:Math.round(cost*100)/100,fee:Math.round(fee*100)/100,total:Math.round((cost+fee)*100)/100};
}
function calculate(budget,codes,summaries,entries,date,premiums={},budgetMonth=date.slice(0,7)){
 if(!Number.isFinite(budget)||budget<0||!codes.length||new Set(codes).size!==codes.length)throw Error('请输入有效月预算，并选择ETF。');
 entries.forEach(window.InvestmentLogic.validateEntry);
 const month=budgetMonth,buys=entries.filter(e=>e.date.slice(0,7)===month&&['买入','加仓'].includes(e.action));
 const spent=money(buys.reduce((n,e)=>n+e.amount,0));let remaining=Math.max(0,money(budget-spent));
 const rows=codes.map(code=>{
  const s=summaries.find(s=>s.symbol===code),used=money(buys.filter(e=>e.code===code).reduce((n,e)=>n+e.amount,0)),cap=money(budget/codes.length);
  let fraction=({buy:0.5,normal_buy:0.5,add:1,buy_more:1,small_buy:0.25,allocate:0.5,starter:0.1}[s?.status]||0),reason=s?.reason||'暂无行情';
  if(!s||s.date!==date||s.details?.data_warning||s.details?.insufficient_history||s.risk_level==='high'||!Number.isFinite(s.metrics?.price)||s.metrics.price<=0){fraction=0;reason='行情日期不一致、数据不足或风险条件未通过，先留现金';}
  if(s?.details?.strategy_mode==='us_monthly_trend'&&fraction){const p=premiums[code];if(!Number.isFinite(p)||p>2){fraction=0;reason='溢价未取得有效数据或高于2%，暂停新增投入（试行上限）';}}
  const target=money(cap*fraction),amount=Math.min(remaining,Math.max(0,money(target-used)));remaining=money(remaining-amount);
  return {code,name:s?.name||code,cap,used,target,amount,reason};
 });
 return {month,budget,spent,remaining:Math.max(0,money(budget-spent)),suggested:money(rows.reduce((n,r)=>n+r.amount,0)),rows,overBudget:spent>budget};
}
window.MonthlyBudgetLogic={calculate,parsePremiums,premiumFresh,orderFor,PREMIUM_URL};
const root=document.getElementById('invest-plan');if(!root)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const card=document.createElement('div');card.className='card';root.prepend(card);
const month=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit'}).format(new Date()),key='monthly_budget_v1_'+month;
const assets=window.CORRELATION_PRICES||[];
card.innerHTML=`<h2>每月投入预算</h2><p>${esc(month)} · 总月预算固定，所选ETF各分一等份；无买点的份额留现金。</p><form id="monthlyBudgetForm"><label>每月可投入金额（元） <input id="monthlyBudgetAmount" type="number" min="0" step="100" value="1000" required></label><div class="review-choices">${assets.map(a=>`<label><input type="checkbox" name="monthlyAsset" value="${esc(a.code)}">${esc(a.name)}</label>`).join('')}</div><p class="muted">美股溢价自动获取自东方财富延迟行情，按价格÷IOPV−1计算；高于2%暂停新增投入。2%是试行上限，并非回测最优值。IOPV是参考估值，下单仍需核对券商行情。</p><button type="button" id="monthlyPremiumRefresh" class="btn gray">刷新溢价</button><p id="monthlyPremiumStatus" role="status">正在获取溢价…</p><div id="monthlyPremiumQuotes"></div><details><summary>委托价格与交易费用</summary><p class="muted">填写你愿意支付的每份最高价格。美股自动带入延迟行情价格，可修改；其他ETF请核对券商报价填写。价格不会保证成交，回测另用次日开盘执行。</p><div id="monthlyLimitPrices"></div><label>最低佣金（元） <input id="monthlyMinFee" type="number" min="0" step="1" value="5" style="width:90px"></label> <label>佣金费率（万分之） <input id="monthlyFeeRate" type="number" min="0" step="0.1" value="1" style="width:90px"></label></details><p><button class="btn">保存预算并计算本次投入</button></p></form><p id="monthlyBudgetStatus" role="status"></p><div id="monthlyBudgetResult"></div><p class="muted">买入累计到该ETF月额度的50%，加仓累计到100%；其他小额买入沿用对应档位。重复信号仅补足差额，不重复投入。成交后务必记入投资日记，实际买入和加仓都会占用月额度，卖出不恢复额度。有成交后本月预算与标的锁定。未用金额留现金，不自动滚入下月；无买点不要求卖出原持仓。金额上限不含佣金，下单请预留费用并按100份取整。预算与日记保存在当前浏览器，换设备不会自动同步。这是预算控制试行规则，尚未证明最优。</p>`;
const el=id=>document.getElementById(id);let plan=null,broken=false,quotes={};const limitPrices={};
el('monthlyLimitPrices').innerHTML=assets.map(a=>`<label style="display:block">${esc(a.name)} 委托限价（元/份） <input type="number" min="0.001" step="0.001" data-monthly-limit="${esc(a.code)}" style="width:110px" placeholder="如 2.399"></label>`).join('');
function readEntries(){const e=JSON.parse(localStorage.getItem('investment_diary_v1')||'[]');if(!Array.isArray(e))throw Error('日记格式异常，停止计算');e.forEach(window.InvestmentLogic.validateEntry);return e;}
try{plan=JSON.parse(localStorage.getItem(key)||'null');if(plan&&(!Number.isFinite(plan.budget)||plan.budget<0||!Array.isArray(plan.codes)||!plan.codes.length||new Set(plan.codes).size!==plan.codes.length||plan.codes.some(c=>!assets.some(a=>a.code===c))))throw Error('本月预算数据异常');if(plan){el('monthlyBudgetAmount').value=plan.budget;card.querySelectorAll('[name=monthlyAsset]').forEach(i=>i.checked=plan.codes.includes(i.value));}}catch(e){broken=true;el('monthlyBudgetStatus').textContent='预算读取失败，停止计算，请检查浏览器保存数据。';}
function render(){try{if(broken||!plan)return;const raw=window.STRATEGY_SUMMARIES||[],summaries=window.summaryWithValuationYears?raw.map(s=>window.summaryWithValuationYears(s,window.selectedValuationYears())):raw,premiums={};for(const [code,quote] of Object.entries(quotes)){if(premiumFresh(quote))premiums[code]=Math.max(quote.premium,((limitPrices[code]??quote.price)/quote.iopv-1)*100);}const entries=readEntries(),r=calculate(plan.budget,plan.codes,summaries,entries,window.InvestmentLogic.marketContext().date,premiums,month);const locked=entries.some(e=>e.date.slice(0,7)===month&&['买入','加仓'].includes(e.action));el('monthlyBudgetAmount').disabled=locked;card.querySelectorAll('[name=monthlyAsset]').forEach(i=>i.disabled=locked);el('monthlyBudgetResult').innerHTML=`<p>本月已买 ${r.spent.toFixed(2)} 元 · 剩余月额度 ${r.remaining.toFixed(2)} 元 · 本次建议 ${r.suggested.toFixed(2)} 元</p>${r.overBudget?'<p>本月实际买入已超过预算，暂停新增投入。</p>':''}<div style="overflow:auto"><table><tr><th>ETF</th><th>月额度</th><th>已买</th><th>本次额度</th><th>委托限价</th><th>可买份数</th><th>含佣金金额</th></tr>${r.rows.map(x=>{const price=limitPrices[x.code]??quotes[x.code]?.price,order=orderFor(x.amount,price,Number(el('monthlyMinFee').value),Number(el('monthlyFeeRate').value)/10000);return `<tr><td>${esc(x.name)}</td><td>${x.cap.toFixed(2)}</td><td>${x.used.toFixed(2)}</td><td><b>${x.amount.toFixed(2)}元</b></td><td>${Number.isFinite(price)?price.toFixed(3):'请填写'}</td><td>${order.quantity}份</td><td>${order.total.toFixed(2)}元</td></tr><tr><td colspan="7" class="muted">${esc(x.reason)}${x.amount>0&&!order.quantity?'；价格未填或额度不足一手，暂不下单':''}</td></tr>`;}).join('')}</table></div>`;}catch(e){el('monthlyBudgetResult').innerHTML='';el('monthlyBudgetStatus').textContent='停止计算：'+e.message;}}
el('monthlyBudgetForm').onsubmit=e=>{e.preventDefault();try{if(broken)throw Error('原预算异常，请先检查保存数据');const entries=readEntries(),locked=entries.some(e=>e.date.slice(0,7)===month&&['买入','加仓'].includes(e.action));if(locked&&!plan)throw Error('本月已有成交但未设置预算，请下月启用；不能事后推定原预算');const next=locked?plan:{budget:Number(el('monthlyBudgetAmount').value),codes:[...card.querySelectorAll('[name=monthlyAsset]:checked')].map(i=>i.value)};calculate(next.budget,next.codes,[],entries,month+'-01');localStorage.setItem(key,JSON.stringify(next));plan=next;el('monthlyBudgetStatus').textContent='已保存；建议不会自动记为成交。';render();}catch(e){el('monthlyBudgetStatus').textContent=e.message;}};
const previous=window.setInvestmentSummaries;window.setInvestmentSummaries=function(list){previous(list);render();};
document.getElementById('diaryForm')?.addEventListener('submit',render);
document.getElementById('journalList')?.addEventListener('click',render);
window.addEventListener('investment-diary-changed',render);
window.addEventListener('storage',render);render();
function showQuotes(){
 const fmt=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
 el('monthlyPremiumQuotes').innerHTML=['513100','513500'].map(code=>{const q=quotes[code],name=assets.find(a=>a.code===code)?.name||code;return `<p><b>${esc(name)}：</b>${q?`${q.premium>=0?'+':''}${q.premium.toFixed(2)}% · 价格 ${q.price} / IOPV ${q.iopv}<br><span class="muted">行情时间 ${esc(fmt.format(new Date(q.timestamp*1000)))}（北京时间）${premiumFresh(q)?'':' · 数据过期，暂停新增投入'}</span>`:'暂无有效溢价，暂停新增投入'}</p>`;}).join('');
}
async function refreshPremiums(){
 const button=el('monthlyPremiumRefresh');if(button.disabled)return;
 button.disabled=true;quotes={};showQuotes();render();el('monthlyPremiumStatus').textContent='正在获取溢价…';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
 try{
  const response=await fetch(PREMIUM_URL+'&_='+Date.now(),{signal:controller.signal,cache:'no-store',credentials:'omit'});
  if(!response.ok)throw Error('HTTP '+response.status);
  quotes=parsePremiums(await response.json());
  card.querySelectorAll('[data-monthly-limit]').forEach(input=>{const code=input.dataset.monthlyLimit;if(!(code in limitPrices)&&quotes[code])input.value=quotes[code].price.toFixed(3);});
  const complete=['513100','513500'].every(code=>premiumFresh(quotes[code]));
  el('monthlyPremiumStatus').textContent=complete?'溢价已更新（延迟行情）；买入金额自动按溢价检查。':'部分行情缺失或过期，对应ETF暂停新增投入。';
 }catch(e){quotes={};el('monthlyPremiumStatus').textContent='自动获取失败，暂不建议新增美股投入；联网后点击刷新溢价。';}
 finally{clearTimeout(timer);button.disabled=false;showQuotes();render();}
}
el('monthlyPremiumRefresh').onclick=refreshPremiums;
card.querySelectorAll('[data-monthly-limit]').forEach(input=>input.oninput=()=>{limitPrices[input.dataset.monthlyLimit]=input.value.trim()?Number(input.value):NaN;render();});
['monthlyMinFee','monthlyFeeRate'].forEach(id=>el(id).oninput=render);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refreshPremiums();});
setInterval(()=>{if(document.visibilityState==='visible'){showQuotes();render();}},60000);
refreshPremiums();
})();
