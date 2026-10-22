const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={window:{},document:{getElementById:()=>null}};vm.createContext(context);vm.runInContext(fs.readFileSync('archive/legacy_ui/correlation_tools.js','utf8'),context);
const calc=context.window.CorrelationLogic.calculate;
function asset(code, direction=1,flat=false){let p=100;const prices=[];for(let i=0;i<251;i++){if(i)p*=1+(flat?0:direction*((i%7)-3)*.001);prices.push([String(i).padStart(4,'0'),p]);}return {code,name:code,prices};}
let r=calc([asset('a'),asset('b'),asset('c',-1)],60);assert.equal(r.count,60);assert(Math.abs(r.matrix[0][1]-1)<1e-10);assert(Math.abs(r.matrix[0][2]+1)<1e-10);
assert.equal(calc([asset('a'),asset('flat',1,true)],120).matrix[0][1],null);
assert.throws(()=>calc([asset('a')],60));
const missing=asset('b');missing.prices.splice(200,1);assert.throws(()=>calc([asset('a'),missing],250));assert.equal(calc([asset('a'),missing],60).count,60);
console.log('Correlation alignment, positive/negative correlation, flat series and insufficient history: OK');
const recommend=context.window.CorrelationLogic.recommend;
let rec=recommend(r,2);
assert.equal(rec.group.length,2);assert(rec.group.some(a=>a.code==='c'));
assert(rec.reason.includes('一组轮动候选'));
assert.equal(recommend(calc([asset('a'),asset('b')],60),2).group.length,0);
assert.equal(recommend(calc([asset('a'),asset('flat',1,true)],60),2).group.length,0);
const groupCase={assets:[{code:'a',name:'A'},{code:'b',name:'B'},{code:'c',name:'C'}],matrix:[[1,.1,.9],[.1,1,.2],[.9,.2,1]]};
assert.deepEqual(Array.from(recommend(groupCase,2).group,a=>a.code),['a','b']);
const tripleCase={...groupCase,matrix:[[1,.1,.3],[.1,1,.2],[.3,.2,1]]};
assert.equal(recommend(tripleCase,3).group.length,3);
assert.equal(recommend({...groupCase,assets:groupCase.assets.slice(1),matrix:[[1,.2],[.2,1]]},2).group.length,2);
// Exercise submit, persistence and history reload with minimal DOM surfaces.
function ui(saved='[]'){
 const nodes={},data=[asset('a'),asset('c',-1)],storage={investment_correlations_v1:saved};
 for(const id of ['correlationForm','correlationAssets','correlationWindow','correlationCount','correlationCountField','correlationThreshold','correlationRecommend','correlationResult','correlationStatus','correlationHistory','correlationExport'])nodes[id]={innerHTML:'',textContent:'',value:'60',addEventListener(type,fn){this[type]=fn;},querySelectorAll(sel){return sel==='input:checked'?data.map(a=>({value:a.code})):[];}};
 nodes.correlationThreshold.value='0.5';nodes.correlationCount.value='2';nodes.correlationRecommend.checked=true;
 const ctx={window:{CORRELATION_PRICES:data,STRATEGY_SUMMARIES:[]},document:{getElementById:id=>nodes[id]},localStorage:{getItem:k=>storage[k]||null,setItem:(k,v)=>storage[k]=v},crypto:{randomUUID:()=>String(Object.keys(storage).length)+Math.random()}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('archive/legacy_ui/correlation_tools.js','utf8'),ctx);nodes.correlationCount.value='2';return {nodes,storage};
}
const page=ui();page.nodes.correlationForm.submit({preventDefault(){}});
const saved=JSON.parse(page.storage.investment_correlations_v1);assert.equal(saved.length,1);assert.equal(saved[0].recommendations.group.length,2);assert(page.nodes.correlationResult.innerHTML.includes('轮动推荐'));
assert(ui(page.storage.investment_correlations_v1).nodes.correlationHistory.innerHTML.includes('轮动推荐'));
const broken=ui('{broken');broken.nodes.correlationForm.submit({preventDefault(){}});assert.equal(broken.storage.investment_correlations_v1,'{broken');
console.log('Selected ETF group recommendation, pairwise correlation, exclusions, persistence and history reload: OK');

assert.throws(()=>recommend(r));assert.throws(()=>recommend(r,4));assert.equal(recommend(r,3).group.length,0);assert.equal(recommend(r,3).count,3);
console.log('Explicit rotation count, exact group size and no automatic reduction: OK');

const correlationOnly=ui();correlationOnly.nodes.correlationRecommend.checked=false;correlationOnly.nodes.correlationCount.value='';correlationOnly.nodes.correlationForm.submit({preventDefault(){}});
assert.equal(JSON.parse(correlationOnly.storage.investment_correlations_v1)[0].recommendations,undefined);
assert(correlationOnly.nodes.correlationResult.innerHTML.includes('相关性计算结果'));
assert(!correlationOnly.nodes.correlationResult.innerHTML.includes('查看轮动推荐'));
assert(page.nodes.correlationResult.innerHTML.indexOf('相关性计算结果')<page.nodes.correlationResult.innerHTML.indexOf('查看轮动推荐'));
console.log('Correlation result first and optional recommendations: OK');

assert.equal(recommend(groupCase,3,.5).group.length,0);
assert.equal(recommend(groupCase,3,.9).group.length,3);
assert.equal(recommend(groupCase,3,.9).threshold,.9);
for(const t of [NaN,Infinity,-1.01,1.01])assert.throws(()=>recommend(groupCase,2,t));
assert.equal(saved[0].recommendations.threshold,.5);
const adjusted=ui();adjusted.nodes.correlationThreshold.value='0.75';adjusted.nodes.correlationForm.submit({preventDefault(){}});
assert.equal(JSON.parse(adjusted.storage.investment_correlations_v1)[0].recommendations.threshold,.75);
assert(ui(adjusted.storage.investment_correlations_v1).nodes.correlationHistory.innerHTML.includes('0.75'));
const empty=ui();empty.nodes.correlationThreshold.value='';empty.nodes.correlationForm.submit({preventDefault(){}});
assert.equal(empty.storage.investment_correlations_v1,'[]');
console.log('Adjustable threshold, bounds, saved settings and history display: OK');

const allocate=context.window.CorrelationLogic.allocation;
const selected=[asset('a'),asset('b'),asset('c')];
const signals=[{symbol:'a',date:'0250',status:'buy_more',metrics:{price:100},reason:'低估且回撤较大'},{symbol:'b',date:'0250',status:'buy',metrics:{price:100},reason:'低估且回撤中等'},{symbol:'c',date:'0250',status:'watch',metrics:{price:100},reason:'先观察'}];
const weights=allocate(selected,signals);
assert.deepEqual(Array.from(weights.rows,r=>r.percent),[33.3,16.6,0]);
assert.equal(weights.cash,50.1);
assert.equal(Math.round((weights.cash+weights.rows.reduce((n,r)=>n+r.percent,0))*10),1000);
assert.equal(allocate(selected,signals.map(s=>({...s,status:'reduce'}))).cash,100);
assert.equal(allocate(selected,[]).cash,100);
assert.equal(allocate(selected,signals.map(s=>({...s,date:'0249'}))).cash,100);
assert.equal(allocate(selected,signals.map(s=>({...s,details:{insufficient_history:true}}))).cash,100);
assert.equal(allocate(selected,signals.map(s=>({...s,risk_level:'high'}))).cash,100);
assert.equal(saved[0].allocation.cash,100);
assert(ui(page.storage.investment_correlations_v1).nodes.correlationHistory.innerHTML.includes('当前建议配比'));
assert(correlationOnly.nodes.correlationResult.innerHTML.includes('当前建议配比'));
assert(page.nodes.correlationResult.innerHTML.indexOf('相关性计算结果')<page.nodes.correlationResult.innerHTML.indexOf('当前建议配比'));
console.log('Signal-based allocations, cash total, missing/stale data and history snapshots: OK');
