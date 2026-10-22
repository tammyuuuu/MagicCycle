/* Public fund identity lookup. Identity never implies strategy-asset equivalence. */
(function(){
 const source='https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx';
 function parse(payload,code){
  const row=payload?.Datas?.find(r=>String(r.CODE)===code&&r.CATEGORY===700),base=row?.FundBaseInfo;
  if(payload?.ErrCode!==0||!row||String(base?.FCODE)!==code||typeof row.NAME!=='string'||!row.NAME.trim()||/[<>]/.test(row.NAME))throw Error('未查到代码与名称一致的基金');
  const nav=Number(base.DWJZ),date=base.FSRQ,valid=window.ProductAssets.dateOK(date)&&date<=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())&&Number.isFinite(nav)&&nav>0;
  return {code,name:row.NAME.trim(),identityVerified:true,identitySource:source,identityDate:new Date().toISOString(),nav:valid?[[date,nav]]:[],publicInfo:{minimum:Number.isFinite(base.MINSG)&&base.MINSG>0?base.MINSG:null,status:base.ISBUY||null}};
 }
 function local(code,p){
  const f=window.WORKSPACE_DATA.funds[code],row=window.FUND_ACCESS_MONITOR?.rows?.find(r=>r.code===code),saved=p.productData?.[code];
  if(f)return {code,name:f.name,identityVerified:true,identitySource:'versioned workspace fund catalog',nav:[]};
  if(row?.name)return {code,name:row.name,identityVerified:true,identitySource:'purchase monitor catalog',nav:[]};
  if(saved?.identityVerified&&saved.identitySource===source&&saved.name)return {code,...saved};
  return null;
 }
 function lookup(code,p,refresh=false){
  if(!/^\d{6}$/.test(code))return Promise.reject(Error('请输入六位基金代码'));
  const known=local(code,p);if(known&&!refresh)return Promise.resolve(known);
  return new Promise((resolve,reject)=>{const callback='xingxunFund_'+Date.now()+'_'+Math.random().toString(36).slice(2),script=document.createElement('script');let timer;
   const clean=()=>{clearTimeout(timer);script.remove();delete window[callback];};
   window[callback]=payload=>{try{resolve(parse(payload,code));}catch(e){reject(e);}finally{clean();}};
   script.src=source+'?m=1&key='+code+'&callback='+callback;script.onerror=()=>{clean();reject(Error('基金名称暂无法核实，请联网重试'));};timer=setTimeout(()=>{clean();reject(Error('基金查询超时，未保存交易'));},12000);document.head.append(script);
  });
 }
 window.FundLookup={lookup,parse,refresh:code=>lookup(code,{},true)};
})();
