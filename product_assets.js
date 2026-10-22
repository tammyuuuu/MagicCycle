/* Asset identity and product terms. No names, prices or public quotas duplicated here. */
(function(){
 const registry=window.PRODUCT_ASSETS,assets=registry.assets;
 const dateOK=d=>typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d))&&new Date(d).toISOString().slice(0,10)===d;
 function mapping(code,p={}){const known=registry.products[code],own=p.productMappings?.[code];return known?.verified?known:own?.verified&&own.currency==='CNY'&&assets[own.asset]&&/^https:\/\//.test(own.source||'')&&dateOK(own.date)?own:null;}
 const assetOf=(code,p)=>mapping(code,p)?.asset||'unmapped-'+code;
 function weights(strategy){const out={};for(const [code,w] of Object.entries(strategy.weights)){const asset=assetOf(code);out[asset]=(out[asset]||0)+w;}return out;}
 function selected(asset,p={}){return p.productChoices?.[asset]||assets[asset]?.default_code;}
 function catalog(D,snapshot,p={}){
  const out=Object.fromEntries(Object.entries(D.funds).map(([c,f])=>[c,{...f,nav:f.nav.map(n=>[...n])}]));
  for(const row of snapshot?.rows||[])if(row.kind==='us'&&!out[row.code])out[row.code]={name:row.name,nav:dateOK(row.nav_date)&&Number.isFinite(row.unit_nav)&&row.unit_nav>0?[[row.nav_date,row.unit_nav]]:[]};
  for(const [code,f] of Object.entries(p.productData||{})){
   out[code]||={name:f.name||code,nav:[]};const points=new Map(out[code].nav);
   for(const point of f.nav||[])if(dateOK(point[0])&&Number.isFinite(point[1])&&point[1]>0)points.set(point[0],point[1]);
   out[code]={...out[code],nav:[...points].sort(([a],[b])=>a.localeCompare(b))};
  }
  return out;
 }
 function candidates(asset,D,snapshot,p={}){
  const codes=new Set([assets[asset]?.default_code,selected(asset,p)]);
  for(const [code] of Object.entries({...registry.products,...p.productMappings}))if(assetOf(code,p)===asset)codes.add(code);
  for(const row of snapshot?.rows||[])if(row.kind==='us'&&row.index===assets[asset]?.monitor_index)codes.add(row.code);
  return [...codes].filter(Boolean);
 }
 function terms(code,p,D,snapshot,day){
  const row=snapshot?.rows?.find(r=>r.code===code),base=D.trading_conditions?.[code],own=p.productTerms?.[code];
  const source=own?.date===day&&own.verified&&own.evidence?.trim()?own:null;
  const channel=source?.channel||'direct',publicCurrent=row?.quota?.source_date===day&&snapshot?.updated_at?.slice(0,10)===day;
  const publicLimit=publicCurrent?window.PurchaseMonitorPolicy?.quota(row.quota[channel==='retail'?'retail_limit':'direct_limit']):null;
  const parse=window.PurchaseMonitorPolicy.quota;
  const ownLimit=source?parse(source.limit):null,baseLimit=base?.as_of===day&&base.limit?parse(base.limit):null;
  const limits=[publicLimit,ownLimit,baseLimit].filter(n=>n!=null&&n>=0),limit=limits.length?Math.min(...limits):null;
  const fee=source?.buy_pct??(base?.as_of===day?base.buy_pct:null),minimum=source?.minimum??base?.minimum;
  const status=source?.status||(base?.as_of===day?base.status:row?.nav_date===day?row.nav_purchase_status:null);
  let reason='';if(!Number.isFinite(fee)||fee<0||fee>100)reason='申购手续费待核实（年费不作为申购费）';else if(!Number.isFinite(minimum)||minimum<=0)reason='最低申购金额待核实';else if(limit==null)reason='当日渠道额度待核实';else if(!source&&row&&!base)reason='个人渠道当日申购状态待核实';else if(!['开放申购','限大额','限制大额申购'].includes(status))reason='申购暂停或状态待核实';
  return {code,row,channel,buy_pct:fee,minimum,limit,status:status||'待核实',as_of:source?.date||base?.as_of||row?.quota?.source_date,redeem_tiers:base?.redeem_tiers,ready:!reason,reason,source};
 }
 window.ProductAssets={assets,mapping,assetOf,weights,selected,catalog,candidates,terms,dateOK};
})();
