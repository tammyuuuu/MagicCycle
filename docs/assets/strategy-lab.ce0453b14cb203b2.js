/* Presentation only. Source runs and research archives are never mutated. */
(function(){
 const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pct=n=>(n*100).toFixed(2)+'%',money=n=>'¥'+n.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
 const {ids,names,label}=window.StrategyLabels;
 const colors=['#345a8b','#207f78','#7955a1','#aa7b20','#b15e35','#a34364','#4b6479','#55833d','#9b624a','#705a98','#1d7270','#b55370'];
 let data,segments=[],current=[],dates=[],hidden=new Set(),dateIndex=0,period='trailing5',initialized=false;
 let runCache=new WeakMap(),segmentCache=new Map(),plotCache=new Map();
 function visibleSeries(){const visible=current.filter(s=>!hidden.has(s.id));return visible.length?visible:current.slice(0,1);}
 function validRun(run,segment){
  if(run&&runCache.has(run))return runCache.get(run);
  if(!run||run.mode!=='rebalance'||run.data_type!==segment.data_type||!Number.isFinite(run.cagr)||!Number.isFinite(run.mdd)||!Number.isFinite(run.fees)||!Array.isArray(run.curve)||run.curve.length<2)return null;
  const curve=run.curve;
  if(curve.some((p,i)=>!Array.isArray(p)||!/^\d{4}-\d{2}-\d{2}$/.test(p[0])||!Number.isFinite(Date.parse(p[0]))||new Date(p[0]).toISOString().slice(0,10)!==p[0]||!Number.isFinite(p[1])||p[1]<=0||(i&&p[0]<=curve[i-1][0])))return null;
  if(curve[0][0]!==run.first||curve.at(-1)[0]!==run.last)return null;
  let peak=1,mdd=0;const points=curve.map(p=>{const nav=p[1]/curve[0][1];peak=Math.max(peak,nav);const dd=nav/peak-1;mdd=Math.min(mdd,dd);return [p[0],nav,dd];});
  const years=(Date.parse(run.last)-Date.parse(run.first))/86400000/365.25,cagr=Math.pow(points.at(-1)[1],1/years)-1;
  // Metadata and daily series must describe the same full interval. No synthetic curves.
  if(!(years>0)||Math.abs(cagr-run.cagr)>1e-6||Math.abs(mdd-run.mdd)>1e-6)return null;
  const valid={run,points,signature:points.map(p=>p[0]).join(',')};runCache.set(run,valid);return valid;
 }
 function segmentRuns(segment){
  if(segmentCache.has(segment.id))return segmentCache.get(segment.id);
  const candidates=ids.map(id=>{const strategy=data.research.strategies.find(s=>s.id===id),run=strategy?.continuous_run||strategy?.runs?.find(r=>r.segment==='real_2020'&&r.mode==='rebalance'),valid=validRun(run,segment);return valid?{...valid,strategy,id,color:colors[ids.indexOf(id)]}:null;}).filter(Boolean);
  if(!candidates.length)return [];
  const end=data.research.history_end||candidates.map(s=>s.run.last).sort()[0],cut=new Date(end+'T00:00:00Z');cut.setUTCFullYear(cut.getUTCFullYear()-segment.years);
  const boundary=cut.toISOString().slice(0,10),reference=candidates.find(s=>s.id==='L5')||candidates[0],calendar=reference.points.map(p=>p[0]).filter(d=>d<=end);
  const anchor=calendar.filter(d=>d<=boundary).at(-1);if(!anchor)return [];
  const selected=calendar.filter(d=>d>=anchor),years=(Date.parse(end)-Date.parse(anchor))/86400000/365.25;
  const result=candidates.filter(s=>{const available=new Set(s.points.map(p=>p[0]));return s.run.first<=anchor&&s.run.last>=end&&selected.every(date=>available.has(date));}).map(s=>{
   const map=new Map(s.points.map(p=>[p[0],p[1]])),base=map.get(anchor);let peak=1,mdd=0;
   const points=selected.map(date=>{const nav=map.get(date)/base;peak=Math.max(peak,nav);const dd=nav/peak-1;mdd=Math.min(mdd,dd);return [date,nav,dd];});
   const fees=s.run.trade_fees?.filter(t=>t[0]>anchor&&t[0]<=end).reduce((n,t)=>n+t[1],0);
   return {...s,points,run:{...s.run,first:anchor,last:end,cagr:points.at(-1)[1]**(1/years)-1,mdd,fees:fees??null},signature:selected.join(',')};
  });
  segmentCache.set(segment.id,result);return result;
 }
 function render(){
  const segment=segments.find(s=>s.id===period);current=segment?segmentRuns(segment):[];dates=current[0]?.points.map(p=>p[0])||[];dateIndex=dates.length-1;
  $('compareSegment').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.period===period)));
  $('labRangeNote').textContent=current.length?`${dates[0]} — ${dates.at(-1)} · 连续账户截取，不重置持仓；复合年化、区间内最大回撤，均含模拟交易费。`:'历史不足，暂无有效回测';
  const cardOrder=(a,b)=>{
   const ar=current.find(x=>x.id===a.id)?.run,br=current.find(x=>x.id===b.id)?.run;
   if(!ar||!br)return Number(!!br)-Number(!!ar)||ids.indexOf(a.id)-ids.indexOf(b.id);
   return (a.id==='L5'?-1:b.id==='L5'?1:0)||br.cagr-ar.cagr||Math.abs(ar.mdd)-Math.abs(br.mdd)||ids.indexOf(a.id)-ids.indexOf(b.id);
  };
  const cards=scenario=>ids.map(id=>data.research.strategies.find(s=>s.id===id)).filter(s=>s?.scenario===scenario).sort(cardOrder).map(s=>{
   const entry=current.find(x=>x.id===s.id),r=entry?.run,weights=r?.actual_weights||s.weights;
   const allocation=s.dynamic?'无许可：债券50%＋黄金50%；仅500许可：债券30%＋黄金50%＋500 20%；300许可：债券10%＋黄金50%＋300 40%。'+(s.id==='L6'?'双许可时改为500 13.33%＋300 26.67%，债券10%＋黄金50%。':'双许可仍优先沪深300。'):Object.entries(weights).map(([c,w])=>`${esc(data.funds[c]?.name||data.research.asset_names?.[c]||c)} ${esc(c)} · ${pct(w)}`).join('<br>');
   return `<details class="strategy" data-strategy="${esc(s.id)}"><summary><span class="lab-strategy-name"><strong>${esc(s.id)}</strong><small>${esc(names[s.id])}</small></span>${r?`<span>${pct(r.cagr)}<small>年化收益</small></span><span>${pct(Math.abs(r.mdd))}<small>最大回撤</small></span>`:'<span class="lab-missing">历史不足</span>'}</summary><p class="fine">${allocation}</p>${r?`<p class="fine">${esc(r.first)} — ${esc(r.last)}${r.fees!=null?'<br>区间模拟交易费 '+money(r.fees):''} · 连续账户，月度2%带</p>`:'<p class="fine">缺少足够历史，未加入曲线。</p>'}</details>`;
  }).join('');
  $('normalStrategies').innerHTML=cards('nasdaq_available');$('limitedStrategies').innerHTML=cards('nasdaq_unavailable');
  $('labLegend').innerHTML=ids.map((id,i)=>`<button type="button" data-lab-toggle="${id}" style="--series:${colors[i]}" aria-controls="researchCurve researchDrawdown" ${current.some(s=>s.id===id)?'':'disabled'}><i></i>${esc(label(id))}</button>`).join('');
  $('labLegend').querySelectorAll('button').forEach(b=>b.onclick=()=>{
   const id=b.dataset.labToggle,visible=visibleSeries();if(!current.some(s=>s.id===id))return;
   if(visible.some(s=>s.id===id)){if(visible.length===1)return;hidden.add(id);}else hidden.delete(id);
   drawCharts();readout(dateIndex);
  });
  drawCharts();
  $('labDateSlider').max=Math.max(0,dates.length-1);$('labDateSlider').disabled=!dates.length;$('labDateLabel').hidden=!dates.length;
  syncVisibility();readout(dateIndex);
 }
 function drawCharts(){
  const key=period+':'+visibleSeries().map(s=>s.id).join(',');
  if(!plotCache.has(key)){if(plotCache.size>=4)plotCache.delete(plotCache.keys().next().value);plotCache.set(key,[plot(1,'所选策略累计净值'),plot(2,'所选策略日度回撤')]);}
  const markup=plotCache.get(key);$('researchCurve').innerHTML=markup[0];$('researchDrawdown').innerHTML=markup[1];
  for(const id of ['researchCurve','researchDrawdown'])bindPointer($(id));syncVisibility();
 }
 function plot(column,label){
  if(!current.length)return '<div class="empty">暂无有效回测</div>';
  const plotted=visibleSeries();let min=Infinity,max=-Infinity;for(const series of plotted)for(const point of series.points){min=Math.min(min,point[column]);max=Math.max(max,point[column]);}
  const pad=(max-min)*.08||.01,lo=min-pad,hi=max+pad;
  const first=Date.parse(dates[0]),last=Date.parse(dates.at(-1)),xs=new Map(dates.map(d=>[d,70+(Date.parse(d)-first)/(last-first)*900])),x=d=>xs.get(d),y=v=>345-(v-lo)/(hi-lo)*320;
  const axes=[0,1,2,3].map(k=>{const value=lo+(hi-lo)*k/3,yy=y(value);return `<line x1="70" x2="970" y1="${yy}" y2="${yy}" stroke="#e4e5de"/><text x="62" y="${yy+7}" text-anchor="end" fill="#78818a" font-size="23">${column===2?(value*100).toFixed(0)+'%':value.toFixed(1)}</text>`;}).join('');
  return `<svg class="lab-plot" viewBox="0 0 1000 380" role="img" aria-label="${label}" tabindex="0"><title>${label}；左右方向键查看日期</title>${axes}${plotted.map(s=>`<path data-lab-series="${s.id}" d="${s.points.map((p,i)=>`${i?'L':'M'}${x(p[0]).toFixed(3)},${y(p[column]).toFixed(3)}`).join(' ')}" fill="none" stroke="${s.color}" stroke-width="2" ${s.id.startsWith('L')?'stroke-dasharray="6 3"':''} vector-effect="non-scaling-stroke"/>`).join('')}<line class="lab-cursor" y1="15" y2="350" stroke="#8994a5" stroke-dasharray="4 4"/></svg><div class="chart-axis"><span>${dates[0]}</span><span>${dates.at(-1)}</span></div>`;
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
  data=payload;segments=data.research.segments;period='trailing5';hidden=new Set();runCache=new WeakMap();segmentCache=new Map();plotCache=new Map();
  $('compareSegment').innerHTML=segments.map(s=>`<button type="button" data-period="${esc(s.id)}" aria-pressed="${s.id===period}">${esc(s.label)}</button>`).join('');
  $('compareSegment').querySelectorAll('button').forEach(b=>b.onclick=()=>{period=b.dataset.period;render();});$('labDateSlider').oninput=e=>readout(Number(e.target.value));render();initialized=true;
 }
 window.StrategyLab={init,render,get initialized(){return initialized;},get ready(){return initialized&&current.length>0;},get state(){return {segment:period,dates:[...dates],series:current.map(s=>({id:s.id,color:s.color,cagr:s.run.cagr,mdd:s.run.mdd,points:s.points.map(p=>[...p])})),hidden:[...hidden],dateIndex};}};
})();
