(function(){
function calculate(assets,windowSize){
 if(assets.length<2)throw Error('请至少选择两只ETF。');
 if(![60,120,250].includes(windowSize))throw Error('计算区间无效。');
 // First compute each security's actual adjacent-day return, then align dates.
 const returns=assets.map(a=>{const out=new Map();for(let i=1;i<a.prices.length;i++){const [date,p]=a.prices[i],prev=a.prices[i-1][1];if(Number.isFinite(p)&&p>0&&Number.isFinite(prev)&&prev>0)out.set(date,{value:p/prev-1,previous:a.prices[i-1][0]});}return out;});
 const dates=[...returns[0].keys()].filter(d=>returns.every(r=>r.has(d)&&r.get(d).previous===returns[0].get(d).previous)).sort().slice(-windowSize);
 if(dates.length<windowSize)throw Error(`共同收益样本只有${dates.length}个，请选择更短区间或更新行情。`);
 const values=returns.map(r=>dates.map(d=>r.get(d).value));
 const means=values.map(v=>v.reduce((a,b)=>a+b,0)/v.length);
 const matrix=values.map((x,i)=>values.map((y,j)=>{let cross=0,xx=0,yy=0;for(let k=0;k<x.length;k++){const a=x[k]-means[i],b=y[k]-means[j];cross+=a*b;xx+=a*a;yy+=b*b;}return xx>0&&yy>0?Math.max(-1,Math.min(1,cross/Math.sqrt(xx*yy))):null;}));
 return {assets:assets.map(({code,name})=>({code,name})),window:windowSize,count:dates.length,start:dates[0],end:dates.at(-1),matrix,method:'共同日期日收益率 Pearson（同一前序交易日）'};
}
function recommend(result,count,threshold=.5){
 if(!Number.isFinite(threshold)||threshold< -1||threshold>1)throw Error("相关性上限请输入−1到1之间的数字。");
 if(!Number.isInteger(count)||count<2||count>result.assets.length)throw Error('请选择轮动数量，且不能超过勾选的ETF数量。');
 let best=[],bestAverage=Infinity;
 function visit(indices,next){
  if(indices.length===count){
   const correlations=[];for(let i=0;i<indices.length;i++)for(let j=i+1;j<indices.length;j++)correlations.push(result.matrix[indices[i]][indices[j]]);
   const average=correlations.reduce((a,b)=>a+b,0)/correlations.length;
   if(average<bestAverage){best=indices.slice();bestAverage=average;}
  }
  if(indices.length===count)return;
  for(let i=next;i<result.assets.length;i++){
   if(indices.every(j=>Number.isFinite(result.matrix[i][j])&&result.matrix[i][j]<=threshold))visit([...indices,i],i+1);
  }
 }
 visit([],0);
 const group=best.map(i=>result.assets[i]);
 return {version:'rotation_group_v5',count,threshold,group,averageCorrelation:group.length?bestAverage:null,
         reason:group.length?'这几只ETF同涨同跌程度较低，适合作为一组轮动候选。':`所选ETF中暂未找到适合${count}只一起轮动的组合，可更换标的、调整数量或相关性上限。`};
}

function allocation(assets,summaries){
 if(!assets.length)throw Error('请先选择ETF。');
 const asOf=assets.map(a=>a.prices?.at(-1)?.[0]||'').sort().at(-1);
 const labels={buy_more:'加仓',add:'加仓',buy:'买入',watch:'观察',reduce:'减仓',exit:'退出'};
 const rows=assets.map(a=>{
  const summary=summaries.find(s=>s.symbol===a.code),status=summary?.status||'watch';
  const usable=summary&&summary.date===asOf&&Number.isFinite(summary.metrics?.price)&&!summary.details?.data_warning&&!summary.details?.insufficient_history&&summary.risk_level!=='high';
  const strength=usable?({buy_more:2,add:2,buy:1}[status]||0):0;
  return {code:a.code,name:a.name,status,action:labels[status]||'观察',date:summary?.date||null,
   percent:Math.floor(strength/(2*assets.length)*1000)/10,
   reason:!summary?'暂无策略行情，先留现金':summary.date!==asOf?'行情日期不一致，先留现金':!usable?'数据不足或风险条件未通过，先留现金':summary.reason||'按当前策略信号分配'};
 });
 return {version:'signal_allocation_v1',asOf,rows,cash:Math.round((100-rows.reduce((sum,r)=>sum+r.percent,0))*10)/10,
  rule:'每只ETF以资金的等份为参考：加仓使用一整份，买入使用半份，其他信号暂不配置，剩余留现金。'};
}
window.CorrelationLogic={calculate,recommend,allocation};
const el=id=>document.getElementById(id),form=el('correlationForm');if(!form?.addEventListener)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const assets=window.CORRELATION_PRICES||[],key='investment_correlations_v1';let history=[],valid=true;
function validate(rows){if(!Array.isArray(rows)||rows.some(r=>!r||typeof r.id!=='string'||typeof r.savedAt!=='string'||!Array.isArray(r.assets)||!Array.isArray(r.matrix)||r.matrix.length!==r.assets.length||r.matrix.some(row=>!Array.isArray(row)||row.length!==r.assets.length||row.some(v=>v!==null&&(!Number.isFinite(v)||v< -1||v>1)))))throw Error('历史格式异常');return rows;}
try{history=validate(JSON.parse(localStorage.getItem(key)||'[]'));}catch(e){valid=false;el('correlationStatus').textContent='计算历史读取失败，请先导出备份；不会覆盖原数据。';}
el('correlationCount').innerHTML='<option value="" selected disabled>请选择几只ETF</option>'+assets.slice(1).map((_,i)=>'<option value="'+(i+2)+'">'+(i+2)+'只</option>').join('');
el('correlationCount').value=assets.length>=3?'3':'';
el('correlationAssets').innerHTML=assets.map(a=>`<label class="review-choice"><input type="checkbox" value="${esc(a.code)}" checked> ${esc(a.name)} ${esc(a.code)}</label>`).join('');
function recommendations(r){
 if(!r.recommendations)return '';
 const rec=['rotation_group_v3','rotation_group_v4','rotation_group_v5'].includes(r.recommendations.version)?r.recommendations:{group:[],reason:'这次历史计算未选择轮动数量，可重新计算。'};
 return `<details open style="margin-top:18px"><summary>查看轮动推荐</summary><h3>${rec.group.length?rec.group.map(a=>esc(a.name)+' '+esc(a.code)).join(' ↔ '):'暂无合适组合'}</h3><p>${esc(rec.reason)}</p><p class="muted">按你指定的数量筛选两两相关性不高于${esc((rec.threshold??.5).toFixed(2))}的组合，再选平均相关性更低的一组；数量不自动减少。推荐是候选筛选，不是买入信号。</p></details>`;
}

function allocationTable(a){
 if(!a)return '';
 return `<h3>当前建议配比</h3><p>${esc(a.scope||'所选ETF')} · 行情截至 ${esc(a.asOf||'暂无')} · 按待配置资金的100%计算</p><table><tr><th>ETF</th><th>策略判断</th><th>建议配比</th></tr>${a.rows.map(r=>`<tr><td>${esc(r.name)} ${esc(r.code)}</td><td>${esc(r.action)}</td><td><b>${r.percent.toFixed(1)}%</b></td></tr>`).join('')}<tr><td>现金</td><td>等待更好的买点</td><td><b>${a.cash.toFixed(1)}%</b></td></tr></table><details><summary>查看配比理由</summary>${a.rows.map(r=>`<p><b>${esc(r.name)}：</b>${esc(r.reason)}</p>`).join('')}<p>${esc(a.rule)}</p></details><p class="muted">按当前买点分配的试行规则，尚未回测验证最优；0%表示暂不配置新资金，已有持仓的减仓、退出请看今日提醒。改变策略年限后重新计算，历史保留原配比。</p>`;
}
function table(r){return `<h3>相关性计算结果</h3><p>${esc(r.start)}—${esc(r.end)} · ${esc(r.count)}个共同收益样本</p><div style="overflow:auto"><table><tr><th>ETF</th>${r.assets.map(a=>`<th>${esc(a.name)}<br>${esc(a.code)}</th>`).join('')}</tr>${r.assets.map((a,i)=>`<tr><th>${esc(a.name)}</th>${r.matrix[i].map(v=>`<td>${v===null?'无法计算（无波动）':v.toFixed(2)}</td>`).join('')}</tr>`).join('')}</table></div><p class="muted">越接近1越容易同涨同跌，接近0表示同步程度低，接近−1表示容易反向变化。</p>${recommendations(r)}${allocationTable(r.allocation)}`;}
function render(){el('correlationHistory').innerHTML=history.slice().reverse().map(r=>`<article style="margin-top:18px"><div class="journal-heading"><h3>${esc(new Date(r.savedAt).toLocaleString('zh-CN'))}</h3><button type="button" class="btn gray" data-corr-delete="${esc(r.id)}">删除</button></div><details><summary>${esc(r.assets.map(a=>a.name).join(' / '))} · ${esc(r.start)}—${esc(r.end)}</summary>${table(r)}</details></article>`).join('')||'<p class="muted">暂无计算历史。</p>';el('correlationHistory').querySelectorAll('[data-corr-delete]').forEach(b=>b.onclick=()=>{try{const next=history.filter(r=>r.id!==b.dataset.corrDelete);localStorage.setItem(key,JSON.stringify(next));history=next;render();}catch(e){el('correlationStatus').textContent='删除失败：浏览器存储不可用。';}});}
el('correlationRecommend').onchange=()=>{const enabled=el('correlationRecommend').checked;el('correlationCountField').hidden=!enabled;el('correlationCount').disabled=!enabled;el('correlationCount').required=enabled;el('correlationThreshold').disabled=!enabled;el('correlationThreshold').required=enabled;};
el('correlationRecommend').onchange();
form.addEventListener('submit',e=>{e.preventDefault();el('correlationResult').innerHTML='';try{const codes=[...el('correlationAssets').querySelectorAll('input:checked')].map(i=>i.value),r=calculate(assets.filter(a=>codes.includes(a.code)),Number(el('correlationWindow').value));const raw=window.STRATEGY_SUMMARIES||[],summaries=window.summaryWithValuationYears?raw.map(s=>window.summaryWithValuationYears(s,window.selectedValuationYears())):raw;if(el('correlationRecommend').checked)r.recommendations=recommend(r,Number(el('correlationCount').value),el('correlationThreshold').value.trim()===''?NaN:Number(el('correlationThreshold').value));const chosen=r.recommendations?.group?.length?r.recommendations.group.map(g=>assets.find(a=>a.code===g.code)):assets.filter(a=>codes.includes(a.code));r.allocation=allocation(chosen,summaries);r.allocation.scope=r.recommendations?.group?.length?'推荐轮动组合':'所选ETF';el('correlationResult').innerHTML=table(r);if(!valid)throw Error('计算完成，但原历史无法读取，未保存；请先导出备份。');const record={...r,id:crypto.randomUUID(),savedAt:new Date().toISOString()},next=[...history,record];try{localStorage.setItem(key,JSON.stringify(next));}catch(e){throw Error('计算完成，但浏览器存储不可用，历史未保存。');}history=next;render();el('correlationStatus').textContent='计算完成，已保存到历史。';}catch(e){el('correlationStatus').textContent=e.message;}});
el('correlationExport').onclick=()=>{try{const raw=localStorage.getItem(key)||'[]',url=URL.createObjectURL(new Blob([raw],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='相关性计算历史.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){el('correlationStatus').textContent='导出失败：无法读取浏览器存储。';}};
render();
})();
