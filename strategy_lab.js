/* Presentation only. Source runs and research archives are never mutated. */
(function(){
 const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pct=n=>(n*100).toFixed(2)+'%',money=n=>'¥'+n.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
 const {ids,names,label}=window.StrategyLabels;
 const colors=['#345a8b','#207f78','#7955a1','#aa7b20','#b15e35','#a34364','#4b6479','#55833d','#9b624a','#705a98'];
 let data,segments=[],current=[],dates=[],hidden=new Set(),dateIndex=0;
 function visibleSeries(){const visible=current.filter(s=>!hidden.has(s.id));return visible.length?visible:current.slice(0,1);}
 function validRun(run,segment){
  if(!run||run.mode!=='rebalance'||run.data_type!==segment.data_type||!Number.isFinite(run.cagr)||!Number.isFinite(run.mdd)||!Number.isFinite(run.fees)||!Array.isArray(run.curve)||run.curve.length<2)return null;
  const curve=run.curve;
  if(curve.some((p,i)=>!Array.isArray(p)||!/^\d{4}-\d{2}-\d{2}$/.test(p[0])||!Number.isFinite(Date.parse(p[0]))||new Date(p[0]).toISOString().slice(0,10)!==p[0]||!Number.isFinite(p[1])||p[1]<=0||(i&&p[0]<=curve[i-1][0])))return null;
  if(curve[0][0]!==run.first||curve.at(-1)[0]!==run.last)return null;
  let peak=1,mdd=0;const points=curve.map(p=>{const nav=p[1]/curve[0][1];peak=Math.max(peak,nav);const dd=nav/peak-1;mdd=Math.min(mdd,dd);return [p[0],nav,dd];});
  const years=(Date.parse(run.last)-Date.parse(run.first))/86400000/365.25,cagr=Math.pow(points.at(-1)[1],1/years)-1;
  // Metadata and daily series must describe the same full interval. No synthetic curves.
  if(!(years>0)||Math.abs(cagr-run.cagr)>1e-6||Math.abs(mdd-run.mdd)>1e-6)return null;
  return {run,points,signature:points.map(p=>p[0]).join(',')};
 }
 function segmentRuns(segment){
  const candidates=ids.map(id=>{const strategy=data.research.strategies.find(s=>s.id===id),valid=validRun(strategy?.runs.find(r=>r.segment===segment.id&&r.mode==='rebalance'),segment);return valid?{...valid,strategy,id,color:colors[ids.indexOf(id)]}:null;}).filter(Boolean);
  // Require identical full calendars; do not trim metrics to a different period or fill gaps.
  const counts=new Map();for(const x of candidates)counts.set(x.signature,(counts.get(x.signature)||0)+1);
  const signature=[...counts].sort((a,b)=>b[1]-a[1])[0]?.[0];
  return candidates.filter(x=>x.signature===signature);
 }
 function render(){
  const segment=segments.find(s=>s.id===$('compareSegment').value);current=segment?segmentRuns(segment):[];dates=current[0]?.points.map(p=>p[0])||[];dateIndex=dates.length-1;
  $('labRangeNote').textContent=current.length?`${dates[0]} — ${dates.at(-1)} · ${segment.data_type==='index_proxy'?'指数代理':'真实基金'}${segment.id==='historical_2023'?' · 非严格样本外':''} · 月度再平衡，2%带；指标与曲线均含交易费。`:'暂无有效回测';
  const cardOrder=(a,b)=>{
   const ar=current.find(x=>x.id===a.id)?.run,br=current.find(x=>x.id===b.id)?.run;
   if(!ar||!br)return Number(!!br)-Number(!!ar)||ids.indexOf(a.id)-ids.indexOf(b.id);
   return br.cagr-ar.cagr||Math.abs(ar.mdd)-Math.abs(br.mdd)||ids.indexOf(a.id)-ids.indexOf(b.id);
  };
  const cards=scenario=>ids.map(id=>data.research.strategies.find(s=>s.id===id)).filter(s=>s?.scenario===scenario).sort(cardOrder).map(s=>{
   const entry=current.find(x=>x.id===s.id),r=entry?.run,weights=r?.actual_weights||s.weights;
   return `<details class="strategy" data-strategy="${esc(s.id)}"><summary><span class="lab-strategy-name"><strong>${esc(s.id)}</strong><small>${esc(names[s.id])}</small></span>${r?`<span>${pct(r.cagr)}<small>年化收益</small></span><span>${pct(r.mdd)}<small>最大回撤</small></span>`:'<span class="lab-missing">暂无有效数据</span>'}</summary><p class="fine">${Object.entries(weights).map(([c,w])=>`${esc(data.funds[c]?.name||data.research.asset_names?.[c]||c)} ${esc(c)} · ${pct(w)}`).join('<br>')}</p>${r?`<p class="fine">${esc(r.first)} — ${esc(r.last)}<br>累计交易费 ${money(r.fees)} · 月度再平衡，2%带${Object.keys(r.substitutions||{}).length?'<br>代理替换：'+esc(Object.entries(r.substitutions).map(([a,b])=>a+' → '+b).join('；')):''}</p>`:'<p class="fine">缺少有效结果或共同日历，未加入两张曲线。</p>'}</details>`;
  }).join('');
  $('normalStrategies').innerHTML=cards('nasdaq_available');$('limitedStrategies').innerHTML=cards('nasdaq_unavailable');
  $('labLegend').innerHTML=ids.map((id,i)=>`<button type="button" data-lab-toggle="${id}" style="--series:${colors[i]}" aria-controls="researchCurve researchDrawdown" ${current.some(s=>s.id===id)?'':'disabled'}><i></i>${esc(label(id))}</button>`).join('');
  $('labLegend').querySelectorAll('button').forEach(b=>b.onclick=()=>{
   const id=b.dataset.labToggle,visible=visibleSeries();if(!current.some(s=>s.id===id))return;
   if(visible.some(s=>s.id===id)){if(visible.length===1)return;hidden.add(id);}else hidden.delete(id);
   syncVisibility();readout(dateIndex);
  });
  $('researchCurve').innerHTML=plot(1,'所有有效策略累计净值');$('researchDrawdown').innerHTML=plot(2,'所有有效策略日度回撤');
  $('labDateSlider').max=Math.max(0,dates.length-1);$('labDateSlider').disabled=!dates.length;$('labDateLabel').hidden=!dates.length;
  for(const id of ['researchCurve','researchDrawdown'])bindPointer($(id));
  syncVisibility();readout(dateIndex);
 }
 function plot(column,label){
  if(!current.length)return '<div class="empty">暂无有效回测</div>';
  let min=Infinity,max=-Infinity;for(const series of current)for(const point of series.points){min=Math.min(min,point[column]);max=Math.max(max,point[column]);}
  const pad=(max-min)*.08||.01,lo=min-pad,hi=max+pad;
  const first=Date.parse(dates[0]),last=Date.parse(dates.at(-1)),x=d=>70+(Date.parse(d)-first)/(last-first)*900,y=v=>345-(v-lo)/(hi-lo)*320;
  const axes=[0,1,2,3].map(k=>{const value=lo+(hi-lo)*k/3,yy=y(value);return `<line x1="70" x2="970" y1="${yy}" y2="${yy}" stroke="#e4e5de"/><text x="62" y="${yy+7}" text-anchor="end" fill="#78818a" font-size="23">${column===2?(value*100).toFixed(0)+'%':value.toFixed(1)}</text>`;}).join('');
  return `<svg class="lab-plot" viewBox="0 0 1000 380" role="img" aria-label="${label}" tabindex="0"><title>${label}；左右方向键查看日期</title>${axes}${current.map(s=>`<path data-lab-series="${s.id}" d="${s.points.map((p,i)=>`${i?'L':'M'}${x(p[0]).toFixed(3)},${y(p[column]).toFixed(3)}`).join(' ')}" fill="none" stroke="${s.color}" stroke-width="2" ${s.id.startsWith('L')?'stroke-dasharray="6 3"':''} vector-effect="non-scaling-stroke"/>`).join('')}<line class="lab-cursor" y1="15" y2="350" stroke="#8994a5" stroke-dasharray="4 4"/></svg><div class="chart-axis"><span>${dates[0]}</span><span>${dates.at(-1)}</span></div>`;
 }
 function syncVisibility(){
  const visible=new Set(visibleSeries().map(s=>s.id));
  document.querySelectorAll('[data-lab-series]').forEach(el=>el.style.display=visible.has(el.dataset.labSeries)?'':'none');
  $('labLegend').querySelectorAll('button').forEach(b=>{const shown=visible.has(b.dataset.labToggle);b.setAttribute('aria-pressed',String(shown));b.title=b.disabled?'暂无有效数据':shown&&visible.size===1?'至少保留一条可见曲线':shown?'点击隐藏两张图中的该策略':'点击显示两张图中的该策略';});
 }
 function readout(index){
  if(!dates.length){$('labReadout').textContent='暂无有效回测';return;}
  dateIndex=Math.max(0,Math.min(index,dates.length-1));$('labDateSlider').value=dateIndex;
  const visible=visibleSeries();
  $('labReadout').innerHTML=`<b>${dates[dateIndex]}</b><small>策略 · 净值 / 回撤</small><div class="lab-values">${visible.map(s=>`<span style="--series:${s.color}"><b>${esc(label(s.id))}</b> ${s.points[dateIndex][1].toFixed(4)} / ${pct(s.points[dateIndex][2])}</span>`).join('')||'点击图例显示策略'}</div>`;
  const x=70+(Date.parse(dates[dateIndex])-Date.parse(dates[0]))/(Date.parse(dates.at(-1))-Date.parse(dates[0]))*900;
  document.querySelectorAll('.lab-cursor').forEach(el=>{el.setAttribute('x1',x);el.setAttribute('x2',x);});
 }
 function bindPointer(root){
  const svg=root.querySelector('svg');if(!svg)return;
  const inspect=e=>{const box=svg.getBoundingClientRect(),ratio=Math.max(0,Math.min(1,((e.clientX-box.left)/box.width*1000-70)/900)),time=Date.parse(dates[0])+ratio*(Date.parse(dates.at(-1))-Date.parse(dates[0]));let lo=0,hi=dates.length-1;while(lo<hi){const mid=Math.floor((lo+hi)/2);if(Date.parse(dates[mid])<time)lo=mid+1;else hi=mid;}if(lo&&time-Date.parse(dates[lo-1])<Date.parse(dates[lo])-time)lo--;readout(lo);};
  svg.onpointerdown=e=>{svg.setPointerCapture(e.pointerId);inspect(e);};svg.onpointermove=inspect;
  svg.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();readout(dateIndex+(e.key==='ArrowLeft'?-1:1));}};
 }
 function init(payload){
  data=payload;segments=data.research.segments.filter(s=>segmentRuns(s).length);hidden=new Set();
  $('compareSegment').innerHTML=segments.map(s=>`<option value="${esc(s.id)}">${esc(s.label)}${s.data_type==='actual_fund'&&!s.label.includes('真实')?' · 真实基金':''}</option>`).join('');
  $('compareSegment').disabled=!segments.length;$('compareSegment').onchange=render;$('labDateSlider').oninput=e=>readout(Number(e.target.value));render();
 }
 window.StrategyLab={init,render,get state(){return {segment:$('compareSegment').value,dates:[...dates],series:current.map(s=>({id:s.id,color:s.color,cagr:s.run.cagr,mdd:s.run.mdd,points:s.points.map(p=>[...p])})),hidden:[...hidden],dateIndex};}};
})();
