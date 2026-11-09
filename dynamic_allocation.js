/* Frozen L5/L6 targets. Signal permission is the existing persistent strategy state. */
(function(){
 const assets={'510500':{name:'中证500',family:'csi500_'},'510300':{name:'沪深300',family:'csi300_'}};
 const validDate=date=>typeof date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(date)&&Number.isFinite(Date.parse(date))&&new Date(date).toISOString().slice(0,10)===date;
 function summaries(){return Array.isArray(window.TODAY_STRATEGY_SUMMARIES)&&window.TODAY_STRATEGY_SOURCE===window.STRATEGY_SUMMARIES?window.TODAY_STRATEGY_SUMMARIES:window.STRATEGY_SUMMARIES;}
 function freshness(signalDate,date,calendar=window.ASHARE_CALENDAR){
  if(!validDate(signalDate)||!validDate(date)||signalDate>date)return {ready:false,code:'invalid_date',reason:'信号日期缺失、无效或晚于当前日期'};
  const covered=calendar&&signalDate>=calendar.valid_from&&date<=calendar.valid_through;
  const closed=d=>[0,6].includes(new Date(d+'T00:00:00Z').getUTCDay())||(covered&&(calendar.closed_ranges||[]).some(([a,b])=>d>=a&&d<=b));
  if(covered&&closed(signalDate))return {ready:false,code:'invalid_date',reason:'信号日期不是A股交易日'};
  if(!covered&&(Date.parse(date)-Date.parse(signalDate))/86400000>7)return {ready:false,code:'calendar_outdated',reason:'暂不生成交易建议'};
  let missed=0;const cursor=new Date(signalDate+'T00:00:00Z');
  for(cursor.setUTCDate(cursor.getUTCDate()+1);cursor.toISOString().slice(0,10)<=date;cursor.setUTCDate(cursor.getUTCDate()+1))if(!closed(cursor.toISOString().slice(0,10)))missed++;
  // Source feeds can publish one session apart. Do not compare dates with other assets.
  return {ready:missed<=1,missedSessions:missed,calendarVerified:!!covered,code:missed>1?'stale':null,reason:missed>1?'暂不生成交易建议':'',date:signalDate};
 }
 function permission(s){
  const status=String(s.status||'').toLowerCase(),d=s.details||{};
  if(['exit','sell','closed','退出','卖出'].includes(status))return false;
  if(['buy','add','buy_more','hold','holding','买入','加仓','持有'].includes(status))return true;
  if(['watch','wait','observe','观察','等待'].includes(status))return d.strategy_position===1||d.strategy_position===true||['hold','holding','long','持有'].includes(d.strategy_state);
  return null;
 }
 function weights(id,p500,p300){
  let a=0,b=0;
  if(p300){if(id==='L6'&&p500){a=.4/3;b=.8/3;}else b=.4;}
  else if(p500)a=.2;
  return {'000015':.5-a-b,'008701':.5,'001214':a,'160706':b};
 }
 function resolve(strategy,list=summaries(),date=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())){
  if(!strategy.dynamic)return {ready:true,weights:strategy.weights};
  const found={};
  const diagnostics=[];
  for(const [symbol,asset] of Object.entries(assets)){
   const candidates=(Array.isArray(list)?list:[]).map(x=>x?.summary||x).filter(s=>String(s?.symbol||s?.code||'')===symbol).sort((a,b)=>String(b.date).localeCompare(String(a.date))),s=candidates[0];
   let issue=null;const d=s?.details||{},version=d.strategy_version||s?.strategy_version||d.strategy_presentation?.version,shownVersion=d.strategy_presentation?.version;
   const timing=s?freshness(s.date,date):null;
   if(!s)issue={code:'missing',reason:'许可缺失，今日提醒暂无正式摘要'};
   else if(typeof version!=='string'||!version.startsWith(asset.family)||(shownVersion&&shownVersion!==version)||(d.strategy_mode&&d.strategy_mode!=='broad_individual'))issue={code:'version',reason:'策略版本缺失或摘要元数据不一致'};
   else if(d.insufficient_history||d.data_warning)issue={code:'unavailable',reason:'暂不生成交易建议'};
   else if(!timing.ready)issue=timing;
   else if(permission(s)===null)issue={code:'state',reason:'正式策略状态无法识别'};
   diagnostics.push({symbol,name:asset.name,date:s?.date,version,status:s?.status,permission:issue?null:permission(s),...timing,ready:!issue,...(issue?{code:issue.code,reason:issue.reason}:{})});
   if(!issue)found[symbol]=s;
  }
  const failed=diagnostics.filter(d=>!d.ready);
  if(failed.length)return {ready:false,weights:strategy.weights,diagnostics,reason:failed.map(d=>d.name+'：'+d.reason+(d.date?'（'+d.date+'）':'')).join('；')+'。暂停计算新的申赎建议。'};
  const p500=permission(found['510500']),p300=permission(found['510300']);
  return {ready:true,weights:weights(strategy.id,p500,p300),p500,p300,
   signalDate:[found['510500'].date,found['510300'].date].sort()[0],
   diagnostics,source:'today_reminders',state:p500&&p300?'双许可':p300?'沪深300许可':p500?'中证500许可':'无股票许可'};
 }
 window.DynamicAllocation={weights,resolve,permission,freshness,summaries};
})();
